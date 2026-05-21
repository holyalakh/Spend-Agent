import type { ChatSession } from "../types";
import { formatTimestamp } from "../utils/parseArtifacts";

interface ChatHistorySidebarProps {
  sessions: ChatSession[];
  activeSessionId: string;
  onSelect: (id: string) => void;
  onNewChat: () => void;
}

export function ChatHistorySidebar({
  sessions,
  activeSessionId,
  onSelect,
  onNewChat,
}: ChatHistorySidebarProps) {
  const sorted = [...sessions].sort(
    (a, b) => b.timestamp.getTime() - a.timestamp.getTime(),
  );

  return (
    <aside className="flex w-[200px] shrink-0 flex-col border-r border-cursor-border bg-cursor-sidebar">
      <div className="border-b border-cursor-border px-2 py-2">
        <button
          type="button"
          onClick={onNewChat}
          className="flex w-full items-center gap-1.5 rounded px-2 py-1.5 text-[11px] text-cursor-subtle transition hover:bg-cursor-input/60 hover:text-cursor-text"
        >
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="h-3.5 w-3.5">
            <path d="M10.75 4.75a.75.75 0 00-1.5 0v4.5h-4.5a.75.75 0 000 1.5h4.5v4.5a.75.75 0 001.5 0v-4.5h4.5a.75.75 0 000-1.5h-4.5v-4.5z" />
          </svg>
          New chat
        </button>
      </div>

      <div className="px-3 py-2">
        <p className="text-[10px] font-medium uppercase tracking-wider text-cursor-subtle">
          Chat history
        </p>
      </div>

      <div className="flex-1 overflow-y-auto pb-2">
        {sorted.length === 0 && (
          <p className="px-3 text-[11px] text-cursor-subtle">No chats yet</p>
        )}

        <ul>
          {sorted.map((session) => {
            const isActive = session.id === activeSessionId;
            return (
              <li key={session.id}>
                <button
                  type="button"
                  onClick={() => onSelect(session.id)}
                  className={`mx-1 flex w-[calc(100%-8px)] flex-col rounded px-2 py-1.5 text-left transition ${
                    isActive
                      ? "bg-cursor-input text-cursor-text"
                      : "text-cursor-subtle hover:bg-cursor-input/40 hover:text-cursor-text"
                  }`}
                >
                  <span className="truncate text-[11px] leading-tight">{session.title}</span>
                  <span className="mt-0.5 text-[10px] text-cursor-subtle/80">
                    {formatTimestamp(session.timestamp)}
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      </div>
    </aside>
  );
}
