"""Reference creation/editing with disposable catalogs; no network or production writes."""
import copy
import hashlib
import http.client
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import reference_intake as intake
import review_actions as storage
import project_index as index
from serve import Handler

class Quiet(Handler):
    def log_message(self,*args):pass

class ReferenceTests(unittest.TestCase):
    def test_ui_reference_creation_date_survives_duplicate_intake_and_edits(self):
        from datetime import datetime
        saved=intake.save(self.body)
        entry=self.data()['entries'][0];created=entry['created_at']
        self.assertIsNotNone(datetime.fromisoformat(created).tzinfo)
        intake.save(self.body)
        state=intake.current(saved['id'])
        intake.save({'action':'edit','id':saved['id'],'revision':state['revision'],'title':'Updated','creator':'Demo Creator','note':'Keep the opening.'})
        self.assertEqual(len(self.data()['entries']),1)
        self.assertEqual(self.data()['entries'][0]['created_at'],created)

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name).resolve();self.base=self.root/'style-library';self.base.mkdir()
        self.catalog=self.base/'catalog.json';self.catalog.write_text(json.dumps({'schema_version':4,'entries':[],'techniques':[]}), encoding='utf-8')
        self.index=self.base/'projects.json';self.index.write_text('{"projects":[]}', encoding='utf-8')
        self.patches=[patch.object(index,'STUDIO',self.root),patch.object(index,'REGISTRY',self.index),patch.object(storage,'BASE',self.base),patch.object(storage,'CATALOG',self.catalog),patch.object(storage,'JOURNALS',self.base/'runtime/review-actions'),patch.object(intake,'CATALOG',self.catalog)]
        for p in self.patches:p.start()
        self.body={'action':'create','url':'https://www.instagram.com/reel/demo123/?utm_source=share','title':'An opening I like','creator':'Demo Creator','note':'The five cards arrive around the speaker.'}
    def tearDown(self):
        for p in self.patches:p.stop()
        self.tmp.cleanup()
    def data(self):return json.loads(self.catalog.read_text(encoding='utf-8'))
    def test_create_is_unanalyzed_and_does_not_fetch(self):
        result=intake.save(self.body);e=self.data()['entries'][0]
        self.assertTrue(result['saved']);self.assertEqual(e['id'],result['id']);self.assertEqual(e['analysis_status'],'not_analyzed')
        self.assertNotIn('media_path',e);self.assertEqual(e['source_url'],'https://www.instagram.com/reel/demo123/')
        self.assertEqual(e['reference_note'],self.body['note']);self.assertEqual(self.data()['techniques'],[])
        self.assertTrue(list((self.base/'runtime/review-actions').glob('*/before-0.data')))
    def test_tracking_and_platform_variants_are_duplicates_without_writes(self):
        first=intake.save(self.body);before=self.catalog.read_bytes()
        result=intake.save({**self.body,'url':'https://instagram.com/reels/demo123/?srtk=tracking','note':'Never overwrite the earlier note.'})
        self.assertEqual(first['id'],result['id']);self.assertTrue(result['duplicate']);self.assertEqual(self.catalog.read_bytes(),before)
        for a,b in [('https://youtu.be/abc','https://www.youtube.com/shorts/abc'),('https://www.tiktok.com/@someone/video/12345?_t=x','https://www.tiktok.com/@someone/video/12345?_r=y')]:self.assertEqual(intake.key(intake.source_url(a)),intake.key(intake.source_url(b)))
    def test_edit_keeps_analysis_source_and_techniques(self):
        result=intake.save(self.body);data=self.data();e=data['entries'][0];e.update(traits={'Motion':'Verified card reveal'},analysis_status='analyzed',moments=[{'time':1,'label':'Reveal'}],keep=['A steady hold'],media_path='references/demo/sample.mp4');data['techniques']=[{'id':'tech-unchanged','examples':[]}];self.catalog.write_text(json.dumps(data), encoding='utf-8')
        state=intake.current(result['id']);intake.save({'action':'edit','id':result['id'],'revision':state['revision'],'title':'A clearer title','creator':'Demo Creator','note':'Focus on the first card.'})
        edited=self.data()['entries'][0]
        for field in ['source_url','traits','analysis_status','moments','keep','media_path']:self.assertEqual(edited[field],e[field])
        self.assertEqual(self.data()['techniques'],data['techniques']);self.assertEqual(edited['title'],'A clearer title')
    def test_stale_edit_and_own_work_are_rejected(self):
        result=intake.save(self.body);state=intake.current(result['id']);update={'action':'edit','id':result['id'],'revision':state['revision'],'title':'Changed','creator':'Demo Creator','note':''}
        intake.save(update)
        with self.assertRaises(intake.IntakeError) as e:intake.save(update)
        self.assertEqual(e.exception.status,409)
        data=self.data();data['entries'][0]['collection']='mine';self.catalog.write_text(json.dumps(data), encoding='utf-8')
        with self.assertRaises(intake.IntakeError):intake.current(result['id'])
    def test_creator_names_are_canonical_and_blank_is_honest(self):
        intake.save(self.body);intake.save({**self.body,'url':'https://example.com/second','creator':'demo creator'})
        a,b=self.data()['entries'];self.assertEqual(a['creator_id'],b['creator_id']);self.assertEqual(a['creator'],b['creator'])
        result=intake.save({**self.body,'url':'https://example.com/third','creator':''});e=next(e for e in self.data()['entries'] if e['id']==result['id']);self.assertEqual(e['creator'],'Creator not added')
    def test_unsafe_urls_and_fields_rejected_without_writes(self):
        before=self.catalog.read_bytes()
        for url in ['javascript:alert(1)','file:///tmp/file','http://localhost/x','http://127.0.0.1/x','http://[::1]/x','https://example.com:8443/x','https://user:password@example.com/x','https://example.com/has space','https://example.local/x']:
            with self.subTest(url=url),self.assertRaises(intake.IntakeError):intake.save({**self.body,'url':url})
        for delta in [{'title':'x'*121},{'creator':False},{'note':'x'*1001},{'note':'bad\x00input'},{'action':'delete'},{'extra':'unexpected'}]:
            with self.subTest(delta=delta),self.assertRaises(intake.IntakeError):intake.save({**self.body,**delta})
        self.assertEqual(self.catalog.read_bytes(),before)
    def test_external_catalog_change_is_preserved(self):
        commit=storage.commit
        external={'entries':[],'techniques':[],'owner_change':'Keep this'}
        def changed(*args,**kwargs):self.catalog.write_text(json.dumps(external), encoding='utf-8');return commit(*args,**kwargs)
        with patch.object(storage,'commit',side_effect=changed),self.assertRaises(intake.IntakeError):intake.save(self.body)
        self.assertEqual(self.data(),external)
    def test_corrupt_or_symlinked_catalog_is_not_overwritten(self):
        self.catalog.write_text('{bad', encoding='utf-8')
        with self.assertRaises(intake.IntakeError):intake.save(self.body)
        self.catalog.unlink();outside=self.root/'outside.json';outside.write_text('{"entries":[]}', encoding='utf-8');self.catalog.symlink_to(outside)
        with self.assertRaises(storage.ReviewError):intake.save(self.body)
        self.assertEqual(outside.read_text(encoding='utf-8'),'{"entries":[]}')
    def test_threaded_creates_preserve_both_references(self):
        errors=[]
        def save(url):
            try:intake.save({**self.body,'url':url})
            except Exception as e:errors.append(e)
        threads=[threading.Thread(target=save,args=(f'https://example.com/{i}',)) for i in range(2)]
        for t in threads:t.start()
        for t in threads:t.join()
        self.assertFalse(errors);self.assertEqual(len(self.data()['entries']),2)
    def test_endpoint_guards_and_persistence(self):
        server=ThreadingHTTPServer(('127.0.0.1',0),Quiet);t=threading.Thread(target=server.serve_forever,daemon=True);t.start();origin=f'http://127.0.0.1:{server.server_port}'
        valid={'Origin':origin,'Content-Type':'application/json','X-Studio-Action':'reference'}
        def request(headers,body=None,path='/references',method='POST'):
            c=http.client.HTTPConnection('127.0.0.1',server.server_port);c.request(method,path,body=json.dumps(self.body) if body is None else body,headers=headers);r=c.getresponse();result=(r.status,r.read());c.close();return result
        try:
            for remove in ['Origin','X-Studio-Action']:
                headers=valid.copy();headers.pop(remove);self.assertEqual(request(headers)[0],403)
            for extra in [{'Host':'attacker.invalid'},{'Origin':'https://attacker.invalid'},{'Sec-Fetch-Site':'cross-site'}]:self.assertEqual(request({**valid,**extra})[0],403)
            self.assertEqual(request({**valid,'Content-Type':'text/plain'})[0],415)
            self.assertEqual(request(valid,'x'*16385)[0],413);self.assertEqual(request(valid,'{bad')[0],400)
            status,raw=request(valid);self.assertEqual(status,200);id=json.loads(raw)['id']
            status,raw=request({},'',path='/reference-state?id='+id,method='GET');self.assertEqual(status,200);self.assertIn('revision',json.loads(raw))
            for headers in [{'Host':'attacker.invalid'},{'Origin':'https://attacker.invalid'},{'Sec-Fetch-Site':'cross-site'}]:self.assertEqual(request(headers,'',path='/reference-state?id='+id,method='GET')[0],403)
        finally:server.shutdown();server.server_close();t.join()


    def test_remove_restore_both_collections_preserves_entries_and_dependencies(self):
        first=intake.save(self.body)['id'];second=intake.save({**self.body,'url':'https://example.com/own'})['id']
        data=self.data();next(e for e in data['entries'] if e['id']==second)['collection']='mine'
        data['techniques']=[{'id':'tech-demo','examples':[{'id':'exact-example','style_id':first}]}]
        self.catalog.write_text(json.dumps(data), encoding='utf-8');before=copy.deepcopy(data)
        for id in [first,second]:
            state=intake.visibility_state(id)
            removed=intake.set_visibility({'id':id,'action':'remove','revision':state['revision']})
            self.assertTrue(removed['removed']);self.assertTrue(removed['changed'])
            self.assertEqual(self.data()['entries'],before['entries']);self.assertEqual(self.data()['techniques'],before['techniques'])
            count=len(list(storage.JOURNALS.glob('*/transaction.json')))
            repeat=intake.set_visibility({'id':id,'action':'remove','revision':removed['revision']})
            self.assertFalse(repeat['changed']);self.assertEqual(count,len(list(storage.JOURNALS.glob('*/transaction.json'))))
            restored=intake.set_visibility({'id':id,'action':'restore','revision':removed['revision']})
            self.assertFalse(restored['removed']);self.assertNotIn(id,self.data()['removed_references'])
        self.assertEqual(self.data()['entries'],before['entries']);self.assertEqual(self.index.read_text(encoding='utf-8'),'{"projects":[]}')

    def test_visibility_rejects_stale_unknown_and_invalid_requests(self):
        id=intake.save(self.body)['id'];state=intake.visibility_state(id)
        body={'id':id,'action':'remove','revision':state['revision']}
        removed=intake.set_visibility(body)
        with self.assertRaises(intake.IntakeError) as error:intake.set_visibility(body)
        self.assertEqual(error.exception.status,409)
        before=self.catalog.read_bytes()
        for delta in [{'id':'../outside'},{'id':'unknown'},{'revision':False},{'action':'delete'},{'extra':'x'}]:
            with self.subTest(delta=delta),self.assertRaises(intake.IntakeError):intake.set_visibility({**body,**delta})
        self.assertEqual(before,self.catalog.read_bytes())
        # A later source update cannot be overwritten by an old Restore action.
        data=self.data();data['entries'][0]['summary']='New analysis';self.catalog.write_text(json.dumps(data), encoding='utf-8')
        with self.assertRaises(intake.IntakeError):intake.set_visibility({'id':id,'action':'restore','revision':removed['revision']})
        self.assertEqual(self.data()['entries'][0]['summary'],'New analysis')

    def test_duplicate_and_detail_edit_do_not_restore_removed_reference(self):
        id=intake.save(self.body)['id'];state=intake.visibility_state(id)
        intake.set_visibility({'id':id,'action':'remove','revision':state['revision']})
        before=self.catalog.read_bytes();result=intake.save(self.body)
        self.assertTrue(result['duplicate']);self.assertEqual(before,self.catalog.read_bytes())
        edit=intake.current(id);intake.save({'action':'edit','id':id,'revision':edit['revision'],'title':'Edited','creator':edit['creator'],'note':edit['note']})
        self.assertTrue(intake.visibility_state(id)['removed']);self.assertEqual(self.data()['entries'][0]['title'],'Edited')

    def test_visibility_concurrent_removals_and_external_changes(self):
        ids=[intake.save({**self.body,'url':f'https://example.com/{i}'})['id'] for i in range(2)]
        bodies=[{'id':id,'action':'remove','revision':intake.visibility_state(id)['revision']} for id in ids]
        errors=[]
        def remove(body):
            try:intake.set_visibility(body)
            except Exception as error:errors.append(error)
        threads=[threading.Thread(target=remove,args=(body,)) for body in bodies]
        for thread in threads:thread.start()
        for thread in threads:thread.join()
        self.assertFalse(errors);self.assertEqual(set(self.data()['removed_references']),set(ids))
        commit=storage.commit;external=self.data();external['owner_change']='Keep this'
        def changed(*args,**kwargs):self.catalog.write_text(json.dumps(external), encoding='utf-8');return commit(*args,**kwargs)
        with patch.object(storage,'commit',side_effect=changed),self.assertRaises(intake.IntakeError):
            intake.set_visibility({'id':ids[0],'action':'restore','revision':intake.visibility_state(ids[0])['revision']})
        self.assertEqual(self.data(),external)

    def test_visibility_corrupt_symlink_and_recovery_storage_are_preserved(self):
        id=intake.save(self.body)['id'];state=intake.visibility_state(id);body={'id':id,'action':'remove','revision':state['revision']}
        data=self.data();data['removed_references']=[];self.catalog.write_text(json.dumps(data), encoding='utf-8');before=self.catalog.read_bytes()
        with self.assertRaises(intake.IntakeError):intake.set_visibility(body)
        self.assertEqual(before,self.catalog.read_bytes())
        self.catalog.unlink();outside=self.root/'outside.json';outside.write_bytes(before);self.catalog.symlink_to(outside)
        with self.assertRaises(storage.ReviewError):intake.set_visibility(body)
        self.assertEqual(before,outside.read_bytes());self.catalog.unlink();data.pop('removed_references');self.catalog.write_text(json.dumps(data), encoding='utf-8')
        journal=storage.JOURNALS/'unfinished';journal.mkdir();(journal/'transaction.json').write_text('{"state":"prepared"}', encoding='utf-8')
        before=self.catalog.read_bytes()
        with self.assertRaises(intake.IntakeError):intake.set_visibility(body)
        self.assertEqual(before,self.catalog.read_bytes())

    def test_visibility_endpoint_guards_and_reload(self):
        id=intake.save(self.body)['id'];server=ThreadingHTTPServer(('127.0.0.1',0),Quiet)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();origin=f'http://127.0.0.1:{server.server_port}'
        headers={'Origin':origin,'Content-Type':'application/json','X-Studio-Action':'reference-visibility'}
        body=json.dumps({'id':id,'action':'remove','revision':intake.visibility_state(id)['revision']})
        def request(h,payload=body,method='POST',path='/reference-visibility'):
            c=http.client.HTTPConnection('127.0.0.1',server.server_port);c.request(method,path,body=payload,headers=h);r=c.getresponse();result=(r.status,r.read());c.close();return result
        try:
            before=self.catalog.read_bytes()
            for remove in ['Origin','X-Studio-Action']:
                h=headers.copy();h.pop(remove);self.assertEqual(request(h)[0],403)
            for extra in [{'Host':'attacker.invalid'},{'Origin':'https://attacker.invalid'},{'Sec-Fetch-Site':'cross-site'}]:self.assertEqual(request({**headers,**extra})[0],403)
            self.assertEqual(request({**headers,'Content-Type':'text/plain'})[0],415)
            self.assertEqual(request(headers,'x'*4097)[0],413);self.assertEqual(request(headers,'{bad')[0],400)
            self.assertEqual(before,self.catalog.read_bytes());self.assertEqual(request(headers)[0],200)
            status,raw=request({},'',method='GET',path='/reference-visibility?id='+id);self.assertEqual(status,200);self.assertTrue(json.loads(raw)['removed'])
            self.assertEqual(request({'Origin':'https://attacker.invalid'},'',method='GET',path='/reference-visibility?id='+id)[0],403)
        finally:server.shutdown();server.server_close();thread.join()
