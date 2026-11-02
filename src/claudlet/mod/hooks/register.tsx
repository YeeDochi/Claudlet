// claudlet mod — 데스크톱 펫과 이 세션을 잇는다.
//
// 1. 말 넣기: 펫은 `claudlet-<sid>.send` 에 한 줄씩 쌓기만 하고(쓰는 쪽은 펫 하나),
//    mod 는 읽기만 한다. 어디까지 넣었는지(ack)는 `$.store` 와 하트비트 파일
//    `claudlet-<sid>.mod` 에 남기고, 펫이 다음에 쓸 때 ack 이하 줄을 걷어낸다.
//    파일 하나에 쓰는 쪽이 하나뿐이라 rename 없이도 잃거나 두 번 넣지 않는다.
// 2. 터미널 방문: 펫이 `claudlet-<sid>.frame` 에 자기 그림을 반 블록 칸으로 내보내면
//    프롬프트 위 띠에 Raster 로 그린다. [집에 가] 는 하트비트의 `home` 을 바꾼다.
// 설계: docs/superpowers/specs/2026-10-12-mod-send-design.md
import { atom, read, update } from 'claude-code'
import type { Register, EngineInterface } from 'claude-code'

import type { ClaudletFrame } from '../types'

const POLL_MS = 500
const FRAME_MS = 150
const BEAT_MS = 10_000
const STALE_S = 3 // 펫이 이만큼 그림을 안 보내면 띠를 비운다

type Line = { id: number; text: string; framed?: boolean; context?: string }

const frame = atom({ plugin: 'claudlet', key: 'frame' } as const, null)

// 넣은 말 -> 그 턴에 붙일 덧붙임. 줄을 선 프롬프트가 열릴 때 prompt.submit 이 집어 간다.
const contexts = new Map<string, string>()
// 턴이 도는 동안엔 띠를 멈춘다 — 답이 쏟아질 때 움직이면 읽기를 방해한다
let turning = false
// 이번 방문에서 가장 큰 자세의 높이 — 띠는 줄어들지 않는다(프롬프트가 들썩이지 않게)
let bandRows = 0
// [집에 가] 버튼이 하트비트를 다시 쓰는 길 (session.start 가 채운다)
let goHome: (() => Promise<void>) | null = null

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

