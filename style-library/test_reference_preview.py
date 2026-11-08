"""Public thumbnail retrieval is bounded and never changes analysis or existing sources."""
import hashlib
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
import reference_preview as preview
import reference_intake as intake
import review_actions as storage
import project_index as index

class PreviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name).resolve();self.base=self.root/'style-library';(self.base/'dist/assets').mkdir(parents=True)
        self.catalog=self.base/'catalog.json';self.entry={'id':'sample','collection':'reference','source_url':'https://example.com/video','analysis_status':'partial','reference_note':'The cards I like','poster':'assets/link-reference.svg','title':'Sample'}
        self.catalog.write_text(json.dumps({'entries':[self.entry],'techniques':[],'removed_references':{'sample':{'removed_at':'2026-10-27T00:00:00Z'}}}), encoding='utf-8')
        self.patches=[patch.object(index,'STUDIO',self.root),patch.object(index,'REGISTRY',self.base/'projects.json'),patch.object(storage,'BASE',self.base),patch.object(storage,'CATALOG',self.catalog),patch.object(storage,'JOURNALS',self.base/'runtime/review-actions'),patch.object(intake,'CATALOG',self.catalog)]
        for p in self.patches:p.start()
        self.image=b'\x89PNG\r\n\x1a\nfixture'
    def tearDown(self):
        for p in self.patches:p.stop()
        self.tmp.cleanup()
    def test_public_cover_changes_only_image_metadata(self):
        with patch.object(preview,'retrieve',return_value=(self.image,'.png','https://cdn.example.com/cover.png')):result=preview.save({'id':'sample'})
        data=json.loads(self.catalog.read_text(encoding='utf-8'));entry=data['entries'][0]
        self.assertTrue(result['available']);self.assertEqual(entry['analysis_status'],'partial');self.assertEqual(entry['reference_note'],self.entry['reference_note']);self.assertEqual(data['removed_references']['sample']['removed_at'],'2026-10-27T00:00:00Z')
        self.assertEqual((self.base/'dist'/entry['poster']).read_bytes(),self.image)
    def test_missing_cover_keeps_catalog_byte_for_byte(self):
        before=self.catalog.read_bytes()
        with patch.object(preview,'retrieve',side_effect=preview.PreviewError('Unavailable')):self.assertFalse(preview.save({'id':'sample'})['available'])
        self.assertEqual(before,self.catalog.read_bytes())
    def test_existing_image_or_media_is_never_replaced(self):
        entry={**self.entry,'poster':'assets/real.jpg'};self.catalog.write_text(json.dumps({'entries':[entry]}), encoding='utf-8')
        with patch.object(preview,'retrieve') as get:self.assertFalse(preview.save({'id':'sample'})['changed']);get.assert_not_called()
    def test_concurrent_entry_edit_is_preserved(self):
        def change(url):
            data=json.loads(self.catalog.read_text(encoding='utf-8'));data['entries'][0]['reference_note']='New owner note';self.catalog.write_text(json.dumps(data), encoding='utf-8');return self.image,'.png','https://cdn.example.com/cover.png'
        with patch.object(preview,'retrieve',side_effect=change),self.assertRaises(preview.PreviewError) as error:preview.save({'id':'sample'})
        self.assertEqual(error.exception.status,409);self.assertEqual(json.loads(self.catalog.read_text(encoding='utf-8'))['entries'][0]['reference_note'],'New owner note')
    def test_nonpublic_dns_and_unsafe_urls_are_rejected(self):
        for address in ['127.0.0.1','10.0.0.1','169.254.169.254','::1','::ffff:127.0.0.1']:
            with patch.object(preview.socket,'getaddrinfo',return_value=[(2,1,6,'',(address,443))]),self.assertRaises(preview.PreviewError):preview.addresses('example.com')
        for url in ['http://example.com/x','https://user:password@example.com/x','https://example.com:8443/x']:
            with self.assertRaises(intake.IntakeError):preview.request(url,100,time.monotonic()+5)
    def test_metadata_is_not_script_execution_and_redirects_are_bounded(self):
        html=b'<script>ignore()</script><meta property="og:image" content="/cover.png">'
        with patch.object(preview,'request',side_effect=[(200,'text/html',html),(200,'image/png',self.image)]) as req:
            data,ext,url=preview.retrieve('https://example.com/watch');self.assertEqual(ext,'.png');self.assertEqual(url,'https://example.com/cover.png');self.assertEqual(req.call_count,2)
        with patch.object(preview,'request',return_value=(302,'/loop',b'')) as req,self.assertRaises(preview.PreviewError):preview.fetch('https://example.com',100,time.monotonic()+5)
        self.assertEqual(req.call_count,4)
        with self.assertRaises(preview.PreviewError):preview.image_extension('image/svg+xml',b'<svg/>')
    def test_large_social_page_cover_is_read_with_the_bounded_transport(self):
        html=b'<html><head>'+b' '*821539+b'<meta property="og:image" content="/cover.png"></head></html>'
        class Response:
            status=200
            def __init__(self,kind,data):self.kind=kind;self.data=data;self.offset=0
            def getheader(self,key,default=None):return {'Content-Type':self.kind,'Content-Length':str(len(self.data))}.get(key,default)
            def read1(self,size):part=self.data[self.offset:self.offset+size];self.offset+=len(part);return part
        replies=iter([Response('text/html',html),Response('image/png',self.image)])
        class Connection:
            sock=None
            def __init__(self,*args,**kwargs):pass
            def request(self,*args,**kwargs):pass
            def getresponse(self):return next(replies)
            def close(self):pass
        with patch.object(preview,'PublicHTTPS',Connection):
            data,ext,url=preview.retrieve('https://example.com/watch')
        self.assertGreater(len(html),524288);self.assertEqual(data,self.image);self.assertEqual(ext,'.png');self.assertEqual(url,'https://example.com/cover.png')
    def test_transport_still_rejects_oversized_pages_and_streams(self):
        class Response:
            status=200
            def getheader(self,key,default=None):return {'Content-Type':'text/html','Content-Length':str(preview.HTML_LIMIT+1)}.get(key,default)
            def read1(self,size):raise AssertionError('Oversized declared responses must not be read')
        class Connection:
            sock=None
            def __init__(self,*args,**kwargs):pass
            def request(self,*args,**kwargs):pass
            def getresponse(self):return Response()
            def close(self):pass
        with patch.object(preview,'PublicHTTPS',Connection),self.assertRaises(preview.PreviewError):preview.retrieve('https://example.com/watch')
        class Stream(Response):
            def getheader(self,key,default=None):return 'text/html' if key=='Content-Type' else default
            def read1(self,size):return b'x'*size
        with patch.object(preview,'PublicHTTPS',Connection),patch.object(Connection,'getresponse',return_value=Stream()),self.assertRaises(preview.PreviewError):preview.request('https://example.com/watch',100,time.monotonic()+2)
    def test_symlinked_storage_and_invalid_body_cannot_write(self):
        (self.base/'dist/assets/reference-previews').symlink_to(self.root,target_is_directory=True)
        with patch.object(preview,'retrieve',return_value=(self.image,'.png','https://cdn.example.com/a.png')),self.assertRaises(preview.PreviewError):preview.save({'id':'sample'})
        for body in [{},{'id':'../sample'},{'id':'sample','url':'https://other.example.com'}]:
            with self.assertRaises(preview.PreviewError):preview.save(body)

