"""Start the next edit round of a project in its own folder: versions/v01, v02, ...

    python scripts/new_version.py projects/<id> [--from vNN] [--copy <project file> ...]

Never reuses a folder, so a version the creator approved (whose exact files the studio froze
in approval-state.json) is never overwritten. The new folder is a self-contained HyperFrames
project home: fonts/ holds the studio's bundled OFL fonts (Secular One, Heebo, Suez One,
Karantina, Bellefair; Hebrew + Latin files with their licenses) and fonts/fonts.css declares
them -- link it from index.html; gsap.min.js is copied from node_modules when installed;
empty renders/, storyboard/ and sfx/ folders are ready for ffmpeg. --copy puts project files (e.g. work/media/<file>) into
media/. --from vNN copies ONLY that version's composition sources -- index.html, scenes.json
and media/ -- to refine; never its derived outputs (cut.mp4, cut.words.json, cut.map.json,
captions.json, mix.wav, matte/, base.mp4, renders/, storyboard/, ...). Those steps are run again
in the new version (docs/skills/review-loop.md), so a new round never silently reuses a stale
cut, caption file or mix. Prints {"version", "folder", "fonts", "media", "gsap"} as JSON.

A project the creator marked final in the studio gets no new version (register.final, the
same refusal as register.py --append-version) until they press "פתיחה מחדש" / "Reopen" there,
so a round is never built that could not be registered.

registered(<version folder>) tells cut.py and captions.py whether the studio already points at
a file of that version (then it is frozen: make a new version instead of redoing a step there).
"""
import argparse
import json
from pathlib import Path
import re
import shutil
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
import jobscope  # noqa: E402  (RULING R51: every path stays inside the job folder)

ROOT = Path(__file__).resolve().parents[1]
FONTS = ROOT / 'style-library' / 'dist' / 'assets' / 'fonts'
HEBREW_RANGE = 'U+0590-05FF, U+200C-2010, U+20AA, U+25CC, U+FB1D-FB4F'
LATIN_RANGE = 'U+0000-00FF, U+0131, U+0152-0153, U+02BB-02BC, U+02C6, U+02DA, U+02DC, U+2000-206F, U+20AC, U+2122'
# family -> (css weight, font file stem, license file stem)
FAMILIES = {'Secular One': ('400', 'secular-one-400', 'secular-one'), 'Heebo': ('100 900', 'heebo-100-900', 'heebo'),
            'Suez One': ('400', 'suez-one-400', 'suez-one'), 'Karantina': ('700', 'karantina-700', 'karantina'),
            'Bellefair': ('400', 'bellefair-400', 'bellefair')}
SOURCES = ('index.html', 'scenes.json', 'media')  # all --from copies; everything else is re-made
REGISTRY = ROOT / 'style-library' / 'projects.json'
EMPTY = ('renders', 'storyboard', 'sfx')  # ffmpeg cannot create folders, so every version starts with these
GSAP = ROOT / 'node_modules' / 'gsap' / 'dist' / 'gsap.min.js'
VERSION = re.compile(r'^v(\d{2,})$')


FINAL_MESSAGE = ('register.final: הפרויקט סומן כסופי בסטודיו. כדי להוסיף גרסה חדשה, לחצו קודם "פתיחה מחדש" בסטודיו. '
                 '/ This project is marked final in the studio. Press "Reopen" in the studio first, '
                 'then a new version can be added.')


class VersionError(Exception):
    def __init__(self, message, code='new_version.failed'):
        super().__init__(message)
        self.code = code


def is_final(record):
    """A record the creator approved as final and has not reopened (register.final applies)."""
    return (isinstance(record, dict) and record.get('state') == 'final' and
            (record.get('review_decision') or {}).get('action') != 'reopen')


def _record(project_name, registry=None):
    try:
        projects = json.loads(Path(registry or REGISTRY).read_text(encoding='utf-8')).get('projects', [])
    except (OSError, ValueError, AttributeError):
        return None
    return next((p for p in projects if isinstance(p, dict) and p.get('id') == project_name), None)


def _font_file(stem, script):
    for ext in ('.woff2', '.woff'):
        if (FONTS / f'{stem}-{script}{ext}').is_file():
            return FONTS / f'{stem}-{script}{ext}'
    raise VersionError(f'bundled font missing: {stem}-{script}')


