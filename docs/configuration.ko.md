# 설정

[← README](../README.ko.md) · [English](configuration.md) | **한국어**

어떤 Claude Code 활동에 어떤 애니메이션을 보일지 `~/.config/claudlet/config.json`에서
재매핑해요 (모든 키 선택).

> **팁:** `claudlet-config`(또는 Claude에게 `/claudlet config`) 실행하면 정확한 경로,
> 현재 적용값, 그리고 오타·잘못된 슬롯 때문에 **조용히 버려진 항목**까지 보여줘요.
> `claudlet-config init`은 시작 템플릿 생성, `claudlet-config open`은 에디터로 열기.

예시:

```json
{
  "tools":      { "Bash": "work_search", "Grep": "sing", "*": "work_computer" },
  "events":     { "prompt": "thinking", "celebrate": "juggle" },
  "raw_events": { "PostToolUse": "celebrate", "SubagentStop": "wave" }
}
```

- **`tools`** — 도구명 → 상태. `"*"`는 매핑 안 된 도구의 폴백. `mcp__*`는 명시 안 하면
  `work_web`.
- **`events`** — 이벤트 슬롯 → 상태. 슬롯: `start`, `prompt`, `done`, `celebrate`, `error`,
  `permission`, `idle_prompt`.
- **`raw_events`** — 슬롯 없는 원본 훅 이벤트명 → 상태 (`PostToolUse`, `SubagentStop`,
  `PreCompact` 등). 훅이 보내는 이벤트명만 알면 매핑 가능. 슬롯 있는 이벤트는 기본 동작 유지.

값은 알려진 상태/모션이어야 해요:

```
work_computer  work_search  work_web  work_agent  work_skill
idle  sleeping  thinking  attention  asking  error  celebrate
jump  wave  sing  juggle
```

모르는 값은 무시돼 기본값으로 폴백하니, 오타가 나도 안전해요. 바꾸면 펫 재시작.

## 언어

`lang`은 펫의 말풍선·트레이 툴팁·우클릭 메뉴 언어를 정해요 — `"ko"`, `"en"`, 또는
`"auto"`(기본값; 로케일 따라가고, 안 되면 영어):

```json
{ "lang": "en" }
```
