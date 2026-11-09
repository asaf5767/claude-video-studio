"""Release exports fail closed when a private or symlinked file is added to the list."""
import importlib.util
import json
from pathlib import Path
import tempfile
import re
import unittest
from unittest.mock import patch

path=Path(__file__).resolve().parents[1]/'scripts/export_release.py'
spec=importlib.util.spec_from_file_location('release_export',path)
export=importlib.util.module_from_spec(spec);spec.loader.exec_module(export)
check_spec=importlib.util.spec_from_file_location('release_check',path.with_name('check_release.py'))
release_check=importlib.util.module_from_spec(check_spec);check_spec.loader.exec_module(release_check)

class ReleaseConsistencyTests(unittest.TestCase):
    def setUp(self):
        self.files=dict(export.sources())
    def test_release_versions_and_empty_seeds_agree(self):
        self.assertEqual(release_check.verify(self.files),json.loads(self.files['package.json'])['version'])
    def test_install_docs_cannot_hardcode_a_tag(self):
        for name in ['README.md','README.en.md','INSTALL_PROMPT.md','docs/PILOT.md','SETUP.md']:
            files=self.files.copy();files[name]=files[name]+b'\nUse tag v0.1.0-beta.6.\n'
            with self.subTest(name=name),self.assertRaisesRegex(ValueError,'Hardcoded installation tag'):release_check.verify(files)
    def test_one_message_install_text_is_verbatim(self):
        # Task 19: the guide on Assaf's site tells followers to paste exactly this text.
        self.assertEqual(release_check.INSTALL_MESSAGE_HE,'תשתמש בסקיל של הסטודיו לעריכת וידאו מהכתובת הזאת: https://github.com/asaf5767/claude-video-studio — תתקין את כל מה שצריך, תשאל אותי לפני כל התקנה, ותסביר לי בעברית פשוטה מה אתה עושה. כשהכל מוכן, תפתח לי את הסטודיו בדפדפן.')
        self.assertEqual(release_check.INSTALL_MESSAGE_EN,"Use the video studio skill from https://github.com/asaf5767/claude-video-studio — install everything it needs, ask me before each install, and explain in plain English what you're doing. When it's ready, open the studio in my browser.")
        he=release_check.INSTALL_MESSAGE_HE.encode();en=release_check.INSTALL_MESSAGE_EN.encode()
        for name,old,new in [('README.md',he,he.replace('בעברית פשוטה'.encode(),'בעברית'.encode())),('INSTALL_PROMPT.md',he,b''),
                             ('README.en.md',en,en.replace(b'ask me before each install, ',b'')),('INSTALL_PROMPT.md',en,en+b'\n'+en)]:
            files=self.files.copy();files[name]=files[name].replace(old,new)
            with self.subTest(name=name,new=new[:20]),self.assertRaisesRegex(ValueError,'one-message install'):release_check.verify(files)
    def test_readmes_open_with_the_claude_code_section(self):
        for name in ['README.md','README.en.md']:
            # the pointer to Claude Code's section must stay near the top
            files=self.files.copy();files[name]=b'# Title\n\n'+b'x'*700+b'\n\n'+files[name]
            with self.subTest(name=name,case='pointer'),self.assertRaisesRegex(ValueError,'If you are Claude Code'):release_check.verify(files)
            # and the section itself must exist
            files=self.files.copy();files[name]=files[name].replace(b'\n## If you are Claude Code',b'\n## Install notes')
            with self.subTest(name=name,case='section'),self.assertRaisesRegex(ValueError,'If you are Claude Code'):release_check.verify(files)
            files=self.files.copy();files[name]=files[name].replace(release_check.SETUP_SKILL.encode(),b'SETUP.md')
            with self.subTest(name=name,skill=True),self.assertRaisesRegex(ValueError,'If you are Claude Code'):release_check.verify(files)
    def test_nothing_shipped_points_updates_at_the_upstream_releases(self):
        self.assertFalse([n for n,d in self.files.items() if release_check.UPSTREAM_RELEASES.encode() in d])
        for name in ['style-library/dist/i18n/he.json','docs/UPDATING.md','scripts/check_install.py']:
            files=self.files.copy();files[name]=files[name]+b'\nhttps://github.com/'+release_check.UPSTREAM_RELEASES.encode()+b'\n'
            with self.subTest(name=name),self.assertRaisesRegex(ValueError,'upstream releases'):release_check.verify(files)
        files=self.files.copy();files['README.md']=files['README.md']+b'\nhttps://github.com/mattp68/ai-video-studio\n'
        release_check.verify(files)  # the credit link to Matt's project itself stays allowed
    def test_setup_skill_ships(self):
        self.assertIn('.claude/skills/setup-studio/SKILL.md',self.files)
        self.assertTrue(self.files['.claude/skills/setup-studio/SKILL.md'].replace(b'\r\n',b'\n').startswith(b'---\nname: setup-studio\n'))
        files=self.files.copy();del files['.claude/skills/setup-studio/SKILL.md']
        with self.assertRaisesRegex(ValueError,'setup-studio skill'):release_check.verify(files)
    def test_old_interface_cannot_ship(self):
        for name in ['style-library/dist/index.html','STATUS.md','BRIEF.md','PROJECT_CONTEXT.md']:
            files=self.files.copy();version=json.loads(files['package.json'])['version']
            files[name]=files[name].replace(version.encode(),b'0.0.0-outdated')
            with self.subTest(name=name),self.assertRaises(ValueError):release_check.verify(files)
    def test_lock_drift_is_rejected(self):
        lock=json.loads(self.files['package-lock.json']);lock['packages']['']['version']='0.0.0'
        self.files['package-lock.json']=json.dumps(lock).encode()
        with self.assertRaisesRegex(ValueError,'lock versions'):release_check.verify(self.files)
    def test_populated_starter_seeds_cannot_ship(self):
        for name,key in [('catalog','entries'),('catalog','techniques'),('projects','projects')]:
            files=self.files.copy();path='style-library/'+name+'.example.json';value=json.loads(files[path]);value[key]=[{'id':'private-owner-fixture'}];files[path]=json.dumps(value).encode()
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,'owner data'):release_check.verify(files)
    def test_look_sample_jpgs_are_in_the_real_export(self):
        magic={'.jpg':b'\xff\xd8','.png':b'\x89PNG'}
        for name in export.CLEARED_BINARIES:
            self.assertIn(name,self.files)
            self.assertTrue(self.files[name].startswith(magic[Path(name).suffix]))
    def test_internal_planning_docs_never_ship(self):
        # R44: most of docs/plan/* (and any future docs/superpowers/*) is sdd/implementation
        # scratch that the private repo tracks but never ships -- see release-internal.txt.
        # A few docs/plan/*-contract.md files ARE shipped deliberately (shipped code cites
        # them, and testers find them useful); those are covered by
        # test_ci_infrastructure_files_ship's sibling below, not excluded here.
        for name in self.files:
            self.assertFalse(name.startswith('docs/superpowers/'),name)
        for name in export.internal_paths():
            self.assertNotIn(name,self.files,name)
    def test_ci_infrastructure_files_ship(self):
        # .gitattributes and the Node test-runner scripts are real source, needed by
        # anyone who clones the repo to run the same checks CI runs -- not internal-only,
        # so (like .github/workflows/check.yml) they belong in the public release.
        for name in ['.gitattributes','scripts/check_js.mjs','scripts/run_node_tests.mjs',
                     'scripts/test_check_js.mjs','scripts/test_run_node_tests.mjs']:
            self.assertIn(name,self.files)
    def test_public_export_declares_its_own_extra_files(self):
        # The public repo commits the export as-is, so its CI's check_release --git-ref HEAD
        # must find RELEASE-MANIFEST.json declared by the release-internal.txt the export writes.
        declared={l for l in export.PUBLIC_INTERNAL.splitlines() if l and not l.startswith('#')}
        self.assertEqual(declared,{'RELEASE-MANIFEST.json','release-internal.txt'})
        for name in declared:self.assertNotIn(name,self.files)
    def test_cited_planning_contracts_ship(self):
        # R44: these three docs/plan/*.md files ship, not just stay tracked internally --
        # learn-style-contract.md is cited directly by shipped code (inspiration.py);
        # addons-contract.md and clean-machine-test.md are the maintainer's call to ship
        # too (addons-contract.md documents the addons.py/dist/addons-ui.js contract;
        # clean-machine-test.md is the setup checklist testers actually run).
        for name in ['docs/plan/addons-contract.md','docs/plan/learn-style-contract.md',
                     'docs/plan/clean-machine-test.md']:
            self.assertIn(name,self.files)

