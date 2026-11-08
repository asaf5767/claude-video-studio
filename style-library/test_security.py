"""Regression tests for former legacy-route release gaps, using disposable fixtures."""
import copy
import http.client
from http.server import ThreadingHTTPServer
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import serve
from security import registered_file,MEDIA

class Quiet(serve.Handler):
    def log_message(self,*args):pass

class SecurityTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.folder=self.root/'references/demo';self.folder.mkdir(parents=True)
        (self.folder/'video.mp4').write_bytes(b'0123456789');(self.folder/'note.md').write_text('Synthetic note', encoding='utf-8')
        self.e={'id':'demo','media_path':'references/demo/video.mp4','notes':['references/demo/note.md'],'asset_type':'carousel','slides':[{'path':'references/demo/video.mp4'}],'archive_path':'references/demo/package.zip'}
        (self.folder/'package.zip').write_bytes(b'zip fixture')
        self.patches=[patch.object(serve,'STUDIO',self.root),patch.object(serve,'entry_map',side_effect=lambda:{'demo':self.e})]
        for p in self.patches:p.start()
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Quiet);self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join()
        for p in self.patches:p.stop()
        self.tmp.cleanup()
    def request(self,path,method='HEAD',headers=None):
        c=http.client.HTTPConnection('127.0.0.1',self.server.server_port);c.request(method,path,headers=headers or {});r=c.getresponse();result=(r.status,dict(r.getheaders()),r.read());c.close();return result
    def test_all_get_routes_reject_untrusted_headers(self):
        for path in ['/','/api/health','/catalog.json','/site-settings.json','/brief?ids=demo','/media/demo','/notes/demo/0','/slides/demo/0','/download/demo','/projects.json']:
            for headers in [{'Host':'attacker.invalid'},{'Origin':'https://attacker.invalid'},{'Sec-Fetch-Site':'cross-site'}]:
                with self.subTest(path=path,headers=headers):self.assertEqual(self.request(path,headers=headers)[0],403)
    def test_numeric_indices_have_exact_shape(self):
        for route in ['notes','slides']:
            self.assertEqual(self.request(f'/{route}/demo/0')[0],200)
            for suffix in ['-1','01','1','0/extra','+0']:
                self.assertEqual(self.request(f'/{route}/demo/{suffix}')[0],404)
    def test_absolute_parent_and_symlink_escape_are_blocked(self):
        outside=self.root/'outside.mp4';outside.write_bytes(b'outside')
        (self.folder/'escape.mp4').symlink_to(outside)
        for value in [str(outside),'references/demo/../../outside.mp4','references/demo/escape.mp4']:
            self.e['media_path']=value
            self.assertEqual(self.request('/media/demo')[0],404,value)
    def test_notes_and_archive_are_confined_too(self):
        outside=self.root/'outside.md';outside.write_text('outside', encoding='utf-8')
        self.e['notes']=[str(outside)];self.e['archive_path']=str(outside)
        self.assertEqual(self.request('/notes/demo/0')[0],404)
        self.assertEqual(self.request('/download/demo')[0],404)
    def test_safe_range_and_headers(self):
        status,headers,body=self.request('/media/demo','GET',{'Range':'bytes=2-4'})
        self.assertEqual((status,body),(206,b'234'))
        self.assertEqual(headers['X-Content-Type-Options'],'nosniff')
        self.assertIn("frame-ancestors 'none'",headers['Content-Security-Policy'])
        self.assertEqual(self.request('/media/demo',headers={'Range':'bytes=100-'})[0],416)
    def test_collection_root_symlink_is_blocked(self):
        other=self.root/'other';other.mkdir();(other/'x.mp4').write_bytes(b'x')
        (self.root/'projects').symlink_to(other,target_is_directory=True)
        with self.assertRaises(ValueError):registered_file(self.root,'projects/demo/x.mp4',MEDIA)
