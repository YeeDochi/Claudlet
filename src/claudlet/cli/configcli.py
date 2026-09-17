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
    if explicit is not None:
        return explicit if explicit in agents.AGENTS else agents.DEFAULT
    det = agents.detected()
    return det[0] if len(det) == 1 else agents.DEFAULT


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

    agent = _pick_agent(agent_arg)
    out = configui.apply({"agent": agent, "avatar": creature})
    print("%s now wears %s (%d pet(s) updated)" % (agent, creature, out.get("pets", 0)))
    return 0


# ---------- export / import: share a creature ----------

def _bundled_module_path(name):
    """The bundled avatars/<name>.py this creature name is drawn by, or None.
    The one irregular filename is the built-in ("claudlet" -> builtin.py);
    every other bundled creature's module is named after itself."""
    d = os.path.dirname(avatars.__file__)
    fname = "builtin.py" if name == "claudlet" else name + ".py"
    p = os.path.join(d, fname)
    return p if os.path.isfile(p) else None


def export_creature(name, out=None):
    """Zip a creature's package so it can be shared. Returns (dest_path, None)
    or (None, error). A user creature under CREATURES_DIR is preferred over a
    same-named bundled one, since that is the one actually in effect."""
    if name not in avatars.available():
        return None, "unknown creature: %s" % name
    default_name = "%s.claudlet-creature.zip" % name
    if out is None:
        dest = os.path.abspath(default_name)
    elif out.endswith(".zip"):
        dest = os.path.abspath(out)
    else:
        dest = os.path.abspath(os.path.join(out, default_name))
    os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)

    user_dir = os.path.join(avatars.CREATURES_DIR, name)
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
        top_dirs = set()
        for info in infos:
            fn = info.filename.replace("\\", "/")
            if not fn or fn.startswith("/") or os.path.isabs(fn):
                return None, [], 0, "unsafe path in archive: %s" % info.filename
            parts = fn.split("/")
            if ".." in parts or "" in parts[:-1]:
                return None, [], 0, "unsafe path in archive: %s" % info.filename
            if _is_symlink_entry(info):
                return None, [], 0, "archive contains a symlink: %s" % info.filename
            top_dirs.add(parts[0])
        if len(top_dirs) != 1:
            return None, [], 0, ("archive must contain exactly one top-level "
                                 "directory (found %d)" % len(top_dirs))
        name = next(iter(top_dirs))
        entries = [i.filename for i in infos]
        total = sum(i.file_size for i in infos if not i.filename.endswith("/"))
    return name, entries, total, None


def import_creature(zip_path, dest_root=None, force=False):
    """Extract a validated creature archive into dest_root/<name>/. Returns
    (name, None) or (None, error). Never fetches anything -- the file must
    already be local."""
    dest_root = dest_root if dest_root is not None else avatars.CREATURES_DIR
    name, entries, total, err = inspect_creature_zip(zip_path)
    if err:
        return None, err
    target = os.path.join(dest_root, name)
    if os.path.isdir(target):
        if not force:
            return None, "creature '%s' already exists (use --force to overwrite)" % name
        shutil.rmtree(target)

    dest_root_abs = os.path.abspath(dest_root)
    os.makedirs(dest_root_abs, exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            if info.filename.endswith("/"):
                continue
            out_path = os.path.abspath(os.path.join(dest_root_abs, info.filename))
            if not out_path.startswith(dest_root_abs + os.sep):
                return None, "unsafe path in archive: %s" % info.filename
            os.makedirs(os.path.dirname(out_path), exist_ok=True)
            with zf.open(info) as src, open(out_path, "wb") as dst:
                dst.write(src.read())
    return name, None


def cmd_export(argv):
    creature, out = None, None
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--out" and i + 1 < len(argv):
            out = argv[i + 1]
            i += 2
        elif a.startswith("--out="):
            out = a.split("=", 1)[1]
            i += 1
        elif creature is None:
            creature = a
            i += 1
        else:
            i += 1
    if not creature:
        print("usage: claudlet-config export <creature> [--out <path>]")
        return 1
    dest, err = export_creature(creature, out)
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
    for e in entries:
        print("  " + e)
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
