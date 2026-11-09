"""Task 17: the three project skills (.claude/skills/*/SKILL.md) that Claude Code runs headless
from the studio's "Send to Claude" button. scripts/check_skills.py holds them to the
contracts the rest of the studio relies on; these tests run it on the real skills and prove
it catches each kind of drift on synthetic copies."""
import importlib.util
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location('studio_check_skills', REPO_ROOT / 'scripts/check_skills.py')
check_skills = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check_skills)


class RealSkillsTests(unittest.TestCase):
    def test_the_shipped_skills_pass(self):
        self.assertEqual(check_skills.check(REPO_ROOT), [])

    def test_step_lists_match_the_brief_and_the_progress_helper(self):
        self.assertEqual(check_skills.FIXED_STEPS, {
            'talking-head': ['ingest', 'transcribe', 'cut', 'captions', 'graphics', 'sound', 'storyboard'],
            'faceless-reel': ['voice', 'transcribe', 'scenes', 'captions', 'sound', 'storyboard'],
            'learn-style': ['watch', 'analyze', 'card']})
        _p = importlib.util.spec_from_file_location('studio_progress', REPO_ROOT / 'scripts/progress.py')
        progress = importlib.util.module_from_spec(_p)
        _p.loader.exec_module(progress)
        self.assertEqual(progress.STEPS, check_skills.FIXED_STEPS)

    def test_the_runner_starts_exactly_these_skills(self):
        import claude_runner
        self.assertEqual(set(claude_runner.SKILL_BY_KIND.values()) | {'learn-style'}, set(check_skills.FIXED_STEPS))
        self.assertEqual(check_skills.allowed_prefixes(REPO_ROOT, 'learn-style'), [])  # R53: no shell
        self.assertEqual(check_skills.allowed_prefixes(REPO_ROOT, 'talking-head'),
                         check_skills.allowed_prefixes(REPO_ROOT, 'faceless-reel'))
        studio = claude_runner.studio_path()
        self.assertEqual([p.replace(f'"{studio}/', '').replace('.py"', '.py')
                          for p in claude_runner.bash_prefixes('edit')],
                         check_skills.allowed_prefixes(REPO_ROOT, 'talking-head'))

    def test_cli(self):
        done = subprocess.run([sys.executable, str(REPO_ROOT / 'scripts/check_skills.py')],
                              capture_output=True, text=True, encoding='utf-8', cwd=REPO_ROOT)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)


