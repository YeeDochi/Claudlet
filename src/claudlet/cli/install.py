#!/usr/bin/env python3
"""claudlet post-install setup: register the Claude Code hooks and link the
/claudlet skill into ~/.claude/skills/. Idempotent.

With a pipx/pip install the `claudlet*` commands and Python deps (PyQt6, plus
pyobjc-framework-Quartz on macOS) are already provided by the package, so this
only wires claudlet into Claude Code. Run after installing:

    claudlet-install            set up hooks + skill
    claudlet-install --remove   remove hooks + skill link (package stays)
"""
import os
import sys

from claudlet.core import agents

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_SRC = os.path.join(os.path.dirname(HERE), "skill")  # packaged skill data (claudlet/skill, not cli/skill)

# README links shown when setup finishes. EN points at the repo root (GitHub
# renders README.md there); KO points at the Korean README explicitly.
README_EN = "https://github.com/YeeDochi/Claudlet"
README_KO = "https://github.com/YeeDochi/Claudlet/blob/master/README.ko.md"
# Release notes / changelog — one bilingual page, so the same URL regardless of
# locale; only the label follows the user's language.
RELEASES = "https://github.com/YeeDochi/Claudlet/releases/latest"

_COLOR = (sys.stdout.isatty() and os.name != "nt"
          and os.environ.get("NO_COLOR") is None)


def _c(code, s):
    return "\033[%sm%s\033[0m" % (code, s) if _COLOR else s


def head(s):
    print("\n" + _c("1;36", s))


def ok(label, detail=""):
    print("  %s %s%s" % (_c("32", "+"), label,
                         ("  " + _c("2", detail)) if detail else ""))


def warn(s):
    print("  %s %s" % (_c("33", "!"), s), file=sys.stderr)


def _link_is_ours(link):
    """True if `link` already resolves to SKILL_SRC — a symlink, or a Windows
    directory junction. os.path.islink() can't see junctions (reparse points,
    not symlinks), so an install that fell back to `mklink /J` looked like
    someone else's directory to every later run, which re-warned "isn't a
    symlink" forever. samefile() follows junctions."""
    if os.path.islink(link):
        return True
    try:
        return os.path.isdir(link) and os.path.samefile(link, SKILL_SRC)
    except OSError:
        return False


def _link_skill_at(link):
    """Symlink the packaged skill into `link` (a `.../skills/claudlet` path
    under one agent's skills dir). Returns (path, note).

    The whole body is one try/except: `os.makedirs` and `os.unlink` can raise
    OSError (e.g. a read-only ~/.codex) just as easily as `os.symlink` can, and
    an unhandled one here used to escape `_link_skills()` entirely, aborting
    every OTHER agent's link too. One agent failing must only fail that agent."""
    try:
        os.makedirs(os.path.dirname(link), exist_ok=True)
        if os.path.exists(link) and not _link_is_ours(link):
            return None, ("%s exists and isn't a link to the claudlet skill"
                          " - left as-is" % link)
        if os.path.islink(link):
            os.unlink(link)  # refresh: a stale symlink may point at an old install
        elif os.path.exists(link):
            return link, None    # a junction already pointing at THIS skill — keep it
        os.symlink(SKILL_SRC, link, target_is_directory=True)
        return link, None
    except OSError as e:
        if os.name == "nt" and _link_skill_junction(link):
            return link, None
        return None, "could not link skill (%s); link it manually: %s -> %s" % (
            e, link, SKILL_SRC)


