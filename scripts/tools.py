"""Windows-safe tool resolution: never call npm/npx/node/python3 by bare name.

A bare command name like 'npm' handed straight to subprocess fails on Windows
(it's an npm.CMD shim, not an .exe, and Windows' CreateProcess will not run it
without a shell); resolve() finds the real executable path with shutil.which
so subprocess can launch it directly, on any OS. python() always returns the
exact interpreter running this process (sys.executable), not a bare 'python3'
that may not exist on Windows or may resolve to a different interpreter than
the one actually installed into. hint() prints the right command for a
user-facing "run this next" message depending on the current OS.

refresh_path() covers tools installed after this process (or the window it
was started from) began: on Windows it re-reads the saved PATH from the
registry, on a Mac it adds Homebrew's folders, which a fresh Homebrew install
does not put on PATH until the shell profile is reloaded.
"""
import os
import shutil
import sys

# Homebrew's bin folders: Apple Silicon first, then Intel.
MAC_BREW_DIRS = ('/opt/homebrew/bin', '/usr/local/bin')


class ToolMissing(Exception):
    def __init__(self, name):
        super().__init__(name)
        self.name = name


def resolve(name):
    """Return the absolute path to `name`, found via shutil.which -- or, on a Mac,
    in Homebrew's folders when PATH does not include them yet."""
    found = shutil.which(name)
    if not found and sys.platform == 'darwin':
        for folder in MAC_BREW_DIRS:
            candidate = os.path.join(folder, name)
            if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                found = candidate
                break
    if not found:
        raise ToolMissing(name)
    return found


def python():
    """Return the exact Python interpreter running this process."""
    return sys.executable


def hint(script):
    """Return the right user-facing command to run `script` on this OS."""
    return ('python ' if os.name == 'nt' else 'python3 ') + script


def saved_windows_path():
    """Windows' saved machine + user PATH entries (what a brand-new terminal would get)."""
    import winreg
    entries = []
    for root, key in [(winreg.HKEY_LOCAL_MACHINE, r'SYSTEM\CurrentControlSet\Control\Session Manager\Environment'),
                      (winreg.HKEY_CURRENT_USER, 'Environment')]:
        try:
            with winreg.OpenKey(root, key) as handle:
                value, _ = winreg.QueryValueEx(handle, 'Path')
        except OSError:
            continue
        entries += [os.path.expandvars(part) for part in str(value).split(';') if part.strip()]
    return entries


def refresh_path(saved_entries=None):
    """Append PATH entries this process doesn't have yet, so a tool installed a moment
    ago (winget on Windows, Homebrew on a Mac) is found without reopening anything.
    Existing entries keep their order and win. `saved_entries` overrides the lookup
    (tests). Returns whether PATH changed; a no-op on other systems."""
    if saved_entries is None:
        if os.name == 'nt':
            try:
                saved_entries = saved_windows_path()
            except (ImportError, OSError):
                return False
        elif sys.platform == 'darwin':
            saved_entries = [folder for folder in MAC_BREW_DIRS if os.path.isdir(folder)]
        else:
            return False
    current = [part for part in os.environ.get('PATH', '').split(os.pathsep) if part]
    known = {os.path.normcase(part.rstrip('\\/')) for part in current}
    added = []
    for part in saved_entries:
        norm = os.path.normcase(part.rstrip('\\/'))
        if part and norm not in known:
            known.add(norm)
            added.append(part)
    if not added:
        return False
    os.environ['PATH'] = os.pathsep.join(current + added)
    return True
