---
name: claudlet
description: Launch/attach the claudlet desktop buddy, trigger a motion, or update it. "/claudlet" attaches a pet to the CURRENT session; "/claudlet standalone" launches an unattached roaming pet; "/claudlet <motion>" plays a motion (jump/wave/sing/juggle/float/celebrate/thinking/sleeping/error/attention); "/claudlet list" lists motions; "/claudlet stop" clears a held motion; "/claudlet update" pulls the latest version and reinstalls. Use when the user types "/claudlet", "펫 띄워", "펫 붙여", "펫 점프", "펫 업데이트", "update the pet", "start the pet".
---

# claudlet — launch the desktop buddy

A frameless roaming pixel creature. By default this **attaches** a pet to the
**current session** (so it reacts to this session's Claude Code activity). Pass
`standalone` for an unattached one.

## How to run a claudlet command

claudlet ships console commands (`claudlet-attach`, `claudlet-motion`,
`claudlet-install`). Define this helper once, then use it in the sections
below — it prefers the installed command (pipx/pip put it on PATH) and falls
back to a source checkout's `bin/` shim:
```bash
cpet() {  # usage: cpet <subcmd> [args...]   e.g. cpet attach --standalone
  local name="claudlet-$1"; shift
  if command -v "$name" >/dev/null 2>&1; then "$name" "$@"
  elif [ -x "$HOME/claudlet/bin/$name" ]; then "$HOME/claudlet/bin/$name" "$@"
  else echo "claudlet isn't installed — see the README"; return 127; fi
}
```

## Routing

Look at the argument the user passed after `/claudlet`:

- a **motion name** (`jump`, `wave`, `sing`, `juggle`, `float`, `celebrate`,
  `thinking`, `sleeping`, `error`, `attention`), or `list`, or `stop`/`clear`
  → **Trigger a motion**; do NOT launch a pet.
- `update` (or `업데이트`) → **Update**.
- `standalone` → **Standalone**.
- nothing → **Attach** (default).

## Attach (default)

```bash
cpet attach
```
`claudlet-attach` finds this session (`$CLAUDE_CODE_SESSION_ID`, else the
newest transcript under `~/.claude/projects/`), detects the host terminal/IDE
so click-to-focus targets the right window, skips if a pet is already attached
(the same liveness handshake the hook uses — a bare connect can't tell a live
pet from a reused stale port), and launches a detached pet bound to the session.
It prints `attached to session ...` or `already attached ...`.

**Reactions require hooks.** The pet only reacts to this session if the
claudlet hooks are installed (`claudlet-install`) AND this session loaded
them. If hooks were installed *after* this session started, restart the session
(or the pet attaches but stays idle). New sessions auto-attach their own pet via
the SessionStart hook, so `/claudlet` is mainly for sessions that predate the
install, or to bring a closed pet back.

## Standalone

An unattached, decorative pet that reacts to no particular session:
```bash
cpet attach --standalone
```

## Trigger a motion

```bash
cpet motion <arg>    # jump | wave | sing | juggle | float | celebrate | thinking | sleeping | error | attention | stop | list
```
e.g. `cpet motion jump`, `cpet motion float` (holds until `cpet motion stop`),
`cpet motion list`. It broadcasts to every running pet and prints how many
reacted; if it says `-> 0 pet(s)`, none is running — offer to attach one with
`/claudlet`.

## Update

Bring claudlet up to date, then re-register the hooks/skill:
```bash
if [ -d "$HOME/claudlet/.git" ]; then            # source checkout
  git -C "$HOME/claudlet" pull --ff-only && cpet install
elif command -v pipx >/dev/null 2>&1; then          # pipx install
  pipx upgrade claudlet && cpet install
else
  echo "update with the same command you installed with (see the README)"
fi
```
If `git pull` fails with local changes / divergence, report it (don't force).
New code only takes effect on a **fresh** pet + session: close any running pet
(right-click → 종료) and restart this Claude Code session (or run `/claudlet`
again) so the reinstalled hooks and new pet code load.

## Notes
- Multiple pets are fine — each is independent. Stop one via right-click → 종료.
- This skill only launches/updates a pet; `claudlet-install` is what edits
  settings/hooks.
