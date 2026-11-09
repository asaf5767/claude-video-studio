"""Repeatable local setup; never changes global tools or overwrites owner data.

Default output is plain-language and bilingual (Hebrew first, English with --lang en
or the studio's saved UI language) -- see scripts/setup_messages.py. Nothing is
installed on this machine, or any system tool, without the owner answering yes to a
plain-language question first (or passing --yes for a non-interactive run). The old
machine-readable report is still available behind --json.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import urllib.request
from urllib.parse import urlsplit
import venv
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tools
import setup_messages

# Windows' default console code page (cp1252/cp437) cannot encode Hebrew; without this,
# printing a Hebrew message on a stock Windows terminal crashes with UnicodeEncodeError
# instead of showing the message it was trying to print. utf-8 covers both languages.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, 'reconfigure'):
        try:
            _stream.reconfigure(encoding='utf-8', errors='replace')
        except (AttributeError, ValueError, OSError):
            pass

ROOT = Path(__file__).resolve().parents[1]
PY = ROOT / '.venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
ENV = {**os.environ, 'HYPERFRAMES_NO_UPDATE_CHECK': '1', 'HYPERFRAMES_NO_TELEMETRY': '1', 'HYPERFRAMES_SKIP_SKILLS': '1'}

# winget/brew ids for the tools setup can offer to install, in the order they are
# checked/asked about. Windows has no winget package for whisper.cpp -- its own
# release zip is downloaded straight into bin/whisper/ (see ensure_whisper_engine).
TOOL_ORDER = ['node', 'ffmpeg', 'whisper-cpp']
WINGET_IDS = {'node': 'OpenJS.NodeJS.LTS', 'ffmpeg': 'Gyan.FFmpeg'}
BREW_NAMES = {'node': 'node', 'ffmpeg': 'ffmpeg', 'whisper-cpp': 'whisper-cpp'}
# v1.9.2 is pinned deliberately, not "latest": per Task 16's report, the newer tagged
# releases v1.9.3-v1.9.5 currently ship zero binary assets (only v1.9.0-v1.9.2 and the
# nightly b### tags do), so "latest" can silently 404.
# Every optional install/download setup asks about, by the name --yes-to accepts. An
# assistant asks the owner about each one in chat first, then passes exactly the ones they
# agreed to (the setup-studio skill does this); anything not listed is still asked here,
# which without a terminal to answer in means "no".
CONSENT_ITEMS = ('node', 'ffmpeg', 'whisper-cpp', 'model-he', 'model-en', 'matting')
# winget otherwise stops to ask about its source/package terms on its own, which nobody can
# answer when setup runs without a terminal. The owner has already said yes to this install.
WINGET_AGREEMENTS = ['--accept-source-agreements', '--accept-package-agreements']
WHISPER_CPP_WINDOWS_ZIP_URL = 'https://github.com/ggml-org/whisper.cpp/releases/download/v1.9.2/whisper-bin-x64.zip'

# Task 16b's chosen presenter-matte backend: HyperFrames' own local remove-background,
# which lazily needs onnxruntime-node pinned to this exact version plus this exact
# model file (see studio.config.json's `matting` key and install_matting() below).
ONNXRUNTIME_NODE_VERSION = '1.21.1'
MATTING_MODEL_URL = 'https://github.com/danielgatis/rembg/releases/download/v0.0.0/u2net_human_seg.onnx'
MATTING_MODEL_SHA256 = '01eb6a29a5c4d8edb30b56adad9bb3a2a0535338e480724a213e0acfd2d1c73c'


def run(args):
    subprocess.run([str(a) for a in args], cwd=ROOT, env=ENV, check=True)

def local_package_present(name):
    if not PY.is_file(): return False
    try:
        result = subprocess.run([str(PY), '-I', '-c',
                                 'import importlib.util,sys;sys.exit(0 if importlib.util.find_spec(sys.argv[1]) else 1)', name],
                                capture_output=True, timeout=10)
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired): return False

def node_supported():
    try:
        node = tools.resolve('node')
    except tools.ToolMissing:
        return False
    try:
        result = subprocess.run([node, '--version'], capture_output=True, text=True, timeout=10, check=True)
        version = tuple(int(part) for part in result.stdout.strip().lstrip('v').split('.'))
        return len(version) == 3 and version >= (22, 12, 0)
    except (OSError, ValueError, subprocess.SubprocessError): return False

def guard_renderer_update():
    """Never replace dependencies underneath this installation's live editors."""
    cli = ROOT/'node_modules/hyperframes/bin/hyperframes.mjs'
    if not cli.is_file(): return
    try:
        result = subprocess.run([tools.resolve('node'), str(cli), 'preview', '--list', '--json'],
                                cwd=ROOT, env=ENV, capture_output=True, text=True,
                                timeout=20, check=True)
        data = json.loads(result.stdout)
        sessions = data['result']['sessions']
        if data.get('ok') is not True or not isinstance(sessions, list): raise ValueError()
        for session in sessions:
            directory = session['projectDir']
            if not isinstance(directory, str) or not Path(directory).is_absolute(): raise ValueError()
            if Path(directory).resolve().is_relative_to(ROOT.resolve()):
                raise SystemExit('This studio has running HyperFrames previews. Media setup stopped before changing dependencies or projects. Save your work and close those previews, then rerun setup. See docs/UPDATING.md.')
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError, tools.ToolMissing):
        raise SystemExit('Could not verify running HyperFrames previews. Media setup stopped before changing dependencies or projects. Ask your assistant to inspect this installation before retrying. See docs/UPDATING.md.')

