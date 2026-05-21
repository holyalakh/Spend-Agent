import { useCallback, useEffect, useRef, useState } from "react";
import { uploadCsv } from "../api/client";
import { useAuth } from "../hooks/useAuth";
import { useChat } from "../hooks/useChat";
import type { PendingUpload } from "../types";
import { ArtifactsPanel } from "./ArtifactsPanel";
import { ChatHistorySidebar } from "./ChatHistorySidebar";
import { ChatInput } from "./ChatInput";
import { ChatMessages } from "./ChatMessages";

export function ChatLayout() {
  const { email, logout } = useAuth();
  const {
    sessions,
    activeSessionId,
    messages,
    isPolling,
    pollStatus,
    artifacts,
    sendMessage,
    newChat,
    selectSession,
  } = useChat();
  const bottomRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [artifactsOpen, setArtifactsOpen] = useState(false);
  const [pendingUpload, setPendingUpload] = useState<PendingUpload | null>(null);
  const [uploadChip, setUploadChip] = useState<{ filename: string; s3_key: string } | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [isUploading, setIsUploading] = useState(false);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isPolling, activeSessionId]);

  useEffect(() => {
    if (artifacts.length > 0) {
      setArtifactsOpen(true);
    }
  }, [artifacts.length, activeSessionId]);

  const handleFileSelect = useCallback(async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;

    if (!file.name.toLowerCase().endsWith(".csv")) {
      setUploadError("Only CSV files are supported");
      return;
    }

    setUploadError(null);
    setIsUploading(true);
    setPendingUpload({ filename: file.name, s3_key: "", progress: 0 });

    try {
      const result = await uploadCsv(file, (progress) => {
        setPendingUpload({ filename: file.name, s3_key: "", progress });
      });
      setUploadChip(result);
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setPendingUpload(null);
      setIsUploading(false);
    }
  }, []);

  return (
    <div className="flex h-full flex-col bg-cursor-bg">
      <header className="flex shrink-0 items-center justify-between border-b border-cursor-border px-4 py-2">
        <span className="truncate text-xs text-cursor-text">{email ?? "Spend Analytics"}</span>
        <button
          type="button"
          onClick={() => logout()}
          className="shrink-0 rounded px-2 py-1 text-xs text-cursor-subtle transition hover:text-cursor-text"
        >
          Sign out
        </button>
      </header>

      <div className="flex min-h-0 flex-1">
        <ChatHistorySidebar
          sessions={sessions}
          activeSessionId={activeSessionId}
          onSelect={selectSession}
          onNewChat={newChat}
        />

        <div className="relative flex min-w-0 flex-1 flex-col">
          <ChatMessages
            messages={messages}
            isPolling={isPolling}
            pollStatus={pollStatus}
            bottomRef={bottomRef}
          />

          {(uploadChip || uploadError || pendingUpload) && (
            <div className="shrink-0 px-4 pb-2">
              {pendingUpload && (
                <p className="text-xs text-cursor-subtle">
                  Uploading {pendingUpload.filename}… {pendingUpload.progress}%
                </p>
              )}
              {uploadChip && (
                <div className="inline-flex items-center gap-2 rounded-full border border-cursor-border bg-cursor-input px-3 py-1 text-xs">
                  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="h-3 w-3 text-green-500">
                    <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.857-9.809a.75.75 0 00-1.214-.882l-3.483 4.79-1.88-1.88a.75.75 0 10-1.06 1.061l2.5 2.5a.75.75 0 001.137-.089l4-5.5z" clipRule="evenodd" />
                  </svg>
                  <span className="text-cursor-text">{uploadChip.filename}</span>
                  <button
                    type="button"
                    onClick={() => setUploadChip(null)}
                    className="text-cursor-subtle hover:text-cursor-text"
                    aria-label="Dismiss"
                  >
                    ×
                  </button>
                </div>
              )}
              {uploadError && <p className="mt-1 text-xs text-red-400">{uploadError}</p>}
            </div>
          )}

          <ChatInput
            onSend={sendMessage}
            onUploadClick={() => fileInputRef.current?.click()}
            disabled={isPolling}
            uploadDisabled={isUploading}
          />

          <ArtifactsPanel
            artifacts={artifacts}
            isOpen={artifactsOpen}
            onToggle={() => setArtifactsOpen((open) => !open)}
          />
        </div>
      </div>

      <input
        ref={fileInputRef}
        type="file"
        accept=".csv,text/csv"
        className="hidden"
        onChange={handleFileSelect}
      />
    </div>
  );
}
