import ReactMarkdown from 'react-markdown'

import { safeUrl } from '@/lib/format'

/** Untrusted Markdown (model output): react-markdown never renders raw HTML, links must be
 * http(s), and `[n]` becomes a link to source card `#<idPrefix>-n` when `n` is a known source. */
export function Markdown({ text, known, idPrefix = 'src' }: { text: string; known: Set<number>; idPrefix?: string }) {
  const withCites = text.replace(/\[(\d{1,2})\](?!\()/g, (m, n) => (known.has(Number(n)) ? `[\\[${n}\\]](#${idPrefix}-${n})` : m))
  return (
    <div className="prose-news">
      <ReactMarkdown
        skipHtml
        components={{
          a: ({ href, children }) => {
            if (href?.startsWith(`#${idPrefix}-`))
              return (
                <a
                  href={href}
                  className="mx-0.5 rounded-md bg-primary/12 px-1.5 py-0.5 text-xs font-semibold text-primary-ink no-underline hover:bg-primary/20"
                  aria-label={`Source ${href.slice(idPrefix.length + 2)}`}
                >
                  {children}
                </a>
              )
            const url = safeUrl(href)
            return url ? (
              <a href={url} target="_blank" rel="noopener noreferrer nofollow">
                {children}
              </a>
            ) : (
              <span>{children}</span>
            )
          },
          img: () => null,
        }}
      >
        {withCites}
      </ReactMarkdown>
    </div>
  )
}
