"""Synthetic reference handoffs; no owner's catalog or source material is needed."""
import json
import threading
import unittest
from unittest.mock import patch
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from http.server import ThreadingHTTPServer
import library
from serve import Handler

ENTRY={'id':'demo-style','title':'Demo style','subtitle':'Synthetic reference','creator':'Demo creator','collection':'reference','version':'V01','summary':'A sample','traits':{'Typography':'Bold'},'keep':['Readability'],'avoid':['Clutter'],'moments':[],'notes':[],'evidence':'Synthetic fixture','source_url':'https://example.com/demo','media_path':'references/demo/video.mp4'}
TECH={'id':'tech-demo','title':'Card entrance','summary':'Reveal a card','direction':'Keep it clear','default_example':'demo-window','keep':['Readable'],'avoid':['Clutter'],'evidence':'Synthetic','examples':[{'id':'demo-window','style_id':'demo-style','label':'Demo window','source_version':'V01','source_path':ENTRY['media_path'],'start':1,'end':3}]}

class ContextTests(unittest.TestCase):
    def setUp(self):
        self.p=patch.object(library,'catalog',return_value={'entries':[ENTRY],'techniques':[TECH]});self.p.start()
    def tearDown(self):self.p.stop()
    def test_short_exact_example_and_notes(self):
        text=library.context_handoff(['demo-style','tech-demo@demo-window'],{'tech-demo@demo-window':{'borrow':'Use my own footage.','focus':'1–3 seconds'}},base_url='http://localhost:4999')
        for item in ['#style=demo-style','#technique=tech-demo&example=demo-window','Use my own footage.','1–3 seconds']:self.assertIn(item,text)
        for item in ['projects/','references/demo','Typography:','Registry:']:self.assertNotIn(item,text)
        self.assertEqual(sum(l.startswith('http://') for l in text.splitlines()),2)
    def test_plain_is_only_name_and_link(self):
        text=library.context_handoff(['demo-style'],base_url='http://localhost:4999')
        self.assertEqual(len([l for l in text.splitlines() if l]),3)
        self.assertNotIn(ENTRY['source_url'],text)
    def test_detailed_is_opt_in(self):
        self.assertIn('Typography: Bold',library.context_handoff(['demo-style'],mode='detailed'))
    def test_bad_inputs(self):
        for ids,notes,mode in [([],{},'short'),(['missing'],{},'short'),(['demo-style@x'],{},'short'),(['tech-demo@missing'],{},'short'),(['demo-style'],{'other':{}},'short'),(['demo-style'],{'demo-style':{'borrow':'x'*1001}},'short'),(['demo-style'],{},'unknown')]:
            with self.subTest(ids=ids,mode=mode),self.assertRaises((KeyError,ValueError)):library.context_handoff(ids,notes,mode)
    def test_api_stateless_and_same_origin(self):
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler);t=threading.Thread(target=server.serve_forever,daemon=True);t.start();base=f'http://127.0.0.1:{server.server_port}'
        try:
            data=json.dumps({'ids':['demo-style']}).encode()
            with urlopen(Request(base+'/context',data,{'Origin':base,'Content-Type':'application/json'})) as r:self.assertIn(base+'/#style=demo-style',r.read().decode())
            for origin in [None,'https://example.com']:
                headers={'Content-Type':'application/json'}
                if origin:headers['Origin']=origin
                with self.assertRaises(HTTPError) as e:urlopen(Request(base+'/context',data,headers))
                self.assertEqual(e.exception.code,403)
        finally:server.shutdown();server.server_close();t.join()
