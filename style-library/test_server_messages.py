"""Final review I2 (round 2): feedback, script, writing and reference-note errors reach the UI as
i18n keys with Hebrew and English text, like the review decision path."""
import http.client
import json
import re
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import library
import project_index as index
import server_messages as messages
from serve import Handler

HERE = Path(__file__).resolve().parent
STRINGS = {lang: json.loads((HERE / 'dist' / 'i18n' / f'{lang}.json').read_text(encoding='utf-8')) for lang in ('he', 'en')}


class QuietHandler(Handler):
    def log_message(self, *args):
        pass


class MessageTableTests(unittest.TestCase):
    def test_every_raised_sentence_has_a_key(self):
        for name in ('feedback.py', 'project_script.py', 'scripting.py', 'reference_notes.py'):
            source = (HERE / name).read_text(encoding='utf-8')
            for text in re.findall(r"(?:FeedbackError|NoteError)\('([^']*)'", source):
                with self.subTest(module=name, text=text):
                    self.assertTrue(messages.code(text).startswith('server.'), text)

    def test_every_route_answer_on_these_routes_has_a_key(self):
        source = (HERE / 'serve.py').read_text(encoding='utf-8')
        for text in re.findall(r"json_error\(\s*(?:400|503)\s*,\s*'([^']*)'", source):
            if re.search(r'feedback|script|writing|Writing|Reference notes|reference note', text):
                with self.subTest(text=text):
                    self.assertTrue(messages.code(text).startswith('server.'), text)

    def test_keys_have_hebrew_and_english_text(self):
        for key, entry in messages.STRINGS.items():
            with self.subTest(key=key):
                self.assertEqual(STRINGS['he'][key], entry['he'])
                self.assertEqual(STRINGS['en'][key], entry['en'])
                self.assertNotRegex(entry['he'], r'[A-Za-z]{3,}', 'Hebrew text has no English prose')
                self.assertRegex(entry['he'], r'[֐-׿]')
                self.assertNotIn('assistant', entry['en'])
                self.assertNotIn('editing chat', entry['en'])

    def test_codes(self):
        self.assertEqual(messages.code('Choose a registered project.'), 'server.choose-a-registered-project')
        self.assertEqual(messages.code('Selected feedback was edited or deleted after copying. Review and copy again. Notes: a, b'),
                         messages.KEYS['Selected feedback was edited or deleted after copying. Review and copy again. Notes: '])
        self.assertEqual(messages.code('Title must be text of up to 120 characters.'), messages.KEYS['Text is too long.'])
        self.assertEqual(messages.code('Invalid review action.'), 'review.error.invalidAction')  # shared storage errors
        self.assertEqual(messages.code('materials.error.filesystem'), 'materials.error.filesystem')  # already a key
        self.assertEqual(messages.code('Something new.'), 'Something new.')


class RouteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name).resolve()
        (root / 'style-library').mkdir()
        (root / 'style-library' / 'projects.json').write_text(json.dumps({'projects': []}), encoding='utf-8')
        self.patches = [patch.object(index, 'STUDIO', root), patch.object(index, 'REGISTRY', root / 'style-library' / 'projects.json'),
                        patch.object(library, 'BASE', root / 'style-library')]
        for p in self.patches:
            p.start()
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), QuietHandler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.host = f'127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        for p in self.patches:
            p.stop()
        self.temp.cleanup()

    def post(self, path, action, body):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port)
        connection.request('POST', path, body=body, headers={'Origin': 'http://' + self.host, 'Host': self.host,
                                                             'X-Studio-Action': action, 'Content-Type': 'application/json'})
        response = connection.getresponse()
        result = response.status, json.loads(response.read() or b'null')
        connection.close()
        return result

    def test_feedback_routes_answer_with_keys(self):
        status, body = self.post('/feedback', 'feedback', '{broken')
        self.assertEqual((status, body['error']), (400, messages.KEYS['Use a valid JSON feedback request.']))
        status, body = self.post('/feedback', 'feedback', json.dumps({'project_id': 'nope'}))
        self.assertTrue(body['error'].startswith('server.'), body)
        self.assertIn(body['error'], STRINGS['he'])


if __name__ == '__main__':
    unittest.main()