async function paths($: EngineInterface) {
  const sid = await $.session.id()
  const dir = await runtimeDir($)
  const sep = dir.includes('\\') ? '\\' : '/'
  const base = `${dir}${sep}claudlet-${sid}`
  return { sid, send: `${base}.send`, beat: `${base}.mod`, frame: `${base}.frame` }
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

export function parseFrame(raw: string, nowS: number): ClaudletFrame | null {
  try {
    const f = JSON.parse(raw)
    if (f?.gone || typeof f?.cells !== 'string' || nowS - f.ts > STALE_S) return null
    return { columns: f.columns, rows: f.rows, cells: f.cells, x: f.x ?? 0, y: f.y ?? 0, ts: f.ts }
  } catch {
    return null
  }
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    const result = await next(e)
    // 크리처 머리(`claude -p`)는 이 환경변수를 달고 뜬다. 거기서 펫의 말을
    // 집어 머리 자신에게 넣으면 안 된다.
    if (await $.env.get('CLAUDLET_CREATURE')) return result

    const p = await paths($)
    const key = `ack:${p.sid}`
    let ack = Number((await $.store.get(key)) ?? 0)
    let home = 0
    let seen = -1
    let seenFrame = -1
    let busy = false

    const beat = (gone = false) =>
      $.fs.write(p.beat, JSON.stringify({ ack, home, ts: Date.now(), gone })).catch(() => {})
    goHome = async () => {
      home = Date.now()
      await beat()
    }

    const poll = async () => {
      if (busy) return
      busy = true
      try {
        const st = await $.fs.stat(p.send).catch(() => null)
        if (!st || st.kind !== 'file' || st.mtimeMs === seen) return
        seen = st.mtimeMs
        const lines = parseLines(await $.fs.read(p.send), ack)
        if (!lines.length) return
        for (const m of lines) {
          // 넣기 전에 ack 를 올린다: 타이머가 다시 돌아도 두 번 넣지 않는다
          ack = m.id
          await $.store.set(key, ack)
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

    const pollFrame = async () => {
      const st = await $.fs.stat(p.frame).catch(() => null)
      const now = Date.now() / 1000
      if (turning) return // 마지막 그림 그대로 가만히 — 다시 그리지 않는다
      if (st && st.kind === 'file' && st.mtimeMs !== seenFrame) {
        seenFrame = st.mtimeMs
        const f = parseFrame(await $.fs.read(p.frame).catch(() => ''), now)
        await update($, frame, () => f)
        return
      }
      // 펫이 죽었거나 멈췄다 — 띠에 유령을 남기지 않는다
      const cur = await read($, frame)
      if (cur && now - cur.ts > STALE_S) await update($, frame, () => null)
    }

    await beat()
    $.clock.every(BEAT_MS, () => void beat())
    $.clock.every(POLL_MS, () => void poll())
    $.clock.every(FRAME_MS, () => void pollFrame().catch(() => {}))
    return result
  })

  on('turn.start', ($, e, next) => {
    turning = true
    return next(e)
  })
  on('turn.complete', ($, e, next) => {
    turning = false
    return next(e)
  })

  // 우리가 넣은 프롬프트가 턴을 열 때 그 턴에만 말투·창 정보를 붙인다.
  // 훅 경계(PostToolUse)에 맡기면 일하는 중인 다른 턴이 가져간다.
  on('prompt.submit', ($, e, next) => {
    const ctx =
      e.origin.kind === 'plugin' && e.origin.name === 'claudlet' ? contexts.get(e.text) : undefined
    if (ctx === undefined) return next(e)
    contexts.delete(e.text)
    return next({ ...e, context: [...(e.context ?? []), ctx] })
  })

  // 펫이 놀러 와 있으면 프롬프트 위 띠에서 걸어 다닌다.
  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    if (e.surface !== 'terminal' || e.props.hasSurvey) return next(e)
    const f = await read($, frame)
    if (!f) {
      bandRows = 0
      return next(e)
    }
    bandRows = Math.max(bandRows, f.rows)
    const { Box, Raster, Button } = $.ui.resolve(e)
    const room = Math.max(0, e.props.bodyColumns - f.columns - 4)
    // 이전 버전이 남긴 값에는 x 가 이상할 수 있다(상태는 리로드를 넘어 남는다)
    const x = Number.isFinite(f.x) ? Math.min(1, Math.max(0, f.x)) : 0
    // 띠는 크리처 높이만큼만. 띠 밖으로 겹쳐 그리면 잘린다(실측: 발만 보였다).
    // 점프는 높이 대신 자세로만 — 띠 높이가 변하면 프롬프트가 들썩인다.
    return (
      <Box key="band" flexDirection="row" alignItems="flex-end" height={bandRows}>
        <Button key="home" plain label="⌂" onPress={() => void goHome?.()} />
        <Box width={2 + Math.round(x * room)} />
        <Raster key="pet" columns={f.columns} rows={f.rows} cells={f.cells} />
      </Box>
    )
  })

  on('session.end', async ($, e, next) => {
    // 펫이 곧바로 옛 길(직접 치기·깨우기)로 돌아가게 하트비트를 끈다
    if (!(await $.env.get('CLAUDLET_CREATURE'))) {
      const p = await paths($)
      const ack = Number((await $.store.get(`ack:${p.sid}`)) ?? 0)
      await $.fs
        .write(p.beat, JSON.stringify({ ack, ts: Date.now(), gone: true }))
        .catch(() => {})
    }
    return next(e)
  })
}
