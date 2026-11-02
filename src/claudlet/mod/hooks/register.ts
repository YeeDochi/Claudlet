// claudlet mod — 펫이 건넨 말을 이 세션의 진짜 턴으로 넣는다.
//
// 펫은 `claudlet-<sid>.send` 에 한 줄씩 쌓기만 하고(쓰는 쪽은 펫 하나),
// mod 는 읽기만 한다. 어디까지 넣었는지(ack)는 `$.store` 와 하트비트 파일
// `claudlet-<sid>.mod` 에 남기고, 펫이 다음에 쓸 때 ack 이하 줄을 걷어낸다.
// 파일 하나에 쓰는 쪽이 하나뿐이라 rename 없이도 잃거나 두 번 넣지 않는다.
// 설계: docs/superpowers/specs/2026-10-12-mod-send-design.md
import type { Register, EngineInterface } from 'claude-code'

const POLL_MS = 500
const BEAT_MS = 10_000

type Line = { id: number; text: string; framed?: boolean }

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

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    const result = await next(e)
    // 크리처 머리(`claude -p`)는 이 환경변수를 달고 뜬다. 거기서 펫의 말을
    // 집어 머리 자신에게 넣으면 안 된다.
    if (await $.env.get('CLAUDLET_CREATURE')) return result

    const sid = await $.session.id()
    const dir = await runtimeDir($)
    const sep = dir.includes('\\') ? '\\' : '/'
    const sendPath = `${dir}${sep}claudlet-${sid}.send`
    const beatPath = `${dir}${sep}claudlet-${sid}.mod`
    const key = `ack:${sid}`

    let ack = Number((await $.store.get(key)) ?? 0)
    let seen = -1
    let busy = false

    const beat = (gone = false) =>
      $.fs.write(beatPath, JSON.stringify({ ack, ts: Date.now(), gone })).catch(() => {})

    const poll = async () => {
      if (busy) return
      busy = true
      try {
        const st = await $.fs.stat(sendPath).catch(() => null)
        if (!st || st.kind !== 'file' || st.mtimeMs === seen) return
        seen = st.mtimeMs
        const lines = parseLines(await $.fs.read(sendPath), ack)
        if (!lines.length) return
        for (const m of lines) {
          // 넣기 전에 ack 를 올린다: 타이머가 다시 돌아도 두 번 넣지 않는다
          ack = m.id
          await $.store.set(key, ack)
          // 일하는 중이면 Claude Code 가 줄을 세웠다가 끝나면 새 턴으로 연다.
          // resolve 는 그 턴이 시작될 때라 기다리지 않는다.
          void $.prompt.submit(m.framed ? { text: m.text } : { text: m.text, asUser: true })
        }
        await beat()
      } catch {
        // 펫이 쓰는 도중이거나 파일이 사라졌다 — 다음 폴링에 다시 본다
      } finally {
        busy = false
      }
    }

    await beat()
    $.clock.every(BEAT_MS, () => void beat())
    $.clock.every(POLL_MS, () => void poll())
    return result
  })

  on('session.end', async ($, e, next) => {
    // 펫이 곧바로 옛 길(직접 치기·깨우기)로 돌아가게 하트비트를 끈다
    if (!(await $.env.get('CLAUDLET_CREATURE'))) {
      const sid = await $.session.id()
      const dir = await runtimeDir($)
      const sep = dir.includes('\\') ? '\\' : '/'
      const ack = Number((await $.store.get(`ack:${sid}`)) ?? 0)
      await $.fs
        .write(`${dir}${sep}claudlet-${sid}.mod`, JSON.stringify({ ack, ts: Date.now(), gone: true }))
        .catch(() => {})
    }
    return next(e)
  })
}
