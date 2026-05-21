import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { startChat, waitForChatJob } from "../api/client";
import type { ChartArtifact, ChatMessage, ChatSession } from "../types";
import { parseChartArtifacts, cleanAgentReply } from "../utils/parseArtifacts";

function createId(): string {
  return crypto.randomUUID();
}

function createSession(): ChatSession {
  return {
    id: createId(),
    title: "New chat",
    timestamp: new Date(),
    messages: [],
    artifacts: [],
  };
}

function titleFromFirstMessage(text: string): string {
  const trimmed = text.trim();
  if (trimmed.length <= 40) return trimmed;
  return `${trimmed.slice(0, 40)}…`;
}

interface ChatContextValue {
  sessions: ChatSession[];
  activeSessionId: string;
  messages: ChatMessage[];
  isPolling: boolean;
  pollStatus: string | null;
  artifacts: ChartArtifact[];
  error: string | null;
  sendMessage: (text: string) => Promise<void>;
  newChat: () => void;
  selectSession: (id: string) => void;
}

const ChatContext = createContext<ChatContextValue | null>(null);

export function ChatProvider({ children }: { children: ReactNode }) {
  const initialSession = createSession();
  const [sessions, setSessions] = useState<ChatSession[]>([initialSession]);
  const [activeSessionId, setActiveSessionId] = useState(initialSession.id);
  const [isPolling, setIsPolling] = useState(false);
  const [pollStatus, setPollStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const activeSession = useMemo(
    () => sessions.find((s) => s.id === activeSessionId) ?? sessions[0],
    [sessions, activeSessionId],
  );

  const messages = activeSession?.messages ?? [];
  const artifacts = activeSession?.artifacts ?? [];

  const updateActiveSession = useCallback(
    (updater: (session: ChatSession) => ChatSession) => {
      setSessions((prev) =>
        prev.map((session) => (session.id === activeSessionId ? updater(session) : session)),
      );
    },
    [activeSessionId],
  );

  const newChat = useCallback(() => {
    const session = createSession();
    setSessions((prev) => [session, ...prev]);
    setActiveSessionId(session.id);
    setError(null);
  }, []);

  const selectSession = useCallback((id: string) => {
    setActiveSessionId(id);
    setError(null);
  }, []);

  const sendMessage = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (!trimmed || isPolling) return;

      const userMessage: ChatMessage = {
        id: createId(),
        role: "user",
        content: trimmed,
        timestamp: new Date(),
      };

      updateActiveSession((session) => ({
        ...session,
        title: session.messages.length === 0 ? titleFromFirstMessage(trimmed) : session.title,
        timestamp: new Date(),
        messages: [...session.messages, userMessage],
      }));

      setIsPolling(true);
      setPollStatus("pending");
      setError(null);

      try {
        const { job_id } = await startChat(trimmed);
        const result = await waitForChatJob(job_id, setPollStatus);

        if (result.status === "failed") {
          throw new Error(result.error ?? "Chat job failed");
        }

        const reply = result.result?.reply ?? "No response received.";
        const parsedArtifacts = parseChartArtifacts(reply);
        const displayReply = cleanAgentReply(reply) || "No response received.";

        const agentMessage: ChatMessage = {
          id: createId(),
          role: "agent",
          content: displayReply,
          timestamp: new Date(),
          artifacts: parsedArtifacts,
        };

        updateActiveSession((session) => ({
          ...session,
          timestamp: new Date(),
          messages: [...session.messages, agentMessage],
          artifacts:
            parsedArtifacts.length > 0
              ? [...session.artifacts, ...parsedArtifacts]
              : session.artifacts,
        }));
      } catch (err) {
        const message = err instanceof Error ? err.message : "Failed to send message";
        setError(message);
        updateActiveSession((session) => ({
          ...session,
          timestamp: new Date(),
          messages: [
            ...session.messages,
            {
              id: createId(),
              role: "agent",
              content: `**Error:** ${message}`,
              timestamp: new Date(),
            },
          ],
        }));
      } finally {
        setIsPolling(false);
        setPollStatus(null);
      }
    },
    [isPolling, updateActiveSession],
  );

  const value = useMemo<ChatContextValue>(
    () => ({
      sessions,
      activeSessionId,
      messages,
      isPolling,
      pollStatus,
      artifacts,
      error,
      sendMessage,
      newChat,
      selectSession,
    }),
    [
      sessions,
      activeSessionId,
      messages,
      isPolling,
      pollStatus,
      artifacts,
      error,
      sendMessage,
      newChat,
      selectSession,
    ],
  );

  return <ChatContext.Provider value={value}>{children}</ChatContext.Provider>;
}

export function useChat() {
  const context = useContext(ChatContext);
  if (!context) {
    throw new Error("useChat must be used within ChatProvider");
  }
  return context;
}
