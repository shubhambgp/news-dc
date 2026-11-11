import ReactMarkdown from 'react-markdown'

/** Untrusted Markdown (model output): react-markdown never renders raw HTML, and `[n]` becomes a
 * link to source card `#<idPrefix>-n` when `n` is a known source. Any other link is shown as
 * plain text: sources already have cards, and a link the model wrote may be injected phishing. */
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
                  className="mx-0.5 rounded bg-primary/10 px-1 text-xs font-medium text-primary no-underline hover:bg-primary/20"
                  aria-label={`Source ${href.slice(idPrefix.length + 2)}`}
                >
                  {children}
                </a>
              )
            return <span>{children}</span>
          },
          img: () => null,
        }}
      >
        {withCites}
      </ReactMarkdown>
    </div>
  )
}
