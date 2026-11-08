"""Build a reviewed, exact allowlist export. Never uses git add, pushes or publishes."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import zipfile

ROOT=Path(__file__).resolve().parents[1]
PRIVATE={'projects','references','runtime','releases','node_modules','.venv','.git'}
SECRETS=[re.compile(r'(?<![A-Za-z0-9])sk-[A-Za-z0-9_-]{24,}'),re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),re.compile(r'gh[pousr]_[A-Za-z0-9]{30,}')]
# Exact repo paths for our own generated art (Task 11's built-in-look poster frames,
# rendered deterministically from the committed sample.html via headless Chrome -- no
# owner data, nothing personal) plus the owner-supplied, owner-cleared presenter cutout
# used across those same look previews (see THIRD_PARTY_NOTICES.md). Everything else
# stays on the binary blocklist below.
CLEARED_BINARIES={'looks/soft/sample.jpg','looks/collage/sample.jpg','looks/signature/sample.jpg','looks/headline/sample.jpg',
                   'looks/_presenter/presenter-cutout.png','style-library/dist/assets/brand/presenter-cutout.png',
                   # README screenshots of the studio itself (demo project)
                   'docs/screenshots/01-home.png','docs/screenshots/02-materials-and-choices.png','docs/screenshots/03-effects.png','docs/screenshots/04-presenter-looks.png','docs/screenshots/05-send-to-claude.png','docs/screenshots/06-storyboard-review.png','docs/screenshots/07-inspiration.png'}

def internal_paths():
    """R44: exact paths (release-internal.txt, one per line, '#' comments allowed -- no
    globs) that the private repo tracks in git but this exporter must never read or ship.
    check_release.py --git-ref treats a tracked file listed here as expected, neither
    missing from nor extra against release-files.txt."""
    path=ROOT/'release-internal.txt'
    if not path.is_file():return set()
    names=set()
    for line in path.read_text(encoding='utf-8').splitlines():
        line=line.strip()
        if not line or line.startswith('#'):continue
        if any(ch in line for ch in '*?[]') or Path(line).is_absolute() or '..' in Path(line).parts:
            raise ValueError('release-internal.txt needs exact paths, no globs: '+line)
        names.add(line)
    return names

def sources():
    rows=[]
    internal=internal_paths()
    for name in (ROOT/'release-files.txt').read_text(encoding='utf-8').splitlines():
        if not name or name.startswith('#'):continue
        if name in internal:raise ValueError('Internal-only path (release-internal.txt) also listed in release-files.txt: '+name)
        p=Path(name)
        if (p.is_absolute() or '..' in p.parts or any(part.startswith('.env') for part in p.parts) or p.suffix in {'.pem','.key','.p12','.pfx'} or name.startswith('style-library/dist/assets/reference-previews/') or name in {'style-library/catalog.json','style-library/projects.json','style-library/settings.json','style-library/reference-notes.json','style-library/writing-voice.json'} or
            (p.parts[0] in PRIVATE and name not in {'projects/README.md','references/README.md'}) or
            (len(p.parts)>1 and p.parts[:2] in {('style-library','runtime'),('style-library','references')}) or
            # .claude/ holds local Claude settings (permissions, env); only the studio's project skills ship.
            (p.parts[0]=='.claude' and p.parts[:2]!=('.claude','skills'))):raise ValueError('Private or unsafe release path: '+name)
        root=ROOT.resolve()
        target=root/p
        if (not target.is_file() or not target.resolve().is_relative_to(root) or
                any((root/Path(*p.parts[:i])).is_symlink() for i in range(1,len(p.parts)+1))):raise ValueError('Missing or symlinked release file: '+name)
        data=target.read_bytes()
        if target.suffix in {'.mp4','.mov','.wav','.mp3','.zip','.jpg','.png','.webp'} and name not in CLEARED_BINARIES:raise ValueError('Uncleared binary in source export: '+name)
        if target.suffix not in {'.woff2','.woff'} and name not in CLEARED_BINARIES:  # bundled OFL fonts and our own cleared art are the only binaries
            text=data.decode('utf-8')
            if any(pattern.search(text) for pattern in SECRETS):raise ValueError('Credential candidate; inspect '+name)
            if re.search(r'(?:/Users|/home)/[A-Za-z0-9_.-]+/',text) or re.search(r'[A-Z]:\\Users\\[^\\]+\\',text):raise ValueError('Personal absolute path; inspect '+name)
        rows.append((name,data))
    if len(rows)!=len({name for name,_ in rows}):raise ValueError('Duplicate allowlist path')
    return rows

def main():
    version=json.loads((ROOT/'package.json').read_text(encoding='utf-8'))['version']
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--name',default='ai-video-studio-'+version);args=parser.parse_args()
    if not re.fullmatch(r'[a-z0-9][a-z0-9.-]*',args.name):raise SystemExit('Use a safe lowercase release name')
    rows=sources();out=ROOT/'releases';out.mkdir(exist_ok=True);archive=out/(args.name+'.zip')
    if archive.exists():raise SystemExit('Export already exists. Use a new --name to preserve it.')
    manifest={'candidate':args.name,'files':[{'path':n,'bytes':len(d),'sha256':hashlib.sha256(d).hexdigest()} for n,d in rows],
              'scan':{'credential_candidates':0,'personal_absolute_paths':0,'method':'Heuristic text patterns plus explicit source allowlist; not a full security guarantee'},
              'publication':'Source archive only; exporter does not publish. Public pilot and validation scope are documented in docs/RELEASE.md.'}
    with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED) as z:
        for name,data in rows:z.writestr(args.name+'/'+name,data)
        z.writestr(args.name+'/RELEASE-MANIFEST.json',json.dumps(manifest,indent=2)+'\n')
    archive.with_suffix('.manifest.json').write_text(json.dumps(manifest,indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'archive':str(archive),'files':len(rows),'sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'published':False}))

if __name__=='__main__':main()
