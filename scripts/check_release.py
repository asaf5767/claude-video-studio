"""Read-only version, empty-seed and exact-source-tree release checks."""
import argparse
import importlib.util
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
REPO_URL = 'https://github.com/asaf5767/claude-video-studio'
SETUP_SKILL = '.claude/skills/setup-studio/SKILL.md'
UPSTREAM_RELEASES = 'mattp68/ai-video-studio' + '/releases'  # split so this check does not flag itself
INSTALL_MESSAGE_HE = ('תשתמש בסקיל של הסטודיו לעריכת וידאו מהכתובת הזאת: ' + REPO_URL + ' — תתקין את כל מה שצריך, '
                      'תשאל אותי לפני כל התקנה, ותסביר לי בעברית פשוטה מה אתה עושה. כשהכל מוכן, תפתח לי את הסטודיו בדפדפן.')
INSTALL_MESSAGE_EN = ('Use the video studio skill from ' + REPO_URL + ' — install everything it needs, ask me before each '
                      "install, and explain in plain English what you're doing. When it's ready, open the studio in my browser.")


def verify(files):
    def data(name):
        return json.loads(files[name])
    version = data('package.json')['version']
    if not re.fullmatch(r'\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?', version):
        raise ValueError('Use a numbered release version without local build metadata.')
    lock = data('package-lock.json')
    if lock['version'] != version or lock['packages']['']['version'] != version:
        raise ValueError('Package/lock versions disagree.')
    html = files['style-library/dist/index.html'].decode()
    if re.findall(r'<meta name="studio-version" content="([^"]+)"', html) != [version]:
        raise ValueError('Installed interface version disagrees with package.json.')
    if 'Local preview' in html:
        raise ValueError('Published interface still says Local preview.')
    # Installation docs are version-free: the one-message install always gets the current main branch.
    for name in ['README.md', 'README.en.md', 'INSTALL_PROMPT.md', 'docs/PILOT.md', 'SETUP.md']:
        if re.search(r'\bv\d+\.\d+\.\d+(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?', files[name].decode()):
            raise ValueError('Hardcoded installation tag in ' + name + '; keep the starter prompt version-free')
    # The one-message install (Task 19): Assaf's guide page tells followers to paste this exact text,
    # so it must appear verbatim, once, wherever we show it.
    for name, message in [('README.md', INSTALL_MESSAGE_HE), ('INSTALL_PROMPT.md', INSTALL_MESSAGE_HE),
                          ('README.en.md', INSTALL_MESSAGE_EN), ('INSTALL_PROMPT.md', INSTALL_MESSAGE_EN)]:
        if files[name].decode().count(message) != 1:
            raise ValueError('The one-message install text is missing or changed in ' + name)
    # Claude Code reads the README first when given that message: it must open with its instructions.
    if SETUP_SKILL not in files:
        raise ValueError('The setup-studio skill must ship: ' + SETUP_SKILL)
    for name in ['README.md', 'README.en.md']:
        text = files[name].decode()
        # People read the top; Claude Code is pointed from the top to its own section at the end.
        if ('\n## If you are Claude Code' not in text or 'If you are Claude Code' not in text[:600]
                or SETUP_SKILL not in text or 'git clone ' + REPO_URL not in text):
            raise ValueError(name + ' needs the "If you are Claude Code" install section and a pointer to it at the top')
    # Updates come from this fork's main branch (ruling R46); nothing shipped may send an owner to
    # the upstream releases, which would replace this studio with Matt Paige's English one.
    upstream = [name for name, data in files.items()
                if UPSTREAM_RELEASES.encode() in data]
    if upstream:
        raise ValueError('Shipped files still point updates at the upstream releases: ' + ', '.join(sorted(upstream)))
    # Plain current-version labels that new users and assistants read first.
    number = r'(\d+\.\d+\.\d+(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?)'
    for name, label in [('STATUS.md', r'^# AI Video Studio — '), ('BRIEF.md', r'Current release:\s*'), ('PROJECT_CONTEXT.md', r'version \*\*')]:
        if re.findall(label + number, files[name].decode(), re.M) != [version]:
            raise ValueError('Wrong current version label in ' + name)
    catalog = data('style-library/catalog.example.json')
    projects = data('style-library/projects.example.json')
    if catalog.get('entries') != [] or catalog.get('techniques') != [] or catalog.get('removed_references'):
        raise ValueError('Starter reference/technique seeds contain owner data.')
    if projects.get('projects') != []:
        raise ValueError('Starter project seed contains owner data.')
    return version


def check_exact_tree(names, files, internal):
    """R44: every git-tracked path (`names`) must be exactly one of -- the release
    allowlist (`files`, release-files.txt) or the internal-only allowlist (`internal`,
    release-internal.txt) -- never neither (an undeclared tracked file) and never both
    (a path that would be both shipped and internal-only at once)."""
    files = set(files)
    overlap = internal & files
    if overlap:
        raise ValueError('Internal-only path(s) also listed in release-files.txt: ' + repr(sorted(overlap)))
    names = set(names)
    expected = files | internal
    if names != expected:
        raise ValueError('Git tree differs from source allowlist: ' + repr(sorted(names ^ expected)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--git-ref', help='Also require this committed tree to equal the reviewed source.')
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location('release_export', ROOT / 'scripts/export_release.py')
    export = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(export)
    files = dict(export.sources())
    version = verify(files)
    if args.git_ref:
        commit = subprocess.check_output(['git', 'rev-parse', '--verify', args.git_ref + '^{commit}'], cwd=ROOT, text=True).strip()
        names = subprocess.check_output(['git', 'ls-tree', '-r', '--name-only', commit], cwd=ROOT, text=True).splitlines()
        check_exact_tree(names, files, export.internal_paths())
        for name, expected in files.items():
            actual = subprocess.check_output(['git', 'show', commit + ':' + name], cwd=ROOT)
            if actual != expected:
                raise ValueError('Committed content differs: ' + name)
    print(json.dumps({'version': version, 'source_files': len(files), 'empty_seeds': True,
                      'git_ref_checked': args.git_ref, 'read_only': True}))


if __name__ == '__main__':
    main()
