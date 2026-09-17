#!/usr/bin/env python3
"""claudlet-config ui — the creature settings page.

Pick a creature, then set how it looks: its colour and how big it is. Served
from a throwaway local HTTP server so the page can show a REAL render of the
creature as you change things — the preview is drawn by the same renderer the
pet uses, so what you see is what lands on the desktop.

stdlib only (`http.server`): a settings screen is not worth a web framework,
and the pet must stay installable with nothing but PyQt6.

Local only. The server binds 127.0.0.1 on an OS-chosen port and stops when the
window is closed / the command is interrupted.

The request handling is split into PURE functions (`state_payload`, `apply`)
that take and return data, so the behaviour is tested without a socket; the
HTTP class below is a thin shell over them.
"""
import json
import os
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

PREVIEW_STATES = ("idle", "work_computer", "celebrate", "sleeping")


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


def current_agent(body, cfg):
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


def apply(body, broadcast=None):
    """Save what the page posted and tell every running pet to re-dress.

    `broadcast` is injectable so tests don't reach for sockets. Returns the
    payload the page redraws from, plus how many pets took it."""
    cfg = petconfig.load_config()
    agent = current_agent(body, cfg)
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


# ---------- the shell ----------

# The page follows the same `lang` setting the pet does. Korean-only was fine
# while this was one developer's tool; it ships now.
TEXT = {
    "ko": {
        "title": "크리처", "lead": "색과 크기를 정합니다. 저장하면 떠 있는 펫에 바로 반영됩니다.",
        "agents": "에이전트",
        "creatures": "크리처", "colour": "색", "size": "크기", "special": "특수 모드",
        "save": "저장", "wear": "이 크리처 입히기", "worn_btn": "입고 있음",
        "reset": "기본으로", "worn": "착용 중", "notworn": "미착용",
        "settings_of": "%s 설정",
        "visor_auto": "오토모드일 때", "visor_on": "항상", "visor_off": "안 함",
        "named": "지금은 %s — 색을 고르면 바뀝니다",
        "saved": "%s 설정을 저장했습니다", "switched": "%s 로 갈아입혔습니다",
        "reverted": "%s 를 기본으로 되돌렸습니다",
        "applied_pets": " — 펫 %d마리에 반영", "applied_next": " — 다음에 뜨는 펫부터",
        "serving": "claudlet 크리처 설정: ", "stop": "(창을 닫거나 Ctrl-C 로 종료)",
    },
    "en": {
        "title": "Creatures", "lead": "Pick a colour and a size. Saving reaches running pets at once.",
        "agents": "Agents",
        "creatures": "Creatures", "colour": "Colour", "size": "Size", "special": "Special mode",
        "save": "Save", "wear": "Wear this one", "worn_btn": "Worn",
        "reset": "Defaults", "worn": "worn", "notworn": "not worn",
        "settings_of": "%s settings",
        "visor_auto": "When unattended", "visor_on": "Always", "visor_off": "Never",
        "named": "currently %s — pick a colour to change it",
        "saved": "Saved %s", "switched": "Now wearing %s",
        "reverted": "%s back to defaults",
        "applied_pets": " — %d pet(s) updated", "applied_next": " — from the next pet on",
        "serving": "claudlet creature settings: ", "stop": "(close the page, or Ctrl-C)",
    },
}


def texts(cfg=None):
    cfg = petconfig.load_config() if cfg is None else cfg
    return TEXT[petconfig.resolve_lang(cfg.get("lang"))]


