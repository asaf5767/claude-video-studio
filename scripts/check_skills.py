"""Check the studio's project skills against the contracts the rest of the studio relies on.

    python scripts/check_skills.py

For .claude/skills/{talking-head,faceless-reel,learn-style}/SKILL.md (plus the files each one
links under its references/ and docs/skills/):
  - front matter with name: <folder> and a description that starts with "Use when";
  - every scripts/... and docs/skills/... path it mentions exists;
  - its "Progress steps:" line lists exactly the fixed step keys (Task 14's progress.json),
    and every progress.py command uses only those keys (talking-head may add matte);
  - every shell command it shows starts with a Bash prefix the headless runner allows for
    that skill's job (style-library/claude_runner.py MEDIA_COMMANDS plus PYTHONS x HELPERS:
    one rule per named helper script), one command per call; raw ffmpeg/ffprobe are not
    allowed, and every `python scripts/media.py ffmpeg|ffprobe ...` it shows must pass
    media.py's own checks (RULING R51);
  - the rules other tasks depend on are stated in SKILL.md itself: bidi-safe <= 28-character RTL captions, the
    HEVC/HDR transcode, never overwriting an approved version, the optional add-ons
    (STUDIO_VOICE_KEY / STUDIO_IMAGE_KEY), and for learn-style "technique only" and "never
    write style-card.json".
Prints one problem per line and exits 1 if there are any.
"""
import ast
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
    'python3 on a Mac': (EDITING, [r'python3']),
    # R53: the skill that reads other people's content never runs a command.
    'no commands': (('learn-style',), [r'No commands', r'never runs anything', r'only Read, Glob, Grep and Write']),
    'text is data': (tuple(FIXED_STEPS), [r'never instructions', r'\.env']),
    'voice tag': (('faceless-reel',), [r'tagged `voice`']),
    'fonts': (EDITING, [r'Secular One', r'Heebo']),
    # Concern 3: an inspiration look reaches an editing run only as the studio's look.json.
    'look.json': (EDITING, [r'look\.json']),
    'technique only': (('learn-style',), [r'footage', r'words', r'logo']),
    'pins': (('learn-style',), [r'never (?:write|writes|change|changes|touch)[^.\n]*style-card\.json',
                                r'pinned']),
}
# Words that start a shell command in prose or code; anything that starts with one of these
# must match an allowed prefix.
COMMAND_WORDS = ('python', 'python3', 'py', 'node', 'npx', 'npm', 'ffmpeg', 'ffprobe', 'pip', 'pip3', 'cp',
                 'mv', 'rm', 'mkdir', 'ls', 'cat', 'curl', 'wget', 'git', 'bash', 'sh', 'cd', 'whisper-cli',
                 'hyperframes', 'claude', 'powershell', 'open', 'start', 'sed', 'grep', 'find', 'echo', 'touch')
INLINE = re.compile(r'`([^`\n]+)`')
FENCE = re.compile(r'```(?:bash|sh|shell|console)?\n(.*?)```', re.S)
FRONT = re.compile(r'\A---\n(.*?)\n---\n', re.S)


TASK_BY_SKILL = {'talking-head': 'edit', 'faceless-reel': 'edit', 'learn-style': 'learn-style'}
# Placeholders in prose ("python scripts/<helper>.py", "python scripts/…") describe the form only.
PLACEHOLDER = re.compile(r'^python3? scripts/(?:…|<[\w-]+>\.py)')
# G1: the skills name every helper by the absolute studio folder, `python "<studio>/scripts/x.py"`;
# the runner's rules use the real absolute path in its place.
ABSOLUTE = re.compile(r'^(python3?) "<studio>/(scripts/[^"\s]+)"')


def _runner_constants(root):
    """MEDIA_COMMANDS, PYTHONS and HELPERS as written in claude_runner.py (literals, not imported)."""
    tree = ast.parse((Path(root) / 'style-library' / 'claude_runner.py').read_text(encoding='utf-8'))
    found = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            if node.targets[0].id in ('MEDIA_COMMANDS', 'PYTHONS', 'HELPERS'):
                found[node.targets[0].id] = ast.literal_eval(node.value)
    return found


