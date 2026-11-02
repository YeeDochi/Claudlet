// claudlet mod — 데스크톱 펫과 이 세션을 잇는다.
//
// 1. 말 넣기: 펫은 `claudlet-<sid>.send` 에 한 줄씩 쌓기만 하고(쓰는 쪽은 펫 하나),
//    mod 는 읽기만 한다. 어디까지 넣었는지(ack)는 `$.store` 와 하트비트 파일
//    `claudlet-<sid>.mod` 에 남기고, 펫이 다음에 쓸 때 ack 이하 줄을 걷어낸다.
//    파일 하나에 쓰는 쪽이 하나뿐이라 rename 없이도 잃거나 두 번 넣지 않는다.
// 2. 크리처 머리: `fork` 줄은 세션에 넣지 않고 `$.model.fork` 로 이 세션의 맥락
//    위에서 따로 묻는다(본 세션의 턴을 잡아먹지 않는다). 답은 `.forked` 에.
// 3. say 도구: 에이전트가 펫의 목소리로 한 줄 말하면 `.said` 에 — 펫이 말풍선에 띄운다.
//    🗨 마커와 트랜스크립트 꼬리 읽기를 대신한다.
// `.forked`·`.said` 는 mod 가 유일한 쓰는 쪽이다(최근 것만 통째로 다시 쓴다).
// 설계: docs/superpowers/specs/2026-10-12-mod-send-design.md
import type { Register, EngineInterface } from 'claude-code'

const POLL_MS = 500
const BEAT_MS = 10_000
const KEEP = 20 // .forked/.said 에 남길 최근 줄 수
const SAY = 'mcp__claudlet__say'

type Line = { id: number; text: string; framed?: boolean; context?: string; fork?: boolean }
type Out = { id: number; text?: string; error?: string }

// 넣은 말 -> 그 턴에 붙일 덧붙임. 줄을 선 프롬프트가 열릴 때 prompt.submit 이 집어 간다.
const contexts = new Map<string, string>()
const forked: Out[] = []
const said: Out[] = []

async function runtimeDir($: EngineInterface): Promise<string> {
  // claudlet.core.hostinfo.runtime_dir() 와 같은 규칙 (tempfile.gettempdir 순서)
  const dir =
    (await $.env.get('XDG_RUNTIME_DIR')) ||
    (await $.env.get('TMPDIR')) ||
    (await $.env.get('TEMP')) ||
    (await $.env.get('TMP')) ||
    '/tmp'
  return dir.replace(/[\\/]+$/, '')
}

async function base($: EngineInterface): Promise<string> {
  const dir = await runtimeDir($)
  const sep = dir.includes('\\') ? '\\' : '/'
  return `${dir}${sep}claudlet-${await $.session.id()}`
}

export function parseLines(raw: string, ack: number): Line[] {
  const out: Line[] = []
  for (const s of raw.split('\n')) {
    try {
      const m = JSON.parse(s)
      if (typeof m?.id === 'number' && m.id > ack && typeof m.text === 'string' && m.text) {
        out.push(m)
      }
    } catch {
      // 빈 줄·쓰다 만 줄은 건너뛴다 — 다음 폴링에 다 쓰여 있다
    }
  }
  return out.sort((a, b) => a.id - b.id)
}

