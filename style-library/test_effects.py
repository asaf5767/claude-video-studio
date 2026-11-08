"""Task 12: the effects board catalogs -- effects/effects.json (After-Effects-style motion
graphics) and looks/presenter.json (presenter looks, "איך אתם נראים") -- read by
effects.list() and served at GET /effects. Every entry's live demo lives in
dist/fx-demos.js and every label lives in dist/i18n/<lang>.json."""
import http.client
import json
import re
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import effects
from serve import Handler

DIST = Path(__file__).resolve().parent / 'dist'
REQUIRED = ('id', 'name_key', 'desc_key', 'category', 'demo', 'instructions')


def i18n(lang):
    return json.loads((DIST / 'i18n' / f'{lang}.json').read_text(encoding='utf-8'))


def demo_registry_keys():
    """The ids registered in fx-demos.js -- each demo is declared as demo('<id>', ...)."""
    source = (DIST / 'fx-demos.js').read_text(encoding='utf-8')
    return re.findall(r"\bdemo\('([a-z][a-z0-9-]*)'", source)


class CatalogTest(unittest.TestCase):
    def setUp(self):
        self.data = effects.list()
        self.all = self.data['effects'] + self.data['looks']

    def test_both_catalogs_load(self):
        self.assertGreaterEqual(len(self.data['effects']), 18)
        self.assertGreaterEqual(len(self.data['looks']), 10)

    def test_unique_ids_across_both_catalogs(self):
        ids = [item['id'] for item in self.all]
        self.assertEqual(len(ids), len(set(ids)))
        for item_id in ids:
            self.assertRegex(item_id, r'^[a-z][a-z0-9-]*$')

    def test_each_entry_has_required_fields(self):
        for item in self.all:
            for key in REQUIRED:
                self.assertIsInstance(item.get(key), str, f'{item.get("id")}: {key}')
                self.assertTrue(item[key].strip(), f'{item.get("id")}: {key} is empty')
            self.assertGreater(len(item['instructions']), 200, item['id'] + ': instructions too thin to build from')

    def test_presenter_looks_say_whether_they_need_a_matte(self):
        for item in self.data['looks']:
            self.assertIsInstance(item.get('requires_matte'), bool, item['id'])
            if item['requires_matte']:
                self.assertIn('matte.py', item['instructions'], item['id'])
                self.assertIn('fg.webm', item['instructions'], item['id'])

    def test_matte_looks_follow_the_matte_py_contract(self):
        # Fix round 1: scripts/matte.py (Task 16b) puts the matte on a constant-frame-rate,
        # even-sized timeline. Callers must decode the ORIGINAL footage through matte.json's
        # retime_filter at its fps and width/height, and run the CLI with the studio's progress
        # flags. There is no RGBA frames folder, and the outputs are not "the clip's own timing".
        for item in self.data['looks']:
            if not item['requires_matte']:
                continue
            text = item['instructions']
            for needle in ('python scripts/matte.py', '--progress', '--step', 'matte.json', 'retime_filter', 'width/height', 'fps'):
                self.assertIn(needle, text, item['id'] + ': missing ' + needle)
            self.assertIn('scale=trunc(iw/2)*2:trunc(ih/2)*2', text, item['id'] + ': use matte.py normalize() filter')
            for false_claim in ('frames folder', 'same size and timing', 'RGBA frames', 'crop=<width>', 'crop it to', 'cropped to'):
                self.assertNotIn(false_claim, text, item['id'])
        agents = (Path(__file__).resolve().parents[1] / 'AGENTS.md').read_text(encoding='utf-8')
        section = agents[agents.index('## Effects and presenter looks'):]
        section = section[:section.index(chr(10) + '## ', 1)]
        for needle in ('retime_filter', '--progress', '--step', 'width/height', 'scale=trunc(iw/2)*2:trunc(ih/2)*2'):
            self.assertIn(needle, section)

    def test_every_demo_exists_in_fx_demos_js(self):
        registered = demo_registry_keys()
        self.assertEqual(len(registered), len(set(registered)), 'a demo id is registered twice')
        missing = [item['id'] for item in self.all if item['demo'] not in registered]
        self.assertEqual(missing, [])

    def test_every_label_key_exists_in_both_languages(self):
        he, en = i18n('he'), i18n('en')
        missing = []
        for item in self.all:
            for key in (item['name_key'], item['desc_key'], 'fx.cat.' + item['category']):
                if key not in he:
                    missing.append('he: ' + key)
                if key not in en:
                    missing.append('en: ' + key)
        self.assertEqual(missing, [])

    def test_ids_helpers(self):
        self.assertIn('zoomthru', effects.effect_ids())
        self.assertIn('popout', effects.look_ids())
        self.assertNotIn('popout', effects.effect_ids())