def _link_skill_junction(link):
    """Windows fallback: directory junctions don't need elevated privilege."""
    import subprocess
    try:
        subprocess.check_call(
            ["cmd", "/c", "mklink", "/J", link, SKILL_SRC],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except (OSError, subprocess.CalledProcessError):
        return False


def _unlink_skill_at(link):
    """Best-effort: one agent's link failing to remove (permissions) must not
    stop the others from being cleaned up in `_unlink_skills()`."""
    try:
        if os.path.islink(link):
            os.unlink(link)
        elif os.name == "nt" and os.path.isdir(link):
            os.rmdir(link)
    except OSError:
        pass


def _skill_link(name, home=None):
    return os.path.join(agents.skills_path(name, home), "claudlet")


def _link_skills(home=None):
    """Link the skill into every detected agent's skills dir. One agent's
    failure (permissions, a foreign directory in the way) must not stop the
    others. Returns a list of (label, path_or_None, note_or_None)."""
    results = []
    for name in agents.detected(home):
        path, note = _link_skill_at(_skill_link(name, home))
        results.append((agents.get(name)["label"], path, note))
    return results


def _unlink_skills(home=None):
    for name in agents.detected(home):
        _unlink_skill_at(_skill_link(name, home))


def _pip_install(pkgs):
    """Best-effort install for a bare source checkout that skipped `pip install`.
    Plain first (venv), then --user (system Python). A pipx/pip install already
    has the deps, so nothing runs then. Returns True on success."""
    import subprocess
    for extra in ([], ["--user"]):
        try:
            if subprocess.call(
                    [sys.executable, "-m", "pip", "install", *extra, *pkgs]) == 0:
                return True
        except Exception:
            pass
    return False


def _importable(name):
    import subprocess
    try:
        return subprocess.call([sys.executable, "-c", "import %s" % name],
                               stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL) == 0
    except Exception:
        return False


def _check_xcb_cursor():
    """Qt 6.5+ needs the libxcb-cursor system lib to load the xcb platform
    plugin. It's not a pip dep, so a fresh Linux box aborts at startup without
    it (native core-dump, not a Python error). Best-effort: apt-install it if we
    can, else point the user at their package manager. Returns a status note or
    None (not Linux / already present)."""
    if not sys.platform.startswith("linux"):
        return None
    import ctypes.util
    if ctypes.util.find_library("xcb-cursor"):
        return None
    import shutil
    import subprocess
    apt = shutil.which("apt-get")
    if apt:
        print("  installing libxcb-cursor0 (may prompt for sudo) ...")
        sudo = [] if os.geteuid() == 0 else (["sudo"] if shutil.which("sudo") else [])
        try:
            subprocess.call([*sudo, apt, "install", "-y", "libxcb-cursor0"])
        except Exception:
            pass
        if ctypes.util.find_library("xcb-cursor"):
            return "libxcb-cursor0 installed"
    warn("libxcb-cursor missing - Qt can't start without it. Install it:\n"
         "      Debian/Ubuntu:  sudo apt install libxcb-cursor0\n"
         "      Fedora:  sudo dnf install xcb-util-cursor    Arch:  sudo pacman -S xcb-util-cursor")
    return "libxcb-cursor MISSING"


def _check_deps():
    """Verify runtime deps (PyQt6; +Quartz on macOS; libxcb-cursor on Linux).
    Normally already present via the package install; only a bare source
    checkout hits the pip fallback."""
    deps = [("PyQt6", "PyQt6")]
    if sys.platform == "darwin":
        deps.append(("Quartz", "pyobjc-framework-Quartz"))
    names = ", ".join(pip for _i, pip in deps)
    missing = [(i, pip) for i, pip in deps if not _importable(i)]
    if missing:
        pkgs = [pip for _i, pip in missing]
        print("  installing %s ..." % ", ".join(pkgs))
        _pip_install(pkgs)
        still = [pip for i, pip in missing if not _importable(i)]
        if still:
            warn("could not install %s - install it with:\n      %s -m pip install %s"
                 % (", ".join(still), os.path.basename(sys.executable), " ".join(still)))
            status = "%s (%s missing)" % (names, ", ".join(still))
        else:
            status = "%s installed" % ", ".join(pkgs)
    else:
        status = "%s present" % names
    xcb = _check_xcb_cursor()
    return status + (", " + xcb if xcb else "")


def _already_installed(install_hooks):
    """True if claudlet hooks are ALREADY registered for ANY detected agent —
    i.e. this run is a reinstall/update, not a first install. Must be checked
    BEFORE install_hooks.main() runs (which registers them and would make every
    run look installed). `is_ours` also matches the pre-rename claude-pet
    markers, so upgrading from an old version still counts as an update. Any
    read error -> treat that agent as not-yet-installed (harmless) rather than
    aborting the whole check -- a corrupt file for one agent must not block
    detection (or later installation) for the others."""
    for name in agents.detected():
        try:
            s = install_hooks.load(agents.settings_path(name))
        except BaseException:
            # install_hooks.load() raises SystemExit (not just Exception) on a
            # corrupt/unreadable settings file.
            continue
        try:
            for groups in s.get("hooks", {}).values():
                if any(install_hooks.is_ours(g) for g in groups):
                    return True
        except Exception:
            continue
    return False


def _link_line(emoji, label, url):
    return "  %s %s  %s" % (_c("1;36", emoji), label, _c("4", url))


def _resolved_lang():
    """User's effective language ("ko"/"en"). Reads config, falling back to the
    OS locale via resolve_lang; "en" if anything goes wrong (never fails setup)."""
    try:
        from claudlet.core import petconfig
        return petconfig.resolve_lang(petconfig.load_config().get("lang", "auto"))
    except Exception:
        return "en"


def _print_readme(was_installed):
    """Guide + changelog links. Fresh install shows BOTH README languages (we
    don't know the user's language yet); an update shows just the one matching
    their resolved language. The changelog link is one bilingual page, so it's
    always a single line with a locale-matched label."""
    lang = _resolved_lang()
    if not was_installed:
        print(_link_line("\U0001F4D6", "Guide: ", README_EN))
        print(_link_line("\U0001F4D6", "가이드:", README_KO))
    elif lang == "ko":
        print(_link_line("\U0001F4D6", "가이드:", README_KO))
    else:
        print(_link_line("\U0001F4D6", "Guide:", README_EN))
    if lang == "ko":
        print(_link_line("\U0001F195", "변경 이력:", RELEASES))
    else:
        print(_link_line("\U0001F195", "What's new:", RELEASES))


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    from claudlet.cli import install_hooks

    if "--remove" in argv:
        # single teardown implementation lives in uninstall; delegate so
        # `claudlet-install --remove` and `claudlet-uninstall` never diverge.
        from claudlet.cli import uninstall
        return uninstall.main(argv)

    # capture BEFORE install_hooks.main() registers our hooks, else every run
    # looks already-installed and the update branch would always win.
    was_installed = _already_installed(install_hooks)

    head("setting up claudlet")
    ok("dependencies", _check_deps())
    install_hooks.main([])
    ok("Claude Code hooks", "registered")
    for label, path, note in _link_skills():
        if path:
            ok("/claudlet skill (%s)" % label, path)
        if note:
            warn("%s: %s" % (label, note))

    head("done")
    print("Restart Claude Code sessions to pick up the hooks (new sessions")
    print("auto-spawn a pet). Run one now with:  " + _c("1", "claudlet"))
    print("Update anytime from inside Claude Code with:  " + _c("1", "/claudlet update"))
    _print_readme(was_installed)


if __name__ == "__main__":
    main()
