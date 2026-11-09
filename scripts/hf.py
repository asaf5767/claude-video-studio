"""Run only the project-local pinned HyperFrames CLI.

In a studio run (STUDIO_JOB_DIR set, RULING R51) only these forms pass, with every path
inside the job folder:
    python scripts/hf.py --help
    python scripts/hf.py check <version folder>
    python scripts/hf.py render <version folder> --output <file.mp4> [--workers N] [--fps N] [--crf N] [--quality Q]
Anything else (other subcommands, --browser-path, --docker, --config, ...) is refused with
the coded error job.outside-folder. A creator's own chat use passes everything through.
"""
import json
import os
from pathlib import Path
import re
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jobscope  # noqa: E402  (RULING R51: every path stays inside the job folder)
import tools  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / 'node_modules/hyperframes/bin/hyperframes.mjs'
RENDER_VALUES = {'--workers': r'[1-9]\d?', '--fps': r'\d{1,3}(?:/\d{1,5})?(?:\.\d+)?', '--crf': r'\d{1,2}',
                 '--quality': r'[a-z]{1,12}'}


def allowed(argv):
    """The argv to pass on, or raise jobscope.JobScopeError."""
    if not jobscope.active():
        return list(argv)
    if argv == ['--help']:
        return list(argv)
    if len(argv) == 2 and argv[0] == 'check':
        jobscope.confine(argv[1], exists=True)
        return list(argv)
    if len(argv) >= 4 and argv[0] == 'render':
        jobscope.confine(argv[1], exists=True)
        rest, output = argv[2:], None
        if len(rest) % 2:
            raise jobscope.JobScopeError('hf.py render takes --flag value pairs only')
        for flag, value in zip(rest[::2], rest[1::2]):
            if flag == '--output':
                if Path(value).suffix.lower() not in ('.mp4', '.mov', '.webm'):
                    raise jobscope.JobScopeError('hf.py render --output must be a new .mp4, .mov or .webm file')
                output = jobscope.confine(value, new=True, write=True)
            elif flag in RENDER_VALUES and re.fullmatch(RENDER_VALUES[flag], value):
                continue
            else:
                raise jobscope.JobScopeError(f'hf.py render: {flag} is not available in a studio run')
        if output is None:
            raise jobscope.JobScopeError('hf.py render needs --output <file> inside the job folder')
        return list(argv)
    raise jobscope.JobScopeError('in a studio run hf.py runs only "check <folder>" and "render <folder> --output <file>"')


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    try:
        args = allowed(argv)
    except jobscope.JobScopeError as error:
        print(json.dumps({'ok': False, 'code': jobscope.CODE, 'message': str(error)}, ensure_ascii=False))
        return 2
    if not CLI.is_file():
        raise SystemExit('Run ' + tools.hint('scripts/setup.py') + ' first.')
    result = subprocess.run([tools.resolve('node'), str(CLI), *args],
                            env={**os.environ, 'HYPERFRAMES_NO_UPDATE_CHECK': '1', 'HYPERFRAMES_NO_TELEMETRY': '1'})
    return result.returncode


if __name__ == '__main__':
    raise SystemExit(main())
