import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

export function MarkdownRenderer({ content }: { content: string }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        p({ children }) {
          return <p className="[&:not(:first-child)]:mt-2">{children}</p>;
        },
        ul({ children }) {
          return <ul className="ml-4 mt-2 list-disc space-y-1">{children}</ul>;
        },
        ol({ children }) {
          return <ol className="ml-4 mt-2 list-decimal space-y-1">{children}</ol>;
        },
        strong({ children }) {
          return <strong className="font-semibold">{children}</strong>;
        },
        a({ href, children }) {
          return (
            <a
              href={href}
              target="_blank"
              rel="noopener noreferrer"
              className="text-primary underline"
            >
              {children}
            </a>
          );
        },
      }}
    >
      {content}
    </ReactMarkdown>
  );
}
