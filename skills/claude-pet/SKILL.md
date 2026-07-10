---
name: claude-pet
description: Launch/attach the claude-pet desktop buddy, or trigger a motion on it. "/claude-pet" attaches a pet to the CURRENT session; "/claude-pet standalone" launches an unattached roaming pet; "/claude-pet <motion>" plays a motion (jump/wave/sing/juggle/float/celebrate/thinking/sleeping/error/attention); "/claude-pet list" lists motions; "/claude-pet stop" clears a held motion. Use when the user types "/claude-pet", "펫 띄워", "펫 붙여", "펫 점프", "start the pet".
---

# claude-pet — launch the desktop buddy

A frameless roaming pixel creature. By default this **attaches** a pet to the
**current session** (so it reacts to this session's Claude Code activity). Pass
`standalone` for an unattached one.

## Routing

Look at the argument the user passed after `/claude-pet`:

- a **motion name** (`jump`, `wave`, `sing`, `juggle`, `float`, `celebrate`,
  `thinking`, `sleeping`, `error`, `attention`), or `list`, or `stop`/`clear`
  → run the motion helper (below); do NOT launch a pet.
- `standalone` → the standalone section.
- nothing → the attach section.

### Trigger a motion

```bash
~/claude-pet/bin/claude-pet-motion <arg>
```
e.g. `~/claude-pet/bin/claude-pet-motion jump`, `~/claude-pet/bin/claude-pet-motion float`
(holds until `~/claude-pet/bin/claude-pet-motion stop`), `~/claude-pet/bin/claude-pet-motion list`.
The helper broadcasts to every running pet and prints how many reacted; if it
says `-> 0 pet(s)`, no pet is running — offer to attach one with `/claude-pet`.

## Default: attach to THIS session

0. **Pick a Python.** `python3` is canonical on Linux/macOS; on Windows it's
   often a Microsoft Store alias stub that's *present on PATH* but exits
   nonzero without doing anything, so `command -v` alone can't tell it apart
   from a real interpreter — probe that it actually runs:
   ```bash
   PY=python3; "$PY" -c "" >/dev/null 2>&1 || PY=python
   ```

1. **Find this session's id.** Claude Code sets `$CLAUDE_CODE_SESSION_ID` for
   the running session; fall back to the newest transcript under
   `~/.claude/projects/` if it's unset:
   ```bash
   SID="${CLAUDE_CODE_SESSION_ID:-$(ls -t ~/.claude/projects/*/*.jsonl 2>/dev/null | head -1 | xargs -n1 basename | sed 's/\.jsonl$//')}"
   ```

2. **Detect the host app** (terminal/IDE) so click-to-focus targets the right window:
   ```bash
   HOST=$("$PY" -c "import sys; sys.path.insert(0, '$HOME/claude-pet/src'); import hostinfo; print(hostinfo.detect_host())")
   ```

3. **Skip if one is already attached, else launch it bound to the session.**
   Pets listen on loopback TCP, not a unix socket (stock Windows Python has no
   `AF_UNIX`, so the whole project uses one TCP code path — see
   `src/hostinfo.py`); check liveness the same way the hook does, via the
   `.port` file it publishes:
   ```bash
   ALIVE=$("$PY" -c "
import sys, socket
sys.path.insert(0, '$HOME/claude-pet/src')
import hostinfo
port = hostinfo.read_session_port('$SID')
ok = False
if port is not None:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(0.3)
    try:
        s.connect((hostinfo.LOOPBACK, port)); ok = True
    except OSError:
        pass
print('yes' if ok else 'no')
")
   if [ "$ALIVE" = "yes" ]; then
       echo "already attached to this session 🐾"
   else
       nohup "$PY" ~/claude-pet/bin/claude-pet --session "$SID" --host "$HOST" >/dev/null 2>&1 < /dev/null &
       disown
       echo "attached to session $SID (host=$HOST) 🐾"
   fi
   ```

**Reactions require hooks.** The pet only reacts to this session if the
claude-pet hooks are installed (`~/claude-pet/bin/claude-pet-install-hooks`) AND
this session loaded them. If hooks were installed *after* this session started,
restart the session (or the pet attaches but stays idle). New sessions
auto-attach their own pet via the SessionStart hook, so `/claude-pet` is mainly
for sessions that predate the install, or to bring a closed pet back.

## `standalone` — an unattached roaming pet

If the user said "standalone" (or just wants a decorative pet that reacts to no
particular session):
```bash
PY=python3; "$PY" -c "" >/dev/null 2>&1 || PY=python
nohup "$PY" ~/claude-pet/bin/claude-pet >/dev/null 2>&1 < /dev/null &
disown
echo "standalone pet running 🐾"
```

## Notes
- Multiple pets are fine — each is independent. Stop one via right-click → 종료.
- This skill never installs hooks or edits settings; it only launches a pet.
