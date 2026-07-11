# Configuration

[← README](../README.md) · **English** | [한국어](configuration.ko.md)

Remap which animation shows for which Claude Code activity in a JSON config at
`~/.config/claudlet/config.json` (all keys optional).

> **Tip:** run `claudlet-config` (or ask Claude `/claudlet config`) to print the
> exact path, the current effective values, and — importantly — any entries
> that were **silently dropped** because of a typo or unknown slot. `claudlet-config
> init` scaffolds a starter file; `claudlet-config open` opens it in your editor.

Example:

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

## Language

`lang` sets the language of the pet's speech bubbles, tray tooltips, and right-click
menu — `"ko"`, `"en"`, or `"auto"` (default; follows your locale, falling back to
English):

```json
{ "lang": "en" }
```
