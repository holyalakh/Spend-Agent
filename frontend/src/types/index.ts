export type ChartType = "bar" | "line" | "pie";

export interface ChartArtifact {
  type: "chart";
  chart_type: ChartType;
  title?: string;
  data: Record<string, unknown>[];
  x_key?: string;
  y_key?: string;
  name_key?: string;
  value_key?: string;
}

export interface ChatMessage {
  id: string;
  role: "user" | "agent";
  content: string;
  timestamp: Date;
  artifacts?: ChartArtifact[];
}

export interface UploadedFile {
  filename: string;
  s3_key: string;
  size: number;
  last_modified: string;
}

export interface PendingUpload {
  filename: string;
  s3_key: string;
  progress: number;
}

export type AuthChallenge = "FORCE_CHANGE_PASSWORD" | null;

export interface AuthUser {
  email: string;
}

export interface ChatJobResult {
  session_id?: string;
  reply?: string;
  guardrail_blocked?: boolean;
}

export interface ChatPollResponse {
  job_id: string;
  status: "pending" | "processing" | "completed" | "failed";
  result?: ChatJobResult;
  error?: string;
}

export interface ChatSession {
  id: string;
  title: string;
  timestamp: Date;
  messages: ChatMessage[];
  artifacts: ChartArtifact[];
}
