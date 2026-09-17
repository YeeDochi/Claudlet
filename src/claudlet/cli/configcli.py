#!/usr/bin/env python3
"""claudlet-config — locate, inspect, scaffold, and open the user config.

Usage:
    claudlet-config            # show path, status, effective values, ignored entries
    claudlet-config --path     # print the absolute config path only
    claudlet-config init       # create a starter template if none exists
    claudlet-config open       # open the config in the OS default editor

Thin presentation/scaffold layer over petconfig — all path/schema/validation
logic lives there. The /claudlet skill documents the schema so Claude can edit
the JSON directly and re-run this command to validate.
"""
import json
import os
import re
import shutil
import stat
import sys
import zipfile

from claudlet.core import agents
from claudlet.core import avatars
from claudlet.core import dock as dockgeom
from claudlet.core import petconfig
from claudlet.core.state_engine import MAPPABLE_STATES, DEFAULT_EVENT_STATES


def diagnose(raw):
    """Split a parsed config dict into what load_config accepts vs silently
    drops. Pure. Returns {"accepted": <petconfig._clean result>, "ignored":
    [human-readable strings]} so a typo'd state or unknown slot is visible
    instead of degrading to defaults with no feedback."""
    accepted = petconfig._clean(raw)
    ignored = []

    for key, val in (raw.get("tools") or {}).items():
        if not (isinstance(key, str) and val in MAPPABLE_STATES):
            ignored.append("tools.%s=%r (not a valid state)" % (key, val))
    for key, val in (raw.get("events") or {}).items():
        if key not in DEFAULT_EVENT_STATES:
            ignored.append("events.%s=%r (unknown event slot)" % (key, val))
        elif val not in MAPPABLE_STATES:
            ignored.append("events.%s=%r (not a valid state)" % (key, val))
    for key, val in (raw.get("raw_events") or {}).items():
        if not (isinstance(key, str) and val in MAPPABLE_STATES):
            ignored.append("raw_events.%s=%r (not a valid state)" % (key, val))
    if "lang" in raw and raw.get("lang") not in ("ko", "en", "auto"):
        ignored.append("lang=%r (use ko | en | auto)" % (raw.get("lang"),))
    d = raw.get("dock")
    if "dock" in raw and not isinstance(d, dict):
        ignored.append("dock=%r (must be an object)" % (d,))
    elif isinstance(d, dict) and d.get("anchor") not in (None,) + dockgeom.ANCHORS:
        ignored.append("dock.anchor=%r (use %s)"
                       % (d.get("anchor"), " | ".join(dockgeom.ANCHORS)))

    return {"accepted": accepted, "ignored": ignored}


_DEFAULTS = {"tool_states": {}, "event_states": {}, "raw_events": {},
             "lang": "auto", "dock": petconfig.default_dock()}


def build_report(path=None):
    """Inspect the config file at `path` (default: the resolved config_path).
    Returns {"path", "status": found|missing|invalid, "error"?, "accepted",
    "ignored"}. Never raises."""
    path = os.path.abspath(path or petconfig.config_path())
    if not os.path.exists(path):
        return {"path": path, "status": "missing",
                "accepted": dict(_DEFAULTS), "ignored": []}
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, ValueError) as e:
        return {"path": path, "status": "invalid", "error": str(e),
                "accepted": dict(_DEFAULTS), "ignored": []}
    if not isinstance(raw, dict):
        return {"path": path, "status": "invalid",
                "error": "top-level JSON must be an object",
                "accepted": dict(_DEFAULTS), "ignored": []}
    d = diagnose(raw)
    return {"path": path, "status": "found",
            "accepted": d["accepted"], "ignored": d["ignored"]}


# A valid, minimal starting point (per-key guidance lives in `show`, the skill
# doc, and docs/configuration.md — JSON has no comments).
TEMPLATE = {
    "lang": "auto",
    "tools": {"Bash": "work_computer"},
    "events": {},
    "raw_events": {},
}


def init_config(path=None):
    """Create a starter template at `path` if it doesn't exist. Returns True if
    a file was created, False if one was already there (never clobbers)."""
    path = os.path.abspath(path or petconfig.config_path())
    if os.path.exists(path):
        return False
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(TEMPLATE, f, indent=2, ensure_ascii=False)
        f.write("\n")
    return True


