# Configuration

[← README](../README.md)

Remap which animation shows for which Claude Code activity in a JSON config at
`~/.config/claude-pet/config.json` (all keys optional):

```json
{
  "tools":      { "Bash": "work_search", "Grep": "sing", "*": "work_computer" },
  "events":     { "prompt": "thinking", "celebrate": "juggle" },
  "raw_events": { "PostToolUse": "celebrate", "SubagentStop": "wave" }
}
```

- **`tools`** — tool name → state. `"*"` is the fallback for unmapped tools;
  `mcp__*` tools default to `work_web` unless named explicitly.
- **`events`** — event slot → state. Slots: `start`, `prompt`, `done`, `celebrate`,
  `error`, `permission`, `idle_prompt`.
- **`raw_events`** — raw hook event name → state, for any event without a slot
  (`PostToolUse`, `SubagentStop`, `PreCompact`, …). Knowing the event name the hook
  sends is enough to map it; slotted events keep their built-in behaviour.

Values must be a known state/motion:

```
work_computer  work_search  work_web  work_agent  work_skill
idle  sleeping  thinking  attention  asking  error  celebrate
jump  wave  sing  juggle
```

Anything unknown is ignored, so a typo just falls back to the defaults. Restart the
pet to pick up changes.
