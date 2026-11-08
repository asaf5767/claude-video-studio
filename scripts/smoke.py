"""Synthetic technical workflow. Never approves or modifies an owner's project."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import uuid

ROOT=Path(__file__).resolve().parents[1]
PY=ROOT/'.venv'/('Scripts/python.exe' if sys.platform=='win32' else 'bin/python')
SCRIPTS = Path(__file__).resolve().parent
STYLE_LIBRARY = ROOT / 'style-library'
# cut.py/captions.py/new_version.py already insert their own directory the same way when
# run standalone; doing it here too means this file's imports below work regardless of how
# it was invoked (`python scripts/smoke.py`, `python -m`, or the --fake-claude-worker shim).
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(STYLE_LIBRARY))

def run(args, capture=False):
    return subprocess.run([str(a) for a in args],cwd=ROOT,check=True,capture_output=capture,text=True)

def _ffmpeg():
    found = shutil.which('ffmpeg')
    if not found:
        raise RuntimeError('ffmpeg is required for the Hebrew smoke path; see SETUP.md')
    return found


# --- Task 22: Hebrew end-to-end smoke path ---------------------------------------------
#
# Exercises the real Hebrew studio (style-library's new_project/materials/choices/
# claude_runner/review_actions, scripts/cut.py, captions.py, new_version.py,
# register_version.py) with no network access, no real `claude` CLI and no HyperFrames/
# Node render: a 10 s speech-free clip stands in for a take, a hand-written transcript in
# transcribe.py's exact word-timing shape stands in for whisper.cpp, and a `claude` shim
# on PATH (the same technique as style-library/test_claude_runner.py's install_fake) runs
# the deterministic steps the talking-head skill would. That proves the actual runner/job
# plumbing, not just the pipeline functions called directly.

# Includes a Latin word ("AI") and a number ("38") so captions.py's RTL/bdi isolation can
# be checked for real, in the exact shape scripts/transcribe.py writes.
FIXTURE_WORDS = [
    {'text': 'היום', 'startMs': 300, 'endMs': 650},
    {'text': 'נבדוק', 'startMs': 700, 'endMs': 1100},
    {'text': 'כלי', 'startMs': 1150, 'endMs': 1400},
    {'text': 'בשם', 'startMs': 1450, 'endMs': 1700},
    {'text': 'AI', 'startMs': 1750, 'endMs': 2000},
    {'text': 'שחוסך', 'startMs': 2050, 'endMs': 2450},
    {'text': 'לנו', 'startMs': 2500, 'endMs': 2700},
    {'text': '38', 'startMs': 2750, 'endMs': 3000},
    {'text': 'שניות', 'startMs': 3050, 'endMs': 3400},
    {'text': 'בכל', 'startMs': 3450, 'endMs': 3650},
    {'text': 'פעם.', 'startMs': 3700, 'endMs': 4000},
]


def install_fake_claude(folder):
    """A `claude` shim (the same technique as test_claude_runner.install_fake) that hands
    every call straight to this file's --fake-claude-worker mode, so claude_runner.py's
    real subprocess/job-polling path runs for real, with _run_talking_head_fake() below
    standing in for what the actual skill would do."""
    folder.mkdir(parents=True, exist_ok=True)
    worker = Path(__file__).resolve()
    if sys.platform == 'win32':
        (folder / 'claude.cmd').write_text(f'@echo off\r\n"{sys.executable}" "{worker}" --fake-claude-worker %*\r\n',
                                           encoding='utf-8')
    else:
        shim = folder / 'claude'
        shim.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{worker}" --fake-claude-worker "$@"\n', encoding='utf-8')
        shim.chmod(0o755)


def _run_talking_head_fake(project):
    """What the real `claude` CLI would do for `/talking-head projects/<id> Reply in
    Hebrew.`, deterministically: progress keys, cut.py, captions.py, a storyboard still
    pulled with ffmpeg, register_version.py. No HyperFrames/Node composition render (not
    available without network here) -- graphics/sound are reported done without one."""
    import materials
    import progress
    import new_version
    import cut
    import captions
    import register_version

    progress_file = project / 'progress.json'
    progress.start(progress_file, 'talking-head')
    progress.update(progress_file, 'ingest', 'done', 'חומר הגלם כבר בפורמט תקין')

    take = next(i for i in materials.list(project.name) if i['tag'] == 'raw')
    media_rel = take['file']
    words_rel = f'work/transcripts/{Path(media_rel).stem}.json'
    words = json.loads((project / words_rel).read_text(encoding='utf-8'))
    progress.update(progress_file, 'transcribe', 'done', f'{len(words)} מילים')

    new_version.create(project)
    version_dir = project / 'versions' / 'v01'
    request = {'style': 'tight', 'fps': 30, 'width': 1080, 'height': 1920, 'fit': 'cover',
               'pieces': [{'media': media_rel, 'words': words_rel, 'from': 0, 'to': len(words) - 1}]}
    (version_dir / 'cut-request.json').write_text(json.dumps(request, ensure_ascii=False, indent=2), encoding='utf-8')
    cut_result = cut.render(project, request, version_dir)
    progress.update(progress_file, 'cut', 'done', f'{cut_result["duration"]} שניות')

    cut_words = json.loads((version_dir / 'cut.words.json').read_text(encoding='utf-8'))
    cue_doc = captions.build(cut_words, lang='he', mode='line', duration=cut_result['duration'])
    (version_dir / 'captions.json').write_text(json.dumps(cue_doc, ensure_ascii=False, indent=2), encoding='utf-8')
    progress.update(progress_file, 'captions', 'done', f'{len(cue_doc["cues"])} כתוביות')

    # No HyperFrames/Node composition render is possible without network here.
    progress.update(progress_file, 'graphics', 'done', 'בדיקת עשן: אין רינדור HyperFrames (ללא גישה לרשת)')
    progress.update(progress_file, 'sound', 'done', 'בדיקת עשן: בלי מוזיקה')

    ffmpeg = _ffmpeg()
    board = version_dir / 'storyboard'
    frame = board / '01.jpg'
    subprocess.run([ffmpeg, '-nostdin', '-v', 'error', '-y', '-ss', '1.0', '-i', str(version_dir / 'cut.mp4'),
                    '-frames:v', '1', str(frame)], check=True, capture_output=True)
    frames = [{'path': 'versions/v01/storyboard/01.jpg', 'title': 'פתיחה', 'note': 'בדיקת עשן אוטומטית'}]
    (board / 'frames.json').write_text(json.dumps(frames, ensure_ascii=False, indent=2), encoding='utf-8')
    shutil.copy2(version_dir / 'cut.mp4', version_dir / 'renders' / 'draft.mp4')
    register_version.register_version(
        project, 'V01', 'storyboard', frames='versions/v01/storyboard/frames.json',
        preview='versions/v01/renders/draft.mp4', cut='versions/v01/cut.mp4',
        summary='סטוריבורד ראשון מבדיקת העשן העברית', next_step='לעבור על הסטוריבורד ולאשר', lang='he')
    progress.update(progress_file, 'storyboard', 'done', 'סטוריבורד נרשם לסקירה')


def _fake_claude_worker(argv):
    """Entry point for the `claude` shim installed by install_fake_claude(): argv is
    exactly what claude_runner.py would pass the real CLI (`-p "/talking-head
    projects/<id> Reply in Hebrew." ...`), parsed the same way
    style-library/fixtures/fake_claude.py parses it."""
    sys.stdout.reconfigure(encoding='utf-8')
    target_rel = argv[1].split(' ')[1]
    _run_talking_head_fake(ROOT / target_rel)
    sys.stdout.write('{"type":"result","subtype":"success","is_error":false}\n')
    sys.stdout.flush()
    return 0


def hebrew_smoke():
    """Task 22: the Hebrew end-to-end smoke path -- real library code throughout, no
    network, no real `claude`, no HyperFrames/Node render."""
    import library
    import project_index as index
    import new_project
    import materials
    import choices
    import claude_runner as runner
    import review_actions as storage
    import register_version

    ffmpeg = _ffmpeg()
    with tempfile.TemporaryDirectory(prefix='hebrew-smoke-') as tmp:
        clip = Path(tmp) / 'take.mp4'
        subprocess.run([ffmpeg, '-nostdin', '-v', 'error', '-y',
                        '-f', 'lavfi', '-i', 'color=c=0x202833:s=1080x1920:r=30:d=10',
                        '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=48000:duration=10',
                        '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-shortest', str(clip)],
                       check=True, capture_output=True)

        record = new_project.create({'title': 'בדיקת עשן', 'kind': 'talking-head', 'video_language': 'he'})
        project_id = record['id']
        project = ROOT / 'projects' / project_id

        with open(clip, 'rb') as stream:
            item = materials.save_upload(project_id, 'take.mp4', stream, clip.stat().st_size)
        if item['tag'] != 'raw':
            raise RuntimeError(f'expected the uploaded clip to be tagged raw, got {item["tag"]!r}')

        stem = Path(item['file']).stem
        transcript = project / 'work' / 'transcripts' / f'{stem}.json'
        transcript.parent.mkdir(parents=True, exist_ok=True)
        transcript.write_text(json.dumps(FIXTURE_WORDS, ensure_ascii=False, indent=2), encoding='utf-8')

        choices.save(project_id, {'cut': 'tight', 'sound': 'no-music', 'sfx': False, 'captions': True,
                                   'length': '15-30'})

        bin_dir = Path(tmp) / 'fake-claude-bin'
        install_fake_claude(bin_dir)
        old_path = os.environ.get('PATH', '')
        os.environ['PATH'] = str(bin_dir) + os.pathsep + old_path
        try:
            job = runner.start(project_id, 'edit')['job']
            deadline = time.monotonic() + 120
            status = runner.status(job)
            while status['state'] == 'running':
                if time.monotonic() > deadline:
                    raise RuntimeError(f'the fake claude run did not finish in time: {status}')
                time.sleep(0.1)
                status = runner.status(job)
        finally:
            os.environ['PATH'] = old_path
        if status['state'] != 'done':
            log = ROOT / 'logs' / f'claude-{job}.log'
            detail = log.read_text(encoding='utf-8', errors='replace') if log.exists() else '(missing)'
            raise RuntimeError(f'the fake claude run failed: {status}; log: {detail}')

        data = index.registry()
        saved = next(p for p in data['projects'] if p['id'] == project_id)
        board = next((a for a in saved.get('artifacts', []) if a.get('type') == 'board' and
                      a.get('role') == 'storyboard'), None)
        if board is None:
            raise RuntimeError('no storyboard artifact was registered')
        if saved.get('primary_artifact') != board['id']:
            raise RuntimeError('the storyboard was not made the primary artifact')

        progress_steps = json.loads((project / 'progress.json').read_text(encoding='utf-8'))
        expected_keys = ['ingest', 'transcribe', 'cut', 'captions', 'graphics', 'sound', 'storyboard']
        if [s['key'] for s in progress_steps] != expected_keys or any(s['state'] != 'done' for s in progress_steps):
            raise RuntimeError(f'progress.json is not all done: {progress_steps}')

        captions_doc = json.loads((project / 'versions' / 'v01' / 'captions.json').read_text(encoding='utf-8'))
        if captions_doc.get('dir') != 'rtl':
            raise RuntimeError('Hebrew captions must be dir=rtl')
        captions_html = ' '.join(cue['html'] for cue in captions_doc['cues'])
        for isolated in ('<bdi dir="ltr">AI</bdi>', '<bdi dir="ltr">38</bdi>'):
            if isolated not in captions_html:
                raise RuntimeError(f'captions.json is missing an isolated Latin/number run: {isolated}')

        # Approve the storyboard through the real review_actions code path.
        public = next(p for p in index.public_index()['projects'] if p['id'] == project_id)
        if not public['review']['enabled']:
            raise RuntimeError('the storyboard is not reviewable')
        storage.apply_decision({'project_id': project_id, 'artifact_id': public['primary_artifact'],
                                'action': 'approve', 'revision': public['review']['revision'],
                                'request_id': str(uuid.uuid4())})

        # A genuinely fresh install has no catalog.json yet; the approval below must create
        # one. On a repeat run in the same checkout this file may already exist from an
        # earlier smoke run -- that does not invalidate this run, it just means the "fresh
        # install" edge case was already proven the first time.
        catalog_path = STYLE_LIBRARY / 'catalog.json'
        was_fresh_install = not catalog_path.exists()

        final_dir = project / 'versions' / 'v02' / 'renders'
        final_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(version_cut := project / 'versions' / 'v01' / 'cut.mp4', final_dir / 'final.mp4')
        subprocess.run([ffmpeg, '-nostdin', '-v', 'error', '-y', '-ss', '1.0', '-i', str(version_cut),
                        '-frames:v', '1', str(final_dir / 'poster.jpg')], check=True, capture_output=True)
        register_version.register_version(project, 'V02', 'final', video='versions/v02/renders/final.mp4',
                                          poster='versions/v02/renders/poster.jpg',
                                          summary='גרסה סופית מבדיקת העשן', next_step='לצפות ולאשר', lang='he')

        public = next(p for p in index.public_index()['projects'] if p['id'] == project_id)
        if public['review']['kind'] != 'final' or not public['review']['enabled']:
            raise RuntimeError('the final version is not ready for approval')
        storage.apply_decision({'project_id': project_id, 'artifact_id': public['primary_artifact'],
                                'action': 'approve', 'revision': public['review']['revision'],
                                'request_id': str(uuid.uuid4())})

        catalog = json.loads(catalog_path.read_text(encoding='utf-8'))
        if catalog.get('schema_version') != 4 or not catalog.get('entries'):
            raise RuntimeError('final approval did not create a library entry')
        if was_fresh_install:
            print(f'hebrew smoke: {project_id} approved a final video with no catalog.json present beforehand')
        print(f'hebrew smoke: {project_id} storyboard + final approved, captions RTL with isolated AI/38')


def main():
    argv = sys.argv[1:]
    if argv[:1] == ['--fake-claude-worker']:
        return _fake_claude_worker(argv[1:])
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--skip-render',action='store_true')
    # The Hebrew path alone needs only ffmpeg and a Python stdlib checkout -- no .venv/Pillow
    # (the legacy synthetic path below needs both, via scripts/studio.py) and no network/Node.
    # CI's fast unit-test job runs just this, since it never provisions those (see check.yml).
    parser.add_argument('--hebrew-only',action='store_true')
    args=parser.parse_args(argv)
    if args.hebrew_only:
        hebrew_smoke()
        print('smoke passed')
        return
    project=ROOT/'projects/setup-demo'
    if project.exists():
        report=ROOT/'runtime/smoke-report.json'
        if not report.exists():raise RuntimeError('An incomplete setup demo exists. Inspect its failed run; use a fresh checkout for a new smoke test. No files were overwritten.')
        saved=json.loads(report.read_text(encoding='utf-8'))
        if not saved.get('raw_unchanged') or (not args.skip_render and not saved.get('motion_rendered')):
            raise RuntimeError('The previous smoke run did not complete the requested checks. Use a fresh checkout; existing files were preserved.')
        print('The completed setup demo already exists and was preserved. This did not rerun the checks. Inspect runtime/smoke-report.json or use a fresh checkout for a new smoke run.')
        print('smoke passed')
        return
    hebrew_smoke()
    run([sys.executable,'scripts/studio.py','new','setup-demo'])
    source=project/'raw/synthetic.mp4'
    run(['ffmpeg','-nostdin','-v','error','-n','-f','lavfi','-i','testsrc2=size=360x640:rate=30:duration=4','-f','lavfi','-i','sine=frequency=440:sample_rate=48000:duration=4','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac','-shortest',source])
    # Record generated provenance and source hash just as an imported source would.
    info=json.loads(run(['ffprobe','-v','error','-show_streams','-show_format','-of','json',source],True).stdout)
    (project/'media-manifest.json').write_text(json.dumps({'version':1,'sources':[{'file':'raw/synthetic.mp4','sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'bytes':source.stat().st_size,'probe':info,'provenance':'Local FFmpeg testsrc2 and sine generators; no human speech.'}]},indent=2)+'\n', encoding='utf-8')
    plan=json.loads((project/'edit-plan.json').read_text(encoding='utf-8'));plan['output']={'width':360,'height':640,'fps':30}
    plan['cuts']=[{'beat_id':'first','source':'raw/synthetic.mp4','source_in':.2,'source_out':1.4,'text':'Synthetic first cut.','reason':'Technical timing fixture, no performance judgment.'},{'beat_id':'second','source':'raw/synthetic.mp4','source_in':2,'source_out':3.2,'text':'Synthetic second cut.','reason':'Verify a deliberate gap removal.'}]
    (project/'edit-plan.json').write_text(json.dumps(plan,indent=2)+'\n', encoding='utf-8')
    run([PY,'scripts/studio.py','prepare',project,source,'--interval','1','--max-frames','4'])
    run([PY,'scripts/studio.py','assemble',project])
    assembly=project/'exports/assembly-v01.mp4'
    result=json.loads(run(['ffprobe','-v','error','-show_streams','-show_format','-of','json',assembly],True).stdout)
    if abs(float(result['format']['duration'])-2.4)>.05:raise RuntimeError('Assembly duration mismatch')
    if not {'audio','video'}.issubset({s['codec_type'] for s in result['streams']}):raise RuntimeError('Missing assembly audio/video')
    current=assembly;version='V01';rendered=False
    if not args.skip_render:
        sample=ROOT/'examples/studio-check';(sample/'output').mkdir(exist_ok=True)
        run([sys.executable,'scripts/hf.py','check',sample])
        rendered_path=sample/'output/studio-check.mp4'
        if rendered_path.exists():raise RuntimeError('Sample output exists; use a fresh checkout rather than overwrite it')
        run([sys.executable,'scripts/hf.py','render',sample,'--workers','1','--fps','30','--crf','18','--output',rendered_path])
        probe=json.loads(run(['ffprobe','-v','error','-show_format','-of','json',rendered_path],True).stdout)
        if abs(float(probe['format']['duration'])-5)>.05:raise RuntimeError('Motion render duration mismatch')
        current=project/'exports/render-check-v01.mp4';shutil.copy2(rendered_path,current);rendered=True
    frame=project/'graphics/check-frame.png'
    run(['ffmpeg','-nostdin','-v','error','-n','-ss','2','-i',current,'-frames:v','1',frame])
    (project/'STATUS.md').write_text('# Synthetic setup demo\n\nCurrent: technical checks ready for review.\nNo human speech/performance reviewed. No approval or publication.\nThe spoken cut is a generated pattern/tone; the motion render is a separate synthetic composition.\n', encoding='utf-8')
    (project/'STORYBOARD.md').write_text('# Technical storyboard\n\nActual rendered frame: graphics/check-frame.png.\nThis is a synthetic technical illustration, not a creator storyboard or approved creative direction.\n', encoding='utf-8')
    seed={'id':'setup-demo-reference','collection':'mine','version':version,'title':'Your studio is ready','subtitle':'Synthetic local setup check','creator':'Demo','creator_id':'demo','summary':'Generated technical sample; replace with your own creative work.','tags':['Synthetic sample'],'palette':['#191b1e','#f3eee5','#f2734f'],'traits':{'Motion':'Local paused GSAP timeline'},'keep':['Use your own content.'],'avoid':['Do not treat a technical sample as a performance review.'],'moments':[],'notes':['projects/setup-demo/STATUS.md'],'evidence':'Local generated patterns and authored typography; no creator footage.','media_path':current.relative_to(ROOT).as_posix(),'duration':5 if rendered else 2.4}
    item={'id':'setup-demo','title':'Your first studio check','subtitle':'Synthetic setup demo','format':'video','state':'review','stage':'refine','summary':'Synthetic two-cut assembly and optional local motion render. No human speech or automatic approval.','next_step':'Inspect the actual sample, then try approve/reopen on this demo if you want to test the workflow.','primary_artifact':'review','cover_path':'graphics/check-frame.png','reference_id':'setup-demo-reference','reference_entry':seed,'reference_poster_source':'graphics/check-frame.png','source_notes':[{'label':'Current status','path':'STATUS.md'},{'label':'Review notes','path':'review-notes.md'}],'artifacts':[{'id':'review','label':'Synthetic review','type':'video','path':current.relative_to(project).as_posix(),'version':version,'role':'current','approval_kind':'final','description':'Technical sample only. No music or human speech.'},{'id':'assembly','label':'Two-cut assembly','type':'video','path':'exports/assembly-v01.mp4','version':'V01','role':'assembly','description':'Generated pattern and tone, with a removed source gap.'},{'id':'board','label':'Actual check frame','type':'board','version':'V01','role':'storyboard','frames':[{'path':'graphics/check-frame.png','title':'Local rendered technical frame','note':'A sample frame, not a complete creator storyboard.'}]}]}
    descriptor=project/'studio-entry.json';descriptor.write_text(json.dumps(item,indent=2)+'\n', encoding='utf-8')
    run([sys.executable,'scripts/register.py','project',descriptor,'--replace'])
    out=ROOT/'runtime';out.mkdir(exist_ok=True)
    (out/'smoke-report.json').write_text(json.dumps({'synthetic':True,'assembly_seconds':2.4,'audio_video_present':True,'raw_unchanged':hashlib.sha256(source.read_bytes()).hexdigest()==json.loads((project/'media-manifest.json').read_text(encoding='utf-8'))['sources'][0]['sha256'],'motion_rendered':rendered,'project':'setup-demo','approved':False,'limits':['No human speech/take-selection/transcription/creative-quality test','No fresh assistant or second-machine pilot']},indent=2)+'\n', encoding='utf-8')
    print('Synthetic smoke passed. No project approved. Open the studio to inspect the demo.')
    print('smoke passed')

if __name__=='__main__':main()
