import { KeyboardEvent, useRef } from "react";

interface ChatInputProps {
  onSend: (message: string) => void;
  onUploadClick: () => void;
  disabled?: boolean;
  uploadDisabled?: boolean;
}

export function ChatInput({ onSend, onUploadClick, disabled, uploadDisabled }: ChatInputProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleSend = () => {
    const value = textareaRef.current?.value ?? "";
    if (!value.trim() || disabled) return;
    onSend(value);
    if (textareaRef.current) {
      textareaRef.current.value = "";
      textareaRef.current.style.height = "auto";
    }
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      handleSend();
    }
  };

  const handleInput = () => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  };

  return (
    <div className="shrink-0 border-t border-cursor-border bg-cursor-input px-4 py-3">
      <div className="flex w-full items-end gap-2">
        <button
          type="button"
          onClick={onUploadClick}
          disabled={uploadDisabled}
          className="mb-2 shrink-0 rounded p-1.5 text-cursor-subtle transition hover:text-cursor-text disabled:opacity-40"
          aria-label="Upload CSV"
          title="Upload CSV"
        >
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="h-5 w-5">
            <path
              fillRule="evenodd"
              d="M15.621 4.379a3 3 0 00-4.242 0l-7 7a3 3 0 004.241 4.243h.001l.497-.5a.75.75 0 011.064 1.057l-.498.501-.002.002a4.5 4.5 0 01-6.364-6.364l7-7a4.5 4.5 0 016.368 6.36l-3.455 3.553A2.625 2.625 0 119.52 9.52l3.45-3.451a.75.75 0 111.06 1.06l-3.45 3.451a1.125 1.125 0 001.587 1.595l3.454-3.553a3 3 0 000-4.242z"
              clipRule="evenodd"
            />
          </svg>
        </button>

        <textarea
          ref={textareaRef}
          rows={1}
          placeholder="Ask about your spend data…"
          disabled={disabled}
          onKeyDown={handleKeyDown}
          onInput={handleInput}
          className="max-h-40 min-h-[40px] flex-1 resize-none rounded-md border border-cursor-border bg-cursor-bg px-4 py-3 text-sm text-cursor-text outline-none placeholder:text-cursor-subtle focus:border-cursor-accent/50 disabled:opacity-50"
        />

        <button
          type="button"
          onClick={handleSend}
          disabled={disabled}
          className="mb-1 shrink-0 rounded-md bg-cursor-accent p-2 text-white transition hover:bg-cursor-accent-hover disabled:opacity-40"
          aria-label="Send message"
        >
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="h-4 w-4">
            <path d="M3.105 2.288a.75.75 0 00-.826.95l1.414 4.926A1.5 1.5 0 005.135 9.25h6.115a.75.75 0 010 1.5H5.135a1.5 1.5 0 00-1.442 1.086l-1.414 4.926a.75.75 0 00.826.95 28.897 28.897 0 0015.293-7.155.75.75 0 000-1.114A28.897 28.897 0 003.105 2.288z" />
          </svg>
        </button>
      </div>
    </div>
  );
}
