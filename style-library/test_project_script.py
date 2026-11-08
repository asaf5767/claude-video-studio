"""Versioned scripts and guarded saves use disposable projects only."""
from pathlib import Path
import http.client
import json
import tempfile
import threading
import unittest
import uuid
from unittest.mock import patch
from http.server import ThreadingHTTPServer
import project_index as index
import review_actions as storage
import project_script as scripts
from feedback import FeedbackError
from serve import Handler


class ScriptTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name).resolve();self.base=self.root/'style-library';self.base.mkdir()
        self.project=self.root/'projects/demo';self.project.mkdir(parents=True);(self.project/'exports').mkdir()
        (self.project/'script.txt').write_text('The script I recorded.\n', encoding='utf-8')
        (self.project/'exports/assembled-script-v04.txt').write_text('The selected words.', encoding='utf-8')
        self.registry=self.base/'projects.json';self.catalog=self.base/'catalog.json';self.catalog.write_text('{"entries":[]}', encoding='utf-8')
        self.registry.write_text(json.dumps({'projects':[{'id':'demo','title':'Demo video','artifacts':[{'id':'spoken-v04','type':'video','version':'V04','approval_kind':'spoken_cut','downloads':[]}]}]}), encoding='utf-8')
        self.patches=[patch.object(index,'STUDIO',self.root),patch.object(index,'REGISTRY',self.registry),patch.object(storage,'BASE',self.base),patch.object(storage,'CATALOG',self.catalog),patch.object(storage,'JOURNALS',self.base/'runtime/review-actions')]
        for p in self.patches:p.start()
    def tearDown(self):
        for p in reversed(self.patches):p.stop()
        self.tmp.cleanup()
    def body(self,text='Use the strongest complete take.'):
        return {'project_id':'demo','revision':scripts.current('demo')['revision'],'request_id':str(uuid.uuid4()),'text':text}
    def test_read_is_nonwriting_and_distinguishes_original_from_selected_words(self):
        before={p:p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        data=scripts.current('demo');self.assertIsNone(data['version_id']);self.assertEqual(data['text'],'The script I recorded.\n');self.assertEqual(data['assembled'],{'text':'The selected words.','version':'V04'})
        self.assertEqual({p:p.read_bytes() for p in self.root.rglob('*') if p.is_file()},before)
        with self.assertRaises(FeedbackError):scripts.current('demo','')
    def test_save_preserves_original_review_state_and_exact_older_versions(self):
        before=self.registry.read_bytes();body=self.body();first=scripts.save(body);second=scripts.save(self.body('A refined script.'))
        self.assertNotEqual(first['version_id'],second['version_id']);self.assertEqual(scripts.current('demo',first['version_id'])['text'],body['text'])
        self.assertTrue(scripts.save(body)['duplicate']);self.assertEqual(scripts.current('demo')['version_id'],second['version_id'])
        self.assertEqual((self.project/'script.txt').read_text(encoding='utf-8'),'The script I recorded.\n');self.assertEqual(self.registry.read_bytes(),before);self.assertFalse((self.project/'approval-state.json').exists())
    def test_stale_and_reused_requests_cannot_overwrite_a_later_save(self):
        body=self.body();scripts.save(self.body('New saved script.'));before=(self.project/'script-state.json').read_bytes()
        with self.assertRaisesRegex(FeedbackError,'changed elsewhere'):scripts.save(body)
        self.assertEqual((self.project/'script-state.json').read_bytes(),before)
        saved=self.body('One script.');scripts.save(saved)
        with self.assertRaisesRegex(FeedbackError,'already used'):scripts.save({**saved,'text':'Different content.'})
    def test_unsafe_corrupt_unknown_and_oversized_inputs_preserve_files(self):
        for body in [{**self.body(),'project_id':'../demo'},self.body('x'*50001),{**self.body(),'extra':True}]:
            with self.assertRaises(FeedbackError):scripts.save(body)
        state=self.project/'script-state.json';state.write_text('{"schema_version":1}', encoding='utf-8')
        with self.assertRaises(FeedbackError):scripts.current('demo')
        self.assertEqual(state.read_text(encoding='utf-8'),'{"schema_version":1}');state.unlink()
        outside=self.root/'outside.json';outside.write_text('keep', encoding='utf-8');state.symlink_to(outside)
        with self.assertRaises(storage.ReviewError):scripts.current('demo')
        self.assertEqual(outside.read_text(encoding='utf-8'),'keep')
    def test_external_change_at_commit_is_not_overwritten(self):
        body=self.body();real=storage.commit
        def changed(*args):
            (self.project/'script.txt').write_text('Changed by another chat.', encoding='utf-8');return real(*args)
        with patch.object(storage,'commit',side_effect=changed),self.assertRaisesRegex(storage.ReviewError,'changed while saving'):scripts.save(body)
        self.assertFalse((self.project/'script-state.json').exists());self.assertEqual((self.project/'script.txt').read_text(encoding='utf-8'),'Changed by another chat.')
    def test_http_requires_same_origin_explicit_action_and_bounded_json(self):
        class Quiet(Handler):
            def log_message(self,*args):pass
        server=ThreadingHTTPServer(('127.0.0.1',0),Quiet);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        origin=f'http://127.0.0.1:{server.server_port}'
        def request(method,headers,body=None):
            conn=http.client.HTTPConnection('127.0.0.1',server.server_port);conn.request(method,'/project-script?project=demo' if method=='GET' else '/project-script',body,headers);r=conn.getresponse();data=r.read();conn.close();return r.status,data
        try:
            self.assertEqual(request('GET',{'Origin':'https://elsewhere.test'})[0],403)
            self.assertEqual(request('GET',{})[0],200);self.assertFalse((self.project/'script-state.json').exists())
            body=json.dumps(self.body());headers={'Origin':origin,'Content-Type':'application/json'}
            self.assertEqual(request('POST',headers,body)[0],403)
            headers['X-Studio-Action']='project-script';self.assertEqual(request('POST',headers,body)[0],200)
            # No body is needed: an oversized declared length must fail before read.
            self.assertEqual(request('POST',{**headers,'Content-Length':'262145'},'')[0],413)
        finally:server.shutdown();server.server_close();thread.join()

if __name__=='__main__':unittest.main()