def open_command(path, platform=None, name=None):
    """How to open `path`: an argv list for a subprocess, or the string
    "startfile" meaning use os.startfile (Windows). Pure."""
    platform = sys.platform if platform is None else platform
    name = os.name if name is None else name
    if name == "nt":
        return "startfile"
    if platform == "darwin":
        return ["open", path]
    return ["xdg-open", path]


def _launch(path):
    cmd = open_command(path)
    if cmd == "startfile":
        os.startfile(path)                      # noqa: Windows only
    else:
        import subprocess
        subprocess.Popen(cmd)


def open_config(path=None):
    """Scaffold the config if missing, then open it in the OS default editor.
    Best-effort (never raises); returns the absolute path so the caller can
    print it as a fallback."""
    path = os.path.abspath(path or petconfig.config_path())
    init_config(path)
    try:
        _launch(path)
    except Exception:
        pass
    return path


def render(r):
    """Human-readable text for a build_report() result."""
    acc = r["accepted"]
    status = r["status"]
    if status == "invalid":
        status += " (%s)" % r.get("error", "")
    elif status == "missing":
        status += " (built-in defaults apply)"
    lines = [
        "config: " + r["path"],
        "status: " + status,
        "lang:   " + acc["lang"],
        "tools:      " + json.dumps(acc["tool_states"], ensure_ascii=False),
        "events:     " + json.dumps(acc["event_states"], ensure_ascii=False),
        "raw_events: " + json.dumps(acc["raw_events"], ensure_ascii=False),
        "dock:       " + json.dumps(acc.get("dock", {}), ensure_ascii=False),
    ]
    if r["ignored"]:
        lines.append("ignored (present in the file but dropped — fix these):")
        lines += ["  - " + s for s in r["ignored"]]
    lines += [
        "---",
        "valid states: " + ", ".join(sorted(MAPPABLE_STATES)),
        "event slots:  " + ", ".join(DEFAULT_EVENT_STATES),
        "dock anchors: " + ", ".join(dockgeom.ANCHORS)
        + "   (dock.enabled=false -> 예전처럼 배회)",
        "edit the file (or ask Claude via /claudlet config), then restart the pet.",
    ]
    return "\n".join(lines)


# ---------- wear: switch creature from the command line ----------

def _wearers(cfg):
    """agent name -> creature it currently wears, for every agent worth
    listing (detected ones, or the whole registry on a fresh machine)."""
    out = {}
    for name in agents.detected() or agents.names():
        out[name] = (petconfig.avatar_for(cfg, name)
                     or agents.get(name)["avatar"] or avatars.DEFAULT)
    return out


def render_creature_list(cfg):
    """Available creatures, each annotated with who currently wears it."""
    wearers = _wearers(cfg)
    lines = ["available creatures:"]
    for name in avatars.available():
        who = [a for a, worn in wearers.items() if worn == name]
        lines.append("  " + name + ("  (worn by: %s)" % ", ".join(who) if who else ""))
    return "\n".join(lines)


def _pick_agent(explicit):
    """Resolve which agent `wear` targets. Returns (agent, error); error is
    None on success. A typo'd EXPLICIT --agent must error rather than silently
    falling back to the default agent -- that fallback used to let
    `--agent codexx` overwrite the Claude pet's creature while reporting
    success, exactly like an unknown creature name already does."""
    if explicit is not None:
        if explicit not in agents.AGENTS:
            return None, "unknown agent: %s" % explicit
        return explicit, None
    det = agents.detected()
    return (det[0] if len(det) == 1 else agents.DEFAULT), None


def cmd_wear(argv):
    """claudlet-config wear <creature> [--agent <name>] -- write that creature
    for that agent and tell running pets to re-dress. Reuses configui.apply()
    for the write so a legacy string `avatar` promotes to a per-agent map the
    same way the settings page does it, instead of a second copy of that
    logic here."""
    from claudlet.cli import configui

    creature, agent_arg = None, None
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--agent" and i + 1 < len(argv):
            agent_arg = argv[i + 1]
            i += 2
        elif a.startswith("--agent="):
            agent_arg = a.split("=", 1)[1]
            i += 1
        elif creature is None:
            creature = a
            i += 1
        else:
            i += 1

    cfg = petconfig.load_config()
    if creature is None:
        print(render_creature_list(cfg))
        return 0
    if creature not in avatars.available():
        print("unknown creature: %s" % creature)
        print(render_creature_list(cfg))
        return 1

    agent, err = _pick_agent(agent_arg)
    if err:
        print(err)
        return 1
    out = configui.apply({"agent": agent, "avatar": creature})
    print("%s now wears %s (%d pet(s) updated)" % (agent, creature, out.get("pets", 0)))
    return 0