class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.patch=patch.object(export,'ROOT',self.root);self.patch.start()
        (self.root/'README.md').write_text('A clean project.', encoding='utf-8')
    def tearDown(self):self.patch.stop();self.tmp.cleanup()
    def select(self,text):(self.root/'release-files.txt').write_text(text, encoding='utf-8')
    def test_exact_allowlist_omits_unlisted_owner_data(self):
        (self.root/'private.mp4').write_bytes(b'private fixture')
        self.select('README.md\n')
        self.assertEqual([n for n,_ in export.sources()],['README.md'])
    def test_private_registry_media_and_credentials_are_rejected(self):
        legacy=self.root/'style-library/references/demo/intake.md';legacy.parent.mkdir(parents=True);legacy.write_text('Private reference notes', encoding='utf-8')
        for name in ['style-library/dist/assets/reference-previews/cover.svg','style-library/reference-notes.json','style-library/writing-voice.json','style-library/catalog.json','projects/demo/STATUS.md','references/demo/source.mp4','style-library/references/demo/intake.md','.env','secret.key','../outside.md']:
            self.select(name+'\n')
            with self.subTest(name=name),self.assertRaises(ValueError):export.sources()
    def test_only_project_skills_ship_from_dot_claude(self):
        for name in ['.claude/skills/setup-studio/SKILL.md','.claude/settings.local.json','.claude/settings.json','.claude/agents/x.md']:
            path=self.root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('---\nname: x\n---\n',encoding='utf-8')
        self.select('.claude/skills/setup-studio/SKILL.md\n')
        self.assertEqual([n for n,_ in export.sources()],['.claude/skills/setup-studio/SKILL.md'])
        for name in ['.claude/settings.local.json','.claude/settings.json','.claude/agents/x.md']:
            self.select(name+'\n')
            with self.subTest(name=name),self.assertRaisesRegex(ValueError,'Private or unsafe'):export.sources()
    def test_symlinks_and_duplicate_paths_are_rejected(self):
        (self.root/'alias.md').symlink_to(self.root/'README.md')
        for value in ['alias.md\n','README.md\nREADME.md\n']:
            self.select(value)
            with self.assertRaises(ValueError):export.sources()
    def test_secret_candidate_stops_export(self):
        (self.root/'README.md').write_text('sk-'+'x'*30, encoding='utf-8')
        self.select('README.md\n')
        with self.assertRaisesRegex(ValueError,'Credential candidate'):export.sources()
    def test_profile_paths_in_every_spelling_stop_export(self):
        # Final review I5: no shipped file may carry a user-profile path. Built from parts,
        # since this test file ships too and its own text must not hold such a path.
        for sep, head, folder in [('/', '', 'Users'), ('\\', 'C:', 'Users'), ('/', 'C:', 'Users'), ('/', '/c', 'Users'),
                                  ('\\\\', 'C:', 'Users'), ('/', '', 'home')]:
            text = sep.join([head, folder, 'bob', 'x'])
            (self.root/'README.md').write_text('see '+text, encoding='utf-8')
            self.select('README.md\n')
            with self.subTest(text=text),self.assertRaisesRegex(ValueError,'Personal absolute path'):export.sources()
        for text in ['~/x', '/Users/<name>/', '%USERPROFILE%\\.claude', '/usr/bin/env']:
            (self.root/'README.md').write_text('see '+text, encoding='utf-8')
            self.select('README.md\n')
            with self.subTest(text=text):self.assertEqual(len(export.sources()),1)
    def test_the_owner_account_name_stops_export(self):
        # The real name is only a hash in export_release.py; plant a stand-in name's hash.
        import hashlib
        with patch.object(export,'PRIVATE_NAME_SHA256',{hashlib.sha256(b'someowner').hexdigest()}):
            for text in ['by SomeOwner', 'path someowner-wt/x', 'clone of someowner']:
                (self.root/'README.md').write_text(text, encoding='utf-8')
                self.select('README.md\n')
                with self.subTest(text=text),self.assertRaisesRegex(ValueError,'account name'):export.sources()
            (self.root/'README.md').write_text('someowners are fine', encoding='utf-8')
            self.assertEqual(len(export.sources()),1)
        self.assertEqual(len(export.PRIVATE_NAME_SHA256),1)
    def test_cleared_look_sample_jpgs_export(self):
        for name in export.CLEARED_BINARIES:
            path=self.root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'\xff\xd8\xff\xe0fakejpeg')
        self.select('\n'.join(sorted(export.CLEARED_BINARIES))+'\n')
        exported={n for n,_ in export.sources()}
        self.assertEqual(exported,set(export.CLEARED_BINARIES))
    def test_other_jpgs_are_still_rejected(self):
        (self.root/'other.jpg').write_bytes(b'\xff\xd8\xff\xe0fakejpeg')
        self.select('other.jpg\n')
        with self.assertRaisesRegex(ValueError,'Uncleared binary'):export.sources()
        (self.root/'looks').mkdir();(self.root/'looks/soft').mkdir()
        (self.root/'looks/soft/other.jpg').write_bytes(b'\xff\xd8\xff\xe0fakejpeg')
        self.select('looks/soft/other.jpg\n')
        with self.assertRaisesRegex(ValueError,'Uncleared binary'):export.sources()
    def test_export_contains_the_interface_dependencies(self):
        actual=Path(__file__).resolve().parents[1]
        with patch.object(export,'ROOT',actual):
            files=dict(export.sources())
        html=files['style-library/dist/index.html'].decode()
        for name in re.findall(r'(?:src|href)="([^"?#]+\.(?:js|css))"',html):
            if name=='launch.js':continue  # Generated by start.py for this installation.
            self.assertIn('style-library/dist/'+name,files)

