/**
 * Markdown renderer — beautiful syntax-highlighted code blocks.
 *
 * Uses react-markdown + react-syntax-highlighter with a custom
 * Synapse-inspired theme. JetBrains Mono for all code, copy buttons,
 * language labels, and styled prose elements.
 */

import { useState, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism'
import { Copy, Check } from 'lucide-react'

/* ---------- Custom Synapse code theme (based on oneDark) ---------- */

// Strip per-line gray backgrounds from oneDark tokens
const synapseTheme: Record<string, React.CSSProperties> = Object.fromEntries(
  Object.entries(oneDark).map(([key, value]) => {
    const style = { ...(value as React.CSSProperties) }
    // Remove background from all token/line styles — only keep pre background
    if (!key.startsWith('pre[') && !key.startsWith('code[')) {
      delete style.background
      delete style.backgroundColor
    }
    return [key, style]
  })
)

// Override container styles
Object.assign(synapseTheme, {
  'pre[class*="language-"]': {
    background: 'var(--ae-code-bg)',
    margin: 0,
    padding: '1.25rem',
    borderRadius: '0.75rem',
    border: '1px solid var(--ae-code-border)',
    fontFamily: '"JetBrains Mono", "Fira Code", ui-monospace, SFMono-Regular, Menlo, monospace',
    fontSize: '0.925rem',
    lineHeight: '1.65',
    overflow: 'auto',
  },
  'code[class*="language-"]': {
    fontFamily: '"JetBrains Mono", "Fira Code", ui-monospace, SFMono-Regular, Menlo, monospace',
    fontSize: '0.925rem',
    background: 'none',
  },
})

/* ---------- Copy button ---------- */

function CopyButton({ text }: { text: string }) {
  const { t } = useTranslation()
  const [copied, setCopied] = useState(false)

  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }, [text])

  return (
    <button
      onClick={handleCopy}
      className="p-1 rounded-md
        text-[var(--ae-code-muted)] hover:text-[var(--ae-code-text)] transition-colors duration-150
        opacity-0 group-hover:opacity-100"
      title={t('chat.copyCode')}
    >
      {copied ? (
        <Check className="w-3.5 h-3.5 text-emerald-400" />
      ) : (
        <Copy className="w-3.5 h-3.5" />
      )}
    </button>
  )
}

/* ---------- Markdown renderer ---------- */

interface MarkdownContentProps {
  content: string
}

export function MarkdownContent({ content }: MarkdownContentProps) {
  return (
    <ReactMarkdown
      className="markdown-body"
      remarkPlugins={[remarkGfm]}
      components={{
        // Code blocks + inline code
        code({ className, children, ...props }: any) {
          const match = /language-(\w+)/.exec(className || '')
          const codeStr = String(children).replace(/\n$/, '')
          const isBlock = match || codeStr.includes('\n')

          if (isBlock) {
            const lang = match?.[1] || 'text'
            return (
              <div className="relative group my-4 rounded-xl overflow-hidden
                border border-[var(--ae-code-border)] bg-[var(--ae-code-bg)]
                shadow-lg shadow-black/20">
                {/* Header bar with language + copy */}
                <div className="flex items-center justify-between px-4 py-1.5
                  bg-[var(--ae-code-header-bg)] border-b border-[var(--ae-code-border)]">
                  <span className="text-[11px] text-[var(--ae-code-muted)] font-mono uppercase tracking-wider select-none">
                    {lang}
                  </span>
                  <CopyButton text={codeStr} />
                </div>
                <SyntaxHighlighter
                  style={synapseTheme}
                  language={lang}
                  PreTag="div"
                  customStyle={{ margin: 0, borderRadius: 0, border: 'none' }}
                >
                  {codeStr}
                </SyntaxHighlighter>
              </div>
            )
          }

          return (
            <code
              className="px-1.5 py-0.5 rounded-md bg-[var(--ae-code-inline-bg)] border border-[var(--ae-code-border)]
                text-[var(--ae-code-inline-text)] font-mono text-[0.9em]"
              {...props}
            >
              {children}
            </code>
          )
        },

        // Make pre transparent (SyntaxHighlighter handles its own wrapper)
        pre({ children }: any) {
          return <>{children}</>
        },

        // Headings — gradient-colored for visual impact
        h1: ({ children }) => (
          <h1 className="text-xl font-bold mt-4 mb-2
            bg-gradient-to-r from-indigo-400 via-purple-400 to-pink-400
            bg-clip-text text-transparent">
            {children}
          </h1>
        ),
        h2: ({ children }) => (
          <h2 className="text-lg font-semibold mt-3 mb-2 pb-1
            text-indigo-300 border-b border-synapse/20">
            {children}
          </h2>
        ),
        h3: ({ children }) => (
          <h3 className="text-base font-semibold mt-2 mb-1 text-purple-300">
            {children}
          </h3>
        ),

        // Paragraphs
        p: ({ children }) => (
          <p className="mb-2 last:mb-0 leading-relaxed">{children}</p>
        ),

        // Lists — colored markers
        ul: ({ children }) => (
          <ul className="list-disc pl-5 mb-2 space-y-0.5 marker:text-purple-400">
            {children}
          </ul>
        ),
        ol: ({ children }) => (
          <ol className="list-decimal pl-5 mb-2 space-y-0.5 marker:text-indigo-400">
            {children}
          </ol>
        ),
        li: ({ children }) => (
          <li className="text-text-primary leading-relaxed">{children}</li>
        ),

        // Blockquotes — vivid accent border
        blockquote: ({ children }) => (
          <blockquote className="border-l-3 border-purple-500/60 pl-4 py-1 my-2
            text-text-secondary italic bg-purple-500/5 rounded-r-lg">
            {children}
          </blockquote>
        ),

        // Links
        a: ({ href, children }) => (
          <a
            href={href}
            target="_blank"
            rel="noopener noreferrer"
            className="text-synapse hover:text-pulse underline underline-offset-2
              decoration-synapse/30 hover:decoration-pulse/50 transition-colors"
          >
            {children}
          </a>
        ),

        // Tables — synapse-accented header
        table: ({ children }) => (
          <div className="overflow-x-auto my-3 rounded-lg border border-synapse/20
            shadow-lg shadow-synapse/5">
            <table className="min-w-full border-collapse">{children}</table>
          </div>
        ),
        thead: ({ children }) => (
          <thead className="bg-gradient-to-r from-synapse/10 to-pulse/10">{children}</thead>
        ),
        th: ({ children }) => (
          <th className="px-3 py-2 text-left text-xs font-semibold text-indigo-300
            border-b border-synapse/20">
            {children}
          </th>
        ),
        td: ({ children }) => (
          <td className="px-3 py-2 text-sm border-b border-slate-mid/15">{children}</td>
        ),

        // Horizontal rule
        hr: () => (
          <hr className="my-4 border-0 h-px bg-gradient-to-r from-transparent via-synapse/20 to-transparent" />
        ),

        // Strong — highlighted with subtle glow color
        strong: ({ children }) => (
          <strong className="font-semibold text-indigo-200">{children}</strong>
        ),
        // Em — soft purple tint
        em: ({ children }) => (
          <em className="italic text-purple-300/80">{children}</em>
        ),
      }}
    >
      {content}
    </ReactMarkdown>
  )
}
