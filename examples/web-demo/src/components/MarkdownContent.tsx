/**
 * Markdown renderer — beautiful syntax-highlighted code blocks.
 *
 * Uses react-markdown + react-syntax-highlighter with a custom
 * Synapse-inspired theme. JetBrains Mono for all code, copy buttons,
 * language labels, and styled prose elements.
 */

import { useState, useCallback } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism'
import { Copy, Check } from 'lucide-react'

/* ---------- Custom Synapse code theme (based on oneDark) ---------- */

const synapseTheme: Record<string, React.CSSProperties> = {
  ...oneDark,
  'pre[class*="language-"]': {
    ...(oneDark['pre[class*="language-"]'] as React.CSSProperties),
    background: '#0f0f17',
    margin: 0,
    borderRadius: '0.75rem',
    border: '1px solid rgba(26, 26, 46, 0.5)',
    fontFamily: '"JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, monospace',
    fontSize: '0.85em',
    lineHeight: '1.7',
  },
  'code[class*="language-"]': {
    ...(oneDark['code[class*="language-"]'] as React.CSSProperties),
    fontFamily: '"JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, monospace',
    fontSize: '0.85em',
  },
}

/* ---------- Copy button ---------- */

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false)

  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }, [text])

  return (
    <button
      onClick={handleCopy}
      className="absolute top-2 right-2 p-1.5 rounded-lg z-10
        bg-slate-dark/80 hover:bg-slate-mid/80 border border-slate-mid/30
        text-text-muted hover:text-text-secondary transition-all duration-200
        opacity-0 group-hover:opacity-100"
      title="Copy code"
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
            return (
              <div className="relative group my-3">
                {match && (
                  <span className="absolute top-2 left-3 text-[10px] text-text-muted/50
                    font-mono uppercase tracking-wider select-none z-10">
                    {match[1]}
                  </span>
                )}
                <CopyButton text={codeStr} />
                <SyntaxHighlighter
                  style={synapseTheme}
                  language={match?.[1] || 'text'}
                  PreTag="div"
                  customStyle={{ paddingTop: match ? '2rem' : '1rem', margin: 0 }}
                >
                  {codeStr}
                </SyntaxHighlighter>
              </div>
            )
          }

          return (
            <code
              className="px-1.5 py-0.5 rounded-md bg-synapse/10 border border-synapse/15
                text-purple-300 font-mono text-[0.85em]"
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
