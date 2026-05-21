import type { ChartArtifact, ChartType } from "../types";

const CHART_TYPES = new Set<ChartType>(["bar", "line", "pie"]);

function isChartArtifact(value: unknown): value is ChartArtifact {
  if (!value || typeof value !== "object") return false;
  const obj = value as Record<string, unknown>;
  return (
    obj.type === "chart" &&
    typeof obj.chart_type === "string" &&
    CHART_TYPES.has(obj.chart_type as ChartType) &&
    Array.isArray(obj.data)
  );
}

function tryParseJson(text: string): unknown | null {
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

function extractFromCodeBlocks(text: string): ChartArtifact[] {
  const artifacts: ChartArtifact[] = [];
  const regex = /```(?:json)?\s*([\s\S]*?)```/gi;
  let match: RegExpExecArray | null;

  while ((match = regex.exec(text)) !== null) {
    const parsed = tryParseJson(match[1].trim());
    if (isChartArtifact(parsed)) {
      artifacts.push(parsed);
    }
  }

  return artifacts;
}

function extractInlineJson(text: string): ChartArtifact[] {
  const artifacts: ChartArtifact[] = [];
  const regex = /\{[\s\S]*?"type"\s*:\s*"chart"[\s\S]*?\}/g;
  let match: RegExpExecArray | null;

  while ((match = regex.exec(text)) !== null) {
    const parsed = tryParseJson(match[0]);
    if (isChartArtifact(parsed)) {
      artifacts.push(parsed);
    }
  }

  return artifacts;
}

function dedupeArtifacts(artifacts: ChartArtifact[]): ChartArtifact[] {
  const seen = new Set<string>();
  return artifacts.filter((artifact) => {
    const key = JSON.stringify(artifact);
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

export function parseChartArtifacts(text: string): ChartArtifact[] {
  const fromBlocks = extractFromCodeBlocks(text);
  const fromInline = extractInlineJson(text);
  return dedupeArtifacts([...fromBlocks, ...fromInline]);
}

export function stripThinkingTags(text: string): string {
  return text.replace(/<thinking>[\s\S]*?<\/thinking>/gi, "").trim();
}

export function stripChartJsonFromReply(text: string): string {
  let cleaned = text.replace(/```(?:json)?\s*\{[\s\S]*?"type"\s*:\s*"chart"[\s\S]*?\}\s*```/gi, "").trim();
  cleaned = cleaned.replace(/\{[\s\S]*?"type"\s*:\s*"chart"[\s\S]*?\}/g, "").trim();
  return cleaned;
}

export function cleanAgentReply(text: string): string {
  return stripChartJsonFromReply(stripThinkingTags(text)).trim();
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function formatTimestamp(date: Date): string {
  return date.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}
