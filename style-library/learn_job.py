"""One "Learn this style" run (RULING R53): analyse on the server, then Claude with no shell.

    python style-library/learn_job.py <studio root> <reference id> <he|en>

claude_runner starts this as the job's process (so cancel stops the whole tree, and the
log gets everything). It:
  1. writes progress.json (watch -> analyze -> card) and runs learn_analysis.analyze()
     into references/<id>/analysis/rNN/ with fixed commands;
  2. starts Claude Code in references/<id>/ (its working folder: a read outside it is
     denied in dontAsk mode) with `--tools Read,Glob,Grep,Write` -- no Bash at all -- and
     rules that allow writing exactly style-card.md (claude_runner.learn_command);
  3. checks the card with scripts/check_card.py and finishes the progress steps.
Its last stdout line is a stream-json "result" event the runner classifies.
"""
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / 'scripts'))
import claude_runner  # noqa: E402
import learn_analysis  # noqa: E402
import progress  # noqa: E402
import tools  # noqa: E402

TEXT = {
    'he': {'watch': 'צופים בסרטון ומודדים אותו', 'watched': '{shots} שוטים, {seconds} שניות',
           'no-source': 'צריך את קובץ הסרטון', 'unreadable': 'אי אפשר לקרוא את הסרטון',
           'analyze': 'קלוד לומד את הסגנון', 'analyzed': 'הניתוח הושלם', 'card': 'כותבים את כרטיס הסגנון',
           'card-done': 'כרטיס הסגנון מוכן', 'card-missing': 'הכרטיס חסר שורות: {keys}', 'stopped': 'הריצה לא הסתיימה'},
    'en': {'watch': 'Watching and measuring the video', 'watched': '{shots} shots, {seconds} seconds',
           'no-source': 'The video file is needed', 'unreadable': 'The video cannot be read',
           'analyze': 'Claude is learning the style', 'analyzed': 'Analysis done', 'card': 'Writing the style card',
           'card-done': 'The style card is ready', 'card-missing': 'The card is missing rows: {keys}', 'stopped': 'The run did not finish'},
}


def result(subtype, is_error=True):
    print(json.dumps({'type': 'result', 'subtype': subtype, 'is_error': is_error}), flush=True)


def run_claude(argv, cwd, env):
    """Run Claude, passing its stream-json through to our stdout (the job log); returns
    (exit code, whether its result event was an error)."""
    proc = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT)
    failed = False
    for raw in proc.stdout:
        sys.stdout.buffer.write(raw)
        sys.stdout.buffer.flush()
        try:
            event = json.loads(raw)
        except ValueError:
            continue
        if isinstance(event, dict) and event.get('type') == 'result':
            failed = bool(event.get('is_error'))
    return proc.wait(), failed


def main(argv=None):
    studio, ref_id, lang = (argv or sys.argv[1:])[:3]
    studio = Path(studio).resolve()
    lang = lang if lang in TEXT else 'he'
    words = TEXT[lang]
    folder = studio / 'references' / ref_id
    steps = folder / 'progress.json'
    progress.start(steps, 'learn-style')
    progress.update(steps, 'watch', 'running', words['watch'])
    try:
        analysis = learn_analysis.analyze(folder, studio, language=lang, lang=lang)
    except learn_analysis.AnalysisError as error:
        progress.update(steps, 'watch', 'todo', words['no-source' if error.code == 'analysis.no-source' else 'unreadable'])
        result('studio.no-source' if error.code == 'analysis.no-source' else 'studio.unreadable')
        return 3
    except (OSError, subprocess.SubprocessError, tools.ToolMissing) as error:
        progress.update(steps, 'watch', 'todo', words['unreadable'])
        print(f'analysis failed: {error}', flush=True)
        result('studio.unreadable')
        return 3
    measured = analysis['measured']
    progress.update(steps, 'watch', 'done', words['watched'].format(shots=measured['shots'],
                                                                     seconds=round(measured['duration'])))
    progress.update(steps, 'analyze', 'running', words['analyze'])
    round_folder = folder / 'analysis' / analysis['round']
    (round_folder / 'instructions.md').write_text(claude_runner.learn_instructions(ref_id, analysis['round'], lang),
                                                  encoding='utf-8')
    claude = tools.resolve('claude')
    command = claude_runner.learn_command(claude, ref_id, analysis['round'], lang)
    code, failed = run_claude(command, folder, claude_runner.child_env(job_dir=folder))
    if code != 0 or failed:
        progress.update(steps, 'analyze', 'todo', words['stopped'])
        return code or 1
    progress.update(steps, 'analyze', 'done', words['analyzed'])
    progress.update(steps, 'card', 'running', words['card'])
    import check_card  # scripts/check_card.py: the same rules the skill used to run itself
    report = check_card.check(folder)
    if not report['ok']:
        progress.update(steps, 'card', 'todo', words['card-missing'].format(keys=', '.join(report['missing'] + report['changed_pins'])))
        result('studio.card-invalid')
        return 1
    progress.update(steps, 'card', 'done', words['card-done'])
    return 0


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    raise SystemExit(main())
