"""Task 10: tap-to-choose project choices -- the project brief Claude reads is written by
the studio UI's four steps (cut / look / sound / finish) instead of by a typed prompt.

Design decision (documented here since the brief leaves it open): the TEXT of every label
lives in dist/i18n/<lang>.json -- the same single source of truth every other UI string
in this app already uses. `choices.config.json` next to this module never repeats that
text; it only records step/option *ids* plus the i18n key name that carries each one's
label, mirroring materials.py's TAGS / materials-ui.js's TAG_LABEL_KEY duplication (a
small, reviewable ids-only table kept in sync by hand, not a generated artifact). The
studio UI never needs a dedicated "fetch the config" route: GET /choices already returns
both this project's saved choices and the full config object in one response, and
choices-ui.js calls I18N.t(option.label_key) to render each tap card in the active
language -- so the *shape* (which options exist, their ids) is still a single JSON
document shared by Python and JS, just not the rendered strings.

Saving is a server-side merge, not a client-side read-modify-write: `save()` reads the
project's current choices.json under CHOICES_LOCK, merges the caller's patch over it
(`{**current, **patch}`), validates the *merged* result, and writes both choices.json and
the rewritten <!-- choices --> ... <!-- /choices --> block in brief.md from that merged
object. A tap that only sends e.g. {"cut": "tight"} therefore can never clobber an
unrelated field such as "effects" or "presenter" (Task 12's own save path) -- the field simply never
appears in that call's patch, so the merge leaves whatever was already on disk alone.

Task 12: "effects" items must name an effect id from effects/effects.json (each id at
most once) and "presenter" is one look id from looks/presenter.json or null. The brief
renders both as "<name in the video's language> [<id>]" -- the bracketed id is the key
Claude looks up in those catalogs for the build instructions.

Fix round 1, finding 2 (same-field rapid taps / out-of-order responses) tried a
server-side `seq` guard here. Fix round 2, controller ruling R33, removed it: `fieldSeq`
only ever lived in a browser tab's JS closure, so it reset on reload or didn't exist at
all in a second tab, while this module's old `_seq` bookkeeping lived in choices.json --
after a reload, a real, brand-new tap could come in with a seq the server had already
seen (or a lower one, since the counter restarted), get silently dropped as "stale", and
the UI would optimistically show the tap, get back a 200 with the *old* value, and revert
with no visible error. The race this was meant to guard against -- a rapid run of taps on
the same field racing each other's HTTP responses -- is instead prevented client-side
only, in choices-ui.js: per field, it never has more than one /choices request in flight;
a tap that arrives while one is already in flight replaces whatever was queued (only the
latest value survives) and is sent the moment the in-flight one settles, and that
in-flight request's own response (success or failure) is discarded unapplied the instant
something newer is queued. Out-of-order application is therefore impossible by
construction -- there is never more than one outstanding request per field to *be*
out of order with -- and this module stays a plain, stateless, last-request-wins merge:
whatever `patch` a save() call carries simply wins, with no seq, no per-field ordering
state, and nothing that can go stale across a reload or a second tab.

A choices.json written by the brief round 1 build may still carry a leftover `_seq` key
from that abandoned approach. `_read_choices()` strips it unconditionally on every read
(not just once) so those old files keep working forever: the key just quietly stops being
written back once this file reads and re-saves it, and nothing downstream (`_brief_lines`,
a GET /choices response, a save() result) ever has to know it used to exist.
"""
import json
import re
import threading
from pathlib import Path

import project_index as index
import looks
import effects as fx_catalog
from atomic import atomic_write

BASE = Path(__file__).resolve().parent
CONFIG_PATH = BASE / 'choices.config.json'
CATALOG = BASE / 'catalog.json'
I18N_DIR = BASE / 'dist' / 'i18n'

CHOICES_LOCK = threading.RLock()

FIELDS = {'cut', 'look', 'sound', 'sfx', 'captions', 'length', 'extra', 'effects', 'presenter'}
MAX_EXTRA = 1000
MAX_EFFECT_FIELD = 80
MAX_EFFECTS = 20

# Free text that lands inside the <!-- choices --> block of brief.md (the "when I say" word and
# the "anything else?" note) must stay on one line: real control characters are refused.
UNSAFE_TEXT = re.compile(r'[\x00-\x1f\x7f-\x9f\u2028\u2029]')


