"""Run only the project-local pinned HyperFrames CLI."""
import os
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tools

ROOT=Path(__file__).resolve().parents[1]
cli=ROOT/'node_modules/hyperframes/bin/hyperframes.mjs'
if not cli.is_file():raise SystemExit('Run '+tools.hint('scripts/setup.py')+' first.')
result=subprocess.run([tools.resolve('node'),str(cli),*sys.argv[1:]],env={**os.environ,'HYPERFRAMES_NO_UPDATE_CHECK':'1','HYPERFRAMES_NO_TELEMETRY':'1'})
raise SystemExit(result.returncode)