class DriftTests(unittest.TestCase):
    """A copy of the real skills with one thing broken at a time."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        for folder in ('.claude/skills', 'docs/skills', 'scripts'):
            shutil.copytree(REPO_ROOT / folder, self.root / folder)
        (self.root / 'style-library').mkdir()
        shutil.copy2(REPO_ROOT / 'style-library/claude_runner.py', self.root / 'style-library/claude_runner.py')
        self.assertEqual(check_skills.check(self.root), [])

    def tearDown(self):
        self.tmp.cleanup()

    def edit(self, skill, old, new, count=1):
        path = self.root / '.claude/skills' / skill / 'SKILL.md'
        text = path.read_text(encoding='utf-8')
        self.assertIn(old, text)
        path.write_text(text.replace(old, new, count), encoding='utf-8')

    def problems(self):
        return '\n'.join(check_skills.check(self.root))

    def test_missing_front_matter_name(self):
        self.edit('learn-style', 'name: learn-style\n', '')
        self.assertIn('learn-style: front matter needs name: learn-style', self.problems())

    def test_description_must_say_when_to_use(self):
        self.edit('faceless-reel', 'description: Use when', 'description: Makes')
        self.assertIn('faceless-reel: description must start with "Use when"', self.problems())

    def test_unknown_script_path(self):
        self.edit('talking-head', 'scripts/prepare_media.py', 'scripts/prepare_everything.py', count=10)
        self.assertIn('talking-head: mentions scripts/prepare_everything.py, which does not exist', self.problems())

    def test_wrong_step_order(self):
        self.edit('talking-head', '`captions` → `graphics`', '`graphics` → `captions`')
        self.assertIn('talking-head: progress steps', self.problems())

    def test_unknown_progress_key_in_a_command(self):
        self.edit('talking-head', 'Progress steps:',
                  '`python "<studio>/scripts/progress.py" "projects/<id>/progress.json" chop running "x"`' + chr(10) * 2
                  + 'Progress steps:')
        self.assertIn("talking-head: progress step 'chop' is not one of", self.problems())

    def test_command_outside_the_allowlist(self):
        self.edit('faceless-reel', 'python "<studio>/scripts/hf.py"', 'npx hyperframes', count=1)
        self.assertIn('faceless-reel: command not allowed headless: npx hyperframes', self.problems())

    def test_python3_works_but_other_interpreters_do_not(self):
        self.edit('talking-head', 'python "<studio>/scripts/prepare_media.py"', 'python3 "<studio>/scripts/prepare_media.py"')
        self.assertEqual(self.problems(), '')  # allowed for Macs without a plain `python`
        self.edit('talking-head', 'python3 "<studio>/scripts/prepare_media.py"', 'py "<studio>/scripts/prepare_media.py"')
        self.assertIn('talking-head: command not allowed headless: py "<studio>/scripts/prepare_media.py"', self.problems())

    def test_learn_style_may_show_no_command_at_all(self):
        # R53: the skill that reads other people's content never runs anything.
        self.edit('learn-style', 'Read `analysis.json`', 'Run `python "<studio>/scripts/progress.py" x` and read `analysis.json`')
        self.assertIn('learn-style: this skill runs no commands', self.problems())

    def test_a_relative_helper_path_is_refused(self):
        # G1: a helper must be named by the studio folder, never as python scripts/...
        self.edit('talking-head', 'python "<studio>/scripts/prepare_media.py"', 'python scripts/prepare_media.py')
        self.assertIn('talking-head: name the helper by the studio folder', self.problems())

    def test_a_helper_not_listed_in_the_runner_is_not_allowed(self):
        self.edit('talking-head', 'python "<studio>/scripts/prepare_media.py"', 'python "<studio>/scripts/setup.py"')
        self.assertIn('talking-head: command not allowed headless: python scripts/setup.py', self.problems())

    def test_hf_subcommands_other_than_check_and_render_are_not_allowed(self):
        self.edit('faceless-reel', 'python "<studio>/scripts/hf.py" check', 'python "<studio>/scripts/hf.py" publish', count=1)
        self.assertIn('faceless-reel: command not allowed headless: python scripts/hf.py publish', self.problems())

    def test_raw_ffmpeg_is_not_allowed_headless(self):
        # RULING R51: ffmpeg/ffprobe only through scripts/media.py.
        self.edit('talking-head', 'python "<studio>/scripts/matte.py"', 'ffmpeg -i x.mp4 -c copy', count=1)
        self.assertIn('talking-head: command not allowed headless: ffmpeg -i x.mp4 -c copy', self.problems())

    def test_a_documented_media_command_must_pass_media_py(self):
        path = self.root / 'docs/skills/review-loop.md'
        text = path.read_text(encoding='utf-8')
        self.assertIn('ffmpeg -nostdin -v error -n -ss 2.40', text)
        path.write_text(text.replace('ffmpeg -nostdin -v error -n -ss 2.40', 'ffmpeg -nostdin -v error -y -ss 2.40'),
                        encoding='utf-8')
        self.assertIn('talking-head: media.py would refuse:', self.problems())

    def test_editing_skills_read_look_json_not_the_inspiration(self):
        # Round 4: an inspiration look reaches an editing run only as the studio's look.json.
        self.edit('talking-head', '`projects/<id>/look.json`', '`references/<id>/style-card.md`')
        problems = self.problems()
        self.assertIn('talking-head: SKILL.md points at an inspiration file', problems)

    def test_text_is_data_rule_required(self):
        self.edit('learn-style', 'never instructions', 'not orders', count=10)
        self.assertIn('learn-style: missing rule: text is data', self.problems())

    def test_hf_check_and_render_name_the_version_folder(self):
        self.edit('talking-head', 'python "<studio>/scripts/hf.py" check "projects/<id>/versions/v01"', 'python "<studio>/scripts/hf.py" check')
        self.assertIn('talking-head: hf.py check needs the version folder', self.problems())

    def test_progress_starts_before_the_project_is_read(self):
        text = (self.root / '.claude/skills/faceless-reel/SKILL.md').read_text(encoding='utf-8')
        start = 'First of all, before reading anything: `python "<studio>/scripts/progress.py" "projects/<id>/progress.json" --start faceless-reel` (the studio shows the run at once). '
        self.assertIn(start, text)
        self.edit('faceless-reel', start, '')
        self.edit('faceless-reel', '## 1. voice', start + '\n\n## 1. voice')
        self.assertIn('faceless-reel: start progress (--start) before reading the project', self.problems())

    def test_bidi_rule_required(self):
        self.edit('talking-head', '<bdi', '<span', count=10)
        self.assertIn('talking-head: missing rule: bidi', self.problems())

    def test_hevc_rule_required(self):
        self.edit('faceless-reel', 'HEVC', 'video', count=10)
        self.assertIn('faceless-reel: missing rule: HEVC', self.problems())

    def test_addons_rule_required(self):
        self.edit('faceless-reel', 'STUDIO_VOICE_KEY', 'a key', count=10)
        self.assertIn('faceless-reel: missing rule: add-ons', self.problems())

    def test_faceless_reads_the_voice_tag_first(self):
        self.edit('faceless-reel', 'tagged `voice`', 'marked as voice')
        self.assertIn('faceless-reel: missing rule: voice tag', self.problems())

    def test_addon_clients_are_optional_files_but_must_be_named(self):
        self.edit('talking-head', 'scripts/addons_voice.py', 'a voice script', count=10)
        self.assertIn('talking-head: missing rule: add-ons', self.problems())

    def test_learn_style_technique_only_rule_required(self):
        self.edit('learn-style', 'logo', 'brand', count=10)
        self.assertIn('learn-style: missing rule: technique only', self.problems())

    def test_learn_style_never_writes_style_card_json(self):
        self.edit('learn-style', 'style-card.json', 'the pins file', count=10)
        self.assertIn('learn-style: missing rule: pins', self.problems())


if __name__ == '__main__':
    unittest.main()
