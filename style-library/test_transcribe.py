"""Task 16: local Hebrew/English word-timed transcription with whisper.cpp.

merge_tokens() turns whisper.cpp's `-ojf` sub-word tokens into words; transcribe()
drives ffmpeg + whisper-cli and refuses to clobber an existing out.json without --force.
"""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[1]
_path = REPO_ROOT / 'scripts/transcribe.py'
_spec = importlib.util.spec_from_file_location('transcribe_cli', _path)
transcribe_cli = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(transcribe_cli)

FIXTURE = REPO_ROOT / 'style-library/fixtures/whisper_he_tokens.json'


def _tok(text, start, end, **extra):
    token = {'text': text, 'offsets': {'from': start, 'to': end}}
    token.update(extra)
    return token


class MergeTokensHebrewFixtureTests(unittest.TestCase):
    def test_merge_tokens_hebrew_fixture(self):
        doc = json.loads(FIXTURE.read_text(encoding='utf-8'))
        tokens = transcribe_cli._flatten_whisper_tokens(doc)
        words = transcribe_cli.merge_tokens(tokens)
        self.assertEqual([w['text'] for w in words], ['שלום', 'לכולם', 'היום'])
        times = []
        for w in words:
            self.assertLessEqual(w['startMs'], w['endMs'])
            times.append(w['startMs'])
            times.append(w['endMs'])
        self.assertEqual(times, sorted(times))  # monotonic


class MergeTokensMixedScriptTests(unittest.TestCase):
    def test_mixed_hebrew_english_numbers(self):
        # "AI חוסך 38 שניות" -- Latin, Hebrew, digits and Hebrew each form their own word,
        # even where the BPE stream glues scripts together without a leading space.
        tokens = [
            _tok('AI', 0, 200),
            _tok(' חו', 200, 450),
            _tok('סך', 450, 600),
            _tok(' 38', 600, 750),
            _tok(' שניות', 750, 1100),
        ]
        words = transcribe_cli.merge_tokens(tokens)
        self.assertEqual([w['text'] for w in words], ['AI', 'חוסך', '38', 'שניות'])
        self.assertEqual(words[0]['startMs'], 0)
        self.assertEqual(words[-1]['endMs'], 1100)

    def test_latin_digit_boundary_without_leading_space(self):
        # A script change alone starts a new word, even with no leading-space token.
        tokens = [_tok('AI', 0, 100), _tok('38', 100, 200)]
        words = transcribe_cli.merge_tokens(tokens)
        self.assertEqual([w['text'] for w in words], ['AI', '38'])

    def test_hebrew_prefix_not_split(self):
        # A Hebrew prefix (here ו) tokenized separately from its stem has no leading
        # space and the same script class, so it stays attached to the word.
        tokens = [_tok('ו', 0, 80), _tok('שלום', 80, 400)]
        words = transcribe_cli.merge_tokens(tokens)
        self.assertEqual([w['text'] for w in words], ['ושלום'])
        self.assertEqual(words[0]['startMs'], 0)
        self.assertEqual(words[0]['endMs'], 400)

    def test_punctuation_attaches_to_preceding_word(self):
        tokens = [_tok(' שלום', 0, 300), _tok(',', 300, 300), _tok(' להתראות', 300, 700)]
        words = transcribe_cli.merge_tokens(tokens)
        self.assertEqual([w['text'] for w in words], ['שלום,', 'להתראות'])

    def test_special_tokens_are_skipped(self):
        tokens = [_tok(' שלום', 0, 300), _tok('[_TT_30]', 300, 300), _tok(' עולם', 300, 600)]
        words = transcribe_cli.merge_tokens(tokens)
        self.assertEqual([w['text'] for w in words], ['שלום', 'עולם'])


class RefusesOverwriteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name) / 'out.json'
        self.out.write_text('[]', encoding='utf-8')

    def tearDown(self):
        self.tmp.cleanup()

    def test_refuses_overwrite_without_force(self):
        with self.assertRaises(transcribe_cli.TranscribeError) as ctx:
            transcribe_cli.transcribe(Path('media.mp4'), self.out, 'he')
        self.assertEqual(ctx.exception.code, 'transcribe.exists')

    def test_force_bypasses_existing_out_check(self):
        # With --force, the existing-file guard is skipped entirely and execution
        # proceeds to engine resolution (which fails fast here since none is installed
        # in this sandbox) -- proving the refusal above was specifically about the
        # missing --force, not something else.
        with patch.object(transcribe_cli, '_whisper_binary', side_effect=transcribe_cli.TranscribeError('transcribe.no-engine', 'x')):
            with self.assertRaises(transcribe_cli.TranscribeError) as ctx:
                transcribe_cli.transcribe(Path('media.mp4'), self.out, 'he', force=True)
        self.assertEqual(ctx.exception.code, 'transcribe.no-engine')


