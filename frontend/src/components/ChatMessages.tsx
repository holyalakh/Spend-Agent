import ReactMarkdown from "react-markdown";
import type { ChatMessage } from "../types";
import { formatTimestamp } from "../utils/parseArtifacts";

interface ChatMessagesProps {
  messages: ChatMessage[];
  isPolling: boolean;
  pollStatus: string | null;
  bottomRef: React.RefObject<HTMLDivElement>;
}

function TypingIndicator({ status }: { status: string | null }) {
  return (
    <div className="border-b border-cursor-border/50 px-6 py-4">
      <p className="mb-2 text-[10px] font-medium uppercase tracking-widest text-cursor-subtle">
        Spend Agent
      </p>
      <div className="flex items-center gap-2 border-l-2 border-cursor-accent pl-4">
        <div className="flex gap-1">
          <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-cursor-subtle [animation-delay:-0.3s]" />
          <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-cursor-subtle [animation-delay:-0.15s]" />
          <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-cursor-subtle" />
        </div>
        <span className="text-xs text-cursor-subtle">
          {status === "processing" ? "Analyzing…" : "Thinking…"}
        </span>
      </div>
    </div>
  );
}

function MessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";

  return (
    <div
      className={`group border-b border-cursor-border/50 px-6 py-4 ${
        isUser ? "flex justify-end" : ""
      }`}
    >
      {isUser ? (
        <div className="relative max-w-[75%]">
          <div className="rounded-lg border border-cursor-border bg-cursor-user px-4 py-2.5">
            <p className="whitespace-pre-wrap text-sm text-cursor-text">{message.content}</p>
          </div>
          <span className="pointer-events-none absolute -bottom-4 right-0 whitespace-nowrap text-[10px] text-cursor-subtle opacity-0 transition-opacity group-hover:opacity-100">
            {formatTimestamp(message.timestamp)}
          </span>
        </div>
      ) : (
        <div className="relative max-w-full">
          <p className="mb-2 text-[10px] font-medium uppercase tracking-widest text-cursor-subtle">
            Spend Agent
          </p>
          <div className="border-l-2 border-cursor-accent pl-4">
            <div className="prose-agent">
              <ReactMarkdown>{message.content}</ReactMarkdown>
            </div>
          </div>
          <span className="pointer-events-none absolute -bottom-1 left-0 whitespace-nowrap text-[10px] text-cursor-subtle opacity-0 transition-opacity group-hover:opacity-100">
            {formatTimestamp(message.timestamp)}
          </span>
        </div>
      )}
    </div>
  );
}

export function ChatMessages({ messages, isPolling, pollStatus, bottomRef }: ChatMessagesProps) {
  return (
    <div className="flex-1 overflow-y-auto bg-cursor-bg">
      {messages.length === 0 && !isPolling && (
        <div className="flex h-full flex-col items-center justify-center px-6 text-center">
          <svg
            xmlns="http://www.w3.org/2000/svg"
            viewBox="0 0 24 24"
            fill="currentColor"
            className="mb-3 h-8 w-8 text-cursor-subtle/60"
          >
            <path
              fillRule="evenodd"
              d="M4.848 2.771A49.144 49.144 0 0112 2.25c2.43 0 4.817.178 7.152.52 1.978.292 3.348 2.023 3.348 3.997v6.139c0 1.972-1.367 3.703-3.348 3.997a48.901 48.901 0 01-3.476.383.39.39 0 00-.297.17l-2.755 4.133a.75.75 0 01-1.14.037 12.04 12.04 0 01-3.128-3.467 48.896 48.896 0 01-6.102-5.1A77.839 77.839 0 012.25 12c0-5.385 2.374-10.335 6.162-13.72a.75.75 0 01.436-.509z"
              clipRule="evenodd"
            />
          </svg>
          <h2 className="text-sm font-medium text-cursor-text">Spend Analytics Agent</h2>
          <p className="mt-1.5 max-w-sm text-xs text-cursor-subtle">
            Ask questions about your spend data. Upload a CSV to get started.
          </p>
        </div>
      )}

      {messages.map((message) => (
        <MessageBubble key={message.id} message={message} />
      ))}

      {isPolling && <TypingIndicator status={pollStatus} />}
      <div ref={bottomRef} />
    </div>
  );
}
