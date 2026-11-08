"""Writing context tests use disposable owner data and real guarded HTTP routes."""
import hashlib
import http.client
import json
import threading
import unittest
import uuid
from http.server import ThreadingHTTPServer
from unittest.mock import patch
import test_project_script as fixtures
import scripting
import project_script
from feedback import FeedbackError
from review_actions import ReviewError
from serve import Handler


class ScriptingTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.ScriptTests(methodName='runTest')
        self.fixture.setUp()
        self.base = self.fixture.base
        self.project = self.fixture.project

    def tearDown(self):
        self.fixture.tearDown()

    def voice(self, text='Keep transitions conversational.', state=None):
        state = state or scripting.voice_current()
        return {'revision': state['revision'], 'request_id': str(uuid.uuid4()),
                'preferences': [{'id': str(uuid.uuid4()), 'text': text, 'source': 'Explicit owner feedback on a script revision.'}]}

    def remember(self, memory=None):
        memory = memory or {'id': str(uuid.uuid4()), 'text': 'Use short, direct transitions.',
                            'source': 'Explicit feedback in this chat.'}
        return {'revision': scripting.voice_current()['revision'], 'request_id': str(uuid.uuid4()), 'memory': memory}

    def example(self, **values):
        return {'id': str(uuid.uuid4()), 'before': 'Longer wording.', 'after': 'Short wording.',
                'feedback': 'This is shorter but it is still not great.', 'context': 'Shortening a spoken transition.', **values}

    def test_writing_memory_remembers_exact_evidence_and_recall_keeps_qualified_feedback(self):
        body = self.remember()
        body['memory']['examples'] = [self.example()]
        saved = scripting.voice_remember(body)
        recalled = scripting.voice_recall('Shortening a spoken transition')
        self.assertEqual(recalled['examples'][0]['feedback'], body['memory']['examples'][0]['feedback'])
        self.assertEqual(recalled['preferences'][0]['text'], body['memory']['text'])
        self.assertEqual(scripting.voice_memory_current(body['memory']['id'], saved['revision'])['memory'], saved['preferences'][0])
        scripting.voice_remember(self.remember())
        with self.assertRaises(FeedbackError):
            scripting.voice_memory_current(body['memory']['id'], saved['revision'])
        self.assertEqual(scripting.voice_remember(body), scripting.voice_current())

    def test_memory_examples_accumulate_without_replacing_earlier_choices_or_legacy_notes(self):
        legacy = self.voice()
        scripting.voice_save(legacy)
        note = {**legacy['preferences'][0], 'examples': [self.example()]}
        first = self.remember(note)
        scripting.voice_remember(first)
        second = self.remember({**note, 'examples': [self.example(context='Personal story pacing.')]})
        scripting.voice_remember(second)
        self.assertEqual(len(scripting.voice_current()['preferences'][0]['examples']), 2)
        self.assertEqual(scripting.voice_remember(second), scripting.voice_current())
        old_caller = {**legacy, 'revision': scripting.voice_current()['revision'], 'request_id': str(uuid.uuid4())}
        scripting.voice_save(old_caller)
        self.assertEqual(len(scripting.voice_current()['preferences'][0]['examples']), 2)
        self.assertEqual(scripting.voice_save(old_caller), scripting.voice_current())

    def test_forget_survives_reload_and_legacy_saves_and_undo_restores_the_same_examples(self):
        body = self.remember()
        body['memory']['examples'] = [self.example()]
        saved = scripting.voice_remember(body)
        action = {'revision': saved['revision'], 'request_id': str(uuid.uuid4()),
                  'memory_id': body['memory']['id'], 'forgotten': True}
        forgotten = scripting.voice_forget(action)
        self.assertEqual(forgotten['preferences'], [])
        self.assertEqual(scripting.voice_recall()['examples'], [])
        self.assertIn(body['memory']['id'], forgotten['forgotten_ids'])
        with self.assertRaises(FeedbackError):
            scripting.voice_remember(self.remember(body['memory']))
        with self.assertRaises(FeedbackError):
            scripting.voice_save({'revision': forgotten['revision'], 'request_id': str(uuid.uuid4()),
                                   'preferences': [body['memory']]})
        scripting.voice_remember(self.remember())
        self.assertEqual(scripting.voice_forget(action), scripting.voice_current())
        undo = {**action, 'revision': scripting.voice_current()['revision'], 'request_id': str(uuid.uuid4()), 'forgotten': False}
        restored = scripting.voice_forget(undo)
        self.assertEqual(next(p for p in restored['preferences'] if p['id'] == body['memory']['id']), body['memory'])
        self.assertEqual(scripting.voice_forget(undo), restored)
        state = json.loads((self.base/'writing-voice.json').read_text(encoding='utf-8'))
        self.assertTrue(any(p.get('forgotten_at') for v in state['versions'] for p in v['value']))

    def test_memory_source_script_validation_and_conflicting_writes_preserve_the_winner(self):
        before = project_script.save(self.fixture.body('Longer wording.'))
        after = project_script.save(self.fixture.body('Short wording.'))
        example = self.example(project_id='demo', before_version=before['version_id'], after_version=after['version_id'])
        body = self.remember()
        body['memory']['examples'] = [example]
        scripting.voice_remember(body)
        bad = self.remember({**body['memory'], 'examples': [{**example, 'after': 'Made up wording.'}]})
        with self.assertRaises(FeedbackError):
            scripting.voice_remember(bad)
        stale = self.remember()
        winner = scripting.voice_remember(self.remember())
        with self.assertRaises(FeedbackError):
            scripting.voice_remember(stale)
        self.assertEqual(scripting.voice_current(), winner)
        self.assertEqual(project_script.current('demo')['text'], 'Short wording.')

    def test_fresh_memory_recall_never_creates_owner_files_and_ranks_relevant_examples(self):
        self.assertEqual(scripting.voice_recall()['examples'], [])
        self.assertFalse((self.base/'writing-voice.json').exists())
        a = self.remember()
        a['memory']['examples'] = [self.example(context='Apartment tours and rental lists.')]
        scripting.voice_remember(a)
        b = self.remember()
        b['memory']['examples'] = [self.example(context='Cooking dinner and baking a cake.')]
        scripting.voice_remember(b)
        self.assertEqual(scripting.voice_recall('Apartment rental tours', limit=1)['examples'][0]['memory_id'], a['memory']['id'])
        with self.assertRaises(FeedbackError):
            scripting.voice_recall(limit=-1)

    def brief(self, ready=None):
        return {'project_id': 'demo', 'revision': scripting.brief_current('demo')['revision'],
                'request_id': str(uuid.uuid4()), 'idea': 'A useful idea', 'references': 'A source and what to borrow',
                'ready_script': ready}

    def test_approval_and_reopen_preserve_exact_history_context_and_other_project_files(self):
        scripting.brief_save(self.brief())
        saved = project_script.save(self.fixture.body('Use these exact words.'))
        state_path = self.project/'script-state.json'
        before = {p: p.read_bytes() for p in (state_path, self.fixture.registry, self.project/'script.txt')}
        body = {'project_id': 'demo', 'revision': scripting.brief_current('demo')['revision'],
                'request_id': str(uuid.uuid4()), 'script_version': saved['version_id'],
                'script_revision': saved['revision'], 'ready': True}
        approved = scripting.script_ready(body)
        self.assertTrue(approved['ready'])
        self.assertEqual(approved['idea'], 'A useful idea')
        self.assertEqual(approved['references'], 'A source and what to borrow')
        reopened = scripting.script_ready({**body, 'ready': False, 'revision': approved['revision'], 'request_id': str(uuid.uuid4())})
        self.assertFalse(reopened['ready'])
        self.assertFalse(scripting.script_ready(body)['ready'])
        history = json.loads((self.project/'script-brief.json').read_text(encoding='utf-8'))
        self.assertTrue(any(row['value']['ready_script'] == saved['version_id'] for row in history['versions']))
        self.assertEqual({p: p.read_bytes() for p in before}, before)
        self.assertFalse((self.project/'approval-state.json').exists())

    def test_approval_rejects_stale_context_and_script(self):
        saved = project_script.save(self.fixture.body('First draft.'))
        body = {'project_id': 'demo', 'revision': scripting.brief_current('demo')['revision'],
                'request_id': str(uuid.uuid4()), 'script_version': saved['version_id'],
                'script_revision': saved['revision'], 'ready': True}
        scripting.brief_save(self.brief())
        with self.assertRaises(FeedbackError):
            scripting.script_ready(body)
        fresh = {**body, 'revision': scripting.brief_current('demo')['revision']}
        project_script.save(self.fixture.body('Second draft.'))
        with self.assertRaises(FeedbackError):
            scripting.script_ready(fresh)
        self.assertIsNone(scripting.brief_current('demo')['ready_script'])

    def test_first_read_is_empty_and_never_seeds_owner_files(self):
        before = {p: p.read_bytes() for p in self.fixture.root.rglob('*') if p.is_file()}
        self.assertEqual(scripting.voice_current()['preferences'], [])
        self.assertFalse(scripting.brief_current('demo')['ready'])
        self.assertEqual({p: p.read_bytes() for p in self.fixture.root.rglob('*') if p.is_file()}, before)

    def test_voice_is_private_versioned_and_retries_do_not_revert_a_newer_value(self):
        first_body = self.voice()
        first = scripting.voice_save(first_body)
        second_body = {'revision': first['revision'], 'request_id': str(uuid.uuid4()), 'preferences': []}
        second = scripting.voice_save(second_body)
        self.assertEqual(second['preferences'], [])
        self.assertEqual(scripting.voice_save(first_body)['revision'], second['revision'])
        history = json.loads((self.base/'writing-voice.json').read_text(encoding='utf-8'))
        self.assertEqual(len(history['versions']), 2)
        self.assertEqual(history['versions'][0]['value'][0]['source'], first_body['preferences'][0]['source'])

    def test_stale_voice_save_preserves_the_winning_change(self):
        stale = self.voice('A stale change')
        winner = scripting.voice_save(self.voice('Use my actual words.'))
        with self.assertRaises(FeedbackError):
            scripting.voice_save(stale)
        self.assertEqual(scripting.voice_current(), winner)

    def test_preferences_require_evidence_and_distinct_ids(self):
        body = self.voice()
        body['preferences'][0]['source'] = ''
        with self.assertRaises(FeedbackError):
            scripting.voice_save(body)
        body = self.voice()
        body['preferences'] *= 2
        with self.assertRaises(FeedbackError):
            scripting.voice_save(body)
        self.assertFalse((self.base/'writing-voice.json').exists())

    def test_ready_is_tied_to_exact_saved_script_and_never_approves_footage(self):
        registry = self.fixture.registry.read_bytes()
        original = (self.project/'script.txt').read_bytes()
        first = project_script.save(self.fixture.body('My first script.'))
        self.assertTrue(scripting.brief_save(self.brief(first['version_id']))['ready'])
        later = project_script.save(self.fixture.body('My revised script.'))
        self.assertFalse(scripting.brief_current('demo')['ready'])
        with self.assertRaises(FeedbackError):
            scripting.brief_save(self.brief(first['version_id']))
        self.assertTrue(scripting.brief_save(self.brief(later['version_id']))['ready'])
        self.assertEqual(self.fixture.registry.read_bytes(), registry)
        self.assertEqual((self.project/'script.txt').read_bytes(), original)
        self.assertEqual((self.project/'exports/assembled-script-v04.txt').read_text(encoding='utf-8'), 'The selected words.')

    def test_script_history_keeps_exact_versions(self):
        first = project_script.save(self.fixture.body('First version.'))
        second = project_script.save(self.fixture.body('Second version.'))
        old = project_script.current('demo', first['version_id'])
        self.assertEqual(old['text'], 'First version.')
        self.assertEqual(old['current_version_id'], second['version_id'])
        self.assertEqual(old['versions'][0]['id'], second['version_id'])

    def test_brief_conflict_and_broken_memory_are_preserved(self):
        stale = self.brief()
        winner = scripting.brief_save(self.brief())
        stale['idea'] = 'Outdated'
        with self.assertRaises(FeedbackError):
            scripting.brief_save(stale)
        self.assertEqual(scripting.brief_current('demo'), winner)
        path = self.base/'writing-voice.json'
        path.write_text('broken owner data', encoding='utf-8')
        with self.assertRaises(ValueError):
            scripting.voice_current()
        self.assertEqual(path.read_text(encoding='utf-8'), 'broken owner data')

    def test_symlinked_voice_file_never_writes_outside_the_installation(self):
        target = self.fixture.root/'private.json'
        target.write_text('keep me', encoding='utf-8')
        (self.base/'writing-voice.json').symlink_to(target)
        with self.assertRaises(FeedbackError):
            scripting.voice_save({'revision': '0'*64, 'request_id': str(uuid.uuid4()), 'preferences': []})
        self.assertEqual(target.read_text(encoding='utf-8'), 'keep me')

    def test_http_requires_same_origin_explicit_actions_and_private_file_is_not_static(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        origin = 'http://127.0.0.1:'+str(server.server_port)
        def request(method, path, body=None, headers=None):
            c = http.client.HTTPConnection('127.0.0.1', server.server_port)
            c.request(method, path, json.dumps(body) if body is not None else None, headers or {})
            response = c.getresponse()
            result = response.status, response.read()
            c.close()
            return result
        try:
            self.assertEqual(request('GET', '/writing-voice')[0], 200)
            self.assertEqual(request('GET', '/writing-voice', headers={'Origin': 'https://example.com'})[0], 403)
            body = self.voice()
            headers = {'Content-Type': 'application/json', 'Origin': origin, 'X-Studio-Action': 'writing-voice'}
            self.assertEqual(request('POST', '/writing-voice', body)[0], 403)
            self.assertEqual(request('POST', '/writing-voice', body, headers)[0], 200)
            state = scripting.voice_current()
            memory = {**state['preferences'][0], 'text': 'Keep the useful detail.'}
            remember = {'revision': state['revision'], 'request_id': str(uuid.uuid4()), 'memory': memory}
            self.assertEqual(request('POST', '/writing-memory', remember, headers)[0], 403)
            headers['X-Studio-Action'] = 'writing-memory'
            self.assertEqual(request('POST', '/writing-memory', remember, headers)[0], 200)
            forget = {'revision': scripting.voice_current()['revision'], 'request_id': str(uuid.uuid4()),
                      'memory_id': memory['id'], 'forgotten': True}
            self.assertEqual(request('POST', '/writing-memory-forget', forget)[0], 403)
            headers['X-Studio-Action'] = 'writing-memory-forget'
            self.assertEqual(request('POST', '/writing-memory-forget', forget, headers)[0], 200)
            self.assertEqual(scripting.voice_current()['preferences'], [])
            self.assertEqual(request('GET', '/writing-voice.json')[0], 404)
            self.assertEqual(request('GET', '/script-brief?project=demo')[0], 200)
            self.assertEqual(request('GET', '/script-brief?project=demo&project=demo')[0], 400)
            headers['X-Studio-Action'] = 'script-brief'
            self.assertEqual(request('POST', '/script-brief', self.brief(), headers)[0], 200)
            saved = project_script.save(self.fixture.body('Approve this exact text.'))
            approval = {'project_id': 'demo', 'revision': scripting.brief_current('demo')['revision'],
                        'request_id': str(uuid.uuid4()), 'script_version': saved['version_id'],
                        'script_revision': saved['revision'], 'ready': True}
            self.assertEqual(request('POST', '/script-ready', approval, headers)[0], 403)
            headers['X-Studio-Action'] = 'script-ready'
            self.assertEqual(request('POST', '/script-ready', approval, headers)[0], 200)
            self.assertTrue(scripting.brief_current('demo')['ready'])

        finally:
            server.shutdown()
            server.server_close()
            thread.join()


class ScriptIterationTests(unittest.TestCase):
    setUp = ScriptingTests.setUp
    tearDown = ScriptingTests.tearDown
    def hooks(self):
        saved = project_script.save(self.fixture.body('An original opening.\n\nThe body stays the same.'))
        options = [{'id': str(uuid.uuid4()), 'opening': opening} for opening in
                   ['An original opening.', 'A different opening.\n\nA compatible bridge.', 'A third opening.']]
        body = {'project_id': 'demo', 'revision': scripting.hooks_current('demo')['revision'],
                'request_id': str(uuid.uuid4()), 'script_version': saved['version_id'],
                'prefix': 'An original opening.', 'options': options}
        return saved, body

    def choice(self, saved, hooks, option):
        return {'project_id': 'demo', 'revision': project_script.current('demo')['revision'],
                'request_id': str(uuid.uuid4()), 'script_version': saved['version_id'],
                'hook_revision': hooks['revision'], 'option_id': option['id']}

    def feedback(self, saved, feedback='Make the opening more personal.', references=''):
        return {'project_id': 'demo', 'request_id': str(uuid.uuid4()), 'script_version': saved['version_id'],
                'feedback': feedback, 'references': references}

    def test_iteration_reads_never_create_owner_records(self):
        before = {p: p.read_bytes() for p in self.fixture.root.rglob('*') if p.is_file()}
        self.assertEqual(scripting.hooks_current('demo')['options'], [])
        self.assertEqual(scripting.feedback_current('demo')['requests'], [])
        self.assertEqual({p: p.read_bytes() for p in self.fixture.root.rglob('*') if p.is_file()}, before)

    def test_hook_choice_creates_a_version_keeps_the_body_and_can_restore_original(self):
        saved, body = self.hooks(); registry = self.fixture.registry.read_bytes()
        hooks = scripting.hooks_save(body)
        original_id = hooks['selected_id']; request = self.choice(saved, hooks, body['options'][1])
        result = scripting.hook_apply(request)
        self.assertEqual(result['text'], 'A different opening.\n\nA compatible bridge.\n\nThe body stays the same.')
        self.assertEqual(project_script.current('demo', saved['version_id'])['text'], saved['text'])
        self.assertEqual(result['hooks']['selected_id'], body['options'][1]['id'])
        restore = {**self.choice(result, result['hooks'], {'id': original_id})}
        self.assertEqual(scripting.hook_apply(restore)['version_id'], saved['version_id'])
        self.assertEqual(self.fixture.registry.read_bytes(), registry)
        self.assertEqual((self.project/'script.txt').read_text(encoding='utf-8'), 'The script I recorded.\n')
        self.assertFalse((self.project/'approval-state.json').exists())

    def test_hook_retries_never_revert_a_later_script(self):
        saved, body = self.hooks(); hooks = scripting.hooks_save(body)
        request = self.choice(saved, hooks, body['options'][1]); scripting.hook_apply(request)
        newer = project_script.save(self.fixture.body('A later manual revision.'))
        self.assertTrue(scripting.hook_apply(request)['duplicate'])
        self.assertEqual(project_script.current('demo')['version_id'], newer['version_id'])

    def test_stale_hook_set_or_script_never_overwrites_work(self):
        saved, body = self.hooks(); hooks = scripting.hooks_save(body)
        request = self.choice(saved, hooks, body['options'][1])
        changed = {**body, 'revision': hooks['revision'], 'request_id': str(uuid.uuid4()),
                   'options': [body['options'][0], {'id': str(uuid.uuid4()), 'opening': 'A newer option.'}]}
        scripting.hooks_save(changed)
        before = (self.project/'script-state.json').read_bytes()
        with self.assertRaises(FeedbackError): scripting.hook_apply(request)
        self.assertEqual((self.project/'script-state.json').read_bytes(), before)
        hooks = scripting.hooks_current('demo'); request = self.choice(saved, hooks, changed['options'][1])
        newer = project_script.save(self.fixture.body('Changed elsewhere.'))
        with self.assertRaises(FeedbackError): scripting.hook_apply(request)
        self.assertEqual(project_script.current('demo')['version_id'], newer['version_id'])

    def test_invalid_opening_sets_are_rejected_without_writing(self):
        saved, body = self.hooks()
        for invalid in [{**body, 'prefix': 'Not the actual opening'}, {**body, 'prefix': 'An original'},
                        {**body, 'script_version': None}, {**body, 'options': [body['options'][1], body['options'][2]]},
                        {**body, 'options': [body['options'][0], body['options'][0]]}]:
            with self.assertRaises(FeedbackError): scripting.hooks_save(invalid)
        self.assertFalse((self.project/'script-hooks.json').exists())
        self.assertEqual(project_script.current('demo')['version_id'], saved['version_id'])

    def test_feedback_is_exact_immutable_and_reference_only_is_sufficient(self):
        saved = project_script.save(self.fixture.body('A saved script.'))
        original = (self.project/'script-state.json').read_bytes(); registry = self.fixture.registry.read_bytes()
        request = self.feedback(saved, '', 'https://example.org/clip — borrow the opening question.')
        first = scripting.feedback_save(request); self.assertEqual(first['script_version'], saved['version_id'])
        self.assertEqual(scripting.feedback_save(request), first)
        self.assertEqual(len(scripting.feedback_current('demo')['requests']), 1)
        with self.assertRaises(FeedbackError): scripting.feedback_current('demo', first['id'], 'f'*64)
        with self.assertRaises(FeedbackError): scripting.feedback_save({**request, 'feedback': 'Different text.'})
        self.assertEqual((self.project/'script-state.json').read_bytes(), original)
        self.assertEqual(self.fixture.registry.read_bytes(), registry)
        self.assertFalse((self.base/'writing-voice.json').exists())
        self.assertFalse((self.project/'approval-state.json').exists())

    def test_feedback_keeps_earlier_version_and_unavailable_ids_do_not_substitute(self):
        saved = project_script.save(self.fixture.body('The earlier draft.'))
        newer = project_script.save(self.fixture.body('The newer draft.'))
        request = self.feedback(saved); row = scripting.feedback_save(request)
        self.assertEqual(scripting.feedback_current('demo', row['id'])['script_version'], saved['version_id'])
        self.assertEqual(project_script.current('demo')['version_id'], newer['version_id'])
        with self.assertRaises(FeedbackError): scripting.feedback_save({**request, 'script_version': 'f'*64})
        with self.assertRaises(FeedbackError): scripting.feedback_current('demo', str(uuid.uuid4()))
        with self.assertRaises(FeedbackError): scripting.feedback_save(self.feedback(saved, '', ''))

    def test_iteration_symlinks_and_corrupt_files_are_preserved(self):
        saved, body = self.hooks(); outside = self.fixture.root/'outside.json'; outside.write_text('private', encoding='utf-8')
        path = self.project/'script-hooks.json'; path.symlink_to(outside)
        with self.assertRaises(ReviewError): scripting.hooks_save(body)
        self.assertEqual(outside.read_text(encoding='utf-8'), 'private'); path.unlink()
        path = self.project/'script-feedback.json'; path.write_text('broken owner data', encoding='utf-8')
        with self.assertRaises(ValueError): scripting.feedback_save(self.feedback(saved))
        self.assertEqual(path.read_text(encoding='utf-8'), 'broken owner data'); path.unlink(); path.symlink_to(outside)
        with self.assertRaises(ReviewError): scripting.feedback_save(self.feedback(saved))
        self.assertEqual(outside.read_text(encoding='utf-8'), 'private')

    def test_hook_file_changed_at_commit_is_not_overwritten_or_applied(self):
        saved, body = self.hooks(); hooks = scripting.hooks_save(body)
        request = self.choice(saved, hooks, body['options'][1]); real = scripting.storage.commit
        path = self.project/'script-hooks.json'
        def changed(*args):
            path.write_bytes(path.read_bytes()+b' '); return real(*args)
        before = (self.project/'script-state.json').read_bytes()
        with patch.object(scripting.storage, 'commit', side_effect=changed), self.assertRaises(ReviewError):
            scripting.hook_apply(request)
        self.assertEqual((self.project/'script-state.json').read_bytes(), before)

    def test_iteration_http_guards_and_private_files(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        origin = 'http://127.0.0.1:'+str(server.server_port)
        def request(method, path, body=None, headers=None):
            c = http.client.HTTPConnection('127.0.0.1', server.server_port)
            c.request(method, path, json.dumps(body) if body is not None else None, headers or {})
            response = c.getresponse(); result = response.status, response.read(); c.close(); return result
        try:
            saved, body = self.hooks()
            headers = {'Content-Type': 'application/json', 'Origin': origin, 'X-Studio-Action': 'script-hooks'}
            self.assertEqual(request('POST', '/script-hooks', body)[0], 403)
            self.assertEqual(request('POST', '/script-hooks', body, headers)[0], 200)
            self.assertEqual(request('GET', '/script-hooks?project=demo&project=demo')[0], 400)
            self.assertEqual(request('GET', '/script-hooks?project=demo', headers={'Origin':'https://example.com'})[0], 403)
            hooks = scripting.hooks_current('demo'); headers['X-Studio-Action'] = 'script-hook'
            self.assertEqual(request('POST', '/script-hook', self.choice(saved, hooks, body['options'][1]), headers)[0], 200)
            headers['X-Studio-Action'] = 'script-feedback'; feedback = self.feedback(saved)
            self.assertEqual(request('POST', '/script-feedback', feedback, headers)[0], 200)
            self.assertEqual(request('GET', '/script-feedback?project=demo&request='+feedback['request_id'])[0], 200)
            self.assertEqual(request('GET', '/script-feedback?project=demo&request=')[0], 400)
            self.assertEqual(request('GET', '/script-feedback.json')[0], 404)
        finally:
            server.shutdown(); server.server_close(); thread.join()


if __name__ == '__main__':
    unittest.main()