class CodedErrorsTests(unittest.TestCase):
    def test_no_engine_is_a_coded_error_not_a_traceback(self):
        with patch.object(transcribe_cli.shutil, 'which', return_value=None):
            with patch.object(Path, 'is_file', return_value=False):
                with self.assertRaises(transcribe_cli.TranscribeError) as ctx:
                    transcribe_cli._whisper_binary()
        self.assertEqual(ctx.exception.code, 'transcribe.no-engine')

    def test_model_missing_is_a_coded_error(self):
        with patch.object(Path, 'is_file', return_value=False):
            with self.assertRaises(transcribe_cli.TranscribeError) as ctx:
                transcribe_cli._model_path('he')
        self.assertEqual(ctx.exception.code, 'transcribe.model-missing')


class CommandUsesLanguageAndModelTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name) / 'out.json'
        self.media = Path(self.tmp.name) / 'media.mp4'
        self.media.write_bytes(b'fake')
        self.model = Path(self.tmp.name) / 'model.bin'
        self.model.write_bytes(b'fake-model')
        self.whisper_bin = Path(self.tmp.name) / 'whisper-cli'
        self.whisper_bin.write_bytes(b'fake-bin')

    def tearDown(self):
        self.tmp.cleanup()

    def test_command_uses_language_and_model(self):
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            if cmd[0] == 'ffmpeg-path':
                return subprocess.CompletedProcess(cmd, 0)
            # whisper-cli call: write the json output it was told to produce (-of <prefix>)
            prefix = Path(cmd[cmd.index('-of') + 1])
            doc = json.loads(FIXTURE.read_text(encoding='utf-8'))
            prefix.with_suffix('.json').write_text(json.dumps(doc), encoding='utf-8')
            return subprocess.CompletedProcess(cmd, 0)

        with patch.object(transcribe_cli, '_whisper_binary', return_value=self.whisper_bin), \
             patch.object(transcribe_cli, '_model_path', return_value=self.model), \
             patch.object(transcribe_cli.tools, 'resolve', return_value='ffmpeg-path'), \
             patch.object(transcribe_cli.subprocess, 'run', side_effect=fake_run):
            words = transcribe_cli.transcribe(self.media, self.out, 'he')

        self.assertEqual([w['text'] for w in words], ['שלום', 'לכולם', 'היום'])
        whisper_call = calls[1]
        self.assertEqual(whisper_call[0], str(self.whisper_bin))
        self.assertIn('-m', whisper_call)
        self.assertEqual(whisper_call[whisper_call.index('-m') + 1], str(self.model))
        self.assertIn('-l', whisper_call)
        self.assertEqual(whisper_call[whisper_call.index('-l') + 1], 'he')
        self.assertIn('-ojf', whisper_call)
        self.assertTrue(self.out.is_file())
        self.assertEqual(json.loads(self.out.read_text(encoding='utf-8')), words)