# ---------- export / import: share a creature ----------

def _bundled_module_path(name):
    """The source file the bundled avatar named `name` is defined in, or None.
    Derived from the registry entry's own `__module__` (via importlib) rather
    than a hardcoded name->filename table, so a fifth bundled creature needs no
    edit here -- the one irregular case (builtin.py holding the "claudlet"
    avatar) falls out of this the same as every regular one."""
    import importlib
    cls = avatars.bundled().get(name)
    if cls is None:
        return None
    try:
        mod = importlib.import_module(cls.__module__)
    except ImportError:
        return None
    p = getattr(mod, "__file__", None)
    return p if p and os.path.isfile(p) else None


def _find_user_dir_by_declared_name(name):
    """A user creature directory under CREATURES_DIR whose DECLARED AVATAR.name
    is `name`, for when the two differ (dirname != declared name)."""
    try:
        entries = os.listdir(avatars.CREATURES_DIR)
    except OSError:
        return None
    for d in entries:
        path = os.path.join(avatars.CREATURES_DIR, d)
        if not os.path.isdir(path):
            continue
        made = avatars._load_dir(path)
        if getattr(made, "name", None) == name:
            return path
    return None


def export_creature(name, out=None, force=False):
    """Zip a creature's package so it can be shared. Returns (dest_path, None)
    or (None, error). A user creature under CREATURES_DIR is preferred over a
    same-named bundled one, since that is the one actually in effect; it is
    looked up by directory name first, then by its declared AVATAR.name (the
    two can differ). Refuses to overwrite an existing destination without
    `force`, and never creates a missing destination directory -- a typo'd
    `--out` should fail loudly, not silently invent a new folder."""
    if name not in avatars.available():
        return None, "unknown creature: %s" % name
    default_name = "%s.claudlet-creature.zip" % name
    if out is None:
        dest = os.path.abspath(default_name)
    elif out.endswith(".zip"):
        dest = os.path.abspath(out)
    else:
        dest = os.path.abspath(os.path.join(out, default_name))

    parent = os.path.dirname(dest) or "."
    if not os.path.isdir(parent):
        return None, "no such directory: %s" % parent
    if os.path.exists(dest) and not force:
        return None, "%s already exists (use --force to overwrite)" % dest

    user_dir = os.path.join(avatars.CREATURES_DIR, name)
    if not os.path.isdir(user_dir):
        user_dir = _find_user_dir_by_declared_name(name) or user_dir
    if os.path.isdir(user_dir):
        with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, dirs, files in os.walk(user_dir):
                dirs[:] = [d for d in dirs if d != "__pycache__"]
                for f in files:
                    if f.endswith(".pyc"):
                        continue
                    full = os.path.join(root, f)
                    rel = os.path.relpath(full, avatars.CREATURES_DIR)
                    zf.write(full, rel.replace(os.sep, "/"))
        return dest, None

    mod_path = _bundled_module_path(name)
    if mod_path:
        with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(mod_path, "%s/__init__.py" % name)
        return dest, None
    return None, "cannot find a source package for: %s" % name


def _is_symlink_entry(info):
    mode = (info.external_attr >> 16) & 0xFFFF
    return stat.S_ISLNK(mode)


def _has_control_chars(s):
    return any(ord(c) < 0x20 or ord(c) == 0x7F for c in s)


def _esc(s):
    """Escape a string so it prints as one visible line -- used both as a
    belt-and-suspenders layer when printing archive-controlled text (which
    inspect_creature_zip already refuses to contain control characters) and
    for names embedded in error messages."""
    return s.encode("unicode_escape").decode("ascii")


# A code-drawn creature (see the bundled ones) is a handful of small .py files;
# ~10-16 KB total. These are generous multiples of that, not a measured limit
# for "big" art -- an archive anywhere near them is not a creature anymore.
MAX_CREATURE_ENTRIES = 200
MAX_CREATURE_TOTAL_SIZE = 512 * 1024  # bytes, declared uncompressed total

# The top-level directory name becomes a path component under CREATURES_DIR
# (and, unescaped, part of every message shown about the import). No dot-only
# names (`.` resolves to CREATURES_DIR itself -- see the rmtree history this
# guards against), no leading dot, no path separators or other punctuation.
_SAFE_TOP_NAME_RE = re.compile(r'^[A-Za-z0-9_][A-Za-z0-9_.-]*$')