def _brief_safe(text):
    """Ruling R35: users may type any printable text, and choices.json keeps it exactly. Only
    the copy written into brief.md's <!-- choices --> block neutralizes comment markers, so a
    "-->" or "<!--" typed by the user can never end or fake the block (BLOCK_RE)."""
    return text.replace('<!--', '‹!--').replace('-->', '→')

BLOCK_RE = re.compile(r'<!-- choices -->\n.*?<!-- /choices -->\n?', re.DOTALL)


class ChoicesError(Exception):
    """status: HTTP status to answer with. message_key: an i18n key, not English prose --
    the studio UI calls I18N.t(message_key) to show it in the active language."""
    def __init__(self, status, message_key):
        super().__init__(message_key)
        self.status = status
        self.message_key = message_key


# --- config / i18n lookups -------------------------------------------------

def _config():
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        raise ChoicesError(503, 'choices.error.filesystem')
    if not isinstance(data, dict):
        raise ChoicesError(503, 'choices.error.filesystem')
    return data


def _i18n(lang):
    try:
        return json.loads((I18N_DIR / f'{lang}.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def _label(i18n_dict, key):
    return i18n_dict.get(key, key)


def _ids(options):
    return {o['id'] for o in options}


def _reference_exists(ref_id):
    try:
        data = json.loads(CATALOG.read_text(encoding='utf-8')) if CATALOG.exists() else {'entries': []}
    except (OSError, ValueError):
        return False
    if not isinstance(data, dict) or not isinstance(data.get('entries'), list):
        return False
    return any(isinstance(e, dict) and e.get('id') == ref_id for e in data['entries'])


# --- validation --------------------------------------------------------

def _validate_look(value):
    if not isinstance(value, str) or not value:
        raise ChoicesError(400, 'choices.error.unknownOption')
    if value.startswith('ref:'):
        ref_id = value[len('ref:'):]
        if not index.TOKEN.fullmatch(ref_id) or not _reference_exists(ref_id):
            raise ChoicesError(400, 'choices.error.unknownOption')
        return
    if value not in {item['id'] for item in looks.list()}:
        raise ChoicesError(400, 'choices.error.unknownOption')


def _fx_catalog():
    """Task 12's effects board catalogs (effects/effects.json + looks/presenter.json)."""
    try:
        return fx_catalog.list()
    except (OSError, ValueError):
        raise ChoicesError(503, 'choices.error.filesystem')


def _validate_effects(value):
    if not isinstance(value, list) or len(value) > MAX_EFFECTS:
        raise ChoicesError(400, 'choices.error.invalidRequest')
    for item in value:
        if (not isinstance(item, dict) or set(item) != {'effect', 'when'} or
                not isinstance(item['effect'], str) or not 1 <= len(item['effect']) <= MAX_EFFECT_FIELD or
                not isinstance(item['when'], str) or len(item['when']) > MAX_EFFECT_FIELD or
                UNSAFE_TEXT.search(item['when'])):
            raise ChoicesError(400, 'choices.error.invalidRequest')
    ids = [item['effect'] for item in value]
    if len(ids) != len(set(ids)):
        raise ChoicesError(400, 'choices.error.invalidRequest')
    known = {item['id'] for item in _fx_catalog()['effects']}
    if any(effect_id not in known for effect_id in ids):
        raise ChoicesError(400, 'choices.error.unknownOption')


def _validate_presenter(value):
    """A single presenter look id from looks/presenter.json, or None to clear it."""
    if value is None:
        return
    if not isinstance(value, str) or value not in {item['id'] for item in _fx_catalog()['looks']}:
        raise ChoicesError(400, 'choices.error.unknownOption')


def _validate(patch, config):
    if not isinstance(patch, dict) or not patch or set(patch) - FIELDS:
        raise ChoicesError(400, 'choices.error.invalidRequest')
    if 'cut' in patch and patch['cut'] not in _ids(config['cut']['options']):
        raise ChoicesError(400, 'choices.error.unknownOption')
    if 'sound' in patch and patch['sound'] not in _ids(config['sound']['options']):
        raise ChoicesError(400, 'choices.error.unknownOption')
    if 'length' in patch and patch['length'] not in _ids(config['finish']['length_options']):
        raise ChoicesError(400, 'choices.error.unknownOption')
    if 'sfx' in patch and not isinstance(patch['sfx'], bool):
        raise ChoicesError(400, 'choices.error.invalidRequest')
    if 'captions' in patch and not isinstance(patch['captions'], bool):
        raise ChoicesError(400, 'choices.error.invalidRequest')
    if 'extra' in patch:
        if not isinstance(patch['extra'], str):
            raise ChoicesError(400, 'choices.error.invalidRequest')
        if len(patch['extra']) > MAX_EXTRA:
            raise ChoicesError(400, 'choices.error.extraTooLong')
        if UNSAFE_TEXT.search(patch['extra']):
            raise ChoicesError(400, 'choices.error.invalidRequest')
    if 'look' in patch:
        _validate_look(patch['look'])
    if 'effects' in patch:
        _validate_effects(patch['effects'])
    if 'presenter' in patch:
        _validate_presenter(patch['presenter'])


# --- project / file access ----------------------------------------------

def _project_root(project_id):
    if not isinstance(project_id, str) or not index.TOKEN.fullmatch(project_id):
        raise ChoicesError(404, 'choices.error.unknownProject')
    try:
        registry = index.registry()
    except (OSError, ValueError):
        raise ChoicesError(503, 'choices.error.filesystem')
    project = next((p for p in registry['projects'] if p.get('id') == project_id), None)
    if project is None:
        raise ChoicesError(404, 'choices.error.unknownProject')
    projects_root = (index.STUDIO / 'projects').resolve()
    root = (index.STUDIO / 'projects' / project_id).resolve()
    if root.parent != projects_root or not root.is_dir() or not (root / 'choices.json').is_file():
        raise ChoicesError(404, 'choices.error.unknownProject')
    return root, project


def _read_choices(root):
    try:
        data = json.loads((root / 'choices.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        raise ChoicesError(503, 'choices.error.filesystem')
    if not isinstance(data, dict):
        raise ChoicesError(503, 'choices.error.filesystem')
    # Fix round 2 (controller ruling R33): drop a leftover `_seq` key from the abandoned
    # server-side race guard, unconditionally, on every read -- see module docstring. Never
    # one of FIELDS, so it would fail validation if it ever reached save() any other way.
    data.pop('_seq', None)
    return data


def _write_choices(root, data):
    try:
        atomic_write(root / 'choices.json', (json.dumps(data, indent=2, ensure_ascii=False) + '\n').encode())
    except OSError:
        raise ChoicesError(503, 'choices.error.filesystem')


def _read_brief(root):
    try:
        return (root / 'brief.md').read_text(encoding='utf-8')
    except OSError:
        raise ChoicesError(503, 'choices.error.filesystem')


def _write_brief(root, text):
    try:
        atomic_write(root / 'brief.md', text.encode('utf-8'))
    except OSError:
        raise ChoicesError(503, 'choices.error.filesystem')


# --- brief rendering -----------------------------------------------------

def _option_label(i18n_dict, options, value):
    for opt in options:
        if opt['id'] == value:
            return _label(i18n_dict, opt['label_key'])
    return value


def _look_label(lang, i18n_dict, config, value):
    if value.startswith('ref:'):
        return _label(i18n_dict, config['look']['ref_label_key'])
    for item in looks.list():
        if item['id'] == value:
            return item['name_he'] if lang == 'he' else item['name_en']
    return value


def _brief_lines(lang, choices, config):
    i18n = _i18n(lang)
    lines = []
    if 'cut' in choices:
        lines.append('- {}: {}'.format(_label(i18n, config['cut']['label_key']),
                                        _option_label(i18n, config['cut']['options'], choices['cut'])))
    if 'look' in choices:
        lines.append('- {}: {}'.format(_label(i18n, config['look']['label_key']),
                                        _look_label(lang, i18n, config, choices['look'])))
    sound_parts = []
    if 'sound' in choices:
        sound_parts.append(_option_label(i18n, config['sound']['options'], choices['sound']))
    if choices.get('sfx') is True:
        sound_parts.append(_label(i18n, config['sound']['with_sfx_brief_label_key']))
    if sound_parts:
        lines.append('- {}: {}'.format(_label(i18n, config['sound']['label_key']), ', '.join(sound_parts)))
    finish_parts = []
    if choices.get('captions') is True:
        finish_parts.append(_label(i18n, config['finish']['captions_label_key']))
    if 'length' in choices:
        finish_parts.append(_option_label(i18n, config['finish']['length_options'], choices['length']))
    if finish_parts:
        lines.append('- {}: {}'.format(_label(i18n, config['finish']['label_key']), ', '.join(finish_parts)))
    effects = choices.get('effects')
    presenter = choices.get('presenter')
    catalog = _fx_catalog() if effects or presenter else {'effects': [], 'looks': []}
    if effects:
        names = {item['id']: _label(i18n, item['name_key']) for item in catalog['effects']}
        when = _label(i18n, config['effects']['when_brief_label_key'])
        rendered = '; '.join(
            '{} [{}]'.format(names.get(e['effect'], e['effect']), e['effect']) +
            (' ({})'.format(when.replace('{when}', _brief_safe(e['when']))) if e.get('when') else '')
            for e in effects)
        lines.append('- {}: {}'.format(_label(i18n, config['effects']['brief_label_key']), rendered))
    if presenter:
        names = {item['id']: _label(i18n, item['name_key']) for item in catalog['looks']}
        lines.append('- {}: {} [{}]'.format(_label(i18n, config['presenter']['brief_label_key']),
                                           names.get(presenter, presenter), presenter))
    extra = choices.get('extra')
    if extra:
        lines.append('- {}: {}'.format(_label(i18n, config['extra']['brief_label_key']), _brief_safe(extra)))
    return lines


def _render_block(lines):
    body = ('\n'.join(lines) + '\n') if lines else ''
    return '<!-- choices -->\n{}<!-- /choices -->\n'.format(body)


def apply_block(text, block):
    if BLOCK_RE.search(text):
        return BLOCK_RE.sub(lambda _m: block, text, count=1)
    sep = '' if text.endswith('\n') or not text else '\n'
    return text + sep + block


def render_block(lang, choices_data):
    """The exact <!-- choices --> ... <!-- /choices --> block text for `choices_data` in
    `lang`. Public (no leading underscore) because new_project.py calls it too (Task 10
    fix round 1, finding 5): a project created from an inspiration reference writes
    choices.json as {"look": "ref:<id>"} up front, and without this call brief.md's block
    would stay empty until the user's first tap in the UI -- the two files would disagree
    about the project's look from the moment it's created. new_project.py never has a
    registered project yet at that point, so it calls this directly rather than save()."""
    config = _config()
    return _render_block(_brief_lines(lang, choices_data, config))


# --- public interface ------------------------------------------------------

def current(project_id):
    """GET /choices?project=<id>: this project's saved choices plus the shared config
    (step/option ids and their i18n label keys) the UI needs to render the tap cards."""
    root, _project = _project_root(project_id)
    with CHOICES_LOCK:
        saved = _read_choices(root)
    return {'choices': saved, 'config': _config()}


def save(project_id, patch):
    """choices.save(project_id, patch) -> dict: validates `patch` against
    choices.config.json, merges it over the project's current choices.json (never
    dropping a field the caller's patch doesn't mention -- see module docstring), writes
    the merged result, and rewrites the <!-- choices --> block in brief.md in the
    project's own video language. Raises ChoicesError(400) for any unknown option.

    Plain last-request-wins: whatever `patch` says, wins, unconditionally (fix round 2,
    controller ruling R33 -- see module docstring for why there is no seq/staleness
    bookkeeping here; choices-ui.js is responsible for never having two requests for the
    same field in flight at once)."""
    config = _config()
    _validate(patch, config)
    root, project = _project_root(project_id)
    with CHOICES_LOCK:
        merged = {**_read_choices(root), **patch}
        lang = project.get('video_language') if project.get('video_language') in ('he', 'en') else 'en'
        block = _render_block(_brief_lines(lang, merged, config))
        brief_text = apply_block(_read_brief(root), block)
        _write_choices(root, merged)
        _write_brief(root, brief_text)
    return merged
