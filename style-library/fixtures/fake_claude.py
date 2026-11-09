"""Test-only stand-in for the `claude` CLI (Task 14).

The runner tests put a tiny `claude` (POSIX sh) or `claude.cmd` (Windows) shim first on
PATH that runs this file with the test's Python. Behaviour comes from environment
variables so each test can script one run:

  FAKE_CLAUDE_RECORD  path: write {"argv", "cwd", "pid", "env", "session_env"} as JSON before doing
                      anything else ("env": the Bash timeout variables the runner sets for the
                      child; "session_env": every CLAUDE*/ANTHROPIC*/STUDIO_* variable and
                      PYTHONUTF8/PYTHONIOENCODING it received)
  FAKE_CLAUDE_STEPS   comma-separated step keys: write <target>/progress.json (all "done")
  FAKE_CLAUDE_OUTPUT  text printed to stdout (default: a stream-json success result line)
  FAKE_CLAUDE_SLEEP   seconds to sleep before exiting (for busy / cancel tests)
  FAKE_CLAUDE_EXIT    exit code (default 0)
  FAKE_CLAUDE_WRITE   a studio-relative path the fake "run" writes (an attack that slipped
                      through, for the integrity tests)
  FAKE_CLAUDE_CARD    path of a file whose text the fake writes to ./style-card.md (learn-style
                      runs in the reference's folder)

<target> is the folder named in the prompt ("/talking-head projects/<id> Reply in ...").
"""
import json
import os
import sys
import time


def main():
    sys.stdout.reconfigure(encoding='utf-8')  # like the real CLI, whatever the console code page
    argv = sys.argv[1:]
    record = os.environ.get('FAKE_CLAUDE_RECORD')
    if record:
        with open(record, 'w', encoding='utf-8') as stream:
            json.dump({'argv': argv, 'cwd': os.getcwd(), 'pid': os.getpid(),
                       'env': {k: os.environ.get(k) for k in ('BASH_DEFAULT_TIMEOUT_MS', 'BASH_MAX_TIMEOUT_MS')},
                       'session_env': {k: v for k, v in os.environ.items()
                                       if k.upper().startswith(('CLAUDE', 'ANTHROPIC', 'STUDIO_'))
                                       or k.upper() in ('PYTHONUTF8', 'PYTHONIOENCODING')}},
                      stream)
    planted = os.environ.get('FAKE_CLAUDE_WRITE')
    if planted:
        os.makedirs(os.path.dirname(planted) or '.', exist_ok=True)
        with open(planted, 'w', encoding='utf-8') as stream:
            stream.write('# planted by a test\n')
    steps = [key for key in os.environ.get('FAKE_CLAUDE_STEPS', '').split(',') if key]
    card = os.environ.get('FAKE_CLAUDE_CARD')
    if card:
        with open(card, encoding='utf-8') as source, open('style-card.md', 'w', encoding='utf-8') as stream:
            stream.write(source.read())
    if steps and len(argv) > 1 and argv[1].split(' ')[1].startswith(('projects/', 'references/')):
        target = argv[1].split(' ')[1]
        with open(os.path.join(target, 'progress.json'), 'w', encoding='utf-8') as stream:
            json.dump([{'key': key, 'state': 'done'} for key in steps], stream)
    sys.stdout.write(os.environ.get('FAKE_CLAUDE_OUTPUT', '{"type":"result","subtype":"success","is_error":false}') + '\n')
    sys.stdout.flush()
    time.sleep(float(os.environ.get('FAKE_CLAUDE_SLEEP', '0')))
    return int(os.environ.get('FAKE_CLAUDE_EXIT', '0'))


if __name__ == '__main__':
    sys.exit(main())