class ValidationTest(unittest.TestCase):
    def write(self, folder, fx, looks):
        (folder / 'effects').mkdir()
        (folder / 'looks').mkdir()
        (folder / 'effects' / 'effects.json').write_text(json.dumps(fx), encoding='utf-8')
        (folder / 'looks' / 'presenter.json').write_text(json.dumps(looks), encoding='utf-8')
        return [patch.object(effects, 'EFFECTS_PATH', folder / 'effects' / 'effects.json'),
                patch.object(effects, 'LOOKS_PATH', folder / 'looks' / 'presenter.json')]

    def entry(self, item_id, **extra):
        return {'id': item_id, 'name_key': 'n', 'desc_key': 'd', 'category': 'type', 'demo': item_id,
                'instructions': 'x', **extra}

    def run_with(self, fx, looks):
        with tempfile.TemporaryDirectory() as tmp:
            patches = self.write(Path(tmp), fx, looks)
            for p in patches:
                p.start()
            try:
                return effects.list()
            finally:
                for p in patches:
                    p.stop()

    def test_valid_minimal_catalog(self):
        result = self.run_with([self.entry('a')], [self.entry('b', requires_matte=True)])
        self.assertEqual([e['id'] for e in result['effects']], ['a'])
        self.assertEqual([e['id'] for e in result['looks']], ['b'])

    def test_missing_field_rejected(self):
        bad = self.entry('a')
        del bad['demo']
        with self.assertRaises(ValueError):
            self.run_with([bad], [])

    def test_duplicate_id_across_catalogs_rejected(self):
        with self.assertRaises(ValueError):
            self.run_with([self.entry('a')], [self.entry('a', requires_matte=False)])

    def test_bad_id_rejected(self):
        with self.assertRaises(ValueError):
            self.run_with([self.entry('../x')], [])

    def test_look_without_requires_matte_rejected(self):
        with self.assertRaises(ValueError):
            self.run_with([], [self.entry('b')])

    def test_not_a_list_rejected(self):
        with self.assertRaises(ValueError):
            self.run_with({'effects': []}, [])


class QuietHandler(Handler):
    def log_message(self, *args):
        pass


class EffectsRouteTest(unittest.TestCase):
    def setUp(self):
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), QuietHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.host = f'127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def get(self, path, **headers):
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port)
        conn.request('GET', path, headers={'Host': self.host, **headers})
        response = conn.getresponse()
        body = response.read()
        conn.close()
        return response.status, body

    def test_get_effects_returns_both_catalogs(self):
        status, body = self.get('/effects')
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertEqual({e['id'] for e in data['effects']}, set(effects.effect_ids()))
        self.assertEqual({e['id'] for e in data['looks']}, set(effects.look_ids()))

    def test_get_effects_rejects_query_and_cross_site(self):
        self.assertEqual(self.get('/effects?x=1')[0], 400)
        self.assertEqual(self.get('/effects', **{'Sec-Fetch-Site': 'cross-site'})[0], 403)
        self.assertEqual(self.get('/effects', Origin='http://evil.example')[0], 403)

    def test_broken_catalog_is_503(self):
        with patch.object(effects, 'EFFECTS_PATH', Path(tempfile.gettempdir()) / 'no-such-effects.json'):
            self.assertEqual(self.get('/effects')[0], 503)


if __name__ == '__main__':
    unittest.main()
