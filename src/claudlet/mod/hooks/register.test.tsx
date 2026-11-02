import { expect, test } from 'claude-code/testing'

import { parseFrame, parseLines } from './register'

const BAND = {
  plugin: 'claudlet',
  component: 'AbovePrompt',
  props: {
    hasSurvey: false,
    isWorking: false,
    maxRows: 20,
    bodyColumns: 60,
    scroll: { offset: 0, bodyRows: 20 },
    view: {},
  },
} as const

test('only lines past the ack are sent, in id order', () => {
  const raw = '{"id":3,"text":"c"}\nhalf-writ\n{"id":1,"text":"a"}\n{"id":2,"text":"b"}'
  expect(parseLines(raw, 1).map(l => l.text)).toEqual(['b', 'c'])
})

test('a gone or stale frame clears the band', () => {
  const f = '{"ts":100,"columns":2,"rows":1,"cells":"AAAA","x":0.5}'
  expect(parseFrame(f, 101)?.columns).toBe(2)
  expect(parseFrame(f, 200)).toBe(null)
  expect(parseFrame('{"ts":100,"gone":true}', 100)).toBe(null)
})

test('a frame an earlier version stored (no y) still draws', async ($, on) => {
  on('state.get', () => ({
    value: { value: { columns: 1, rows: 1, cells: 'gCUAAAAA/wAAAAAB', x: 0.5, ts: Date.now() / 1000 }, version: 1 },
  }))
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await ui.find({ key: 'pet' })).toBeDefined()
  await ui.unmount()
})

test('the visiting pet is drawn above the prompt with a way home', async ($, on) => {
  const cells = btoa(String.fromCharCode(...new Uint8Array(Uint32Array.of(0x2580, 0xff0000, 0x01000000).buffer)))
  on('state.get', () => ({
    value: { value: { columns: 1, rows: 1, cells, x: 0, y: 0, ts: Date.now() / 1000 }, version: 1 },
  }))
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await ui.find({ key: 'pet' })).toBeDefined()
  expect(await ui.find({ key: 'home' })).toBeDefined()
  await ui.unmount()
})