/** 최근 KEEP 줄만 남겨 통째로 다시 쓴다(mod 가 유일한 쓰는 쪽). */
function keep(list: Out[], item: Out): string {
  list.push(item)
  list.splice(0, Math.max(0, list.length - KEEP))
  return list.map(m => JSON.stringify(m)).join('\n') + '\n'
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    const result = await next(e)
    // 크리처 머리(`claude -p`)는 이 환경변수를 달고 뜬다. 거기서 펫의 말을
    // 집어 머리 자신에게 넣으면 안 된다.
    if (await $.env.get('CLAUDLET_CREATURE')) return result

    const b = await base($)
    const key = `ack:${await $.session.id()}`
    let ack = Number((await $.store.get(key)) ?? 0)
    let seen = -1
    let busy = false

    const beat = (gone = false) =>
      $.fs.write(`${b}.mod`, JSON.stringify({ ack, ts: Date.now(), gone })).catch(() => {})

    const ask = async (m: Line) => {
      const r = await $.model.fork({ prompt: m.text }).catch(() => null)
      const out: Out = r?.isAnswered ? { id: m.id, text: r.text } : { id: m.id, error: r ? r.reason : 'failed' }
      await $.fs.write(`${b}.forked`, keep(forked, out)).catch(() => {})
    }

    const poll = async () => {
      if (busy) return
      busy = true
      try {
        const st = await $.fs.stat(`${b}.send`).catch(() => null)
        if (!st || st.kind !== 'file' || st.mtimeMs === seen) return
        seen = st.mtimeMs
        const lines = parseLines(await $.fs.read(`${b}.send`), ack)
        if (!lines.length) return
        for (const m of lines) {
          // 넣기 전에 ack 를 올린다: 타이머가 다시 돌아도 두 번 넣지 않는다
          ack = m.id
          await $.store.set(key, ack)
          if (m.fork) {
            void ask(m) // 세션을 건드리지 않고 따로 묻는다
            continue
          }
          // 일하는 중이면 Claude Code 가 줄을 세웠다가 끝나면 새 턴으로 연다.
          // resolve 는 그 턴이 시작될 때라 기다리지 않는다.
          if (m.context) contexts.set(m.text, m.context)
          void $.prompt.submit(m.framed ? { text: m.text } : { text: m.text, asUser: true })
        }
        await beat()
      } catch {
        // 펫이 쓰는 도중이거나 파일이 사라졌다 — 다음 폴링에 다시 본다
      } finally {
        busy = false
      }
    }

    await $.tool.register({
      name: 'say',
      description:
        "Say one short line out loud as the user's desktop pet creature; it shows in the " +
        "pet's speech bubble. Use it ONLY when this turn carries a [claudlet] note asking " +
        'for the pet\'s line (the user talked to the pet). Never otherwise.',
      inputSchema: {
        type: 'object',
        properties: { text: { type: 'string', description: 'One short line in the pet voice.' } },
        required: ['text'],
      },
      isDeferred: false,
    })

    await beat()
    $.clock.every(BEAT_MS, () => void beat())
    $.clock.every(POLL_MS, () => void poll())
    return result
  })

  // 우리 도구는 빌트인 타입표에 없다(매처로 좁히면 tsc 가 터진다) — 이름으로 거르고 입력은 두 모양 다 읽는다
  on('tool.call', async ($, e, next) => {
    if (String(e.tool) !== SAY) return next(e)
    const raw = e as unknown as { text?: unknown; input?: { text?: unknown } }
    const text = String(raw.text ?? raw.input?.text ?? '').trim()
    if (!text) return { deny: 'text is empty' }
    await $.fs.write(`${await base($)}.said`, keep(said, { id: Date.now(), text }))
    return { result: 'said' }
  })

  // 우리가 넣은 프롬프트가 턴을 열 때 그 턴에만 말투·창 정보를 붙인다.
  // 훅 경계(PostToolUse)에 맡기면 일하는 중인 다른 턴이 가져간다.
  on('prompt.submit', ($, e, next) => {
    const ctx = e.origin.kind === 'plugin' && e.origin.name === 'claudlet' ? contexts.get(e.text) : undefined
    if (ctx === undefined) return next(e)
    contexts.delete(e.text)
    return next({ ...e, context: [...(e.context ?? []), ctx] })
  })

  on('session.end', async ($, e, next) => {
    // 펫이 곧바로 옛 길(직접 치기·깨우기)로 돌아가게 하트비트를 끈다
    if (!(await $.env.get('CLAUDLET_CREATURE'))) {
      const ack = Number((await $.store.get(`ack:${await $.session.id()}`)) ?? 0)
      await $.fs.write(`${await base($)}.mod`, JSON.stringify({ ack, ts: Date.now(), gone: true })).catch(() => {})
    }
    return next(e)
  })
}
