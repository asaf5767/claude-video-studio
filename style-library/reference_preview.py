"""Best-effort public cover images. Never fetch video, log in, or change analysis."""
import hashlib
import http.client
import ipaddress
import json
import socket
import ssl
import time
import uuid
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse
from pathlib import Path
import project_index as index
import review_actions as storage
import reference_intake as intake

HTML_LIMIT=3*1024*1024
IMAGE_LIMIT=3*1024*1024

class PreviewError(intake.IntakeError):pass

class Metadata(HTMLParser):
    def __init__(self):super().__init__();self.images=[]
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if tag.lower()=='meta' and (a.get('property') or a.get('name') or '').lower() in {'og:image','og:image:secure_url','twitter:image','twitter:image:src'}:
            if a.get('content'):self.images.append(a['content'])

def addresses(host):
    values=list(dict.fromkeys(a[4][0] for a in socket.getaddrinfo(host,443,type=socket.SOCK_STREAM)))
    if not values or any(not ipaddress.ip_address(a).is_global for a in values):raise PreviewError('A public preview image is unavailable.')
    return values

class PublicHTTPS(http.client.HTTPSConnection):
    def connect(self):
        # Pin the already-validated address; TLS still verifies the original hostname.
        self.sock=socket.create_connection((addresses(self.host)[0],443),self.timeout)
        self.sock=self._context.wrap_socket(self.sock,server_hostname=self.host)

def request(url,limit,deadline):
    clean=intake.source_url(url);p=urlparse(clean)
    if p.scheme!='https':raise PreviewError('A public HTTPS preview image is unavailable.')
    remaining=deadline-time.monotonic()
    if remaining<=0:raise PreviewError('The source did not provide a preview image in time.')
    conn=PublicHTTPS(p.hostname,timeout=min(3,remaining),context=ssl.create_default_context())
    try:
        conn.request('GET',p.path+(';' + p.params if p.params else '')+('?' + p.query if p.query else ''),headers={'User-Agent':'AI-Video-Studio/1.0 (public cover image)','Accept':'text/html,image/jpeg,image/png,image/webp,image/gif','Accept-Encoding':'identity'})
        response=conn.getresponse();status=response.status
        if status in {301,302,303,307,308}:return status,response.getheader('Location',''),b''
        if status!=200:raise PreviewError('The source did not provide a public preview image.')
        if response.getheader('Content-Encoding','identity').lower()!='identity':raise PreviewError('The source did not provide a usable preview image.')
        size=response.getheader('Content-Length')
        if size and int(size)>limit:raise PreviewError('The preview response is too large.')
        chunks=[];total=0
        while True:
            remaining=deadline-time.monotonic()
            if remaining<=0:raise PreviewError('The preview request timed out.')
            if conn.sock:conn.sock.settimeout(min(3,remaining))
            chunk=response.read1(min(32768,limit+1-total))
            if not chunk:break
            total+=len(chunk)
            if total>limit:raise PreviewError('The preview response is too large.')
            chunks.append(chunk)
        return status,response.getheader('Content-Type','').split(';')[0].strip().lower(),b''.join(chunks)
    finally:conn.close()

def fetch(url,limit,deadline):
    for _ in range(4):
        status,kind,data=request(url,limit,deadline)
        if status==200:return url,kind,data
        url=urljoin(url,kind)
    raise PreviewError('The source redirected too many times.')

def image_extension(kind,data):
    if kind=='image/jpeg' and data.startswith(b'\xff\xd8\xff'):return '.jpg'
    if kind=='image/png' and data.startswith(b'\x89PNG\r\n\x1a\n'):return '.png'
    if kind=='image/webp' and data[:4]==b'RIFF' and data[8:12]==b'WEBP':return '.webp'
    if kind=='image/gif' and data[:6] in {b'GIF87a',b'GIF89a'}:return '.gif'
    raise PreviewError('The source did not provide a supported cover image.')

def retrieve(url):
    deadline=time.monotonic()+12
    page,kind,html=fetch(url,HTML_LIMIT,deadline)
    if intake.key(page)!=intake.key(url):raise PreviewError('The source redirected away from this reference; no cover was saved.')
    if kind not in {'text/html','application/xhtml+xml'}:raise PreviewError('The source did not provide a public cover image.')
    parser=Metadata();parser.feed(html.decode('utf-8',errors='replace'))
    if not parser.images:raise PreviewError('No public cover image was available. Your reference is saved.')
    # Only the page's declared image. No embeds, scripts, video URLs or guessed private endpoints.
    image_url=urljoin(page,parser.images[0]);_,kind,data=fetch(image_url,IMAGE_LIMIT,deadline)
    return data,image_extension(kind,data),image_url

def save(body):
    if not isinstance(body,dict) or set(body)!={'id'} or not isinstance(body['id'],str) or not index.TOKEN.fullmatch(body['id']):raise PreviewError('Choose a saved reference.')
    with index.STATE_LOCK:
        storage.check_storage();before,catalog=intake.read_catalog()
        entry=next((e for e in catalog['entries'] if e.get('id')==body['id']),None)
        if not entry or not intake.editable(entry):raise PreviewError('Choose a creator reference.',404)
        if entry.get('media_path') or entry.get('poster')!='assets/link-reference.svg':return {'id':entry['id'],'available':True,'changed':False}
        revision=intake.revision(entry);url=entry['source_url']
    try:data,extension,image_url=retrieve(url)
    except (OSError,ValueError,http.client.HTTPException,intake.IntakeError):return {'id':body['id'],'available':False,'changed':False,'message':'No public cover image was available. Your link and notes are saved.'}
    with index.STATE_LOCK:
        storage.check_storage();before,catalog=intake.read_catalog()
        entry=next((e for e in catalog['entries'] if e.get('id')==body['id']),None)
        if not entry or intake.revision(entry)!=revision:raise PreviewError('This reference changed. Refresh before getting its preview.',409)
        for journal in storage.JOURNALS.glob('*/transaction.json'):
            if json.loads(journal.read_text(encoding='utf-8')).get('state')=='prepared':raise PreviewError('An earlier save needs recovery first.',503)
        base=storage.BASE.resolve();folder=base/'dist/assets/reference-previews'
        if any((base/p).resolve()!=base/p for p in ['dist','dist/assets','dist/assets/reference-previews']):raise PreviewError('The preview folder needs repair.',503)
        folder.mkdir(exist_ok=True)
        name=hashlib.sha256(data).hexdigest()+extension;target=folder/name
        if target.is_symlink():raise PreviewError('The preview path needs repair.',503)
        entry['poster']='assets/reference-previews/'+name
        entry['preview_image']={'source_url':image_url,'sha256':hashlib.sha256(data).hexdigest(),'kind':'public_cover'}
        changes={target:data,intake.CATALOG.resolve():storage.json_bytes(catalog)}
        expected={target:index.digest(target) if target.exists() else None,intake.CATALOG.resolve():hashlib.sha256(before).hexdigest()}
        storage.commit(changes,{'request_id':str(uuid.uuid4()),'operation':'save-reference-cover','reference_id':entry['id']},expected)
        return {'id':entry['id'],'available':True,'changed':True}
