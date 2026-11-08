"""Compare installed application files with a published release manifest (read-only).

Answers "is this studio really up to date?" from file contents rather than the
version label. Only files listed in the release manifest are hashed; owner
projects, media, libraries and settings are never read or changed.

  python3 scripts/check_install.py                      # installed version's official manifest
  python3 scripts/check_install.py --tag v0.1.0-beta.4  # another published release
  python3 scripts/check_install.py --manifest path/to/ai-video-studio-0.1.0-beta.4.manifest.json
  python3 scripts/check_install.py --root ../my-studio  # check another installation
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
# This fork's own published release manifests. Not part of the update flow any more:
# updates follow the main branch (docs/UPDATING.md). Kept for manual checks.
RELEASES = 'https://github.com/asaf5767/claude-video-studio/releases/download/'
VERSION = re.compile(r'\d+\.\d+\.\d+(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?')
LIMIT = 2 * 1024 * 1024


def installed_version(root):
    found = re.findall(r'<meta name="studio-version" content="([^"]+)"', (root / 'style-library/dist/index.html').read_text(encoding='utf-8'))
    if len(found) != 1:
        raise ValueError('Installed interface version not found')
    return found[0]


def default_tag(label):
    # A +local/+ux suffix marks local customizations of that published release.
    return 'v' + label.split('+')[0]


def manifest_url(tag):
    if not tag.startswith('v') or not VERSION.fullmatch(tag[1:]):
        raise ValueError('Use a numbered release tag such as v0.1.0-beta.4')
    return f'{RELEASES}{tag}/ai-video-studio-{tag[1:]}.manifest.json'


def load_manifest(source):
    if source.startswith(('http://', 'https://')):
        if not source.startswith(RELEASES):
            raise ValueError('Only official release manifests are fetched')
        with urllib.request.urlopen(source, timeout=10) as response:
            data = response.read(LIMIT + 1)
        if len(data) > LIMIT:
            raise ValueError('Manifest is unexpectedly large')
    else:
        data = Path(source).read_bytes()
    manifest = json.loads(data)
    files = manifest.get('files') if isinstance(manifest, dict) else None
    if not isinstance(files, list) or not files:
        raise ValueError('Manifest lists no files')
    for item in files:
        path = item.get('path') if isinstance(item, dict) else None
        if (not isinstance(path, str) or Path(path).is_absolute() or '..' in Path(path).parts or
                not re.fullmatch(r'[0-9a-f]{64}', str(item.get('sha256')))):
            raise ValueError('Unsafe or malformed manifest entry')
    return manifest


def compare(root, manifest):
    root = root.resolve()
    result = {'identical': [], 'modified': [], 'missing': []}
    for item in manifest['files']:
        target = root / item['path']
        if target.is_symlink() or not target.is_file() or not target.resolve().is_relative_to(root):
            result['missing'].append(item['path'])
            continue
        with target.open('rb') as f:
            digest = hashlib.file_digest(f, 'sha256').hexdigest()
        result['identical' if digest == item['sha256'] else 'modified'].append(item['path'])
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--root', type=Path, default=ROOT, help='installation to check (default: this one)')
    source = parser.add_mutually_exclusive_group()
    source.add_argument('--tag', help='published release tag, such as v0.1.0-beta.4')
    source.add_argument('--manifest', help='local release manifest JSON')
    parser.add_argument('--json', action='store_true', help='print a machine-readable report')
    args = parser.parse_args()
    try:
        label = installed_version(args.root)
        manifest = load_manifest(args.manifest or manifest_url(args.tag or default_tag(label)))
        result = compare(args.root, manifest)
    except (OSError, ValueError) as error:
        parser.exit(2, f'check_install: {error}\n')
    report = {'installed_label': label, 'compared_with': manifest.get('candidate', 'manifest'), 'files': len(manifest['files']),
              **{key: len(value) for key, value in result.items()}, 'modified_files': result['modified'], 'missing_files': result['missing']}
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"Installed label: {label}\nCompared with: {report['compared_with']} ({report['files']} application files)")
        print(f"  identical {report['identical']} · modified {report['modified']} · missing {report['missing']}")
        if result['modified']:
            print('Modified: local customizations or older copies to reconcile during an update.')
            print(''.join(f'  {name}\n' for name in result['modified']), end='')
        if result['missing']:
            print('Missing: part of that release but absent here.')
            print(''.join(f'  {name}\n' for name in result['missing']), end='')
        if not result['modified'] and not result['missing']:
            print('Every application file matches that release.')
    return 0 if not result['modified'] and not result['missing'] else 1


if __name__ == '__main__':
    sys.exit(main())