def capability_report():
    tool_checks = {t: bool(shutil.which(t)) for t in ['node', 'npm', 'ffmpeg', 'ffprobe']}
    supported_node = node_supported()
    apple_silicon = (platform.system(), platform.machine()) == ('Darwin', 'arm64')
    renderer = (ROOT/'node_modules/hyperframes/bin/hyperframes.mjs').is_file()
    pillow = local_package_present('PIL')
    speech = local_package_present('mlx_whisper') if apple_silicon else False
    registries = all((ROOT/f'style-library/{name}.json').is_file() for name in ['catalog', 'projects', 'settings'])
    ready = all(tool_checks.values()) and supported_node and renderer and pillow
    return {'python': platform.python_version(), 'platform': platform.system(), 'machine': platform.machine(),
            'tools': tool_checks, 'node_supported': supported_node, 'media_venv': PY.is_file(), 'renderer': renderer,
            'ready_for_studio': registries, 'ready_for_media': ready,
            'capabilities': {
                'studio': {'status': 'ready' if registries else 'run_setup', 'detail': 'Use --studio-only for the home base without media packages.'},
                'rendering': {'status': 'ready_for_smoke' if ready else 'missing_dependencies', 'detail': 'Dependency check only. Run scripts/smoke.py to verify an actual render and browser.'},
                'transcription': {'status': 'available' if speech else 'not_installed' if apple_silicon else 'unsupported_platform', 'detail': 'Optional --transcription on Apple Silicon macOS; model downloads on first use. Else provide a word-timed transcript.'},
                'reference_browser': {'status': 'check_in_chat', 'detail': 'Your assistant must verify its browser connection and source access. Sign in in that browser if needed; provide a file if access fails.'},
                'basic_sound_effects': {'status': 'available' if tool_checks['ffmpeg'] else 'needs_ffmpeg', 'detail': 'The assistant can synthesize simple sounds locally with code/FFmpeg. Audition the result; no paid library is required.'},
                'image_generation': {'status': 'optional_check_in_chat', 'detail': 'Use an available assistant feature, your own service, or supplied images. No image-generation account is bundled.'},
                'external_services': {'status': 'optional_user_accounts', 'detail': 'No site credentials, reference downloader or paid sound/media subscription is configured by setup.'}},
            'validation_scope': 'Full media workflow validated locally on Apple Silicon macOS. Other platforms and fresh assistant/team use remain pilot coverage.'}


# ---------------------------------------------------------------------------
# Plain-language, consent-based setup (Task 18)
# ---------------------------------------------------------------------------

