#!/usr/bin/env python3
"""claudlet-config ui — the creature settings page.

Pick a creature, then set how it looks: its colour and how big it is. Served
from a throwaway local HTTP server so the page can show a REAL render of the
creature as you change things — the preview is drawn by the same renderer the
pet uses, so what you see is what lands on the desktop.

stdlib only (`http.server`): a settings screen is not worth a web framework,
and the pet must stay installable with nothing but PyQt6.

Local only. The server binds 127.0.0.1 on a FIXED preferred port (so an
installed PWA keeps one origin across runs) and stops when the
window is closed / the command is interrupted. This is unauthenticated on
loopback by design (any same-user process can already write the config files
this page edits) -- except POST /api/import, which is the one endpoint that
can plant and later execute new code (a creature package), so it alone is
gated behind a per-run token: that closes the gap for a process that is
filesystem-sandboxed but still allowed to reach loopback sockets.

The request handling is split into PURE functions (`state_payload`, `apply`)
that take and return data, so the behaviour is tested without a socket; the
HTTP class below is a thin shell over them.
"""
import hmac
import json
import os
import secrets
import sys
import time

from claudlet.core import agents, avatars, hostinfo, petconfig

# The page is often opened from the pet's right-click menu, where there is no
# terminal to Ctrl-C and closing the tab would otherwise leave a server running
# for the rest of the session. So the page says it is still there and the server
# stops when nothing has for a while: open tab, server up; tab closed, gone
# within a minute.
IDLE_TIMEOUT = 90.0
HEARTBEAT_MS = 25000

# One fixed origin, not an OS-chosen port: an installed app (PWA) is keyed by
# origin, so a new port every run would orphan the install. The port is only
# PREFERRED -- if something else holds it we fall back, and if ANOTHER claudlet
# settings server holds it we hand the page over to that one instead of running
# two (clicking "settings" twice, or from two pets, must not start two servers).
PREFERRED_PORT = 8770
APP_ID = "claudlet-config"        # what /api/alive answers with, so we can
                                  # recognise our own server on the port
# chromium-family binaries, in the order we would rather have them, and the
# window a dashboard-shaped page wants
APP_BROWSERS = ("google-chrome", "chromium", "chromium-browser",
                "microsoft-edge", "brave-browser")
APP_WINDOW = (1120, 860)

# A page refresh fires the same `pagehide` -> /api/bye as a real tab close.
# Killing the server at once (the old `last_seen = 0.0`) left a refresh
# stranded on a dead port. Instead `bye` leaves this many seconds of runway:
# enough for the refreshed page's next request (a heartbeat or /api/state) to
# arrive and revive the server before the idle timeout would have hit anyway.
# A real close never sends another request, so it still dies within the grace.
BYE_GRACE = 4.0


def bye_last_seen(now, idle_timeout, grace=BYE_GRACE):
    """`last_seen` to record on a `bye` beacon. Pure: leaves `grace` seconds
    before `idle_timeout` fires, rather than expiring the server immediately.
    Clamped so a grace bigger than the timeout can't push `elapsed` negative
    (which would read as MORE time left than the server ever had)."""
    elapsed = max(0.0, idle_timeout - grace)
    return now - elapsed

PREVIEW_STATES = ("idle", "work_computer", "celebrate", "sleeping")


# ---------- pure: where to serve it and how to open it ----------

def port_plan(preferred, probe):
    """What to do about the preferred port. `probe(port)` answers
    "free" | "ours" | "other"; returns ("bind", port) to serve there,
    ("attach", port) to just open the browser at the server already running,
    or ("fallback", 0) to let the OS pick a free port. Pure."""
    seen = probe(preferred)
    if seen == "free":
        return ("bind", preferred)
    if seen == "ours":
        return ("attach", preferred)
    return ("fallback", 0)


def probe_port(port, timeout=0.6):
    """Is `port` free, ours, or somebody else's? Asked over HTTP in ONE request,
    because a bind test cannot tell our own server from a stranger's (and a
    second connection would be eaten by a single-request server)."""
    import urllib.error
    import urllib.request
    try:
        with urllib.request.urlopen(
                "http://127.0.0.1:%d/api/alive" % port, timeout=timeout) as r:
            return "ours" if json.loads(r.read()).get("app") == APP_ID else "other"
    except urllib.error.URLError as e:
        # refused == nothing listening; anything else is somebody's server
        return "free" if isinstance(e.reason, ConnectionRefusedError) else "other"
    except Exception:
        return "other"


APP_CLASS = "claudlet"        # WM_CLASS / Wayland app_id for the app window


