"""Register a skill's new storyboard or video version in the studio (never approves anything).

    python scripts/register_version.py projects/<id> --version V01 --kind storyboard
        --frames versions/v01/storyboard/frames.json [--preview versions/v01/renders/draft.mp4]
        [--cut versions/v01/cut.mp4] --summary "..." --next-step "..." [--lang he|en]
    python scripts/register_version.py projects/<id> --version V02 --kind final
        --video versions/v02/renders/final.mp4 --poster versions/v02/storyboard/poster.jpg
        --summary "..." --next-step "..." [--lang he|en]

Writes projects/<id>/studio-entry.json with the round's new artifacts (storyboard board of
JPEG frames with titles/notes, its draft preview video, the spoken cut, or the edited video)
and hands it to `scripts/register.py project --append-version`, which keeps the project's
record as it is -- the fields the studio created (kind, video_language, created_at, ...),
every earlier version and every decision the creator saved in the studio, byte for byte --
and only adds the new versions and makes the first one current. It works for the first
storyboard of a draft and for a final video after the storyboard was approved alike.
frames.json is [{"path", "title", "note"}] with project-relative JPEG paths. A final video
also needs --poster (a JPEG frame of it): with it the descriptor carries the library entry
seed (reference_entry + reference_poster_source) the studio needs when the creator marks the
video final. Creates
review-notes.md if missing (the studio needs it to save a decision). Coded errors:
register.unknown-project, register.exists (that version is already registered: make a new
one), register.final (the creator marked the project final in the studio: nothing is written;
they must press "פתיחה מחדש" / "Reopen" in the studio first), register.failed. Never approves
anything.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
import jobscope  # noqa: E402  (RULING R51: every path stays inside the job folder)

_spec = importlib.util.spec_from_file_location('studio_register', Path(__file__).resolve().parent / 'register.py')
register = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(register)

LABELS = {
    'he': {'storyboard': 'סטוריבורד', 'preview': 'טיוטה מונפשת', 'cut': 'החיתוך', 'video': 'הסרטון',
           'status': 'מצב נוכחי', 'notes': 'הערות סקירה', 'brief': 'תקציר'},
    'en': {'storyboard': 'Storyboard', 'preview': 'Draft preview', 'cut': 'Spoken cut', 'video': 'Video',
           'status': 'Current status', 'notes': 'Review notes', 'brief': 'Brief'},
}


class RegisterError(Exception):
    def __init__(self, code, message):
        super().__init__(f'{code}: {message}')
        self.code, self.message = code, message


def _file(project, relative):
    """`relative` when it names a file inside `project` (G9: resolved, so `..` or a link cannot
    register a file from elsewhere)."""
    if not isinstance(relative, str):
        raise RegisterError('register.failed', f'{relative} is not a file in this project')
    target = (Path(project) / relative).resolve()
    if not target.is_relative_to(Path(project).resolve()) or not target.is_file():
        raise RegisterError('register.failed', f'{relative} is not a file in this project')
    return relative


def _library_seed(record, version, video, summary, lang):
    return {'id': f'{record["id"]}-video', 'title': record.get('title', record['id']), 'subtitle': '',
            'creator': 'אני' if lang == 'he' else 'Me', 'creator_id': 'owner', 'summary': summary,
            'tags': [], 'palette': [], 'traits': {}, 'keep': [], 'avoid': [], 'moments': [],
            'notes': [f'projects/{record["id"]}/STATUS.md'], 'version': version, 'collection': 'mine',
            'evidence': "Edited in this studio from the creator's own materials.",
            'media_path': f'projects/{record["id"]}/{video}'}


def register_version(project, version, kind, *, frames=None, preview=None, cut=None, video=None, poster=None,
                     summary, next_step, lang='he'):
    project = Path(project)
    words = LABELS.get(lang, LABELS['en'])
    record = next((p for p in register.index.registry()['projects'] if p.get('id') == project.name), None)
    if record is None:
        raise RegisterError('register.unknown-project', f'{project.name} is not in the studio')
    if register.new_version.is_final(record):
        raise RegisterError('register.final', register.FINAL_MESSAGE.split(': ', 1)[1])
    tag = version.lower()
    new = []
    if kind == 'storyboard':
        try:
            rows = json.loads((project / _file(project, frames)).read_text(encoding='utf-8'))
            board = [{'path': _file(project, r['path']), 'title': str(r.get('title', '')), 'note': str(r.get('note', ''))}
                     for r in rows]
        except (ValueError, KeyError, TypeError) as error:
            raise RegisterError('register.failed', f'{frames}: {error}') from None
        if not board:
            raise RegisterError('register.failed', 'a storyboard needs at least one frame')
        new.append({'id': f'storyboard-{tag}', 'label': f'{words["storyboard"]} {version}', 'type': 'board',
                    'stage': 'storyboard', 'version': version, 'role': 'storyboard', 'frames': board})
        if preview:
            new.append({'id': f'preview-{tag}', 'label': f'{words["preview"]} {version}', 'type': 'video',
                        'stage': 'storyboard', 'version': version, 'role': 'storyboard', 'path': _file(project, preview)})
        if cut:
            new.append({'id': f'cut-{tag}', 'label': f'{words["cut"]} {version}', 'type': 'video', 'stage': 'spoken',
                        'version': version, 'role': 'assembly', 'path': _file(project, cut)})
        stage = 'storyboard'
    elif kind == 'final':
        if not poster or not str(poster).lower().endswith(('.jpg', '.jpeg', '.png')):
            raise RegisterError('register.failed', 'a final video needs --poster, a JPEG frame of it')
        new.append({'id': f'video-{tag}', 'label': f'{words["video"]} {version}', 'type': 'video', 'stage': 'edit',
                    'version': version, 'role': 'current', 'approval_kind': 'final', 'path': _file(project, video),
                    'poster_path': _file(project, poster)})
        stage = 'edit'
    else:
        raise RegisterError('register.failed', 'kind must be storyboard or final')
    if {a['id'] for a in new} & {a.get('id') for a in record.get('artifacts') or []}:
        raise RegisterError('register.exists', f'{version} is already registered; make a new version')
    notes = project / 'review-notes.md'
    if not notes.exists():
        notes.write_text(f'# {words["notes"]}\n', encoding='utf-8')
    item = {'id': record['id'], 'title': record.get('title', record['id']), 'format': record.get('format', 'video'),
            'state': 'review', 'stage': stage, 'summary': summary, 'next_step': next_step,
            'primary_artifact': new[0]['id'], 'artifacts': new,
            'source_notes': [{'label': label, 'path': path} for path, label in
                             (('STATUS.md', words['status']), ('review-notes.md', words['notes']),
                              ('brief.md', words['brief'])) if (project / path).is_file()]}
    if kind == 'storyboard':
        item['cover_path'] = new[0]['frames'][0]['path']  # used only when the project has no cover yet
    else:
        item['cover_path'] = poster
        item['reference_entry'] = _library_seed(record, version, video, summary, lang)
        item['reference_poster_source'] = poster
    entry = project / 'studio-entry.json'
    entry.write_text(json.dumps(item, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    try:
        register.register('project', entry, append=True)
    except (ValueError, KeyError, OSError, register.storage.ReviewError) as error:
        raise RegisterError('register.failed', str(error)) from None
    return {'registered': project.name, 'primary': item['primary_artifact'], 'version': version}


def main(argv=None):
    if hasattr(sys.stdout, 'reconfigure'):  # Hebrew JSON on a Windows pipe/console (final review M5)
        sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('project', type=Path)
    parser.add_argument('--version', required=True)
    parser.add_argument('--kind', choices=['storyboard', 'final'], required=True)
    parser.add_argument('--frames')
    parser.add_argument('--preview')
    parser.add_argument('--cut')
    parser.add_argument('--video')
    parser.add_argument('--poster')
    parser.add_argument('--summary', required=True)
    parser.add_argument('--next-step', required=True)
    parser.add_argument('--lang', choices=['he', 'en'], default='he')
    args = parser.parse_args(argv)
    files = [args.project / name for name in (args.frames, args.preview, args.cut, args.video, args.poster) if name]
    if (code := jobscope.refuse(args.project, *files)) is not None:
        return code
    try:
        result = register_version(args.project, args.version, args.kind, frames=args.frames, preview=args.preview,
                                  cut=args.cut, video=args.video, poster=args.poster, summary=args.summary, next_step=args.next_step,
                                  lang=args.lang)
    except RegisterError as error:
        print(str(error), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