def resolve_lang(explicit):
    """The message language: an explicit --lang wins, else the studio's saved UI
    language (style-library/settings.json via library.ui_language()), else Hebrew."""
    if explicit in ('he', 'en'):
        return explicit
    try:
        sys.path.insert(0, str(ROOT / 'style-library'))
        import library
        return library.ui_language()
    except (ImportError, OSError, ValueError, AttributeError):
        return 'he'

def detect_os():
    if os.name == 'nt':
        return 'windows'
    if platform.system() == 'Darwin':
        return 'mac'
    return 'other'

def plan_install_one(os_name, tool):
    """The single install command for `tool` on `os_name`, or None if there isn't one
    (e.g. whisper.cpp has no winget package; it is downloaded as a release zip)."""
    if os_name == 'windows':
        winget_id = WINGET_IDS.get(tool)
        return ['winget', 'install', '--id', winget_id, '-e'] if winget_id else None
    if os_name == 'mac':
        brew_name = BREW_NAMES.get(tool)
        return ['brew', 'install', brew_name] if brew_name else None
    return None

def plan_installs(os_name, missing):
    """The ordered list of install commands for every installable tool in `missing`."""
    ordered = [t for t in TOOL_ORDER if t in missing]
    commands = [plan_install_one(os_name, t) for t in ordered]
    return [c for c in commands if c]

def consent_for(auto_yes, item):
    """auto_yes is either a plain True/False (--yes, or ask every time) or the collection of
    CONSENT_ITEMS named with --yes-to: then only those items are pre-answered yes."""
    if isinstance(auto_yes, bool) or auto_yes is None:
        return bool(auto_yes)
    return item in auto_yes

def refresh_path(saved_entries=None):
    """A tool winget/Homebrew just installed is not on this process's PATH yet (PATH is
    read when a terminal starts), so the very next check would still call it missing.
    tools.refresh_path() appends the saved Windows PATH / Homebrew's folders; the commands
    setup runs (ENV) get the same PATH. Returns whether anything was added."""
    changed = tools.refresh_path(saved_entries)
    if changed:
        ENV['PATH'] = os.environ['PATH']
    return changed

def ask_consent(prompt_text, auto_yes):
    """Print `prompt_text` and return whether the owner agreed. --yes answers for them.
    With no one there to answer (stdin isn't a terminal -- piped/CI/non-interactive),
    or an unreadable prompt (EOF mid-read), the answer is always 'no', never a crash
    and never an install that nobody actually agreed to."""
    print(prompt_text)
    if auto_yes:
        return True
    if not sys.stdin.isatty():
        return False
    try:
        answer = input().strip().lower()
    except EOFError:
        return False
    # Accept either language's single-letter answer (scripts/setup_messages.py is the
    # source of truth for it), plus the obvious full-word spellings.
    accepted = {setup_messages.message('setup.consent-yes', 'he'), setup_messages.message('setup.consent-yes', 'en'), 'כן', 'yes'}
    return answer in accepted

def missing_installable_tools(config):
    """Tools setup can offer to install, that are not already on PATH."""
    missing = {t for t in ('node', 'ffmpeg') if not shutil.which(t)}
    engine = ((config or {}).get('transcription') or {}).get('engine')
    if engine == 'whisper.cpp' and platform.system() == 'Darwin' and not shutil.which('whisper-cli'):
        missing.add('whisper-cpp')
    return missing