def chrome_profile_dir(cache_home=None):
    """Where the app window's OWN Chrome profile lives. Pure string math --
    creating the directory is the caller's job (see `launch_browser`)."""
    base = cache_home if cache_home is not None else (
        os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache"))
    return os.path.join(base, "claudlet", "chrome-profile")


def browser_command(url, which=None, size=APP_WINDOW, profile_dir=None):
    """argv that opens `url` as a chrome-less app window, or None when no
    chromium-family browser is installed (then the caller opens it the ordinary
    way). `which` is injected so this is testable without the real PATH. Pure."""
    if which is None:
        import shutil
        which = shutil.which
    if profile_dir is None:
        profile_dir = chrome_profile_dir()
    for name in APP_BROWSERS:
        exe = which(name)
        if exe:
            # --ozone-platform-hint=auto: on a Wayland session that also has an
            # X server around (KDE's XWayland, or a gamescope-provided :1),
            # Chrome otherwise picks X11 and the app window lands in whatever
            # composites that display instead of the user's desktop.
            # --class: name the window after ourselves. Without it the app
            # window carries no identity a desktop can match, and KDE attributes
            # it to whatever owns the display it landed on (a gamescope-provided
            # :1 shows up as "gamescope" in the task bar, icon and all).
            # --user-data-dir: give this launch its OWN Chrome profile. Verified
            # live: without this, if Chrome is already running with the default
            # profile, this second invocation is just handed to the running
            # instance (which then exits) and every flag above is silently
            # ignored -- the window that appears belongs to the OLD process,
            # with none of --app/--window-size/--class applied. A dedicated
            # profile forces a genuinely separate process every time.
            return [exe, "--app=" + url,
                    "--window-size=%d,%d" % (size[0], size[1]),
                    "--class=" + APP_CLASS,
                    "--user-data-dir=" + profile_dir,
                    "--no-first-run", "--no-default-browser-check",
                    "--ozone-platform-hint=auto"]
    return None


def manifest(cfg=None):
    """The PWA manifest, as data. The icons come from /api/icon, which draws the
    creature the user is actually wearing -- the repo carries no image assets."""
    t = texts(cfg)
    return {
        "name": "claudlet " + t["title"],
        "short_name": "claudlet",
        "start_url": "/",
        "scope": "/",
        "display": "standalone",
        "theme_color": "#16161a",
        "background_color": "#16161a",
        "icons": [{"src": "/api/icon?size=%d" % n, "sizes": "%dx%d" % (n, n),
                   "type": "image/png", "purpose": "any"} for n in (192, 512)],
    }


SERVICE_WORKER = """// claudlet settings: a service worker exists because Chrome
// wants one before it will offer to install the page. This is a LOCAL server,
// so there is nothing worth caching -- every request goes to the network.
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (e) => e.waitUntil(self.clients.claim()));
self.addEventListener("fetch", (e) => e.respondWith(fetch(e.request)));
"""


# ---------- pure: what the page shows and what a save does ----------

def _agent_rows(cfg, current):
    """Chips for the agent row -- empty when there is nothing to choose between,
    so a single-agent machine sees exactly the page it always has."""
    det = agents.detected()
    if len(det) < 2:
        return []
    return [{"name": n, "label": agents.get(n)["label"], "selected": n == current,
             "creature": (petconfig.avatar_for(cfg, n)
                          or agents.get(n)["avatar"] or avatars.DEFAULT)}
            for n in det]


def current_agent(body):
    """Which agent the page is dressing. The page posts it; absent (or unknown)
    means the default agent, which is also what a single-agent machine has."""
    a = (body or {}).get("agent")
    return a if a in agents.AGENTS else agents.DEFAULT


def state_payload(cfg=None, agent=None):
    """Everything the page needs to draw itself.

    Appearance belongs to the CREATURE: a slime and a claudlet want different
    colours and sizes, and one shared setting meant switching creature dragged
    the other one's look along."""
    cfg = petconfig.load_config() if cfg is None else cfg
    agent = agent if agent in agents.AGENTS else agents.DEFAULT
    chosen = (petconfig.avatar_for(cfg, agent)
              or agents.get(agent)["avatar"] or avatars.DEFAULT)
    look = petconfig.for_creature(cfg, chosen, avatars.get(chosen))
    pal = look["palette"]
    return {
        # each creature's OWN colour, so the list shows what picking it would
        # actually give you rather than the colour of the one already worn
        "avatars": [{"name": n, "selected": n == chosen,
                     "colour": petconfig.for_creature(
                         cfg, n, avatars.get(n))["palette"]}
                    for n in avatars.available()],
        "creature": chosen,
        # every creature's settings, so the panel can show one without the pet
        # having to put it on first
        "looks": {n: petconfig.for_creature(cfg, n, avatars.get(n))
                  for n in avatars.available()},
        "visor": look["visor"],
        "visor_modes": list(petconfig.VISOR_MODES),
        "palette": pal,
        # the colour the picker should open on: a named palette has no single
        # colour of its own, so fall back to the built-in body colour
        "colour": pal if isinstance(pal, str) and pal.startswith("#") else "#D97757",
        "named": not (isinstance(pal, str) and pal.startswith("#")),
        "scale": look["scale"],
        "scale_range": [petconfig.MIN_SCALE, petconfig.MAX_SCALE],
        "states": list(PREVIEW_STATES),
        # a creature need not draw every state; preview only what it declares,
        # so a four-state creature doesn't show four fallbacks
        "avatar_states": {n: [st for st in PREVIEW_STATES
                              if st in getattr(avatars.get(n), "states", ())]
                          or list(PREVIEW_STATES[:1])
                          for n in avatars.available()},
        "agents": _agent_rows(cfg, agent),
        "agent": agent,
    }


def clean_creature_updates(body):
    """The per-creature appearance keys we will write, cleaned.

    Anything unrecognised is dropped rather than written through: this endpoint
    edits the same file a user hand-writes tools/events into."""
    # A None value means CLEAR, not "store the default". Resetting has to remove
    # the setting so the creature's own default applies again -- writing "auto"
    # instead made every creature reset to claudlet's orange, because a stored
    # value is a choice the user made and outranks what the creature asks for.
    out = {}
    if "palette" in body:
        out["palette"] = petconfig.clean_palette_opt(body.get("palette"))
    if "scale" in body:
        v = body.get("scale")
        out["scale"] = None if v is None else petconfig.clamp_scale(v)
    if "visor" in body:
        v = body.get("visor")
        out["visor"] = None if v is None else petconfig.clean_visor(v)
    return out


def export_api(body):
    """POST /api/export body: {"creature", "out"?, "force"?}. Thin wrapper over
    configcli.export_creature -- all the path/validation logic lives there.
    When `out` is empty the destination defaults to the user's home directory
    (not the server's cwd, which the page's user never chose)."""
    from claudlet.cli import configcli
    creature = body.get("creature")
    if not isinstance(creature, str) or not creature:
        return {"error": "no creature given"}
    out = body.get("out") or None
    if not out:
        out = os.path.expanduser("~")
    dest, err = configcli.export_creature(creature, out, bool(body.get("force")))
    if err:
        return {"error": err}
    return {"path": dest}


def import_api(body):
    """POST /api/import body: {"path"} inspects only and writes nothing;
    {"path", "confirm": true, "force"?} actually installs. Thin wrapper over
    configcli's inspect_creature_zip / import_creature -- the security gate
    (path traversal, symlinks, size/entry ceilings, ...) lives there, not
    here, so the CLI and the web page share one validator."""
    from claudlet.cli import configcli
    path = body.get("path")
    if not isinstance(path, str) or not path:
        return {"error": "no path given"}
    if not body.get("confirm"):
        name, entries, total, err = configcli.inspect_creature_zip(path)
        if err:
            return {"error": err}
        return {"name": name, "entries": entries, "total": total}
    name, err = configcli.import_creature(path, force=bool(body.get("force")))
    if err:
        return {"error": err}
    return {"name": name}


def apply(body, broadcast=None):
    """Save what the page posted and tell every running pet to re-dress.

    `broadcast` is injectable so tests don't reach for sockets. Returns the
    payload the page redraws from, plus how many pets took it."""
    cfg = petconfig.load_config()
    agent = current_agent(body)
    # which creature is worn is a top-level choice; how it LOOKS is stored under
    # that creature, so picking a colour for the slime cannot repaint claudlet.
    top = {}
    name = body.get("avatar")
    if isinstance(name, str) and name in avatars.available():
        cur = cfg.get("avatar")
        if isinstance(cur, dict):
            worn = dict(cur)
        elif isinstance(cur, str) and cur:
            # promote the legacy single choice: it applied to every agent, so
            # every agent keeps it -- except the one being changed now
            worn = {n: cur for n in agents.detected()} or {agents.DEFAULT: cur}
        else:
            worn = {}
        worn[agent] = name
        top["avatar"] = worn
    # settings are saved to the creature the panel is SHOWING, which need not be
    # the one being worn — looking at another creature's settings and editing
    # them should not require putting it on first.
    editing = body.get("creature")
    if isinstance(editing, str) and editing in avatars.available():
        target = editing
    elif isinstance(top.get("avatar"), dict):
        target = top["avatar"][agent]
    else:
        target = petconfig.avatar_for(cfg, agent) or agents.get(agent)["avatar"] or avatars.DEFAULT
    mine = clean_creature_updates(body)
    if mine:
        creatures = dict(cfg.get("creatures") or {})
        merged = dict(creatures.get(target) or {})
        merged.update(mine)
        merged = {k: v for k, v in merged.items() if v is not None}
        creatures[target] = merged
        top["creatures"] = creatures
    updates = top
    if updates:
        petconfig.save_keys(updates)
    send = hostinfo.broadcast if broadcast is None else broadcast
    told = 0
    if updates:
        try:
            told = send(json.dumps({"cmd": "restyle"}))
        except Exception:
            told = 0            # nothing running is not an error
    payload = state_payload(agent=agent)
    payload["applied"] = sorted(list(k for k in top if k != "creatures") + list(mine))
    payload["pets"] = told
    return payload


# ---------- preview: the real renderer, off screen ----------

def preview_frame(state):
    """A frame worth freezing for a still preview.

    States with a speech bubble type it out over time, so an early frame shows
    half a word. Hold at the beat where it is fully typed — the same choice the
    sprite sheet makes."""
    from claudlet.core import creature
    if state in getattr(creature, "SPEECH", ()):
        return len(creature.speech(state)) * 7 + 5
    return 8


def render_png(palette, scale, state="idle", frame=None, avatar=None,
               visor="auto"):
    """A PNG of the creature as these settings would draw it, or b"" if Qt
    can't start (headless box with no offscreen platform)."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PyQt6.QtCore import QBuffer
        from PyQt6.QtGui import QImage, QPainter
        from PyQt6.QtWidgets import QApplication
    except ImportError:
        return b""
    app = QApplication.instance() or QApplication(sys.argv[:1])   # noqa: F841
    avatar = avatars.get(avatar)
    pad = 2
    gw, gh = avatar.grid
    u = petconfig.clamp_scale(scale)
    w, h = (gw + 2 * pad) * u, (gh + 2 * pad) * u
    img = QImage(w, h, QImage.Format.Format_ARGB32)
    img.fill(0)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
    pal = petconfig.resolve_palette(palette, 1.0)   # roll=1.0: never roll shiny
    f = preview_frame(state) if frame is None else frame
    # show what the visor setting actually does. "auto" can't be previewed
    # honestly (it depends on whether Claude is running unattended right now),
    # so it previews as off -- the same as an ordinary session.
    avatar.draw(p, pad * u, pad * u, u, state, f, palette=pal,
                autonomous=(visor == "on"))
    p.end()
    buf = QBuffer()
    buf.open(QBuffer.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    return bytes(buf.data())


def icon_png(size):
    """A square app icon, drawn by the same renderer as everything else (the
    repo ships no image assets), or b"" if Qt can't start -- same contract as
    render_png.

    Deliberately FIXED: the built-in claudlet in its own colours, not whatever
    is being worn. A PWA has ONE icon per origin, and two agents wearing two
    creatures have no single right answer -- so the app icon is the app's."""
    png = render_png("auto", petconfig.MAX_SCALE, "idle",
                     avatar=avatars.DEFAULT, visor="off")
    if not png:
        return b""
    from PyQt6.QtCore import QBuffer, Qt
    from PyQt6.QtGui import QImage, QPainter
    src = QImage()
    src.loadFromData(png)
    # pixel art: blow it up with nearest-neighbour, centred on a square canvas
    fit = src.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio,
                     Qt.TransformationMode.FastTransformation)
    out = QImage(size, size, QImage.Format.Format_ARGB32)
    out.fill(0)
    p = QPainter(out)
    p.drawImage((size - fit.width()) // 2, (size - fit.height()) // 2, fit)
    p.end()
    buf = QBuffer()
    buf.open(QBuffer.OpenModeFlag.WriteOnly)
    out.save(buf, "PNG")
    return bytes(buf.data())


# ---------- the shell ----------

# The page follows the same `lang` setting the pet does. Korean-only was fine
# while this was one developer's tool; it ships now.
TEXT = {
    "ko": {
        "title": "크리처", "lead": "색과 크기를 정합니다. 저장하면 떠 있는 펫에 바로 반영됩니다.",
        "refresh": "새로고침",
        "creatures": "크리처", "colour": "색", "size": "크기", "special": "특수 모드",
        "save": "저장", "wear": "적용", "worn_btn": "적용됨",
        "reset": "기본으로", "worn": "착용 중", "notworn": "미착용",
        "settings_of": "%s 설정",
        "visor_auto": "오토모드일 때", "visor_on": "항상", "visor_off": "안 함",
        "named": "지금은 %s — 색을 고르면 바뀝니다",
        "saved": "%s 설정을 저장했습니다", "switched": "%s 로 갈아입혔습니다",
        "reverted": "%s 를 기본으로 되돌렸습니다",
        "applied_pets": " — 펫 %d마리에 반영", "applied_next": " — 다음에 뜨는 펫부터",
        "serving": "claudlet 크리처 설정: ", "stop": "(창을 닫거나 Ctrl-C 로 종료)",
        "port_taken": "(%d 번 포트는 다른 프로그램이 쓰고 있어 다른 포트로 열었습니다)",
        "export": "내보내기", "export_retry_force": "덮어쓰고 다시 시도",
        "export_dest": "저장 위치", "export_dest_placeholder": "저장할 폴더 (기본: 홈)",
        "import": "가져오기", "import_cancel": "취소",
        "import_placeholder": "가져올 zip 경로",
        "import_check": "확인", "import_confirm": "설치", "force": "덮어쓰기",
        "import_will_install": "'%s' 를 설치합니다",
        "import_installed": "'%s' 설치 완료",
    },
    "en": {
        "title": "Creatures", "lead": "Pick a colour and a size. Saving reaches running pets at once.",
        "refresh": "Refresh",
        "creatures": "Creatures", "colour": "Colour", "size": "Size", "special": "Special mode",
        "save": "Save", "wear": "Apply", "worn_btn": "Applied",
        "reset": "Defaults", "worn": "worn", "notworn": "not worn",
        "settings_of": "%s settings",
        "visor_auto": "When unattended", "visor_on": "Always", "visor_off": "Never",
        "named": "currently %s — pick a colour to change it",
        "saved": "Saved %s", "switched": "Now wearing %s",
        "reverted": "%s back to defaults",
        "applied_pets": " — %d pet(s) updated", "applied_next": " — from the next pet on",
        "serving": "claudlet creature settings: ", "stop": "(close the page, or Ctrl-C)",
        "port_taken": "(port %d is taken by something else; opened on another port)",
        "export": "Export", "export_retry_force": "Overwrite and retry",
        "export_dest": "Destination", "export_dest_placeholder": "Folder to save to (default: home)",
        "import": "Import", "import_cancel": "Cancel",
        "import_placeholder": "path to a zip to import",
        "import_check": "Check", "import_confirm": "Install", "force": "Overwrite",
        "import_will_install": "Will install '%s'",
        "import_installed": "Installed '%s'",
    },
}


def texts(cfg=None):
    cfg = petconfig.load_config() if cfg is None else cfg
    return TEXT[petconfig.resolve_lang(cfg.get("lang"))]


PAGE_TEMPLATE = """<!doctype html><meta charset="utf-8">
<title>claudlet — __T_title__</title>
<link rel="manifest" href="/manifest.webmanifest">
<link rel="icon" href="/api/icon?size=192" type="image/png">
<meta name="theme-color" content="#16161a">
<style>
:root{color-scheme:dark;--bg:#16161a;--card:#212128;--line:#33333d;--fg:#ECECF0;
      --dim:#9A9AA8;--accent:#6B8AFF;--sunk:#0e0e12;--w:1080px}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
     font:14px/1.5 system-ui,-apple-system,"Noto Sans KR",sans-serif;
     /* The window IS the frame: at the size we open at, everything fits and
        only the panes scroll. A page-level scrollbar would undo the dashboard
        feel, so the body is height-locked and the panels own their overflow.
        Below the one-column breakpoint the lock is released (see @media) --
        there, page scrolling is the only way the content stays reachable. */
     height:100dvh;display:flex;flex-direction:column;overflow:hidden}
header{flex:0 0 auto}
.wrap{width:100%;max-width:var(--w);margin:0 auto;padding:0 28px}
header{border-bottom:1px solid var(--line);background:#191920}
.sr-only{position:absolute;width:1px;height:1px;padding:0;margin:-1px;
        overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}
.bar{display:flex;align-items:center;justify-content:space-between;gap:14px;
    padding:14px 0}
h1{margin:0;font-size:18px;letter-spacing:.2px}
nav.tabs{display:flex;gap:4px}
nav.tabs button{background:none;color:var(--dim);border:0;border-bottom:2px solid transparent;
                border-radius:8px 8px 0 0;padding:10px 18px;font-weight:600;font-size:14px}
nav.tabs button[aria-selected=true]{color:var(--fg);border-bottom-color:var(--accent);
                                    background:var(--card)}
main{padding:16px 0 28px;flex:1 1 auto;min-height:0;overflow:hidden}
/* the only pane that scrolls at rest is the preview box (#shots); every other
   row here (creature bar, worn/wear line, colour/size/visor line) always
   stays on screen -- that's the point of this layout. */
#dress{height:100%;display:flex;flex-direction:column;gap:12px;min-height:0}
section{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:18px;
        min-height:0;display:flex;flex-direction:column}
h2{margin:0 0 14px;font-size:13px;color:var(--dim);font-weight:600;
   text-transform:uppercase;letter-spacing:.6px}
#settings{flex:1 1 auto;min-height:0;overflow:hidden}
.worn,.notworn{display:inline-block;padding:1px 8px;
               border-radius:999px;font-size:11px;font-weight:600}
.worn{background:#1F7A4D;color:#DFF7EA}
.notworn{background:#26262E;color:var(--dim)}
.row{display:flex;align-items:center;gap:12px;margin-bottom:18px;flex-wrap:wrap;
    flex:0 0 auto}
label{width:64px;color:var(--dim)}
input[type=color]{width:48px;height:32px;padding:0;border:1px solid var(--line);
                  border-radius:7px;background:none;cursor:pointer}
input[type=range]{flex:1;min-width:140px;accent-color:var(--accent)}
input[type=text]{flex:1;min-width:180px;background:var(--sunk);
                 border:1px solid var(--line);color:var(--fg);
                 border-radius:7px;padding:8px 10px;font:inherit}
code{background:#000;padding:2px 7px;border-radius:5px;font-size:12px}
/* creature row: a standalone import button to the LEFT, then one wide bar
   (the dropdown trigger + the export button) spanning the rest of the row */
.creature-row{margin-bottom:0}
.picker{position:relative;flex:1 1 auto;min-width:0}
.dropdown-bar{display:flex;align-items:center;gap:6px;background:var(--sunk);
             border:1px solid var(--line);border-radius:8px;padding:4px 4px 4px 10px}
.dropdown-bar .icon-btn{border:0}
.card-trigger{display:flex;align-items:center;gap:8px;flex:1 1 auto;min-width:0;
              background:none;color:var(--fg);border:0;
              padding:6px 4px;font-weight:500;cursor:pointer;text-align:left}
.card-trigger img{width:24px;height:24px;image-rendering:pixelated;flex:0 0 auto}
.card-trigger span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
/* drops DOWN over the page at the bar's own width -- an overlay, so opening it
   never reflows the row below and never lengthens the page */
.card-panel{position:absolute;top:calc(100% + 4px);left:0;right:0;z-index:20;
            max-height:45vh;overflow-y:auto;
            background:var(--card);border:1px solid var(--line);border-radius:10px;
            padding:6px;display:flex;flex-direction:column;gap:4px;
            box-shadow:0 8px 24px rgba(0,0,0,.4)}
.card-panel[hidden]{display:none}
.card{display:flex;align-items:center;gap:10px;width:100%;text-align:left;
      background:none;color:var(--fg);border:0;border-radius:7px;
      padding:6px 8px;font:inherit;cursor:pointer}
.card:hover,.card:focus{background:var(--sunk)}
.card img{width:32px;height:32px;image-rendering:pixelated;flex:0 0 auto}
.card .card-name{flex:1}
.icon-btn{background:none;border:1px solid var(--line);border-radius:7px;
          color:var(--dim);padding:6px;display:inline-flex;cursor:pointer}
.icon-btn svg{display:block}
.icon-btn:hover{color:var(--fg);border-color:var(--accent)}
.modal-backdrop{position:fixed;inset:0;background:rgba(0,0,0,.6);
                display:flex;align-items:center;justify-content:center;z-index:50}
.modal-backdrop[hidden]{display:none}
.modal{background:var(--card);border:1px solid var(--line);border-radius:12px;
       padding:20px;max-width:480px;width:90%;max-height:80vh;overflow-y:auto}
/* the one pane that scrolls at rest. flex-basis 0 + min-height 0 is what keeps
   a tall preview inside the box instead of stretching the panel (and with it
   the page) past the window. */
#shots{display:flex;gap:14px;flex-wrap:wrap;align-items:flex-start;align-content:flex-start;
       flex:1 1 0;min-height:0;min-width:0;overflow:auto;
       padding:14px;background:var(--sunk);border-radius:9px}
#shots figure{margin:0;text-align:center}
#shots img{display:block;image-rendering:pixelated;max-width:100%}
#shots figcaption{margin-top:6px;font-size:11px;color:var(--dim)}
button{background:var(--accent);color:#0b0b10;border:0;border-radius:8px;
       padding:10px 18px;font-weight:600;font-size:14px;cursor:pointer}
button[disabled]{opacity:.5;cursor:default}
button.ghost{background:none;color:var(--dim);border:1px solid var(--line)}
.seg{display:flex;gap:6px;flex-wrap:wrap}
.seg button{background:none;color:var(--dim);border:1px solid var(--line);
            padding:6px 14px;font-weight:500}
.seg button[aria-pressed=true]{background:var(--accent);color:#0b0b10;border-color:var(--accent)}
#said{color:var(--dim);font-size:13px;margin-left:12px}
#importInfo ul{margin:8px 0 0;padding-left:20px;color:var(--dim);font-size:12px}
@media (max-width:780px){
  /* narrow window: TIGHTEN the chrome, never release the height lock. Letting
     the page scroll here is what made the previews spill out of their box and
     down the page -- the preview keeps its own scrollbar at every width. */
  .wrap{padding:0 16px}
  label{width:100%}
}
</style>
<header><div class="wrap">
  <h1 class="sr-only">__T_title__</h1>
  <p class="sr-only">__T_lead__</p>
  <div class="bar">
    <nav class="tabs" id="tabs"></nav>
    <button type="button" id="refresh" class="icon-btn"
            title="__T_refresh__" aria-label="__T_refresh__">
      <svg viewBox="0 0 24 24" width="16" height="16" fill="none"
           stroke="currentColor" stroke-width="2" stroke-linecap="round"
           stroke-linejoin="round">
        <path d="M3 12a9 9 0 0 1 15-6.7L21 8"/>
        <path d="M21 3v5h-5"/>
        <path d="M21 12a9 9 0 0 1-15 6.7L3 16"/>
        <path d="M3 21v-5h5"/>
      </svg>
    </button>
  </div>
</div></header>
<main class="wrap">
  <div id="dress">
    <div class="row creature-row">
      <button type="button" id="importBtn" class="icon-btn"
              title="__T_import__" aria-label="__T_import__">
        <svg viewBox="0 0 24 24" width="16" height="16" fill="none"
             stroke="currentColor" stroke-width="2" stroke-linecap="round"
             stroke-linejoin="round">
          <path d="M12 13V3M12 13l4-4M12 13l-4-4"/>
          <path d="M4 15v4a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-4"/>
        </svg>
      </button>
      <div class="picker">
        <span id="pickLabel" class="sr-only">__T_creatures__</span>
        <div class="dropdown-bar">
          <button type="button" id="pickTrigger" class="card-trigger"
                  aria-haspopup="listbox" aria-expanded="false"
                  aria-controls="pickPanel" aria-labelledby="pickLabel"></button>
          <button type="button" id="exportBtn" class="icon-btn"
                  title="__T_export__" aria-label="__T_export__">
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none"
                 stroke="currentColor" stroke-width="2" stroke-linecap="round"
                 stroke-linejoin="round">
              <path d="M12 3v10M12 3l4 4M12 3l-4 4"/>
              <path d="M4 15v4a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-4"/>
            </svg>
          </button>
        </div>
        <div id="pickPanel" class="card-panel" role="listbox" hidden></div>
      </div>
    </div>
    <div class="row" id="exportResultRow">
      <span id="exportResult"></span>
    </div>
    <details id="exportMore">
      <summary>__T_export_dest__</summary>
      <div class="row">
        <input type="text" id="exportOut" placeholder="__T_export_dest_placeholder__">
      </div>
    </details>
    <section id="settings">
      <h2 id="who"></h2>
      <div class="row" id="wornRow">
        <span id="wornBadge"></span>
        <button id="save">__T_save__</button>
        <button id="wear" class="ghost">__T_wear__</button>
        <button id="reset" class="ghost">__T_reset__</button>
        <span id="said"></span>
      </div>
      <div class="row" id="colorSizeRow">
        <label for="col">__T_colour__</label>
        <input type="color" id="col">
        <code id="hex"></code>
        <label for="scale">__T_size__</label>
        <input type="range" id="scale" min="2" max="12" step="1">
        <code id="scaleval"></code>
      </div>
      <div class="row" id="visorRow">
        <label>__T_special__</label>
        <div id="visor" class="seg"></div>
        <span id="isnamed" class="sr-only"></span>
      </div>
      <div id="shots"></div>
    </section>
  </div>
</main>
<div id="importModal" class="modal-backdrop" hidden>
  <div class="modal" role="dialog" aria-modal="true" aria-labelledby="importModalTitle">
    <h2 id="importModalTitle">__T_import__</h2>
    <div class="row">
      <input type="text" id="importPath" placeholder="__T_import_placeholder__">
      <button id="importInspect" class="ghost">__T_import_check__</button>
    </div>
    <div id="importInfo"></div>
    <div class="row" id="importConfirmRow" hidden>
      <button id="importConfirm">__T_import_confirm__</button>
      <label style="width:auto"><input type="checkbox" id="importForce"> __T_force__</label>
    </div>
    <div class="row">
      <button id="importCancel" class="ghost">__T_import_cancel__</button>
    </div>
  </div>
</div>
<script>
let S = null;
let editing = null;      // which creature the panel is showing — NOT necessarily
                         // the one being worn. Looking at another creature's
                         // settings should not put it on the pet.
let tab = null;          // an agent name
const $ = (id) => document.getElementById(id);

function worn() {
  const a = (S.avatars || []).find((x) => x.selected);
  return a ? a.name : "claudlet";
}
function shot(state, cacheBust) {
  const q = new URLSearchParams({palette: $("col").value, scale: $("scale").value,
                                avatar: editing, visor: visorNow(),
                                state, t: cacheBust});
  return `<figure><img src="/api/preview?${q}" alt="${state}">
          <figcaption>${state}</figcaption></figure>`;
}
const T = __T_JSON__;
const IMPORT_TOKEN = __IMPORT_TOKEN__;   // gates POST /api/import only
const VISOR_LABEL = {auto: T.visor_auto, on: T.visor_on, off: T.visor_off};
function visorNow() {
  const on = document.querySelector("#visor button[aria-pressed=true]");
  return on ? on.dataset.v : "auto";
}
function redraw() {
  $("hex").textContent = $("col").value.toUpperCase();
  $("scaleval").textContent = $("scale").value + "x";
  const t = Date.now();
  const states = (S.avatar_states && S.avatar_states[editing]) || S.states;
  $("shots").innerHTML = states.map((s) => shot(s, t)).join("");
  $("who").textContent = T.settings_of.replace("%s", editing);
  const isWorn = editing === worn();
  for (const b of [$("wear")]) {
    b.disabled = isWorn;
    b.textContent = isWorn ? T.worn_btn : T.wear;
  }
  $("wornBadge").className = isWorn ? "worn" : "notworn";
  $("wornBadge").textContent = isWorn ? T.worn : T.notworn;
}
function showCreature(name) {
  editing = name;
  const look = (S.looks && S.looks[name]) || {};
  const pal = look.palette;
  const isHex = typeof pal === "string" && pal.startsWith("#");
  $("col").value = isHex ? pal : "#D97757";
  $("scale").value = look.scale || S.scale;
  $("visor").innerHTML = S.visor_modes.map((v) =>
    `<button data-v="${v}" aria-pressed="${v === (look.visor || "auto")}">` +
    `${VISOR_LABEL[v] || v}</button>`).join("");
  for (const b of document.querySelectorAll("#visor button")) {
    b.addEventListener("click", () => {
      for (const o of document.querySelectorAll("#visor button"))
        o.setAttribute("aria-pressed", String(o === b));
      redraw();
    });
  }
  // the "still on auto" note used to sit in the colour row and crowd it; keep
  // the information for a screen reader, off the visual row (sr-only)
  $("isnamed").textContent = isHex ? "" : T.named.replace("%s", pal);
  renderPickTrigger();
  redraw();
}
// One top-level tab per DETECTED agent. A single-agent machine has no agent
// to choose between, so it shows no tab row at all rather than a lone toggle.
// ---------- creature dropdown: a trigger button + a scrollable card panel
// (the old card-list look), instead of an unbounded list or a native <select>
// that fights the fixed-size, no-page-scroll window ----------
function pickCardEl(a) {
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "card";
  btn.setAttribute("role", "option");
  const img = document.createElement("img");
  const q = new URLSearchParams({palette: a.colour, scale: "4",
                                 avatar: a.name, state: "idle"});
  img.src = "/api/preview?" + q;
  img.alt = "";
  btn.appendChild(img);
  const span = document.createElement("span");
  span.className = "card-name";
  span.textContent = a.name;                     // untrusted text -> textContent
  btn.appendChild(span);
  const badge = document.createElement("span");
  badge.className = a.selected ? "worn" : "notworn";
  badge.textContent = a.selected ? T.worn : T.notworn;
  btn.appendChild(badge);
  btn.addEventListener("click", () => {
    showCreature(a.name);                         // select for viewing, don't wear
    closePanel(false);
  });
  return btn;
}
function renderPickPanel() {
  const panel = $("pickPanel");
  panel.innerHTML = "";
  for (const a of (S.avatars || [])) panel.appendChild(pickCardEl(a));
}
function renderPickTrigger() {
  const trig = $("pickTrigger");
  trig.innerHTML = "";
  const a = (S.avatars || []).find((x) => x.name === editing);
  const img = document.createElement("img");
  const q = new URLSearchParams({palette: (a && a.colour) || "auto", scale: "4",
                                 avatar: editing, state: "idle"});
  img.src = "/api/preview?" + q;
  img.alt = "";
  trig.appendChild(img);
  const span = document.createElement("span");
  span.textContent = editing;                     // untrusted text -> textContent
  trig.appendChild(span);
}
function openPanel() {
  renderPickPanel();
  $("pickPanel").hidden = false;
  $("pickTrigger").setAttribute("aria-expanded", "true");
  document.addEventListener("click", onOutsideClick, true);
  document.addEventListener("keydown", onPanelKeydown, true);
}
function closePanel(focusTrigger) {
  $("pickPanel").hidden = true;
  $("pickTrigger").setAttribute("aria-expanded", "false");
  document.removeEventListener("click", onOutsideClick, true);
  document.removeEventListener("keydown", onPanelKeydown, true);
  if (focusTrigger) $("pickTrigger").focus();
}
function onOutsideClick(e) {
  if (!$("pickPanel").contains(e.target) && e.target !== $("pickTrigger"))
    closePanel(false);
}
function onPanelKeydown(e) {
  if (e.key === "Escape") closePanel(true);
}
function tabRows(s) {
  return (s.agents || []).map((a) => ({name: a.name, label: a.label}));
}
function paintTabs(rows) {
  $("tabs").innerHTML = rows.map((r) =>
    `<button role="tab" data-tab="${r.name}" ` +
    `aria-selected="${r.name === tab}">${r.label}</button>`).join("");
  for (const b of document.querySelectorAll("#tabs button"))
    b.addEventListener("click", () => selectTab(b.dataset.tab));
}
async function selectTab(name) {
  const rows = tabRows(S);
  if (!rows.length) return;
  tab = rows.some((r) => r.name === name) ? name : rows[0].name;
  const r = await fetch("/api/state?agent=" + encodeURIComponent(tab));
  editing = null;                       // show the new agent's creature
  fill(await r.json());
}
function fill(s) {
  S = s;
  closePanel(false);                      // never left open across a refill
  const rows = tabRows(s);
  tab = s.agent;                          // state always belongs to one agent
  paintTabs(rows);
  $("scale").min = s.scale_range[0];
  $("scale").max = s.scale_range[1];
  const target = editing && s.looks[editing] ? editing : worn();
  showCreature(target);
}
$("pickTrigger").addEventListener("click", () => {
  if ($("pickPanel").hidden) openPanel();
  else closePanel(false);
});
// 색 입력은 브라우저에 따라 드래그 중 input 을, OS 색 대화상자를 쓰면 닫을 때
// change 만 쏜다. 둘 다 들어야 고른 색이 바로 미리보기에 뜬다.
for (const ev of ["input", "change"]) {
  $("col").addEventListener(ev, redraw);
  $("scale").addEventListener(ev, redraw);
}
async function post(body, note) {
  for (const b of ["save", "reset", "wear"]) $(b).disabled = true;
  const r = await fetch("/api/config", {method: "POST",
    headers: {"content-type": "application/json"}, body: JSON.stringify(body)});
  const out = await r.json();
  $("said").textContent = note + (out.pets
      ? T.applied_pets.replace("%d", out.pets) : T.applied_next);
  for (const b of ["save", "reset", "wear"]) $(b).disabled = false;
  return out;
}
$("save").addEventListener("click", async () =>
  fill(await post({agent: S.agent, creature: editing, palette: $("col").value,
                   scale: +$("scale").value, visor: visorNow()},
                  T.saved.replace("%s", editing))));
async function doWear() {
  return fill(await post({agent: S.agent, avatar: editing},
                         T.switched.replace("%s", editing)));
}
$("wear").addEventListener("click", doWear);
$("reset").addEventListener("click", async () =>
  // null clears the setting so the creature's own default applies again
  fill(await post({agent: S.agent, creature: editing, palette: null, scale: null,
                   visor: null}, T.reverted.replace("%s", editing))));
// Re-read the server's state and redraw in place. The config file can change
// under the page (the CLI, another pet), and an installed app window has no
// address bar to reload from.
async function refresh() {
  const r = await fetch("/api/state?agent=" + encodeURIComponent(S ? S.agent : ""));
  fill(await r.json());
  $("said").textContent = "";
}
$("refresh").addEventListener("click", refresh);
fetch("/api/state").then((r) => r.json()).then(fill);
// Tell the server the page is still open. It stops when this stops, which is
// what closing the tab looks like from its side — otherwise a settings page
// opened from the pet's menu would leave a server running all session.
// ---------- export / import a creature (paths, not uploads -- the server is
// local, so the file is already on this machine). Both act on `editing`, the
// creature currently shown in the dropdown, so their controls live right next
// to it instead of a separate tab. ----------
function renderExportResult(out) {
  const el = $("exportResult");
  el.innerHTML = "";
  if (out.error) {
    const span = document.createElement("span");
    span.textContent = out.error;                 // untrusted text -> textContent
    el.appendChild(span);
    if (out.error.indexOf("--force") !== -1) {
      el.appendChild(document.createTextNode(" "));
      const btn = document.createElement("button");
      btn.className = "ghost";
      btn.textContent = T.export_retry_force;
      btn.addEventListener("click", () => doExport(true));
      el.appendChild(btn);
    }
    return;
  }
  const code = document.createElement("code");
  code.textContent = out.path;                     // untrusted text -> textContent
  el.appendChild(code);
}
async function doExport(force) {
  const r = await fetch("/api/export", {method: "POST",
    headers: {"content-type": "application/json"},
    body: JSON.stringify({creature: editing, force: !!force,
                          out: $("exportOut").value || undefined})});
  renderExportResult(await r.json());
}
$("exportBtn").addEventListener("click", () => doExport(false));

function openImportModal() {
  $("importModal").hidden = false;
  document.addEventListener("keydown", onImportModalKeydown, true);
}
function closeImportModal() {
  $("importModal").hidden = true;
  document.removeEventListener("keydown", onImportModalKeydown, true);
}
function onImportModalKeydown(e) {
  if (e.key === "Escape") closeImportModal();
}
$("importBtn").addEventListener("click", openImportModal);
$("importCancel").addEventListener("click", closeImportModal);
$("importModal").addEventListener("click", (e) => {
  if (e.target === $("importModal")) closeImportModal();   // backdrop click
});

let pendingImportPath = null;
function renderImportInfo(out) {
  const el = $("importInfo");
  el.innerHTML = "";
  if (out.error) {
    const p = document.createElement("div");
    p.textContent = out.error;                     // untrusted text -> textContent
    el.appendChild(p);
    $("importConfirmRow").hidden = true;
    return;
  }
  const head = document.createElement("div");
  head.textContent = T.import_will_install.replace("%s", out.name)
    + " (" + out.entries.length + ", " + out.total + " bytes)";
  el.appendChild(head);
  const ul = document.createElement("ul");
  for (const e of out.entries) {
    const li = document.createElement("li");
    li.textContent = e;                             // archive entry name -> textContent, never innerHTML
    ul.appendChild(li);
  }
  el.appendChild(ul);
  $("importConfirmRow").hidden = false;
}
$("importInspect").addEventListener("click", async () => {
  pendingImportPath = $("importPath").value;
  const r = await fetch("/api/import", {method: "POST",
    headers: {"content-type": "application/json"},
    body: JSON.stringify({path: pendingImportPath, token: IMPORT_TOKEN})});
  renderImportInfo(await r.json());
});
$("importConfirm").addEventListener("click", async () => {
  const r = await fetch("/api/import", {method: "POST",
    headers: {"content-type": "application/json"},
    body: JSON.stringify({path: pendingImportPath, confirm: true,
                          force: $("importForce").checked, token: IMPORT_TOKEN})});
  const out = await r.json();
  if (out.error) {
    renderImportInfo(out);
    return;
  }
  $("importInfo").innerHTML = "";
  const p = document.createElement("div");
  p.textContent = T.import_installed.replace("%s", out.name);
  $("importInfo").appendChild(p);
  $("importConfirmRow").hidden = true;
  closeImportModal();
  fill(await (await fetch("/api/state")).json());   // new creature is now selectable
});

setInterval(() => fetch("/api/alive").catch(() => {}), __HEARTBEAT__);
window.addEventListener("pagehide", () => {
  // best effort: shuts it down at once instead of after the idle timeout
  try { navigator.sendBeacon("/api/bye"); } catch (e) {}
});
// Installable: Chrome only offers the install if a service worker with a fetch
// handler is registered. Nothing is cached — this is a local server.
if ("serviceWorker" in navigator) {
  try { navigator.serviceWorker.register("/sw.js"); } catch (e) {}
}
</script>
"""


def page(cfg=None, import_token=""):
    """The page in the user's language. Built per request rather than once at
    import: the language can change in the config while the server is up.

    `import_token` is embedded so the page's own JS can send it back on
    POST /api/import -- the one endpoint that plants new code on disk."""
    t = texts(cfg)
    out = PAGE_TEMPLATE.replace("__HEARTBEAT__", str(HEARTBEAT_MS))
    out = out.replace("__T_JSON__", json.dumps(t, ensure_ascii=False))
    out = out.replace("__IMPORT_TOKEN__", json.dumps(import_token))
    for key, val in t.items():
        out = out.replace("__T_%s__" % key, val)
    return out


def _handler_class(initial_agent=None, import_token=""):
    from http.server import BaseHTTPRequestHandler
    from urllib.parse import parse_qs, urlparse

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass                        # don't scribble over the user's terminal

        def _send(self, code, body, ctype):
            self.server.last_seen = time.monotonic()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, payload, code=200):
            self._send(code, json.dumps(payload).encode("utf-8"),
                       "application/json; charset=utf-8")

        def do_GET(self):
            u = urlparse(self.path)
            if u.path == "/":
                return self._send(200, page(import_token=import_token).encode("utf-8"),
                                  "text/html; charset=utf-8")
            if u.path == "/api/alive":
                # doubles as "is the server on this port ours?" -- see port_plan
                return self._json({"ok": True, "app": APP_ID})
            if u.path == "/manifest.webmanifest":
                return self._send(200, json.dumps(manifest()).encode("utf-8"),
                                  "application/manifest+json; charset=utf-8")
            if u.path == "/sw.js":
                return self._send(200, SERVICE_WORKER.encode("utf-8"),
                                  "text/javascript; charset=utf-8")
            if u.path == "/api/icon":
                q = parse_qs(u.query)
                try:
                    size = int(q.get("size", ["192"])[0])
                except ValueError:
                    size = 192
                png = icon_png(max(16, min(size, 1024)))
                return self._send(200 if png else 500, png or b"", "image/png")
            if u.path == "/api/bye":
                self._json({"ok": True})
                self.server.last_seen = bye_last_seen(
                    time.monotonic(), self.server.idle_timeout)
                return
            if u.path == "/api/state":
                q = parse_qs(u.query)
                agent = q.get("agent", [None])[0] or initial_agent
                return self._json(state_payload(agent=agent))
            if u.path == "/api/preview":
                q = parse_qs(u.query)
                png = render_png(q.get("palette", ["auto"])[0],
                                 q.get("scale", [petconfig.DEFAULT_SCALE])[0],
                                 q.get("state", ["idle"])[0],
                                 avatar=q.get("avatar", [None])[0],
                                 visor=q.get("visor", ["auto"])[0])
                return self._send(200 if png else 500, png or b"", "image/png")
            return self._send(404, b"not found", "text/plain")

        def do_POST(self):
            path = urlparse(self.path).path
            if path == "/api/bye":
                self._json({"ok": True})
                self.server.last_seen = bye_last_seen(
                    time.monotonic(), self.server.idle_timeout)
                return
            if path not in ("/api/config", "/api/export", "/api/import"):
                return self._send(404, b"not found", "text/plain")
            try:
                n = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(n) or b"{}")
            except (ValueError, TypeError):
                return self._json({"error": "bad json"}, 400)
            if not isinstance(body, dict):
                return self._json({"error": "bad json"}, 400)
            if path == "/api/config":
                return self._json(apply(body))
            if path == "/api/export":
                return self._json(export_api(body))
            # /api/import is the one endpoint that plants (and later runs) new
            # code on disk, so it alone requires the per-run token the page
            # was served with -- everything else here is unauthenticated on
            # loopback by design.
            given = body.get("token")
            if not isinstance(given, str) or not hmac.compare_digest(given, import_token):
                return self._json({"error": "missing or bad token"}, 403)
            return self._json(import_api(body))

    return Handler


