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

from claudlet.core import avatars, hostinfo, petconfig

PREVIEW_STATES = ("idle", "work_computer", "celebrate", "sleeping")


# ---------- pure: what the page shows and what a save does ----------

def state_payload(cfg=None):
    """Everything the page needs to draw itself."""
    cfg = petconfig.load_config() if cfg is None else cfg
    pal = cfg.get("palette", "auto")
    return {
        "avatars": [{"name": n, "selected": n == avatars.DEFAULT}
                    for n in avatars.available()],
        "palette": pal,
        # the colour the picker should open on: a named palette has no single
        # colour of its own, so fall back to the built-in body colour
        "colour": pal if isinstance(pal, str) and pal.startswith("#") else "#D97757",
        "named": not (isinstance(pal, str) and pal.startswith("#")),
        "scale": petconfig.clamp_scale(cfg.get("scale")),
        "scale_range": [petconfig.MIN_SCALE, petconfig.MAX_SCALE],
        "states": list(PREVIEW_STATES),
    }


def clean_updates(body):
    """The subset of a posted body we are willing to write, cleaned.

    Anything unrecognised is dropped rather than written through: this endpoint
    edits the same file a user hand-writes tools/events into."""
    out = {}
    pal = body.get("palette")
    if isinstance(pal, str) and (pal in petconfig._PALETTE_NAMES
                                 or petconfig.derive_palette(pal) is not None):
        out["palette"] = pal
    if "scale" in body:
        out["scale"] = petconfig.clamp_scale(body.get("scale"))
    return out


def apply(body, broadcast=None):
    """Save what the page posted and tell every running pet to re-dress.

    `broadcast` is injectable so tests don't reach for sockets. Returns the
    payload the page redraws from, plus how many pets took it."""
    updates = clean_updates(body)
    if updates:
        petconfig.save_keys(updates)
    send = hostinfo.broadcast if broadcast is None else broadcast
    told = 0
    if updates:
        try:
            told = send(json.dumps({"cmd": "restyle"}))
        except Exception:
            told = 0            # nothing running is not an error
    payload = state_payload()
    payload["applied"] = sorted(updates)
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


def render_png(palette, scale, state="idle", frame=None):
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
    avatar = avatars.get()
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
    avatar.draw(p, pad * u, pad * u, u, state, f, palette=pal)
    p.end()
    buf = QBuffer()
    buf.open(QBuffer.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    return bytes(buf.data())


# ---------- the shell ----------

PAGE = """<!doctype html><meta charset="utf-8">
<title>claudlet — 크리처</title>
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
.card[aria-selected=true]{border-color:#6B8AFF;background:#1b1b24}
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
#said{color:var(--dim);font-size:13px;margin-left:12px}
@media (max-width:720px){main{padding:16px}label{width:100%}}
</style>
<header>
  <h1>크리처</h1>
  <p>색과 크기를 정합니다. 저장하면 떠 있는 펫에 바로 반영됩니다.</p>
</header>
<main>
  <section id="creatures"><h2>크리처</h2><div id="list"></div></section>
  <section id="settings">
    <h2>설정</h2>
    <div class="row">
      <label for="col">색</label>
      <input type="color" id="col">
      <code id="hex"></code>
      <span id="isnamed" style="color:var(--dim)"></span>
    </div>
    <div class="row">
      <label for="scale">크기</label>
      <input type="range" id="scale" min="2" max="12" step="1">
      <code id="scaleval"></code>
    </div>
    <div id="shots"></div>
    <div class="row" style="margin:18px 0 0">
      <button id="save">저장</button><span id="said"></span>
    </div>
  </section>
</main>
<script>
let S = null;
const $ = (id) => document.getElementById(id);

function shot(state, cacheBust) {
  const q = new URLSearchParams({palette: $("col").value, scale: $("scale").value,
                                state, t: cacheBust});
  return `<figure><img src="/api/preview?${q}" alt="${state}">
          <figcaption>${state}</figcaption></figure>`;
}
function redraw() {
  $("hex").textContent = $("col").value.toUpperCase();
  $("scaleval").textContent = $("scale").value + "x";
  const t = Date.now();
  $("shots").innerHTML = S.states.map((s) => shot(s, t)).join("");
  $("isnamed").textContent = "";
}
function fill(s) {
  S = s;
  $("list").innerHTML = s.avatars.map((a) => `
    <div class="card" aria-selected="${a.selected}">
      <img src="/api/preview?state=idle&scale=3&palette=${encodeURIComponent(s.colour)}">
      <div>${a.name}</div></div>`).join("");
  $("col").value = s.colour;
  $("scale").min = s.scale_range[0];
  $("scale").max = s.scale_range[1];
  $("scale").value = s.scale;
  redraw();
  if (s.named) $("isnamed").textContent = "지금은 " + s.palette + " — 색을 고르면 바뀝니다";
}
$("col").addEventListener("input", redraw);
$("scale").addEventListener("input", redraw);
$("save").addEventListener("click", async () => {
  $("save").disabled = true;
  const r = await fetch("/api/config", {method: "POST",
    headers: {"content-type": "application/json"},
    body: JSON.stringify({palette: $("col").value, scale: +$("scale").value})});
  const out = await r.json();
  $("said").textContent = out.pets ? `저장했습니다 — 펫 ${out.pets}마리에 반영`
                                   : "저장했습니다 — 다음에 뜨는 펫부터";
  $("save").disabled = false;
});
fetch("/api/state").then((r) => r.json()).then(fill);
</script>
"""


def _handler_class():
    from http.server import BaseHTTPRequestHandler
    from urllib.parse import parse_qs, urlparse

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass                        # don't scribble over the user's terminal

        def _send(self, code, body, ctype):
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
                return self._send(200, PAGE.encode("utf-8"),
                                  "text/html; charset=utf-8")
            if u.path == "/api/state":
                return self._json(state_payload())
            if u.path == "/api/preview":
                q = parse_qs(u.query)
                png = render_png(q.get("palette", ["auto"])[0],
                                 q.get("scale", [petconfig.DEFAULT_SCALE])[0],
                                 q.get("state", ["idle"])[0])
                return self._send(200 if png else 500, png or b"", "image/png")
            return self._send(404, b"not found", "text/plain")

        def do_POST(self):
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


def serve(open_browser=True):
    """Run the settings page until interrupted. Returns the URL it served."""
    from http.server import HTTPServer
    srv = HTTPServer(("127.0.0.1", 0), _handler_class())
    url = "http://127.0.0.1:%d/" % srv.server_port
    print("claudlet 크리처 설정: " + url)
    print("(Ctrl-C 로 종료)")
    if open_browser:
        try:
            import webbrowser
            webbrowser.open(url)
        except Exception:
            pass                        # no browser here: the URL is printed
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("")
    finally:
        srv.server_close()
    return url
