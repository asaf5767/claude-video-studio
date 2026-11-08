"""Check the studio's project skills against the contracts the rest of the studio relies on.

    python scripts/check_skills.py

For .claude/skills/{talking-head,faceless-reel,learn-style}/SKILL.md (plus the files each one
links under its references/ and docs/skills/):
  - front matter with name: <folder> and a description that starts with "Use when";
  - every scripts/... and docs/skills/... path it mentions exists;
  - its "Progress steps:" line lists exactly the fixed step keys (Task 14's progress.json),
    and every progress.py command uses only those keys (talking-head may add matte);
  - every shell command it shows starts with a Bash prefix the headless runner allows
    (style-library/claude_runner.py ALLOWED), one command per call;
  - the rules other tasks depend on are stated in SKILL.md itself: bidi-safe <= 28-character RTL captions, the
    HEVC/HDR transcode, never overwriting an approved version, the optional add-ons
    (STUDIO_VOICE_KEY / STUDIO_IMAGE_KEY), and for learn-style "technique only" and "never
    write style-card.json".
Prints one problem per line and exits 1 if there are any.
"""
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
FIXED_STEPS = {
    'talking-head': ['ingest', 'transcribe', 'cut', 'captions', 'graphics', 'sound', 'storyboard'],
    'faceless-reel': ['voice', 'transcribe', 'scenes', 'captions', 'sound', 'storyboard'],
    'learn-style': ['watch', 'analyze', 'card'],
}
OPTIONAL_STEPS = {'talking-head': ['matte']}
# Add-on clients delivered by another task: skills run them only when the file exists.
OPTIONAL_SCRIPTS = {'scripts/addons_voice.py', 'scripts/addons_image.py'}
EDITING = ('talking-head', 'faceless-reel')
# rule name -> (skills, regexes that must all match somewhere in the skill's text)
RULES = {
    'bidi': (EDITING, [r'<bdi', r'\b28\b', r'\bRTL\b']),
    'HEVC': (EDITING, [r'HEVC', r'HDR', r'scripts/prepare_media\.py']),
    'never overwrite': (EDITING, [r'approval-state\.json', r'scripts/new_version\.py']),
    'add-ons': (EDITING, [r'STUDIO_VOICE_KEY', r'STUDIO_IMAGE_KEY', r'addons', r'scripts/addons_voice\.py',
                          r'scripts/addons_image\.py', r'when that file exists']),
    'python3 on a Mac': (tuple(FIXED_STEPS), [r'python3']),
    'voice tag': (('faceless-reel',), [r'tagged `voice`']),
    'fonts': (EDITING, [r'Secular One', r'Heebo']),
    'technique only': (('learn-style',), [r'footage', r'words', r'logo']),
    'pins': (('learn-style',), [r'never (?:write|writes|change|changes|touch)[^.\n]*style-card\.json',
                                r'scripts/check_card\.py']),
}
# Words that start a shell command in prose or code; anything that starts with one of these
# must match an allowed prefix.
COMMAND_WORDS = ('python', 'python3', 'py', 'node', 'npx', 'npm', 'ffmpeg', 'ffprobe', 'pip', 'pip3', 'cp',
                 'mv', 'rm', 'mkdir', 'ls', 'cat', 'curl', 'wget', 'git', 'bash', 'sh', 'cd', 'whisper-cli',
                 'hyperframes', 'claude', 'powershell', 'open', 'start', 'sed', 'grep', 'find', 'echo', 'touch')
INLINE = re.compile(r'`([^`\n]+)`')
FENCE = re.compile(r'```(?:bash|sh|shell|console)?\n(.*?)```', re.S)
FRONT = re.compile(r'\A---\n(.*?)\n---\n', re.S)


def allowed_prefixes(root=ROOT):
    text = (Path(root) / 'style-library' / 'claude_runner.py').read_text(encoding='utf-8')
    block = re.search(r"ALLOWED = \((.*?)\)\n", text, re.S).group(1)
    allowed = ''.join(re.findall(r"'([^']*)'", block))
    prefixes = []
    for pattern in re.findall(r'Bash\(([^)]*)\)', allowed):
        prefix = pattern[:-2] if pattern.endswith(':*') else pattern.rstrip('*')
        prefixes.append(prefix)
    return prefixes


def _texts(root, skill):
    """SKILL.md plus every references/*.md and docs/skills/*.md it links (one level)."""
    folder = Path(root) / '.claude' / 'skills' / skill
    main = (folder / 'SKILL.md').read_text(encoding='utf-8')
    texts = {'SKILL.md': main}
    for relative in sorted(set(re.findall(r'(?<![\w/.-])(references/[\w.-]+\.md)', main))):
        if (folder / relative).is_file():
            texts[relative] = (folder / relative).read_text(encoding='utf-8')
    for relative in sorted(set(re.findall(r'(docs/skills/[\w.-]+\.md)', main))):
        if (Path(root) / relative).is_file():
            texts[relative] = (Path(root) / relative).read_text(encoding='utf-8')
    return folder, texts