def offer_consent_installs(lang, auto_yes, config):
    """Ask, per missing tool, before installing anything. Never installs without a yes."""
    missing = missing_installable_tools(config)
    if not missing:
        return
    os_name = detect_os()
    installer = {'windows': 'winget', 'mac': 'brew'}.get(os_name)
    # Resolve once to an absolute path: a bare "winget"/"brew" handed straight to
    # subprocess can fail on Windows the same way a bare "npm" does (scripts/tools.py's
    # docstring explains why). plan_installs()/plan_install_one() still RETURN the bare
    # form -- tests depend on that -- only the command we actually run is patched up.
    installer_path = shutil.which(installer) if installer else None
    if installer and not installer_path:
        print(setup_messages.message('setup.need-winget' if os_name == 'windows' else 'setup.need-brew', lang))
        return
    for tool in [t for t in TOOL_ORDER if t in missing]:
        key = f'setup.missing-tool.{tool}'
        prompt = setup_messages.message(key, lang)
        if prompt == key:
            prompt = setup_messages.message('setup.missing-tool.generic', lang).format(tool=tool)
        if not ask_consent(prompt, consent_for(auto_yes, tool)):
            print(setup_messages.message('setup.install-skipped', lang).format(tool=tool))
            continue
        command = plan_install_one(os_name, tool)
        if not command:
            continue
        if installer_path:
            command = [installer_path, *command[1:]]
        if os_name == 'windows':
            command = [*command, *WINGET_AGREEMENTS]
        print(setup_messages.message('setup.installing', lang).format(tool=tool))
        try:
            subprocess.run(command, check=True)
            refresh_path()
            print(setup_messages.message('setup.install-ok', lang).format(tool=tool))
        except (OSError, subprocess.SubprocessError):
            print(setup_messages.message('setup.install-failed', lang).format(tool=tool))

def detect_registry_block():
    """True when npm's package registry cannot be reached (npm ping fails, times out,
    or hits a TLS error) -- the common shape of a blocked corporate/VPN network."""
    try:
        npm = tools.resolve('npm')
    except tools.ToolMissing:
        return False
    try:
        result = subprocess.run([npm, 'ping'], capture_output=True, text=True, timeout=15)
        return result.returncode != 0
    except (OSError, subprocess.SubprocessError):
        return True

def ensure_npm_registry_open(lang):
    """Explain a blocked npm registry in plain words and stop cleanly -- never let a
    blocked `npm ci` surface as a raw network traceback."""
    if detect_registry_block():
        print(setup_messages.message('setup.npm-blocked', lang))
        print(setup_messages.message('setup.registry-retry', lang))
        raise SystemExit(1)

def _sha256_of(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()

def _file_matches_sha256(path, sha256):
    path = Path(path)
    return path.is_file() and _sha256_of(path).lower() == str(sha256).lower()

def download_and_verify(url, sha256, dest, lang='he'):
    """Download `url` to `dest`, verifying its SHA-256 before it replaces anything.
    A mismatch or network failure leaves no partial/incorrect file behind. Refuses
    anything but https outright -- a model/binary URL is config data, not something
    typed by a human each time, so there is no excuse for it to be plain http."""
    if urlsplit(url).scheme != 'https':
        print(setup_messages.message('setup.insecure-url', lang))
        return False
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + '.part')
    digest = hashlib.sha256()
    try:
        with urllib.request.urlopen(url, timeout=60) as response, open(tmp, 'wb') as stream:
            for chunk in iter(lambda: response.read(1024 * 1024), b''):
                digest.update(chunk)
                stream.write(chunk)
        if digest.hexdigest().lower() != str(sha256).lower():
            return False
        os.replace(tmp, dest)
        return True
    except (OSError, ValueError):
        return False
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)

def load_studio_config():
    try:
        data = json.loads((ROOT / 'studio.config.json').read_text(encoding='utf-8'))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}

def ensure_transcription_models(config, lang, auto_yes):
    """Download+verify each whisper.cpp model named in studio.config.json's
    transcription.models (Task 16). Task 16's actual shape is `models.<code>` as a
    bare relative-path string, with the url/sha256 in a sibling `model_sources.<code>`
    dict -- but a model entry that is itself a `{"path","url","sha256"}` dict (the
    brief's literal shape) is accepted too. Either way, a model missing a url/sha256
    (Task 16 still filling it in, or a plain path-only entry) is reported as pending,
    never an error."""
    transcription = (config or {}).get('transcription') or {}
    if transcription.get('engine') != 'whisper.cpp':
        return {}
    models = transcription.get('models') or {}
    sources = transcription.get('model_sources') or {}
    result = {}
    for code, entry in models.items():
        if isinstance(entry, dict):
            path, url, sha256 = entry.get('path'), entry.get('url'), entry.get('sha256')
        else:
            path = entry
            source = sources.get(code) if isinstance(sources.get(code), dict) else {}
            url, sha256 = source.get('url'), source.get('sha256')
        if not path or not url or not sha256:
            print(setup_messages.message('setup.model-pending', lang).format(model=code))
            result[code] = 'pending'
            continue
        dest = ROOT / path
        if _file_matches_sha256(dest, sha256):
            result[code] = 'installed'
            continue
        prompt = setup_messages.message('setup.model-consent', lang).format(model=code)
        if not ask_consent(prompt, consent_for(auto_yes, f'model-{code}')):
            print(setup_messages.message('setup.model-skipped', lang).format(model=code))
            result[code] = 'skipped'
            continue
        print(setup_messages.message('setup.model-downloading', lang).format(model=code))
        if download_and_verify(url, sha256, dest, lang=lang):
            print(setup_messages.message('setup.model-ok', lang).format(model=code))
            result[code] = 'installed'
        else:
            print(setup_messages.message('setup.model-checksum-mismatch', lang).format(model=code))
            result[code] = 'failed'
    return result