PAGE_TEMPLATE = """<!doctype html><meta charset="utf-8">
<title>claudlet — __T_title__</title>
<style>
:root{color-scheme:dark;--bg:#16161a;--card:#212128;--line:#33333d;--fg:#ECECF0;--dim:#9A9AA8}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
     font:14px/1.5 system-ui,-apple-system,"Noto Sans KR",sans-serif}
header{padding:20px 24px;border-bottom:1px solid var(--line)}
h1{margin:0;font-size:17px;letter-spacing:.2px}
header p{margin:4px 0 0;color:var(--dim);font-size:13px}
main{display:flex;gap:24px;padding:24px;flex-wrap:wrap;align-items:flex-start}
section{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:18px}
h2{margin:0 0 14px;font-size:13px;color:var(--dim);font-weight:600;
   text-transform:uppercase;letter-spacing:.6px}
#creatures{min-width:210px}
.card{display:flex;gap:12px;align-items:center;padding:10px;border-radius:9px;
      border:1px solid transparent;cursor:pointer}
.card[aria-current=true]{border-color:#6B8AFF;background:#1b1b24}
.worn,.notworn{display:inline-block;margin-top:4px;padding:1px 8px;
               border-radius:999px;font-size:11px;font-weight:600}
.worn{background:#1F7A4D;color:#DFF7EA}
.notworn{background:#26262E;color:var(--dim)}
.card img{width:56px;height:44px;object-fit:contain;image-rendering:pixelated}
#settings{flex:1;min-width:320px}
.row{display:flex;align-items:center;gap:12px;margin-bottom:18px;flex-wrap:wrap}
label{width:64px;color:var(--dim)}
input[type=color]{width:48px;height:32px;padding:0;border:1px solid var(--line);
                  border-radius:7px;background:none;cursor:pointer}
input[type=range]{flex:1;min-width:160px;accent-color:#6B8AFF}
code{background:#000;padding:2px 7px;border-radius:5px;font-size:12px}
#shots{display:flex;gap:14px;flex-wrap:wrap;align-items:flex-end;
       min-height:120px;padding:14px;background:#0e0e12;border-radius:9px}
#shots figure{margin:0;text-align:center}
#shots img{display:block;image-rendering:pixelated}
#shots figcaption{margin-top:6px;font-size:11px;color:var(--dim)}
button{background:#6B8AFF;color:#0b0b10;border:0;border-radius:8px;
       padding:10px 18px;font-weight:600;font-size:14px;cursor:pointer}
button[disabled]{opacity:.5;cursor:default}
button.ghost{background:none;color:var(--dim);border:1px solid var(--line)}
.seg{display:flex;gap:6px}
.seg button{background:none;color:var(--dim);border:1px solid var(--line);
            padding:6px 14px;font-weight:500}
.seg button[aria-pressed=true]{background:#6B8AFF;color:#0b0b10;border-color:#6B8AFF}
.hint{color:var(--dim);font-size:12px;margin:-10px 0 16px 76px}
#said{color:var(--dim);font-size:13px;margin-left:12px}
@media (max-width:720px){main{padding:16px}label{width:100%}}
</style>
<header>
  <h1>__T_title__</h1>
  <p>__T_lead__</p>
</header>
<main>
  <section id="creatures">
    <div id="agents" hidden><h2>__T_agents__</h2><div id="agentlist" class="seg"></div></div>
    <h2>__T_creatures__</h2><div id="list"></div>
  </section>
  <section id="settings">
    <h2 id="who"></h2>
    <div class="row">
      <label for="col">__T_colour__</label>
      <input type="color" id="col">
      <code id="hex"></code>
      <span id="isnamed" style="color:var(--dim)"></span>
    </div>
    <div class="row">
      <label for="scale">__T_size__</label>
      <input type="range" id="scale" min="2" max="12" step="1">
      <code id="scaleval"></code>
    </div>
    <div class="row">
      <label>__T_special__</label>
      <div id="visor" class="seg"></div>
    </div>
    <div id="shots"></div>
    <div class="row" style="margin:18px 0 0">
      <button id="save">__T_save__</button>
      <button id="wear" class="ghost">__T_wear__</button>
      <button id="reset" class="ghost">__T_reset__</button>
      <span id="said"></span>
    </div>
  </section>
</main>
<script>
let S = null;
let editing = null;      // which creature the panel is showing — NOT necessarily
                         // the one being worn. Looking at another creature's
                         // settings should not put it on the pet.
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
  $("wear").disabled = isWorn;
  $("wear").textContent = isWorn ? T.worn_btn : T.wear;
  for (const c of document.querySelectorAll(".card"))
    c.setAttribute("aria-current", String(c.dataset.name === editing));
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
  $("isnamed").textContent = isHex ? ""
    : T.named.replace("%s", pal);
  redraw();
}
function fill(s) {
  S = s;
  const rows = s.agents || [];
  $("agents").hidden = rows.length < 2;
  $("agentlist").innerHTML = rows.map((a) =>
    `<button data-agent="${a.name}" aria-pressed="${a.selected}">${a.label}</button>`
  ).join("");
  for (const b of document.querySelectorAll("#agentlist button"))
    b.addEventListener("click", async () => {
      const r = await fetch("/api/state?agent=" + encodeURIComponent(b.dataset.agent));
      editing = null;                       // show the new agent's creature
      fill(await r.json());
    });
  $("list").innerHTML = s.avatars.map((a) => `
    <div class="card" data-name="${a.name}" aria-selected="${a.selected}">
      <img src="/api/preview?state=idle&scale=3&avatar=${encodeURIComponent(a.name)}&palette=${encodeURIComponent(a.colour)}">
      <div><div>${a.name}</div>
        ${a.selected ? `<span class="worn">${T.worn}</span>`
                     : `<span class="notworn">${T.notworn}</span>`}
      </div></div>`).join("");
  for (const card of document.querySelectorAll(".card"))
    card.addEventListener("click", () => showCreature(card.dataset.name));
  $("scale").min = s.scale_range[0];
  $("scale").max = s.scale_range[1];
  showCreature(editing && s.looks[editing] ? editing : worn());
}
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
  fill(await post({creature: editing, palette: $("col").value,
                   scale: +$("scale").value, visor: visorNow()},
                  T.saved.replace("%s", editing))));
$("wear").addEventListener("click", async () =>
  fill(await post({agent: S.agent, avatar: editing}, T.switched.replace("%s", editing))));
$("reset").addEventListener("click", async () =>
  // null clears the setting so the creature's own default applies again
  fill(await post({creature: editing, palette: null, scale: null, visor: null},
                  T.reverted.replace("%s", editing))));
fetch("/api/state").then((r) => r.json()).then(fill);
// Tell the server the page is still open. It stops when this stops, which is
// what closing the tab looks like from its side — otherwise a settings page
// opened from the pet's menu would leave a server running all session.
setInterval(() => fetch("/api/alive").catch(() => {}), __HEARTBEAT__);
window.addEventListener("pagehide", () => {
  // best effort: shuts it down at once instead of after the idle timeout
  try { navigator.sendBeacon("/api/bye"); } catch (e) {}
});
</script>
"""