def allowed_prefixes(root=ROOT, skill='talking-head'):
    """The Bash command prefixes the runner allows for `skill`'s job (one Bash(<prefix>:*) rule each)."""
    c = _runner_constants(root)
    return list(c['MEDIA_COMMANDS']) + [f'{python} {helper}' for helper in c['HELPERS'][TASK_BY_SKILL[skill]]
                                        for python in c['PYTHONS']]


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
    for path in sorted(set(re.findall(r'(?:(?<=<studio>/)|(?<![\w/.-]))(scripts/[\w.-]+\.(?:py|mjs))', everything))):
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
    if skill == 'learn-style':
        pass  # R53: the studio writes learn-style's progress itself
    elif f'scripts/progress.py' not in main or f'--start {skill}' not in main:
        problems.append(f'{skill}: must start its progress file with python scripts/progress.py <file> --start {skill}')
    else:
        # The studio shows the run only once progress.json exists: start it before reading anything.
        begin = main.index(f'--start {skill}')
        reads = [main.find(word) for word in ('brief.md', 'choices.json', '## 1.') if word in main]
        if reads and begin > min(reads):
            problems.append(f'{skill}: start progress (--start) before reading the project')
    known = FIXED_STEPS[skill] + OPTIONAL_STEPS.get(skill, [])
    for key in re.findall(r'progress\.py"? \S+ ([\w-]+) (?:todo|running|done)\b', everything):
        if key not in known:
            problems.append(f"{skill}: progress step '{key}' is not one of {known}")
    own = allowed_prefixes(root, skill)
    for name, text in texts.items():
        # A shared doc (docs/skills/headless.md) is held to what any skill that links it may run.
        prefixes = own if not name.startswith('docs/') else sorted(
            {p for other in FIXED_STEPS if name in _links(root, other) for p in allowed_prefixes(root, other)})
        problems += _check_commands(skill, _commands(text), prefixes, root)
    if skill in EDITING:
        for name, text in texts.items():
            for found in sorted(set(re.findall(r'references/<id>|style-card\.(?:md|json)', text))):
                problems.append(f'{skill}: {name} points at an inspiration file ({found}); use projects/<id>/look.json')
    for rule, (skills, patterns) in RULES.items():  # stated in SKILL.md itself, not only in a linked doc
        if skill in skills and not all(re.search(p, main) for p in patterns):
            problems.append(f'{skill}: missing rule: {rule}')
    return problems


def _links(root, skill):
    main = (Path(root) / '.claude' / 'skills' / skill / 'SKILL.md').read_text(encoding='utf-8')
    return set(re.findall(r'(docs/skills/[\w.-]+\.md)', main))


def _media_problem(root, command):
    """Why scripts/media.py would refuse this documented command (outside a studio run), or None."""
    import importlib.util
    import shlex
    spec = importlib.util.spec_from_file_location('check_skills_media', Path(root) / 'scripts' / 'media.py')
    media = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(media)
    try:
        media.checked(shlex.split(command)[2:])
    except Exception as error:  # noqa: BLE001 -- Refused or JobScopeError: report it
        return str(error)
    return None


def _check_commands(skill, commands, prefixes, root=ROOT):
    problems = []
    for command in commands:
        written = command
        if command.startswith(('python scripts/', 'python3 scripts/')) and not PLACEHOLDER.match(command):
            problems.append(f'{skill}: name the helper by the studio folder, python "<studio>/scripts/…": {command}')
            continue
        command = ABSOLUTE.sub(r'\1 \2', command)
        if PLACEHOLDER.match(command):
            continue
        if not prefixes:
            problems.append(f'{skill}: this skill runs no commands, but shows: {written}')
            continue
        if not any(command == p or command.startswith(p + ' ') for p in prefixes):
            problems.append(f'{skill}: command not allowed headless: {command}')
        elif '&&' in command or command.startswith('cd '):
            problems.append(f'{skill}: one command per call, no cd/&&: {command}')
        media = re.match(r'python3? scripts/media\.py (ffmpeg|ffprobe) (.*)$', command)
        if media and '…' not in command and '<in>' not in command:
            problem = _media_problem(root, command.replace('"<studio>/scripts/media.py"', 'scripts/media.py'))
            if problem:
                problems.append(f'{skill}: media.py would refuse: {command} ({problem})')
        hf = re.match(r'python3? scripts/hf\.py (check|render)\s*$', command)
        if hf:
            problems.append(f'{skill}: hf.py {hf.group(1)} needs the version folder ("projects/<id>/versions/vNN")')
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