def download_whisper_cpp_windows(dest_dir):
    """Download the official whisper.cpp Windows release zip and extract it into
    `dest_dir` (bin/whisper/). Not unit tested against the real network -- tests patch
    this whole function; ensure_whisper_engine's consent/skip logic is what's covered."""
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    zip_path = dest_dir / 'whisper-cpp.zip'
    try:
        urllib.request.urlretrieve(WHISPER_CPP_WINDOWS_ZIP_URL, zip_path)
        with zipfile.ZipFile(zip_path) as archive:
            archive.extractall(dest_dir)
        return True
    except (OSError, ValueError, zipfile.BadZipFile):
        return False
    finally:
        if zip_path.exists():
            zip_path.unlink(missing_ok=True)

def ensure_whisper_engine(config, lang, auto_yes):
    """Windows: download whisper.cpp's own release zip into bin/whisper/ (no winget
    package exists for it). Mac: handled by offer_consent_installs' `brew install
    whisper-cpp` instead. Returns a status string, or None when there is nothing to do."""
    if ((config or {}).get('transcription') or {}).get('engine') != 'whisper.cpp':
        return None
    if platform.system() == 'Darwin':
        return None
    if os.name != 'nt':
        return None
    cli = ROOT / 'bin/whisper/whisper-cli.exe'
    if cli.is_file():
        return 'installed'
    if not ask_consent(setup_messages.message('setup.missing-tool.whisper-cpp', lang), consent_for(auto_yes, 'whisper-cpp')):
        print(setup_messages.message('setup.install-skipped', lang).format(tool='whisper.cpp'))
        return 'skipped'
    print(setup_messages.message('setup.whisper-download', lang))
    if download_whisper_cpp_windows(ROOT / 'bin/whisper'):
        print(setup_messages.message('setup.whisper-ok', lang))
        return 'installed'
    print(setup_messages.message('setup.install-failed', lang).format(tool='whisper.cpp'))
    return 'failed'

def raise_if_prerequisites_missing(lang):
    """Stop with a plain-language, bilingual message (instead of the raw tool-name
    list) when a required tool is still missing after offer_consent_installs -- either
    because it was declined, its install failed, or there was no winget/brew to use."""
    missing = [t for t in ['node', 'npm', 'ffmpeg', 'ffprobe'] if not shutil.which(t)]
    if missing:
        raise SystemExit(setup_messages.message('setup.prerequisites-missing', lang).format(tools=', '.join(missing)))

def hyperframes_cache_dir():
    """Where the pinned HyperFrames CLI looks for lazily-installed optional packages
    (onnxruntime-node) and downloaded models (background removal) -- same resolution
    HyperFrames itself uses, so setup and the renderer always agree on the location."""
    override = os.environ.get('HYPERFRAMES_CACHE_DIR')
    return Path(override) if override else Path.home() / '.cache' / 'hyperframes'

def matting_runtime_available():
    """True when onnxruntime-node, pinned to the exact version HyperFrames 0.9.16
    expects, is already installed either beside the pinned CLI (node_modules/) or in
    HyperFrames' own optional-package cache."""
    candidates = [
        ROOT / 'node_modules/onnxruntime-node/package.json',
        hyperframes_cache_dir() / 'optional' / f'onnxruntime-node@{ONNXRUNTIME_NODE_VERSION}' / 'node_modules/onnxruntime-node/package.json',
    ]
    for candidate in candidates:
        try:
            if json.loads(candidate.read_text(encoding='utf-8')).get('version') == ONNXRUNTIME_NODE_VERSION:
                return True
        except (OSError, ValueError):
            continue
    return False