class Utf8SplitAcrossTokensTests(unittest.TestCase):
    """whisper.cpp's -ojf writer can split a multi-byte character's bytes across two
    (or more) adjacent tokens (ggml-org/whisper.cpp#1798); each piece is individually
    invalid UTF-8, so the raw file on disk is not valid UTF-8 either."""

    def _split_token_pair(self, prefix, word, start=0, step=120):
        # Splits word[0]'s UTF-8 encoding after its first byte, mirroring the real bug
        # report's byte window (a lone lead byte as one token's whole text).
        full = word.encode('utf-8')
        first_char_bytes = word[0].encode('utf-8')
        self.assertGreaterEqual(len(first_char_bytes), 2, 'need a multi-byte first character')
        piece_a = (prefix.encode('utf-8') + first_char_bytes[:1])
        piece_b = (first_char_bytes[1:] + full[len(first_char_bytes):])
        token_a = {'text': piece_a.decode('utf-8', errors='surrogateescape'),
                   'offsets': {'from': start, 'to': start + step}}
        token_b = {'text': piece_b.decode('utf-8', errors='surrogateescape'),
                   'offsets': {'from': start + step, 'to': start + 2 * step}}
        return token_a, token_b

    def test_repair_tokens_rejoins_a_split_hebrew_character(self):
        token_a, token_b = self._split_token_pair(' ', 'שלום')
        repaired = transcribe_cli._repair_tokens([token_a, token_b])
        self.assertEqual(len(repaired), 1)
        self.assertEqual(repaired[0]['text'], ' שלום')
        self.assertEqual(repaired[0]['offsets'], {'from': 0, 'to': 240})

    def test_repair_tokens_leaves_clean_tokens_alone(self):
        tokens = [_tok(' שלום', 0, 300), _tok(' עולם', 300, 600)]
        repaired = transcribe_cli._repair_tokens(tokens)
        self.assertEqual([t['text'] for t in repaired], [' שלום', ' עולם'])

    def test_real_whisper_json_file_with_a_split_hebrew_character_decodes_and_merges(self):
        # Builds the exact on-disk shape of the real bug: a JSON file that is not valid
        # UTF-8 because one token's "text" field is a lone, unpaired UTF-8 lead byte.
        token_a, token_b = self._split_token_pair(' ', 'שלום')
        doc = {'transcription': [{'tokens': [token_a, token_b, _tok(' לכולם', 240, 600)]}]}
        dumped = json.dumps(doc, ensure_ascii=False)
        raw_bytes = dumped.encode('utf-8', errors='surrogateescape')
        with self.assertRaises(UnicodeDecodeError):
            raw_bytes.decode('utf-8')  # confirm the file really is invalid UTF-8 on disk

        tmp = tempfile.TemporaryDirectory()
        try:
            path = Path(tmp.name) / 'out.json'
            path.write_bytes(raw_bytes)
            loaded = transcribe_cli._read_whisper_json(path)  # must not raise
            tokens = transcribe_cli._repair_tokens(transcribe_cli._flatten_whisper_tokens(loaded))
            words = transcribe_cli.merge_tokens(tokens)
        finally:
            tmp.cleanup()
        self.assertEqual([w['text'] for w in words], ['שלום', 'לכולם'])

    def test_unrepairable_garbage_falls_back_to_replace_without_raising(self):
        # A lone, never-completed UTF-8 lead byte (0xC3 expects one continuation byte
        # that never comes) with nothing after it and no next token to pull bytes from:
        # no amount of joining can produce valid UTF-8, so _repair_tokens must still
        # return (not hang/raise) -- per review finding (a)/controller ruling R32, the
        # U+FFFD placeholder is dropped from the text entirely (not left visible), and
        # the token's own timing is kept rather than discarded.
        lone_lead_byte_text = bytes([0xC3]).decode('utf-8', errors='surrogateescape')
        tokens = [{'text': lone_lead_byte_text, 'offsets': {'from': 0, 'to': 100}}]
        repaired = transcribe_cli._repair_tokens(tokens)
        self.assertEqual(len(repaired), 1)
        self.assertEqual(repaired[0]['text'], '')
        self.assertEqual(repaired[0]['offsets'], {'from': 0, 'to': 100})

    def test_lone_invalid_byte_never_merges_into_neighbouring_space_led_words(self):
        # Review finding (a): a garbled token followed by two ordinary space-led words
        # must stay 3 separate repaired entries -- the garbage must never be fused into
        # either neighbour, even though the old (round-1) implementation merged
        # whatever came next regardless of its leading space.
        garbage = {'text': bytes([0xC3]).decode('utf-8', errors='surrogateescape'),
                   'offsets': {'from': 0, 'to': 50}}
        tokens = [garbage, _tok(' שלום', 50, 350), _tok(' עולם', 350, 650)]
        repaired = transcribe_cli._repair_tokens(tokens)
        self.assertEqual(len(repaired), 3)
        self.assertEqual(repaired[0]['text'], '')  # garbage resolved alone, not merged
        self.assertEqual(repaired[1]['text'], ' שלום')  # untouched, not garbled
        self.assertEqual(repaired[2]['text'], ' עולם')  # untouched, not garbled
        # merge_tokens then sees exactly the two real words -- the empty-text garbage
        # token contributes nothing (same rule that already skips whitespace tokens).
        words = transcribe_cli.merge_tokens(repaired)
        self.assertEqual([w['text'] for w in words], ['שלום', 'עולם'])

    def test_incomplete_split_followed_by_a_space_led_token_does_not_merge(self):
        # Review finding (a), third case: the first piece alone is a *plausibly
        # completable* incomplete sequence (a real Hebrew lead byte, not an impossible
        # byte) -- but the very next token starts a new word, so it must still refuse
        # to extend into it, regardless of how "completable" the sequence looks.
        lead_byte_of_shin = ' שלום'[1].encode('utf-8')[0]  # a real 2-byte Hebrew lead byte
        incomplete = {'text': bytes([lead_byte_of_shin]).decode('utf-8', errors='surrogateescape'),
                      'offsets': {'from': 0, 'to': 50}}
        tokens = [incomplete, _tok(' עולם', 50, 350)]
        repaired = transcribe_cli._repair_tokens(tokens)
        self.assertEqual(len(repaired), 2)
        self.assertEqual(repaired[0]['text'], '')
        self.assertEqual(repaired[1]['text'], ' עולם')

    def test_three_byte_character_split_across_three_tokens(self):
        # A 3-byte UTF-8 character (CJK, not Hebrew) split one byte per token, to prove
        # the repair loop isn't limited to a single 2-byte merge.
        char_bytes = '中'.encode('utf-8')
        self.assertEqual(len(char_bytes), 3)
        tokens = [
            {'text': ' ' + bytes([char_bytes[0]]).decode('utf-8', errors='surrogateescape'),
             'offsets': {'from': 0, 'to': 50}},
            {'text': bytes([char_bytes[1]]).decode('utf-8', errors='surrogateescape'),
             'offsets': {'from': 50, 'to': 100}},
            {'text': bytes([char_bytes[2]]).decode('utf-8', errors='surrogateescape') + '話',
             'offsets': {'from': 100, 'to': 150}},
        ]
        repaired = transcribe_cli._repair_tokens(tokens)
        self.assertEqual(len(repaired), 1)
        self.assertEqual(repaired[0]['text'], ' 中話')
        self.assertEqual(repaired[0]['offsets'], {'from': 0, 'to': 150})

    def test_smuggled_latin1_byte_pair_is_repaired(self):
        # Review finding (b): whisper.cpp can also smuggle a split byte through as the
        # literal Unicode codepoint matching its numeric value (U+0080-U+00FF) instead
        # of as a raw invalid byte -- so the file parses as ordinary-looking JSON with
        # no UTF-8 error at all, and the corruption is purely semantic (mojibake).
        # "×" ("×") is byte 0xD7, a real Hebrew UTF-8 lead byte; "\u0090" is byte
        # 0x90, a real UTF-8 continuation byte. 0xD7 0x90 decodes to 'א' (aleph).
        expected_char = bytes([0xD7, 0x90]).decode('utf-8')
        token_a = {'text': '×', 'offsets': {'from': 0, 'to': 120}}
        token_b = {'text': '\u0090' + 'לום', 'offsets': {'from': 120, 'to': 240}}
        # Confirm this really is the "parses fine, but wrong" disguise: no decode error.
        json.dumps({'a': token_a['text'], 'b': token_b['text']}).encode('utf-8').decode('utf-8')

        repaired = transcribe_cli._repair_tokens([token_a, token_b])
        self.assertEqual(len(repaired), 1)
        self.assertEqual(repaired[0]['text'], expected_char + 'לום')
        self.assertEqual(repaired[0]['offsets'], {'from': 0, 'to': 240})

    def test_smuggled_latin1_byte_respects_word_boundary(self):
        # Same disguise as above, but the next token starts a new word, so there's no
        # continuation byte available to validate against -- review round 3: this must
        # leave the literal "×" untouched (not delete it), since it can no longer be
        # confirmed as a disguised byte at all, not merely "blocked from merging".
        token_a = {'text': '×', 'offsets': {'from': 0, 'to': 120}}
        token_b = _tok(' עולם', 120, 420)
        repaired = transcribe_cli._repair_tokens([token_a, token_b])
        self.assertEqual(len(repaired), 2)
        self.assertEqual(repaired[0]['text'], '×')
        self.assertEqual(repaired[1]['text'], ' עולם')

    def test_literal_multiplication_sign_between_digits_is_untouched(self):
        # Review round 3: '3' + '×4' (one token) must not be corrupted -- '4' is not a
        # UTF-8 continuation byte, so "×" here is ordinary text, not a disguised lead byte.
        tokens = [_tok('3', 0, 50), _tok('×4', 50, 150)]
        repaired = transcribe_cli._repair_tokens(tokens)
        self.assertEqual([t['text'] for t in repaired], ['3', '×4'])

    def test_literal_multiplication_sign_alone_is_untouched(self):
        # Review round 3: '3' + ' ×' + ' 4' -- the "×" token has no following character
        # of its own, and the next token starts a new word, so there's nothing to
        # validate against; it must stay the literal "×", not be deleted.
        tokens = [_tok('3', 0, 50), _tok(' ×', 50, 100), _tok(' 4', 100, 150)]
        repaired = transcribe_cli._repair_tokens(tokens)
        self.assertEqual([t['text'] for t in repaired], ['3', ' ×', ' 4'])

    def test_osterreich_with_latin1_o_umlaut_is_untouched(self):
        # Review round 3: 'Ö' (U+00D6) numerically matches a disguised Hebrew lead byte
        # too, but 's' is not a UTF-8 continuation byte -- ordinary German text must
        # survive completely unchanged.
        tokens = [_tok(' Österreich', 0, 400)]
        repaired = transcribe_cli._repair_tokens(tokens)
        self.assertEqual(repaired[0]['text'], ' Österreich')

    def test_multiplication_sign_before_a_space_led_hebrew_word_is_untouched(self):
        # Review round 3's explicit case: "×" followed by a space-led Hebrew word --
        # must stay exactly as written, not merged and not deleted.
        tokens = [_tok('×', 0, 50), _tok(' שלום', 50, 350)]
        repaired = transcribe_cli._repair_tokens(tokens)
        self.assertEqual([t['text'] for t in repaired], ['×', ' שלום'])


