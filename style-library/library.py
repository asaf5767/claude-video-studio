"""Read-only registry helpers shared by the gallery server and future editing agents."""
from pathlib import Path
import json, sys, re, hashlib, threading
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
from security import registered_file, MEDIA, NOTES
from atomic import atomic_write

BASE = Path(__file__).resolve().parent
STUDIO = BASE.parent
LANGUAGES = ('he', 'en')
MOTIONS = ('auto', 'always', 'off')  # auto follows prefers-reduced-motion; always/off override it
# Guards every read-modify-write of settings.json -- not just language/motion (hence the
# generic name): addons.py (Task 21, fix round 1) reuses this same lock for its own
# settings.json updates so /ui-language, /ui-motion and /addons can never interleave and
# lose each other's write.
_SETTINGS_LOCK = threading.Lock()

def site_settings():
    """Expose only public branding fields, never arbitrary local configuration.

    `library_label` defaults to a translation of "Reference Library" that follows the
    active UI language (see `ui_language()`) rather than a fixed English string -- the
    nav link that shows this label (`#library-nav-label` in index.html) is intentionally
    *not* driven by `data-i18n` (giving it one would make every `I18N.render()` call
    stomp a user's custom branding), so without this the label stayed in English even in
    Hebrew mode until a creator typed their own label into settings.json. A real custom
    `library_label` in settings.json still overrides this, in either language.
    """
    # An empty studio_name/monogram/credit means "use the built-in brand": the UI shows the translated
    # brand.name and the ember-dot logo, and the footer keeps only the upstream (MIT) credit line.
    defaults = {'studio_name': '', 'library_label': 'השראה' if ui_language() == 'he' else 'Reference Library',
                'monogram': '', 'credit': {'name': '', 'url': ''}}
    try:
        settings = json.loads((BASE / 'settings.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return defaults
    if not isinstance(settings, dict):
        return defaults
    for key, limit in [('studio_name', 64), ('library_label', 64), ('monogram', 5)]:
        value = settings.get(key)
        if isinstance(value, str) and value.strip() and len(value) <= limit:
            defaults[key] = value.strip()
    credit = settings.get('credit')
    if isinstance(credit, dict):
        name, url = credit.get('name'), credit.get('url')
        if name == '':
            defaults['credit'] = {'name': '', 'url': ''}
        elif isinstance(name, str) and 0 < len(name) <= 80 and isinstance(url, str):
            try:
                parsed = urlparse(url)
            except ValueError:
                return defaults
            if parsed.scheme in ('https', 'http') and parsed.hostname and not parsed.username and not parsed.password:
                defaults['credit'] = {'name': name, 'url': url}
    return defaults

def ui_language():
    """Persisted UI language; Hebrew first, falling back to Hebrew for anything unrecognized."""
    try:
        settings = json.loads((BASE / 'settings.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return 'he'
    if isinstance(settings, dict) and settings.get('language') in LANGUAGES:
        return settings['language']
    return 'he'

def _save_setting(key, value):
    """Atomically persist one UI setting in settings.json, preserving everything else on disk."""
    path = BASE / 'settings.json'
    with _SETTINGS_LOCK:
        try:
            settings = json.loads(path.read_text(encoding='utf-8'))
            if not isinstance(settings, dict):
                settings = {}
        except (OSError, ValueError):
            settings = {}
        settings[key] = value
        atomic_write(path, (json.dumps(settings, indent=2) + '\n').encode())
    return {key: value}

def set_ui_language(language):
    """Persist the UI language, preserving any other settings already on disk."""
    if language not in LANGUAGES:
        raise ValueError('Choose he or en.')
    return _save_setting('language', language)

def ui_motion():
    """Persisted headline-motion preference; anything unknown means auto (follow the system setting)."""
    try:
        settings = json.loads((BASE / 'settings.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return 'auto'
    if isinstance(settings, dict) and settings.get('motion') in MOTIONS:
        return settings['motion']
    return 'auto'

def set_ui_motion(motion):
    """Persist the headline-motion preference (auto/always/off), preserving other settings."""
    if motion not in MOTIONS:
        raise ValueError('Choose auto, always or off.')
    return _save_setting('motion', motion)

def welcome_seen():
    """Whether the first-run welcome card was dismissed; only an explicit true counts as seen."""
    try:
        settings = json.loads((BASE / 'settings.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return False
    return isinstance(settings, dict) and settings.get('welcome_seen') is True

def set_welcome_seen(value):
    """Persist the welcome card's dismissal. Only true is accepted: the card is shown once, never re-armed here."""
    if value is not True:
        raise ValueError('Only true dismisses the welcome.')
    return _save_setting('welcome_seen', True)

def catalog():
    path = BASE / 'catalog.json'
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'schema_version': 4, 'entries': [], 'techniques': []}

def project_reference_candidates(project, data):
    """Exact active video sources only; titles and coincidentally matching IDs are not evidence."""
    artifact = next((a for a in project.get('artifacts', []) if a.get('id') == project.get('primary_artifact')), None)
    if not artifact or artifact.get('type') != 'video' or not artifact.get('version') or not artifact.get('path'):
        return []
    media = (Path('projects') / project['id'] / artifact['path']).as_posix()
    removed = data.get('removed_references', {})
    return [entry for entry in data.get('entries', []) if
            isinstance(entry.get('id'), str) and re.fullmatch(r'[a-z0-9][a-z0-9-]*', entry['id']) and
            entry.get('collection') == 'mine' and entry.get('asset_type', 'video') == 'video' and
            entry.get('project_id') == project['id'] and
            entry.get('version') == artifact['version'] and entry.get('media_path') == media and
            not entry.get('archived_from') and entry['id'] not in removed]

def entry_map():
    return {e['id']: e for e in catalog()['entries']}

def technique_map():
    return {t['id']: t for t in catalog().get('techniques', [])}

def source_key(url):
    """Deduplicate the actual post, ignoring Instagram URL variants/tracking."""
    p=urlparse(url);host=(p.hostname or '').lower().removeprefix('www.')
    if host=='instagram.com':
        match=re.match(r'^/(?:reel|reels|p)/([^/]+)',p.path)
        if match:return 'instagram:'+match[1]
    if host in ['youtube.com','m.youtube.com']:
        video=parse_qs(p.query).get('v')
        if video:return 'youtube:'+video[0]
    if host=='youtu.be':return 'youtube:'+p.path.strip('/')
    query={k:v for k,v in parse_qs(p.query).items()if not k.startswith('utm_')}
    return urlunparse((p.scheme,host,p.path.rstrip('/'),'',urlencode(query,doseq=True),''))

def reference_brief(ids):
    entries = entry_map()
    techniques = technique_map()
    selected = list(dict.fromkeys(ids))
    if not selected:
        raise ValueError('Choose at least one asset or technique.')
    out = ['CREATIVE STYLE REFERENCE',
           'Use these as creative references. Follow the new brief and my instructions first.',
           'Registry: style-library/catalog.json', '']
    for token in selected:
        id, _, example_id = token.partition('@')
        if id in techniques:
            t = techniques[id]
            example_id = example_id or t['default_example']
            examples = {x['id']: x for x in t['examples']}
            x = examples[example_id]
            e = entries[x['style_id']]
            if x['source_version']!=e['version'] or x['source_path']!=e['media_path']:
                raise ValueError('Recheck technique timestamps against the changed source version.')
            ours = list(dict.fromkeys(entries[v['style_id']]['title'] for v in t['examples'] if entries[v['style_id']]['collection']=='mine'))
            out += [f"EDITING TECHNIQUE: {t['title']} [{t['id']}]",
                    f"Use for: {t['summary']}", f"Direction: {t['direction']}",
                    f"Chosen example: {x['label']} [{x['id']}]",
                    f"Source video: {e['title']} [{e['id']}] · {e['creator']} · {e['version']}",
                    f"Exact source window: {timestamp(x['start'])}–{timestamp(x['end'])} ({x['end']-x['start']:.3f}s; approximate viewing excerpt)",
                    f"Exact example: {e['media_path']}",
                    'Used in our videos: '+(', '.join(ours) if ours else 'Reference only; not yet linked to one of our edits.'),
                    'This is creative direction, not an installed preset or permission to reuse the source media.']
            if e.get('source_url'): out += [f"Original: {e['source_url']}"]
            if e.get('composition'): out += [f"Editable source project: {e['composition']}"]
            out += ['Keep: '+' '.join(t['keep']), 'Avoid: '+' '.join(t['avoid']),
                    'Other examples in this family: '+'; '.join(v['label'] for v in t['examples'] if v['id']!=x['id']),
                    'Read before editing: '+', '.join(e['notes']),
                    'Technique evidence: '+t['evidence'], 'Source evidence: '+e['evidence'], '']
            continue
        if example_id:
            raise ValueError('Only techniques have selectable examples.')
        e = entries[id]
        out += [f"{e['title']} [{e['id']}] · {e['version']}",
                f"Source: {'Our edit' if e['collection']=='mine' else 'Other creator — reference only'} · {e['creator']}",
                f"Use for: {e['summary']}"]
        if e.get('review_status')=='review_pending':out += ['Review state: full review example; not yet the preferred baseline.']
        if e.get('delivery_status')=='final':out += ['Review state: final approved '+('carousel' if e.get('asset_type')=='carousel' else 'video')+'; preferred style example.']
        if e.get('media_path'): out += [f"Exact example: {e['media_path']}"]
        if e.get('asset_type')=='carousel':
            out += ['Format: carousel · '+str(len(e['slides']))+' slides · '+e['aspect_ratio'],
                    'Exact approved slide order:']
            out += [f"{i+1}. {s['title']} — {s['media_type']} — {s['path']}" for i,s in enumerate(e['slides'])]
            if e.get('archive_path'):out += ['Complete final package: '+e['archive_path']]
            if e.get('related_style_id'):out += ['Companion video style ID: '+e['related_style_id']]
            if e.get('article_url'):out += ['Companion article: '+e['article_url']]
        if e.get('source_url'): out += [f"Original: {e['source_url']}"]
        out += [f"{k}: {v}" for k, v in e['traits'].items()]
        out += ['Keep: ' + ' '.join(e['keep']), 'Avoid: ' + ' '.join(e['avoid'])]
        if e['moments']:
            out += ['Useful moments: ' + '; '.join(f"{timestamp(m['time'])} {m['label']}" for m in e['moments'])]
        if e.get('composition'): out += [f"Editable project: {e['composition']}"]
        out += ['Read before editing: ' + ', '.join(e['notes']),
                'Evidence: ' + e['evidence'], '']
    out += ['Preserve the new brief, script and source material. Adapt the treatment to the deliverable.',
            'External examples are inspiration; their footage, soundtrack and distinctive artwork are not reusable production assets.',
            'Check current project status and asset rights before reusing brand-specific or licensed material.']
    return '\n'.join(out)

def timestamp(seconds):
    value=f'{seconds%60:06.3f}'.rstrip('0').rstrip('.')
    return f'{int(seconds)//60}:{value}'

def context_handoff(ids, notes=None, mode='short', base_url=''):
    """Stateless text generation; compact links by default, detailed source analysis on request."""
    if not isinstance(ids, list) or not 1 <= len(ids) <= 60 or not all(isinstance(i, str) and 0 < len(i) <= 200 for i in ids):
        raise ValueError('Choose between 1 and 60 valid references.')
    if mode not in ('short', 'detailed'):
        raise ValueError('Choose short or detailed context.')
    entries, techniques = entry_map(), technique_map()
    resolved = []
    for token in dict.fromkeys(ids):
        id, sep, example_id = token.partition('@')
        t, x = techniques.get(id), None
        if t:
            x = next((v for v in t['examples'] if v['id'] == (example_id or t['default_example'])), None)
            if not x:
                raise ValueError('Unknown technique example.')
            e = entries[x['style_id']]
            if x['source_version'] != e['version'] or x['source_path'] != e['media_path']:
                raise ValueError('Recheck technique timestamps against the changed source version.')
            token = id + '@' + x['id']
        else:
            if sep or id not in entries:
                raise ValueError('Unknown reference.')
            e = entries[id]
        resolved.append((token, e, t, x))
    notes = {} if notes is None else notes
    tokens = {r[0] for r in resolved}
    if not isinstance(notes, dict) or any(k not in tokens for k in notes):
        raise ValueError('Notes must belong to the selected exact references.')
    for note in notes.values():
        if not isinstance(note, dict) or set(note) - {'focus', 'borrow'}:
            raise ValueError('Notes accept a moment and what to borrow.')
        if any(not isinstance(v, str) or len(v) > 1000 or any(ord(c) < 32 and c not in '\n\t' for c in v) for v in note.values()):
            raise ValueError('Each note must be text of at most 1000 characters.')
    if mode == 'detailed':
        out = [reference_brief([r[0] for r in resolved]), '', 'MY REFERENCE NOTES']
        for token, e, t, x in resolved:
            note = notes.get(token, {})
            out += [f"{t['title'] if t else e['title']} [{token}]"]
            out += [f"Moment or slide: {note['focus'].strip()}" ] if note.get('focus', '').strip() else []
            out += [f"What to borrow: {note['borrow'].strip()}" ] if note.get('borrow', '').strip() else []
        out += ['', 'Inspect the selected sources before proposing the edit. If a source is unavailable, tell me and ask for a usable link or upload.']
        return '\n'.join(out)
    if base_url:
        parsed = urlparse(base_url)
        if parsed.scheme not in ('http', 'https') or not parsed.netloc or parsed.query or parsed.fragment or parsed.username or parsed.password:
            raise ValueError('Use a valid library address.')
    out = ['References:', '']
    for n, (token, e, t, x) in enumerate(resolved, 1):
        params = {'technique' if t else 'style': t['id'] if t else e['id']}
        if x:
            params['example'] = x['id']
            title = f"{t['title']} — {x['label']} ({timestamp(x['start'])}–{timestamp(x['end'])})"
        else:
            title = f"{e['title']} — {e['creator']}"
        out += [f'{n}. {title}', base_url.rstrip('/') + '/#' + urlencode(params)]
        note = notes.get(token, {})
        if note.get('focus', '').strip(): out += [f"Moment: {note['focus'].strip()}"]
        if note.get('borrow', '').strip(): out += [f"What to borrow: {note['borrow'].strip()}"]
        out += ['']
    return '\n'.join(out).rstrip()

def served_files(e):
    """Every registered library file the local server will be asked to serve."""
    files = [(e.get('media_path'), MEDIA), (e.get('archive_path'), {'.zip'})]
    files += [(name, NOTES) for name in e.get('notes', [])] + [(s['path'], MEDIA) for s in e.get('slides', [])]
    return [(name, kinds) for name, kinds in files if name]

def check_served(e):
    # Existing files can still be refused by the server's confinement rules; fail
    # here, before an update restarts the studio, rather than leave an item that won't play.
    for name, kinds in served_files(e):
        try: registered_file(STUDIO, name, kinds)
        except ValueError: raise AssertionError('Registered library file would not be served: ' + name) from None

def validate():
    entries = catalog()['entries']; ids = [e['id'] for e in entries]
    assert len(ids)==len(set(ids)), 'Duplicate style id'
    removed=catalog().get('removed_references',{})
    assert isinstance(removed,dict), 'Invalid removed references'
    assert all(isinstance(id,str) and re.fullmatch(r'[a-z0-9][a-z0-9-]*',id) and isinstance(value,dict) and set(value)=={'removed_at'} and isinstance(value['removed_at'],str) and value['removed_at'] for id,value in removed.items()), 'Invalid removed reference marker'
    sources=[source_key(e['source_url'])for e in entries if e.get('source_url')]
    assert len(sources)==len(set(sources)), 'Duplicate source post; update its existing entry.'
    creators={}
    media = 0
    for e in entries:
        assert e['collection'] in ['mine','reference']
        assert e.get('creator_id')and e.get('creator'), 'Creator identity required'
        assert creators.setdefault(e['creator_id'],e['creator'])==e['creator'], 'Creator display names must be consistent'
        for name in [e.get('media_path'), e.get('composition'), *e['notes']]:
            if not name: continue
            f = (STUDIO/name).resolve()
            assert f.is_relative_to(STUDIO) and f.is_file(), name
        assert (BASE/'dist'/e['poster']).is_file(), e['poster']
        if e.get('asset_type')=='carousel':
            assert e.get('slides') and e.get('aspect_ratio')=='3:4'
            for s in e['slides']:
                assert s['media_type'] in ['video','image']
                f=(STUDIO/s['path']).resolve()
                assert f.is_relative_to(STUDIO) and f.is_file(),s['path']
                assert (BASE/'dist'/s['poster']).is_file(),s['poster']
            if e.get('archive_path'):
                f=(STUDIO/e['archive_path']).resolve()
                assert f.is_relative_to(STUDIO) and f.is_file(),e['archive_path']
        assert all(0<=m['time']<e['duration'] for m in e['moments']) if e.get('duration') else not e['moments']
        check_served(e)
        media += bool(e.get('media_path'))
        assert e['id'] in reference_brief([e['id']])
    techniques = list(technique_map().values())
    assert len(techniques)==len(catalog().get('techniques', [])), 'Duplicate technique id'
    assert not set(ids).intersection(t['id'] for t in techniques), 'Video/technique id collision'
    by_id = {e['id']:e for e in entries}
    evidence_path = BASE/'runtime/source-evidence.json'
    source_evidence = {e['id']:e for e in json.loads(evidence_path.read_text(encoding='utf-8'))} if evidence_path.exists() else {}
    technique_examples=0
    used=0
    for t in techniques:
        assert t['id'].startswith('tech-') and t['summary'] and t['direction'] and t['evidence']
        examples = {x['id']:x for x in t['examples']}
        assert examples and len(examples)==len(t['examples']), 'Empty/duplicate examples'
        assert t['default_example'] in examples, 'Invalid default example'
        for x in examples.values():
            e=by_id[x['style_id']]
            assert x['source_version']==e['version'] and x['source_path']==e['media_path'], 'Recheck technique after source-version change'
            actual = hashlib.sha256((STUDIO/e['media_path']).read_bytes()).hexdigest() if e.get('archived_from') else source_evidence[e['id']]['source_sha256']
            assert x['source_sha256']==actual, 'Recheck technique after source-media change'
            assert e.get('media_path'), 'Technique example needs local media'
            assert 0<=x['start']<=x['poster_at']<x['end']<=e['duration'], (t['id'],x['id'])
            assert (BASE/'dist'/x['poster']).is_file(), x['poster']
            brief=reference_brief([t['id']+'@'+x['id']])
            assert e['media_path'] in brief and timestamp(x['start']) in brief and x['id'] in brief
        used += any(by_id[x['style_id']]['collection']=='mine' for x in t['examples'])
        technique_examples += len(examples)
    return {'entries':len(entries),'my_videos':sum(e['collection']=='mine' and e.get('asset_type')!='carousel' for e in entries),'carousels':sum(e.get('asset_type')=='carousel' for e in entries),'other_creators':sum(e['collection']=='reference'for e in entries),'playable_local_examples':media,'distinct_creators':len(creators),'unique_sources':len(sources),'techniques':len(techniques),'technique_examples':technique_examples,'techniques_used_in_our_videos':used}

if __name__=='__main__':
    if len(sys.argv)>1 and sys.argv[1]=='brief':print(reference_brief(sys.argv[2:]))
    elif len(sys.argv)>1 and sys.argv[1]=='validate':print(json.dumps(validate(),indent=2))
    else:
        for e in catalog()['entries']:print(f"{e['id']:24} {e['title']} · {e['version']}")