def install_onnxruntime_node():
    """`npm install onnxruntime-node@<pinned> --prefix <cache>/optional/...` -- option B
    from Task 16b's report (no package.json/lock change, same command HyperFrames
    itself suggests when the optional package isn't found)."""
    target = hyperframes_cache_dir() / 'optional' / f'onnxruntime-node@{ONNXRUNTIME_NODE_VERSION}'
    try:
        npm = tools.resolve('npm')
    except tools.ToolMissing:
        return False
    try:
        target.mkdir(parents=True, exist_ok=True)
        subprocess.run([npm, 'install', f'onnxruntime-node@{ONNXRUNTIME_NODE_VERSION}', '--prefix', str(target)],
                       check=True, timeout=600)
        return True
    except (OSError, subprocess.SubprocessError):
        return False

def install_matting(config, lang='he', auto_yes=False):
    """Optional, consent-gated setup for Task 16b's presenter-look background removal:
    onnxruntime-node (pinned) + the u2net_human_seg model (~380MB total), needed only
    for the "איך אתם נראים" presenter looks (pop-out, green screen, etc.) -- never for
    the rest of the studio. A no-op whenever `matting` is absent from
    studio.config.json (it arrives via Task 16b's own branch merge, not edited here),
    or names a backend this hook doesn't know how to install yet. Never raises --
    declining, or any failure here, must never block the rest of setup."""
    matting = (config or {}).get('matting')
    if not matting:
        return None
    backend, model = matting.get('backend'), matting.get('model')
    if backend != 'hyperframes' or not model:
        return None
    model_path = hyperframes_cache_dir() / 'background-removal/models' / f'{model}.onnx'
    model_ok = _file_matches_sha256(model_path, MATTING_MODEL_SHA256)
    runtime_ok = matting_runtime_available()
    if model_ok and runtime_ok:
        return {'matting': 'installed'}
    prompt = setup_messages.message('setup.matting-consent', lang).format(model=model)
    if not ask_consent(prompt, consent_for(auto_yes, 'matting')):
        print(setup_messages.message('setup.matting-skipped', lang))
        return {'matting': 'skipped'}
    if not runtime_ok:
        print(setup_messages.message('setup.matting-installing-runtime', lang))
        runtime_ok = install_onnxruntime_node()
    if not runtime_ok:
        print(setup_messages.message('setup.install-failed', lang).format(tool='onnxruntime-node'))
        return {'matting': 'failed'}
    if not model_ok:
        print(setup_messages.message('setup.matting-downloading', lang).format(model=model))
        if download_and_verify(MATTING_MODEL_URL, MATTING_MODEL_SHA256, model_path, lang=lang):
            print(setup_messages.message('setup.matting-ok', lang).format(model=model))
        else:
            print(setup_messages.message('setup.matting-checksum-mismatch', lang).format(model=model))
            return {'matting': 'failed'}
    return {'matting': 'installed'}

def print_friendly_report(report, lang):
    """A plain-language rendering of capability_report(), defensive about a report
    missing keys (e.g. a test double) so it never raises mid-print."""
    print(setup_messages.message('setup.checking', lang))
    tool_checks = report.get('tools') or {}
    missing = [name for name in tool_checks if not tool_checks[name]]
    for name in sorted(tool_checks):
        print(('✓ ' if tool_checks[name] else '✗ ') + name)
    if missing:
        for name in missing:
            key = f'setup.missing-tool.{name}'
            text = setup_messages.message(key, lang)
            print(text if text != key else setup_messages.message('setup.missing-tool.generic', lang).format(tool=name))
    else:
        print(setup_messages.message('setup.nothing-missing', lang))
    print(setup_messages.message('setup.studio-ready-yes' if report.get('ready_for_studio') else 'setup.studio-ready-no', lang))
    print(setup_messages.message('setup.media-ready-yes' if report.get('ready_for_media') else 'setup.media-ready-no', lang))

