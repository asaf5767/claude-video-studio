"""Editor isolation, exact versions and sound summaries in disposable projects."""
import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import project_index as index
import project_tools as tools

class ProjectToolsTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name).resolve();self.project=self.root/'projects/demo';self.source=self.project/'assembly-v02';self.source.mkdir(parents=True)
        (self.source/'index.html').write_text('<main data-composition-id="demo" data-duration="2"></main>', encoding='utf-8')
        (self.source/'README.md').write_text('Exact editable V02 source.', encoding='utf-8')
        (self.source/'sound-plan.json').write_text(json.dumps({'music':False,'cues':[{'time':0,'label':'Click'}],'direction':'Sparse, tactile effects.'}), encoding='utf-8')
        (self.project/'review.mp4').write_bytes(b'original export')
        self.p={'id':'demo','primary_artifact':'v02','artifacts':[{'id':'v02','type':'video','path':'review.mp4','downloads':[{'label':'Editable project notes','path':'assembly-v02/README.md'}]},{'id':'v01','type':'video','path':'review.mp4','downloads':[{'label':'Editable project notes','path':'assembly-v02/README.md'}]}]}
        self.registry=self.root/'projects.json';self.registry.write_text(json.dumps({'projects':[self.p]}), encoding='utf-8')
        cli=self.root/'node_modules/hyperframes/bin/hyperframes.mjs';cli.parent.mkdir(parents=True);cli.write_text('fixture', encoding='utf-8')
        self.patches=[patch.object(index,'STUDIO',self.root),patch.object(index,'REGISTRY',self.registry)]
        for p in self.patches:p.start()
    def tearDown(self):
        for p in self.patches:p.stop()
        self.tmp.cleanup()
    def body(self):return {'project_id':'demo','artifact_id':'v02','revision':tools.state('demo','v02')['editor']['revision']}
    def fake_launch(self,args,**kwargs):
        self.assertNotIn('shell',kwargs)
        if '--status' in args:return SimpleNamespace(returncode=1,stdout='')
        self.assertIn('--no-open',args);self.copy=Path(args[3]);self.assertNotEqual(self.copy,self.source)
        return SimpleNamespace(returncode=0,stdout=json.dumps({'ok':True,'result':{'studioUrl':'http://127.0.0.1:'+args[-1]+'/#project/'+self.copy.name}}))
    def test_read_only_sound_and_editor_state(self):
        before=set(self.project.rglob('*'));state=tools.state('demo','v02')
        self.assertEqual(state['sound']['music'],'No background music');self.assertEqual(state['sound']['effects'],'1 timed effect');self.assertTrue(state['editor']['ready']);self.assertEqual(set(self.project.rglob('*')),before)
    def test_history_is_never_inferred_from_shared_source(self):
        self.assertIsNone(tools.state('demo','v01')['editor'])
        self.p['artifacts'][1]['editor_source']='assembly-v02/index.html';self.registry.write_text(json.dumps({'projects':[self.p]}), encoding='utf-8');self.assertIsNotNone(tools.state('demo','v01')['editor'])
    def test_open_copies_source_and_preserves_export(self):
        body=self.body()
        with patch.object(tools.subprocess,'run',side_effect=self.fake_launch):result=tools.open_editor(body)
        self.assertTrue(result['url'].startswith('http://127.0.0.1:'));(self.copy/'index.html').write_text('manual change', encoding='utf-8')
        self.assertIn('data-composition-id',(self.source/'index.html').read_text(encoding='utf-8'));self.assertEqual((self.project/'review.mp4').read_bytes(),b'original export')
    def test_source_change_refuses_before_launch(self):
        body=self.body();(self.source/'index.html').write_text('<main data-composition-id="changed"></main>', encoding='utf-8')
        with patch.object(tools.subprocess,'run') as run,self.assertRaises(tools.ToolsError) as e:tools.open_editor(body)
        self.assertEqual(e.exception.status,409);run.assert_not_called()
    def test_unsafe_source_and_destination_refused(self):
        outside=Path(self.tmp.name).parent/'outside-fixture-ux20.html';outside.write_text('secret', encoding='utf-8')
        try:
            (self.source/'external.html').symlink_to(outside)
            self.assertIsNone(tools.state('demo','v02')['editor'])
        finally:outside.unlink()
        (self.source/'external.html').unlink();body=self.body();(self.project/'work').symlink_to(self.root)
        with self.assertRaises(tools.ToolsError):tools.open_editor(body)
    def test_invalid_requests_missing_tools_and_no_invented_music(self):
        for bad in [{},{**self.body(),'extra':'x'},{**self.body(),'revision':False}]:
            with self.assertRaises(tools.ToolsError):tools.open_editor(bad)
        (self.source/'sound-plan.json').unlink();self.assertFalse(tools.state('demo','v02')['sound']['recorded'])
        (self.root/'node_modules/hyperframes/bin/hyperframes.mjs').unlink();self.assertFalse(tools.state('demo','v02')['editor']['ready'])
        with self.assertRaises(tools.ToolsError):tools.open_editor(self.body())
    def test_project_root_copy_does_not_copy_its_own_working_copies(self):
        self.p['artifacts'][0]['editor_source']='index.html';(self.project/'index.html').write_text('<main data-composition-id="root"></main>', encoding='utf-8');self.registry.write_text(json.dumps({'projects':[self.p]}), encoding='utf-8')
        with patch.object(tools.subprocess,'run',side_effect=self.fake_launch):tools.open_editor(self.body())
        self.assertFalse((self.copy/'work/studio-editor').exists())

    def test_reopening_keeps_manual_changes_in_the_same_working_copy(self):
        body=self.body()
        with patch.object(tools.subprocess,'run',side_effect=self.fake_launch):first=tools.open_editor(body)
        copy=self.copy;(copy/'index.html').write_text('Manual changes to keep', encoding='utf-8')
        self.assertTrue(tools.state('demo','v02')['editor']['working_copy'])
        with patch.object(tools.subprocess,'run',side_effect=self.fake_launch):again=tools.open_editor(body)
        self.assertEqual(first['working_copy'],again['working_copy']);self.assertEqual((copy/'index.html').read_text(encoding='utf-8'),'Manual changes to keep')