def inspect_creature_zip(zip_path):
    """Validate a creature archive WITHOUT writing anything -- this is the
    trust boundary: installing a creature means importing someone else's
    Python, so every entry is checked before anything is shown or written.

    Returns (name, entries, total_size, error). `error` is None on success;
    the other fields are best-effort otherwise."""
    try:
        zf = zipfile.ZipFile(zip_path)
    except (OSError, zipfile.BadZipFile) as e:
        return None, [], 0, "not a valid zip: %s" % e
    with zf:
        infos = zf.infolist()
        if len(infos) > MAX_CREATURE_ENTRIES:
            return None, [], 0, ("archive has %d entries, exceeds the %d-entry "
                                 "limit for a creature" % (len(infos), MAX_CREATURE_ENTRIES))
        top_dirs = set()
        for info in infos:
            # Control characters (including newline) first, and before ANY
            # other check formats a message with this filename in it -- the
            # confirmation listing this function's caller prints is otherwise
            # attacker-controlled text an approving agent could be tricked by.
            if _has_control_chars(info.filename):
                return None, [], 0, "unsafe entry name in archive (control characters)"
            fn = info.filename.replace("\\", "/")
            if not fn or fn.startswith("/") or os.path.isabs(fn):
                return None, [], 0, "unsafe path in archive: %s" % fn
            parts = fn.split("/")
            if ".." in parts or "" in parts[:-1]:
                return None, [], 0, "unsafe path in archive: %s" % fn
            if len(parts) < 2:
                return None, [], 0, ("archive must contain exactly one top-level "
                                     "directory (found a loose file: %s)" % fn)
            top = parts[0]
            if not _SAFE_TOP_NAME_RE.match(top) or top in (".", ".."):
                return None, [], 0, ("unsafe top-level directory name in "
                                     "archive: %s" % _esc(top))
            if _is_symlink_entry(info):
                return None, [], 0, "archive contains a symlink: %s" % fn
            top_dirs.add(top)
        if len(top_dirs) != 1:
            return None, [], 0, ("archive must contain exactly one top-level "
                                 "directory (found %d)" % len(top_dirs))
        name = next(iter(top_dirs))
        entries = [i.filename for i in infos]
        total = sum(i.file_size for i in infos if not i.filename.endswith("/"))
        if total > MAX_CREATURE_TOTAL_SIZE:
            return None, [], 0, ("archive declares %d bytes, exceeds the %d "
                                 "byte limit for a creature"
                                 % (total, MAX_CREATURE_TOTAL_SIZE))
    return name, entries, total, None


def import_creature(zip_path, dest_root=None, force=False):
    """Extract a validated creature archive into dest_root/<name>/. Returns
    (declared_name, None) or (None, error). Never fetches anything -- the file
    must already be local.

    Extraction happens into a temp directory beside the target first, and the
    real target is only ever replaced by an atomic rename at the very end --
    so a failure partway through (or the collision check below) leaves
    whatever was at the target before untouched, instead of the old creature
    already being rmtree'd and the new one half-written.

    After extracting, the package is loaded to read its DECLARED AVATAR.name
    (which need not match the archive's top-level directory name). If that
    name collides with a bundled creature, the import is refused and rolled
    back -- otherwise the imported creature would silently shadow the bundled
    one everywhere, with no sign of which directory did it."""
    dest_root = dest_root if dest_root is not None else avatars.CREATURES_DIR
    name, entries, total, err = inspect_creature_zip(zip_path)
    if err:
        return None, err
    dest_root_abs = os.path.abspath(dest_root)
    target = os.path.join(dest_root_abs, name)
    existed = os.path.isdir(target)
    if existed and not force:
        return None, "creature '%s' already exists (use --force to overwrite)" % name

    os.makedirs(dest_root_abs, exist_ok=True)
    tmp_target = target + ".import-tmp"
    if os.path.exists(tmp_target):
        shutil.rmtree(tmp_target, ignore_errors=True)
    os.makedirs(tmp_target)
    tmp_target_abs = os.path.abspath(tmp_target)
    try:
        with zipfile.ZipFile(zip_path) as zf:
            for info in zf.infolist():
                if info.filename.endswith("/"):
                    continue
                # strip the archive's top-level dir -- it becomes `target`,
                # not a directory nested inside it.
                rel = info.filename.split("/", 1)[1]
                out_path = os.path.abspath(os.path.join(tmp_target_abs, rel))
                if not out_path.startswith(tmp_target_abs + os.sep):
                    return None, "unsafe path in archive: %s" % info.filename
                os.makedirs(os.path.dirname(out_path), exist_ok=True)
                with zf.open(info) as src, open(out_path, "wb") as dst:
                    dst.write(src.read())
    except Exception as e:
        shutil.rmtree(tmp_target, ignore_errors=True)
        return None, "failed to extract archive: %s" % e

    made = avatars._load_dir(tmp_target)
    declared_name = getattr(made, "name", None)
    if declared_name in avatars.bundled():
        shutil.rmtree(tmp_target, ignore_errors=True)
        return None, ("refusing to import: declared creature name '%s' "
                      "collides with a bundled creature" % declared_name)

    backup = None
    if existed:
        backup = target + ".import-backup"
        if os.path.exists(backup):
            shutil.rmtree(backup, ignore_errors=True)
        os.rename(target, backup)
    try:
        os.replace(tmp_target, target)
    except OSError as e:
        if backup:
            os.rename(backup, target)
        shutil.rmtree(tmp_target, ignore_errors=True)
        return None, "failed to install creature: %s" % e
    if backup:
        shutil.rmtree(backup, ignore_errors=True)
    return declared_name or name, None