def write_integrity_baseline():
    """Record the installed studio's files (style-library/integrity.py, RULING R51): every
    "Send to Claude" run checks them before and after. Never fails setup."""
    try:
        sys.path.insert(0, str(ROOT/'style-library'))
        import integrity
        integrity.write_baseline(ROOT)
    except Exception:  # noqa: BLE001 -- the runner writes a first baseline itself if this did not
        pass

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--studio-only', action='store_true', help='Website and data tools only; no media packages')
    parser.add_argument('--transcription', action='store_true', help='Install the optional Apple Silicon speech lock')
    parser.add_argument('--json', action='store_true', help='Print the original machine-readable report instead of plain-language messages')
    parser.add_argument('--lang', choices=['he', 'en'], help="Message language; defaults to the studio's saved UI language")
    parser.add_argument('--yes', action='store_true', help='Answer yes to every install prompt (non-interactive)')
    parser.add_argument('--yes-to', default='', metavar='ITEMS',
                        help='Comma-separated items the owner already agreed to (' + ', '.join(CONSENT_ITEMS) + '); everything else is still asked')
    args = parser.parse_args()
    yes_to = {item.strip() for item in args.yes_to.split(',') if item.strip()}
    unknown = yes_to - set(CONSENT_ITEMS)
    if unknown:
        parser.error('unknown --yes-to item(s): ' + ', '.join(sorted(unknown)) + '. Use: ' + ', '.join(CONSENT_ITEMS))
    consent = True if args.yes else (yes_to or False)
    refresh_path()  # tools installed earlier from this same window are found too
    lang = resolve_lang(args.lang)
    if sys.version_info < (3, 11): raise SystemExit('Use Python 3.11 or newer.')
    if args.transcription and (platform.system(), platform.machine()) != ('Darwin', 'arm64'):
        raise SystemExit('On-device transcription currently supports Apple Silicon macOS. Supply a transcript on other platforms.')
    if args.check:
        report = capability_report()
        if args.json:
            print(json.dumps(report, indent=2))
        else:
            print_friendly_report(report, lang)
        raise SystemExit(0 if (report['ready_for_studio'] if args.studio_only else report['ready_for_media']) else 1)
    config = load_studio_config()
    if not args.studio_only:
        offer_consent_installs(lang, consent, config)
        raise_if_prerequisites_missing(lang)
        if not node_supported():
            raise SystemExit('Node 22.12.0 or newer is required by the pinned renderer. See SETUP.md.')
        guard_renderer_update()
        if not PY.exists(): venv.EnvBuilder(with_pip=True).create(ROOT/'.venv')
        run([PY,'-m','pip','install','--require-hashes','-r','requirements.lock.txt'])
        if args.transcription:
            run([PY,'-m','pip','install','--require-hashes','-r','requirements-transcription-macos.lock.txt'])
        ensure_npm_registry_open(lang)
        run([tools.resolve('npm'),'ci','--ignore-scripts'])
        run([tools.resolve('node'), ROOT/'node_modules/hyperframes/bin/hyperframes.mjs', 'browser', 'ensure'])
        assets = ROOT/'examples/studio-check/assets'; assets.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT/'node_modules/gsap/dist/gsap.min.js', assets/'gsap.min.js')
        ensure_whisper_engine(config, lang, consent)
        ensure_transcription_models(config, lang, consent)
        install_matting(config, lang, consent)
    for name in ['catalog','projects','settings']:
        target = ROOT/f'style-library/{name}.json'
        if not target.exists(): shutil.copy2(ROOT/f'style-library/{name}.example.json',target)
    write_integrity_baseline()
    report = capability_report()
    if args.json:
        print(json.dumps(report, indent=2))
        print('Setup complete. Existing projects/settings were preserved. Start with: ' + tools.hint('style-library/start.py'))
    elif args.studio_only:
        print(setup_messages.message('setup.studio-only-done', lang).format(hint=tools.hint('style-library/start.py')))
    else:
        print(setup_messages.message('setup.done', lang))

if __name__ == '__main__': main()