class NoFfmpegCodedErrorTests(unittest.TestCase):
    def test_missing_ffmpeg_is_a_coded_error_not_a_traceback(self):
        with patch.object(transcribe_cli.tools, 'resolve', side_effect=transcribe_cli.tools.ToolMissing('ffmpeg')):
            with self.assertRaises(transcribe_cli.TranscribeError) as ctx:
                transcribe_cli._ffmpeg_binary()
        self.assertEqual(ctx.exception.code, 'transcribe.no-ffmpeg')

    def test_transcribe_surfaces_no_ffmpeg_not_a_tools_exception(self):
        tmp = tempfile.TemporaryDirectory()
        try:
            out = Path(tmp.name) / 'out.json'
            media = Path(tmp.name) / 'media.mp4'
            media.write_bytes(b'fake')
            with patch.object(transcribe_cli, '_whisper_binary', return_value=Path('whisper-cli')), \
                 patch.object(transcribe_cli, '_model_path', return_value=Path('model.bin')), \
                 patch.object(transcribe_cli.tools, 'resolve', side_effect=transcribe_cli.tools.ToolMissing('ffmpeg')):
                with self.assertRaises(transcribe_cli.TranscribeError) as ctx:
                    transcribe_cli.transcribe(media, out, 'he')
            self.assertEqual(ctx.exception.code, 'transcribe.no-ffmpeg')
        finally:
            tmp.cleanup()


class ThreadFlagAndStderrTailTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_run_whisper_passes_thread_flag(self):
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            prefix = Path(cmd[cmd.index('-of') + 1])
            prefix.with_suffix('.json').write_text('{"transcription":[]}', encoding='utf-8')
            return subprocess.CompletedProcess(cmd, 0)

        with patch.object(transcribe_cli.subprocess, 'run', side_effect=fake_run):
            transcribe_cli._run_whisper(Path('whisper-cli'), Path('model.bin'), 'he', Path('audio.wav'), self.tmp_dir)
        cmd = calls[0]
        self.assertIn('-t', cmd)
        expected = str(min(transcribe_cli.os.cpu_count() or 4, 8))
        self.assertEqual(cmd[cmd.index('-t') + 1], expected)

    def test_run_whisper_failure_surfaces_coded_error_with_stderr_tail(self):
        error = subprocess.CalledProcessError(1, ['whisper-cli'], output=b'', stderr=b'warm-up\nreal cause: bad model file\n')
        with patch.object(transcribe_cli.subprocess, 'run', side_effect=error):
            with self.assertRaises(transcribe_cli.TranscribeError) as ctx:
                transcribe_cli._run_whisper(Path('whisper-cli'), Path('model.bin'), 'he', Path('audio.wav'), self.tmp_dir)
        self.assertEqual(ctx.exception.code, 'transcribe.failed')
        self.assertIn('real cause: bad model file', ctx.exception.message)

    def test_to_wav_failure_surfaces_coded_error_with_stderr_tail(self):
        error = subprocess.CalledProcessError(1, ['ffmpeg'], output=b'', stderr=b'Unknown decoder\n')
        with patch.object(transcribe_cli, '_ffmpeg_binary', return_value='ffmpeg'), \
             patch.object(transcribe_cli.subprocess, 'run', side_effect=error):
            with self.assertRaises(transcribe_cli.TranscribeError) as ctx:
                transcribe_cli._to_wav(Path('media.mp4'), self.tmp_dir)
        self.assertEqual(ctx.exception.code, 'transcribe.failed')
        self.assertIn('Unknown decoder', ctx.exception.message)


if __name__ == '__main__':
    unittest.main()
