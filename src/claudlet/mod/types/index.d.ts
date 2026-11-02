// claudlet mod 의 $.state 계약.
export type ClaudletFrame = {
  columns: number
  rows: number
  cells: string
  /** 띠 안에서의 자리, 0(왼쪽)..1(오른쪽) */
  x: number
  /** 띠 바닥에서 뜬 높이, 0..1 (점프·떨어지기) */
  y: number
  /** 펫이 쓴 시각(초) — 오래되면 펫이 죽은 것 */
  ts: number
}

declare module 'claude-code' {
  interface PluginState {
    claudlet: { frame: ClaudletFrame | null }
  }
}
