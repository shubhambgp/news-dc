import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { Markdown } from './Markdown'

const html = (text: string) => renderToStaticMarkup(<Markdown text={text} known={new Set([1])} />)

describe('Markdown (model output)', () => {
  it('links known citations to their source card', () => {
    expect(html('Cooling grew [1].')).toContain('href="#src-1"')
  })

  it('renders model-written links, unknown citations and raw HTML as text', () => {
    const out = html('See [this](https://evil.example) and [2]. <a href="https://x">x</a>')
    expect(out).not.toContain('evil.example')
    expect(out).not.toContain('href="https://x"')
    expect(out.match(/<a /g)).toBeNull()
    expect(out).toContain('[2]')
  })
})