class InternalPathTests(unittest.TestCase):
    """R44: docs/plan/* and the uncleared presenter source photo stay tracked in git (the
    private repo cites them from shipped code / uses them for testing) but must never be
    exported. release-internal.txt is the explicit, exact-path allowlist for that -- these
    tests cover check_release.py's --git-ref tree check (check_exact_tree) and
    export_release.py's guarantee that an internal-only path never ships."""
    def test_a_tracked_internal_file_passes(self):
        release_check.check_exact_tree(
            names=['README.md','docs/plan/notes.md'],
            files={'README.md':b'ok'},
            internal={'docs/plan/notes.md'})  # must not raise
    def test_an_unlisted_tracked_file_fails(self):
        with self.assertRaisesRegex(ValueError,'Git tree differs'):
            release_check.check_exact_tree(
                names=['README.md','mystery.py'],
                files={'README.md':b'ok'},
                internal=set())
    def test_a_path_in_both_lists_fails(self):
        with self.assertRaisesRegex(ValueError,'also listed in release-files.txt'):
            release_check.check_exact_tree(
                names=['README.md','docs/plan/notes.md'],
                files={'README.md':b'ok','docs/plan/notes.md':b'internal'},
                internal={'docs/plan/notes.md'})
    def test_export_never_reads_or_ships_an_internal_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/'README.md').write_text('A clean project.',encoding='utf-8')
            (root/'docs/plan').mkdir(parents=True)
            (root/'docs/plan/notes.md').write_text('internal implementation notes',encoding='utf-8')
            (root/'release-files.txt').write_text('README.md\n',encoding='utf-8')
            (root/'release-internal.txt').write_text('# R44 internal-only\ndocs/plan/notes.md\n',encoding='utf-8')
            with patch.object(export,'ROOT',root):
                files=dict(export.sources())
            self.assertEqual(set(files),{'README.md'})
            self.assertNotIn('docs/plan/notes.md',files)
    def test_an_internal_path_also_in_release_files_txt_fails_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/'README.md').write_text('A clean project.',encoding='utf-8')
            (root/'docs/plan').mkdir(parents=True)
            (root/'docs/plan/notes.md').write_text('internal implementation notes',encoding='utf-8')
            (root/'release-files.txt').write_text('README.md\ndocs/plan/notes.md\n',encoding='utf-8')
            (root/'release-internal.txt').write_text('docs/plan/notes.md\n',encoding='utf-8')
            with patch.object(export,'ROOT',root),self.assertRaisesRegex(ValueError,'Internal-only path'):
                export.sources()
    def test_internal_paths_rejects_globs_and_unsafe_entries(self):
        import os
        absolute_bad='C:\\secrets\\passwd' if os.name=='nt' else '/etc/passwd'
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for bad in ['docs/plan/*.md',absolute_bad,'../outside.md']:
                (root/'release-internal.txt').write_text(bad+'\n',encoding='utf-8')
                with patch.object(export,'ROOT',root),self.assertRaises(ValueError):
                    export.internal_paths()
    def test_real_repo_internal_and_release_lists_stay_disjoint(self):
        # Exercises the actual committed release-internal.txt/release-files.txt together,
        # independent of the mocked ReleaseConsistencyTests.files fixture above.
        self.assertTrue(export.internal_paths())  # non-empty: R44 added real entries
        self.assertEqual(export.internal_paths()&set(dict(export.sources())),set())