class EndpointGuardsTests(unittest.TestCase):
    def test_new_actions_require_same_origin_and_explicit_headers(self):
        import http.client
        from http.server import ThreadingHTTPServer
        import threading
        import serve
        class Quiet(serve.Handler):
            def log_message(self,*args):pass
        server=ThreadingHTTPServer(('127.0.0.1',0),Quiet);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();host='127.0.0.1:'+str(server.server_port)
        def request(path,method='POST',headers=None):
            c=http.client.HTTPConnection('127.0.0.1',server.server_port)
            c.request(method,path,body='{}' if method=='POST' else None,headers=headers or {});r=c.getresponse();status=r.status;r.read();c.close();return status
        try:
            for path,action,name in [('/reference-preview','reference-preview','save_reference_preview'),('/open-editor','open-editor','open_editor')]:
                with patch.object(serve,name,return_value={'ok':True}) as handler:
                    self.assertEqual(request(path,headers={'Content-Type':'application/json','X-Studio-Action':action}),403)
                    base={'Origin':'http://'+host,'Content-Type':'application/json','X-Studio-Action':action}
                    self.assertEqual(request(path,headers={**base,'Origin':'https://other.example'}),403)
                    self.assertEqual(request(path,headers={**base,'X-Studio-Action':'wrong'}),403)
                    handler.assert_not_called();self.assertEqual(request(path,headers=base),200);handler.assert_called_once()
            with patch.object(serve,'project_tools_state',return_value={'editor':None}) as read,patch.object(serve,'open_editor') as launch:
                self.assertEqual(request('/project-tools?project=demo&artifact=v02',method='GET'),200);read.assert_called_once_with('demo','v02');launch.assert_not_called()
                self.assertEqual(request('/project-tools?project=demo&artifact=v02&artifact=v03',method='GET'),400)
        finally:server.shutdown();server.server_close();thread.join()