def _commands(text):
    found = []
    for block in FENCE.findall(text):
        found += [line.strip() for line in block.splitlines() if line.strip() and not line.strip().startswith('#')]
    for span in INLINE.findall(text):
        first = span.strip().split(' ', 1)[0]
        if first in COMMAND_WORDS and ' ' in span.strip():
            found.append(span.strip())
    return found


def check_skill(root, skill):
    problems = []
    try:
        folder, texts = _texts(root, skill)
    except OSError:
        return [f'{skill}: .claude/skills/{skill}/SKILL.md is missing']
    main = texts['SKILL.md']
    front = FRONT.match(main.replace('\r\n', '\n'))
    if not front:
        problems.append(f'{skill}: SKILL.md must start with a --- front matter block')
    else:
        fields = dict(line.split(':', 1) for line in front.group(1).splitlines() if ':' in line)
        fields = {k.strip(): v.strip() for k, v in fields.items()}
        if fields.get('name') != skill:
            problems.append(f'{skill}: front matter needs name: {skill}')
        if not fields.get('description', '').startswith('Use when'):
            problems.append(f'{skill}: description must start with "Use when"')
        if len(front.group(1)) > 1024:
            problems.append(f'{skill}: front matter is over 1024 characters')
    everything = '\n'.join(texts.values())
    for path in sorted(set(re.findall(r'(?<![\w/.-])(scripts/[\w.-]+\.(?:py|mjs))', everything))):
        if path not in OPTIONAL_SCRIPTS and not (Path(root) / path).is_file():
            problems.append(f'{skill}: mentions {path}, which does not exist')
    for path in sorted(set(re.findall(r'(docs/skills/[\w.-]+\.md)', everything))):
        if not (Path(root) / path).is_file():
            problems.append(f'{skill}: mentions {path}, which does not exist')
    for path in sorted(set(re.findall(r'(?<![\w/.-])(references/[\w.-]+\.md)', main))):
        if not (folder / path).is_file():
            problems.append(f'{skill}: mentions {path}, which does not exist')
    line = re.search(r'^Progress steps:(.*)$', main, re.M)
    steps = re.findall(r'`([\w-]+)`', line.group(1)) if line else []
    if steps != FIXED_STEPS[skill]:
        problems.append(f'{skill}: progress steps {steps} must be exactly {FIXED_STEPS[skill]}')
    if f'scripts/progress.py' not in main or f'--start {skill}' not in main:
        problems.append(f'{skill}: must start its progress file with python scripts/progress.py <file> --start {skill}')
    else:
        # The studio shows the run only once progress.json exists: start it before reading anything.
        begin = main.index(f'--start {skill}')
        reads = [main.find(word) for word in ('brief.md', 'choices.json', '## 1.') if word in main]
        if reads and begin > min(reads):
            problems.append(f'{skill}: start progress (--start) before reading the project')
    known = FIXED_STEPS[skill] + OPTIONAL_STEPS.get(skill, [])
    for key in re.findall(r'progress\.py \S+ ([\w-]+) (?:todo|running|done)\b', everything):
        if key not in known:
            problems.append(f"{skill}: progress step '{key}' is not one of {known}")
    prefixes = allowed_prefixes(root)
    for command in _commands(everything):
        if not any(command == p or command.startswith(p if p.endswith('/') else p + ' ') for p in prefixes):
            problems.append(f'{skill}: command not allowed headless: {command}')
        elif '&&' in command or command.startswith('cd '):
            problems.append(f'{skill}: one command per call, no cd/&&: {command}')
        hf = re.match(r'python3? scripts/hf\.py (check|render)\s*$', command)
        if hf:
            problems.append(f'{skill}: hf.py {hf.group(1)} needs the version folder ("projects/<id>/versions/vNN")')
    for rule, (skills, patterns) in RULES.items():  # stated in SKILL.md itself, not only in a linked doc
        if skill in skills and not all(re.search(p, main) for p in patterns):
            problems.append(f'{skill}: missing rule: {rule}')
    return problems


def check(root=ROOT):
    problems = []
    for skill in FIXED_STEPS:
        problems += check_skill(root, skill)
    return problems


def main():
    problems = check(ROOT)
    for problem in problems:
        print(problem)
    if not problems:
        print('skills ok: ' + ', '.join(FIXED_STEPS))
    return 1 if problems else 0


if __name__ == '__main__':
    raise SystemExit(main())
