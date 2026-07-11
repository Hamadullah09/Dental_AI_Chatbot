"use client";

import ReactMarkdown from "react-markdown";
import rehypeSanitize from "rehype-sanitize";
import remarkGfm from "remark-gfm";

export function SafeMarkdown({ content }: { content: string }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      rehypePlugins={[rehypeSanitize]}
      components={{
        p: ({ children }) => (
          <p className="mb-3 text-[15px] leading-7 text-dental-textPrimary last:mb-0">{children}</p>
        ),
        strong: ({ children }) => (
          <strong className="font-semibold text-dental-textPrimary">{children}</strong>
        ),
        ul: ({ children }) => (
          <ul className="mb-3 ml-5 list-disc space-y-1.5 text-[15px] leading-7 text-dental-textPrimary">{children}</ul>
        ),
        ol: ({ children }) => (
          <ol className="mb-3 ml-5 list-decimal space-y-1.5 text-[15px] leading-7 text-dental-textPrimary">{children}</ol>
        ),
        li: ({ children }) => <li className="pl-1">{children}</li>,
        h1: ({ children }) => <h1 className="mb-3 text-xl font-semibold text-dental-textPrimary">{children}</h1>,
        h2: ({ children }) => <h2 className="mb-3 text-lg font-semibold text-dental-textPrimary">{children}</h2>,
        h3: ({ children }) => <h3 className="mb-2 text-base font-semibold text-dental-textPrimary">{children}</h3>,
        a: ({ children, href }) => (
          <a
            href={href}
            target="_blank"
            rel="noreferrer"
            className="font-medium text-dental-accent underline underline-offset-2 hover:text-dental-accentHover"
          >
            {children}
          </a>
        ),
        code: ({ children }) => (
          <code className="rounded-md bg-dental-muted px-1.5 py-0.5 text-[13px] text-dental-textPrimary">{children}</code>
        ),
      }}
    >
      {content}
    </ReactMarkdown>
  );
}