def cmd_export(argv):
    creature, out, force = None, None, False
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--out" and i + 1 < len(argv):
            out = argv[i + 1]
            i += 2
        elif a.startswith("--out="):
            out = a.split("=", 1)[1]
            i += 1
        elif a == "--force":
            force = True
            i += 1
        elif creature is None:
            creature = a
            i += 1
        else:
            i += 1
    if not creature:
        print("usage: claudlet-config export <creature> [--out <path>] [--force]")
        return 1
    dest, err = export_creature(creature, out, force)
    if err:
        print(err)
        return 1
    print("wrote " + dest)
    return 0


def cmd_import(argv):
    path, yes, force = None, False, False
    for a in argv:
        if a == "--yes":
            yes = True
        elif a == "--force":
            force = True
        elif path is None:
            path = a
    if not path:
        print("usage: claudlet-config import <file.zip> [--yes] [--force]")
        return 1

    name, entries, total, err = inspect_creature_zip(path)
    if err:
        print(err)
        return 1
    files = [e for e in entries if not e.endswith("/")]
    print("about to install creature '%s' from %s" % (name, path))
    print("%d file(s), %d bytes:" % (len(files), total))
    # Entry names come straight from the archive -- untrusted data, not text
    # we composed. inspect_creature_zip already refuses control characters, so
    # this escape is a second, belt-and-suspenders layer.
    for e in entries:
        print("  " + _esc(e))
    print("importing a creature runs its Python the next time claudlet starts.")

    if not yes:
        try:
            reply = input("proceed? [y/N] ")
        except EOFError:
            reply = ""
        if reply.strip().lower() not in ("y", "yes"):
            print("aborted")
            return 1

    installed, err = import_creature(path, force=force)
    if err:
        print(err)
        return 1
    print("installed " + installed)
    print("wear it with: claudlet-config wear " + installed)
    return 0


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    arg = argv[0] if argv else ""

    if arg == "--path":
        print(os.path.abspath(petconfig.config_path()))
        return 0
    if arg == "init":
        path = os.path.abspath(petconfig.config_path())
        created = init_config(path)
        print(("created " if created else "already exists: ") + path)
        return 0
    if arg == "ui":
        # 크리처 설정 페이지. 미리보기를 진짜 렌더러로 그려 주므로 별도 프로세스
        # (여기)에서 Qt를 offscreen으로 띄운다.
        from claudlet.cli import configui
        agent = None
        for i, a in enumerate(argv):
            if a == "--agent" and i + 1 < len(argv):
                agent = argv[i + 1]
            elif a.startswith("--agent="):
                agent = a.split("=", 1)[1]
        configui.serve(open_browser="--no-open" not in argv, agent=agent)
        return 0
    if arg == "open":
        print("opening " + open_config())
        return 0
    if arg == "wear":
        return cmd_wear(argv[1:])
    if arg == "export":
        return cmd_export(argv[1:])
    if arg == "import":
        return cmd_import(argv[1:])
    print(render(build_report()))
    return 0


def _cli():
    """console-script entry point (never raise from the CLI)."""
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception:
        sys.exit(0)


if __name__ == "__main__":
    _cli()