def _fonts(folder):
    target = folder / 'fonts'
    target.mkdir()
    css = ['/* The studio\'s bundled fonts (SIL OFL, licenses alongside). */']
    for family, (weight, stem, license_stem) in FAMILIES.items():
        for script, unicode_range in (('hebrew', HEBREW_RANGE), ('latin', LATIN_RANGE)):
            source = _font_file(stem, script)
            shutil.copy2(source, target / source.name)
            kind = 'woff2' if source.suffix == '.woff2' else 'woff'
            css.append(f"@font-face {{ font-family: '{family}'; font-style: normal; font-weight: {weight}; "
                       f"font-display: block; src: url('{source.name}') format('{kind}'); "
                       f"unicode-range: {unicode_range}; }}")
        license_file = FONTS / f'{license_stem}-LICENSE.txt'
        if license_file.is_file():
            shutil.copy2(license_file, target / license_file.name)
    (target / 'fonts.css').write_text('\n'.join(css) + '\n', encoding='utf-8')
    return list(FAMILIES)


def _inside(project, relative):
    path = (project / relative).resolve()
    if not path.is_relative_to(project.resolve()) or not path.is_file():
        raise VersionError(f'{relative} is not a file inside this project')
    return path


def create(project, source=None, copy=()):
    project = Path(project)
    if not project.is_dir():
        raise VersionError(f'no project folder at {project}')
    if is_final(_record(project.resolve().name)):
        raise VersionError(FINAL_MESSAGE, 'register.final')
    files = [_inside(project, relative) for relative in copy]
    versions = project / 'versions'
    taken = [int(m.group(1)) for p in versions.glob('v*') if (m := VERSION.match(p.name))] if versions.is_dir() else []
    previous = None
    if source is not None:
        previous = versions / source
        if not VERSION.match(source) or not previous.is_dir():
            raise VersionError(f'no earlier version {source}')
    number = max(taken, default=0) + 1
    folder = versions / f'v{number:02}'
    folder.mkdir(parents=True)  # raises if it somehow exists: never write into an old version
    if previous is not None:
        for name in SOURCES:
            item = previous / name
            if item.is_dir():
                shutil.copytree(item, folder / name)
            elif item.is_file():
                shutil.copy2(item, folder / name)
    fonts = _fonts(folder)
    for name in EMPTY:
        (folder / name).mkdir(exist_ok=True)
    if GSAP.is_file():
        shutil.copy2(GSAP, folder / 'gsap.min.js')
    media = []
    if files:
        (folder / 'media').mkdir(exist_ok=True)
        for path in files:
            shutil.copy2(path, folder / 'media' / path.name)
            media.append(f'media/{path.name}')
    return {'version': f'V{number:02}', 'folder': folder.as_posix(), 'fonts': fonts, 'media': media,
            'gsap': (folder / 'gsap.min.js').is_file()}


def registered(folder, registry=None):
    """True when the studio's record of this project points at a file inside versions/vNN."""
    folder = Path(folder).resolve()
    if not VERSION.match(folder.name) or folder.parent.name != 'versions':
        return False
    record = _record(folder.parent.parent.name, registry)
    prefix = f'versions/{folder.name}/'
    for artifact in (record or {}).get('artifacts') or []:
        paths = [artifact.get('path'), artifact.get('poster_path')] + [f.get('path') for f in artifact.get('frames') or []]
        if any(isinstance(p, str) and p.replace('\\', '/').lstrip('./').startswith(prefix) for p in paths):
            return True
    return False


def main(argv=None):
    if hasattr(sys.stdout, 'reconfigure'):  # Hebrew JSON on a Windows pipe/console (final review M5)
        sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('project', type=Path)
    parser.add_argument('--from', dest='source', metavar='vNN')
    parser.add_argument('--copy', nargs='+', default=[], metavar='FILE')
    args = parser.parse_args(argv)
    if (code := jobscope.refuse(args.project, *(args.project / name for name in args.copy))) is not None:
        return code
    try:
        result = create(args.project, args.source, args.copy)
    except VersionError as error:
        print(str(error) if error.code == 'register.final' else f'new_version: {error}', file=sys.stderr)
        return 2
    except OSError as error:
        print(f'new_version: {error}', file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