def page(cfg=None):
    """The page in the user's language. Built per request rather than once at
    import: the language can change in the config while the server is up."""
    t = texts(cfg)
    out = PAGE_TEMPLATE.replace("__HEARTBEAT__", str(HEARTBEAT_MS))
    out = out.replace("__T_JSON__", json.dumps(t, ensure_ascii=False))
    for key, val in t.items():
        out = out.replace("__T_%s__" % key, val)
    return out


def _handler_class():
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
                return self._send(200, page().encode("utf-8"),
                                  "text/html; charset=utf-8")
            if u.path == "/api/alive":
                return self._json({"ok": True})     # the page is still open
            if u.path == "/api/bye":
                self.server.last_seen = 0.0         # tab closed: stop now
                return self._json({"ok": True})
            if u.path == "/api/state":
                q = parse_qs(u.query)
                return self._json(state_payload(agent=q.get("agent", [None])[0]))
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
            if urlparse(self.path).path == "/api/bye":
                self._json({"ok": True})
                self.server.last_seen = 0.0         # sendBeacon posts
                return
            if urlparse(self.path).path != "/api/config":
                return self._send(404, b"not found", "text/plain")
            try:
                n = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(n) or b"{}")
            except (ValueError, TypeError):
                return self._json({"error": "bad json"}, 400)
            if not isinstance(body, dict):
                return self._json({"error": "bad json"}, 400)
            return self._json(apply(body))

    return Handler


def serve(open_browser=True, idle_timeout=IDLE_TIMEOUT):
    """Run the settings page for as long as it is open. Returns the URL.

    Stops on Ctrl-C, and on its own once the page has stopped saying it is
    there — which is what closing the tab looks like from here."""
    from http.server import HTTPServer
    srv = HTTPServer(("127.0.0.1", 0), _handler_class())
    srv.timeout = 5                     # wake up often enough to notice silence
    srv.last_seen = time.monotonic()
    url = "http://127.0.0.1:%d/" % srv.server_port
    t = texts()
    print(t["serving"] + url)
    print(t["stop"])
    if open_browser:
        try:
            import webbrowser
            webbrowser.open(url)
        except Exception:
            pass                        # no browser here: the URL is printed
    try:
        while time.monotonic() - srv.last_seen < idle_timeout:
            srv.handle_request()        # returns on a request or on the timeout
    except KeyboardInterrupt:
        print("")
    finally:
        srv.server_close()
    return url
