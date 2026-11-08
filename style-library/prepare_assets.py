"""Create registered source-backed posters and evidence using bundled fonts."""
import hashlib
import json
from pathlib import Path
import subprocess
from library import BASE, STUDIO, catalog
from security import registered_file, MEDIA

def poster(source, relative, moment=None):
    out=(BASE/'dist'/relative).resolve()
    root=(BASE/'dist/assets').resolve()
    if root.parent != (BASE/'dist').resolve() or not out.is_relative_to(root) or out.suffix.lower() not in {'.jpg','.png','.webp'}:raise ValueError('Poster belongs under dist/assets')
    out.parent.mkdir(parents=True,exist_ok=True)
    if out.exists():return
    command=['ffmpeg','-nostdin','-v','error','-n']
    if moment is not None:command+=['-ss',str(moment)]
    subprocess.run(command+['-i',str(source),'-frames:v','1','-vf','scale=540:-2',str(out)],check=True)

def main():
    entries={e['id']:e for e in catalog()['entries']};evidence=[]
    for e in entries.values():
        if e.get('asset_type')=='carousel':
            for slide in e['slides']:poster(registered_file(STUDIO,slide['path'],MEDIA),slide['poster'],1 if slide['media_type']=='video' else None)
        elif e.get('media_path'):
            source=registered_file(STUDIO,e['media_path'],MEDIA)
            poster(source,e['poster'],e.get('poster_at',0))
            with source.open('rb') as f:digest=hashlib.file_digest(f,'sha256').hexdigest()
            evidence.append({'id':e['id'],'source_sha256':digest,'source':e['media_path'],'version':e['version']})
    for t in catalog().get('techniques',[]):
        for x in t['examples']:poster(registered_file(STUDIO,entries[x['style_id']]['media_path'],MEDIA),x['poster'],x['poster_at'])
    (BASE/'runtime').mkdir(exist_ok=True)
    (BASE/'runtime/source-evidence.json').write_text(json.dumps(evidence,indent=2)+'\n', encoding='utf-8')
    print(f'Prepared {len(evidence)} registered video sources. Fonts are already bundled with licenses.')

if __name__=='__main__':main()
