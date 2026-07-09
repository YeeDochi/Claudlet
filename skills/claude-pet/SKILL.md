---
name: claude-pet
description: Launch/attach the claude-pet desktop buddy. "/claude-pet" attaches a pet to the CURRENT Claude Code session so it reacts to this session's activity; "/claude-pet standalone" launches an unattached roaming pet. Use when the user types "/claude-pet", "펫 띄워", "펫 붙여", "start the pet".
---

# claude-pet — launch the desktop buddy

A frameless roaming pixel creature. By default this **attaches** a pet to the
**current session** (so it reacts to this session's Claude Code activity). Pass
`standalone` for an unattached one.

## Default: attach to THIS session

1. **Find this session's id.** The transcript being written right now is the
   newest `*.jsonl` under `~/.claude/projects/`:
   ```bash
   SID=$(ls -t ~/.claude/projects/*/*.jsonl 2>/dev/null | head -1 | xargs -n1 basename | sed 's/\.jsonl$//')
   ```

2. **Detect the host app** (terminal/IDE) so click-to-focus targets the right window:
   ```bash
   HOST=$(python3 -c "import sys; sys.path.insert(0, '$HOME/claude-pet/src'); import hostinfo; print(hostinfo.detect_host())")
   ```

3. **Skip if one is already attached, else launch it bound to the session:**
   ```bash
   SOCK="${XDG_RUNTIME_DIR:-/tmp}/claude-pet-$SID.sock"
   if python3 -c "import socket,sys; s=socket.socket(socket.AF_UNIX); s.settimeout(0.3); s.connect('$SOCK')" 2>/dev/null; then
       echo "already attached to this session 🐾"
   else
       setsid ~/claude-pet/bin/claude-pet --session "$SID" --host "$HOST" >/dev/null 2>&1 < /dev/null & disown
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
setsid ~/claude-pet/bin/claude-pet >/dev/null 2>&1 < /dev/null & disown
echo "standalone pet running 🐾"
```

## Notes
- Multiple pets are fine — each is independent. Stop one via right-click → 종료.
- This skill never installs hooks or edits settings; it only launches a pet.
