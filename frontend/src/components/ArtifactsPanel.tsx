import type { ChartArtifact } from "../types";
import { ChartArtifactView } from "./ChartArtifact";

interface ArtifactsPanelProps {
  artifacts: ChartArtifact[];
  isOpen: boolean;
  onToggle: () => void;
}

export function ArtifactsPanel({ artifacts, isOpen, onToggle }: ArtifactsPanelProps) {
  return (
    <>
      <button
        type="button"
        onClick={onToggle}
        className={`absolute right-0 top-1/2 z-30 flex -translate-y-1/2 flex-col items-center gap-1 rounded-l-md border border-r-0 border-cursor-border bg-cursor-sidebar px-1.5 py-3 text-[10px] text-cursor-subtle transition hover:bg-cursor-input hover:text-cursor-text ${
          isOpen ? "translate-x-[-400px]" : "translate-x-0"
        }`}
        aria-label={isOpen ? "Close artifacts panel" : "Open artifacts panel"}
        title="Artifacts"
      >
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="h-4 w-4">
          <path d="M2 4.5A2.5 2.5 0 014.5 2h11A2.5 2.5 0 0118 4.5v11a2.5 2.5 0 01-2.5 2.5h-11A2.5 2.5 0 012 15.5v-11zM4.5 4a.5.5 0 00-.5.5v11a.5.5 0 00.5.5h11a.5.5 0 00.5-.5v-11a.5.5 0 00-.5-.5h-11z" />
          <path d="M10 6a1 1 0 011 1v6a1 1 0 11-2 0V7a1 1 0 011-1zM6 8a1 1 0 011 1v2a1 1 0 11-2 0V9a1 1 0 011-1zm8 0a1 1 0 011 1v2a1 1 0 11-2 0V9a1 1 0 011-1z" />
        </svg>
        {artifacts.length > 0 && (
          <span className="font-medium text-cursor-accent">{artifacts.length}</span>
        )}
      </button>

      <aside
        className={`absolute right-0 top-0 z-20 flex h-full w-[400px] flex-col border-l border-cursor-border bg-cursor-sidebar shadow-2xl transition-transform duration-300 ease-in-out ${
          isOpen ? "translate-x-0" : "translate-x-full"
        }`}
      >
        <div className="flex items-center justify-between border-b border-cursor-border px-4 py-3">
          <h2 className="text-xs font-medium uppercase tracking-wider text-cursor-subtle">Artifacts</h2>
          <button
            type="button"
            onClick={onToggle}
            className="rounded p-1 text-cursor-subtle transition hover:bg-cursor-input hover:text-cursor-text"
            aria-label="Close panel"
          >
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="h-4 w-4">
              <path d="M6.28 5.22a.75.75 0 00-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 101.06 1.06L10 11.06l3.72 3.72a.75.75 0 101.06-1.06L11.06 10l3.72-3.72a.75.75 0 00-1.06-1.06L10 8.94 6.28 5.22z" />
            </svg>
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-4">
          {artifacts.length === 0 ? (
            <p className="text-xs text-cursor-subtle">Charts from agent responses will appear here.</p>
          ) : (
            <div className="space-y-4">
              {artifacts.map((artifact, index) => (
                <ChartArtifactView key={`${artifact.title ?? "chart"}-${index}`} artifact={artifact} />
              ))}
            </div>
          )}
        </div>
      </aside>
    </>
  );
}
