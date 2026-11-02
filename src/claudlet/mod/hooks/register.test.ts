import { expect, test } from 'claude-code/testing'

import { parseLines } from './register'

test('only lines past the ack are sent, in id order', () => {
  const raw = '{"id":3,"text":"c"}\nhalf-writ\n{"id":1,"text":"a"}\n{"id":2,"text":"b"}'
  expect(parseLines(raw, 1).map(l => l.text)).toEqual(['b', 'c'])
})
