"""Test-only stand-in for the `claude` CLI (Task 14).

The runner tests put a tiny `claude` (POSIX sh) or `claude.cmd` (Windows) shim first on
PATH that runs this file with the test's Python. Behaviour comes from environment
variables so each test can script one run:

  FAKE_CLAUDE_RECORD  path: write {"argv", "cwd", "pid", "env"} as JSON before doing anything else
                      ("env": the Bash timeout variables the runner sets for the child)
  FAKE_CLAUDE_STEPS   comma-separated step keys: write <target>/progress.json (all "done")
  FAKE_CLAUDE_OUTPUT  text printed to stdout (default: a stream-json success result line)
  FAKE_CLAUDE_SLEEP   seconds to sleep before exiting (for busy / cancel tests)
  FAKE_CLAUDE_EXIT    exit code (default 0)

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
                       'env': {k: os.environ.get(k) for k in ('BASH_DEFAULT_TIMEOUT_MS', 'BASH_MAX_TIMEOUT_MS')}},
                      stream)
    steps = [key for key in os.environ.get('FAKE_CLAUDE_STEPS', '').split(',') if key]
    if steps and len(argv) > 1:
        target = argv[1].split(' ')[1]
        with open(os.path.join(target, 'progress.json'), 'w', encoding='utf-8') as stream:
            json.dump([{'key': key, 'state': 'done'} for key in steps], stream)
    sys.stdout.write(os.environ.get('FAKE_CLAUDE_OUTPUT', '{"type":"result","subtype":"success","is_error":false}') + '\n')
    sys.stdout.flush()
    time.sleep(float(os.environ.get('FAKE_CLAUDE_SLEEP', '0')))
    return int(os.environ.get('FAKE_CLAUDE_EXIT', '0'))


if __name__ == '__main__':
    sys.exit(main())