def serve(open_browser=True, idle_timeout=IDLE_TIMEOUT, agent=None,
          port=PREFERRED_PORT, app_window=False):
    """Run the settings page for as long as it is open. Returns the URL.

    `agent` is which agent's pet opened this page (optional; defaults to
    the registry default agent, the prior behaviour) -- so a right-click on a
    Codex pet opens on Codex instead of always on Claude.

    One server per machine: if the preferred port already has a claudlet
    settings server on it, this hands the page to THAT one and returns instead
    of starting a second (clicking settings twice, or from two pets). Anything
    else on the port means falling back to an OS-chosen one.

    Stops on Ctrl-C, and on its own once the page has stopped saying it is
    there — which is what closing the tab looks like from here."""
    from http.server import HTTPServer
    t = texts()
    what, chosen = port_plan(port, probe_port) if port else ("bind", 0)
    if what == "attach":
        url = "http://127.0.0.1:%d/" % chosen
        print(t["serving"] + url)
        if open_browser:
            launch_browser(url, app_window)
        return url
    import_token = secrets.token_urlsafe(16)   # per-run only; never persisted
    handler = _handler_class(agent, import_token)
    try:
        srv = HTTPServer(("127.0.0.1", chosen), handler)
    except OSError:
        # lost the race, or the probe was wrong: take any free port
        srv = HTTPServer(("127.0.0.1", 0), handler)
        what = "fallback"
    srv.timeout = 5                     # wake up often enough to notice silence
    srv.last_seen = time.monotonic()
    srv.idle_timeout = idle_timeout     # read by the bye handler's grace calc
    url = "http://127.0.0.1:%d/" % srv.server_port
    print(t["serving"] + url)
    if what == "fallback" and port:
        print(t["port_taken"] % port)
    print(t["stop"])
    if open_browser:
        launch_browser(url, app_window)
    try:
        while time.monotonic() - srv.last_seen < idle_timeout:
            srv.handle_request()        # returns on a request or on the timeout
    except KeyboardInterrupt:
        print("")
    finally:
        srv.server_close()
    return url


def launch_browser(url, app_window=False):
    """Open the page in the user's ORDINARY browser.

    `app_window=True` asks for a chrome-less app window instead (its own Chrome
    profile, so the flags actually apply -- a second invocation on the default
    profile is swallowed by the running Chrome). That is opt-in: a bare window
    with no address bar reads as "some strange app", and the page is an ordinary
    local page. Someone who wants it as an app installs it (the manifest is
    served for exactly that) or passes --app.

    Best effort: a settings page that does not open is not worth an exception."""
    cmd = browser_command(url) if app_window else None
    try:
        if cmd:
            import subprocess
            try:
                os.makedirs(chrome_profile_dir(), exist_ok=True)
            except OSError:
                pass                     # Chrome creates it itself if needed
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
            return
        import webbrowser
        webbrowser.open(url)
    except Exception:
        pass                            # no browser here: the URL is printed
