import { getIdToken } from "../auth/cognitoAuth";
import type { ChatPollResponse, UploadedFile } from "../types";

const API_BASE = import.meta.env.VITE_API_BASE_URL.replace(/\/$/, "");

export class ApiError extends Error {
  status: number;
  responseBody: string;

  constructor(message: string, status: number, responseBody = "") {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.responseBody = responseBody;
  }
}

function logApiFailure(context: string, details: Record<string, unknown>) {
  console.error(`[API] ${context}`, details);
}

async function authHeaders(): Promise<HeadersInit> {
  const token = await getIdToken();
  if (!token) {
    throw new ApiError("Not authenticated — sign in again", 401);
  }
  return {
    Authorization: `Bearer ${token}`,
    "Content-Type": "application/json",
  };
}

async function handleResponse<T>(response: Response, context: string): Promise<T> {
  const text = await response.text();
  let parsed: Record<string, unknown> = {};

  if (text) {
    try {
      parsed = JSON.parse(text) as Record<string, unknown>;
    } catch {
      parsed = { raw: text };
    }
  }

  if (!response.ok) {
    const apiMessage = typeof parsed.error === "string" ? parsed.error : null;
    const detail = apiMessage ?? text ?? response.statusText;
    const message = `${context} failed — HTTP ${response.status}: ${detail}`;

    logApiFailure(context, {
      status: response.status,
      statusText: response.statusText,
      url: response.url,
      body: text || "(empty)",
    });

    throw new ApiError(message, response.status, text);
  }

  return (text ? parsed : {}) as T;
}

async function apiFetch(url: string, init: RequestInit, context: string): Promise<Response> {
  try {
    return await fetch(url, init);
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    logApiFailure(context, { error: message, url, type: "network" });
    throw new ApiError(
      `${context} failed — network error (possible CORS): ${message}`,
      0,
    );
  }
}

export async function startChat(message: string, s3FileKey?: string): Promise<{ job_id: string }> {
  const headers = await authHeaders();
  const payload: { message: string; s3_file_key?: string } = { message };
  if (s3FileKey) {
    payload.s3_file_key = s3FileKey;
  }

  const response = await apiFetch(
    `${API_BASE}/chat`,
    { method: "POST", headers, body: JSON.stringify(payload) },
    "POST /chat",
  );

  return handleResponse(response, "POST /chat");
}

export async function pollChatJob(jobId: string): Promise<ChatPollResponse> {
  const headers = await authHeaders();
  const response = await apiFetch(
    `${API_BASE}/chat/${jobId}`,
    { method: "GET", headers },
    `GET /chat/${jobId}`,
  );

  return handleResponse(response, `GET /chat/${jobId}`);
}

export async function waitForChatJob(
  jobId: string,
  onStatus?: (status: string) => void,
  intervalMs = 2000,
): Promise<ChatPollResponse> {
  while (true) {
    const result = await pollChatJob(jobId);
    onStatus?.(result.status);

    if (result.status === "completed" || result.status === "failed") {
      return result;
    }

    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }
}

export async function listFiles(): Promise<UploadedFile[]> {
  const headers = await authHeaders();
  const response = await apiFetch(
    `${API_BASE}/files`,
    { method: "GET", headers },
    "GET /files",
  );

  const body = await handleResponse<{ files: UploadedFile[] }>(response, "GET /files");
  return body.files ?? [];
}

export async function requestUploadUrl(filename: string): Promise<{
  upload_url: string;
  s3_key: string;
  expires_in: number;
}> {
  const headers = await authHeaders();
  const response = await apiFetch(
    `${API_BASE}/upload-url`,
    {
      method: "POST",
      headers,
      body: JSON.stringify({ filename }),
    },
    "POST /upload-url",
  );

  return handleResponse(response, "POST /upload-url");
}

export function uploadFileToS3(
  uploadUrl: string,
  file: File,
  onProgress?: (percent: number) => void,
): Promise<void> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("PUT", uploadUrl);
    xhr.setRequestHeader("Content-Type", "text/csv");

    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable && onProgress) {
        onProgress(Math.round((event.loaded / event.total) * 100));
      }
    };

    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve();
        return;
      }

      const detail = xhr.responseText || xhr.statusText || "(empty)";
      logApiFailure("PUT S3 presigned URL", {
        status: xhr.status,
        statusText: xhr.statusText,
        body: detail,
        url: uploadUrl.split("?")[0],
      });
      reject(
        new ApiError(
          `S3 upload failed — HTTP ${xhr.status}: ${detail}`,
          xhr.status,
          xhr.responseText,
        ),
      );
    };

    xhr.onerror = () => {
      logApiFailure("PUT S3 presigned URL", {
        status: 0,
        error: "XHR onerror — likely CORS on S3 bucket",
        url: uploadUrl.split("?")[0],
      });
      reject(
        new ApiError(
          "S3 upload failed — HTTP 0: network or CORS error on pre-signed URL",
          0,
        ),
      );
    };

    xhr.send(file);
  });
}

export async function uploadCsv(
  file: File,
  onProgress?: (percent: number) => void,
): Promise<{ s3_key: string; filename: string }> {
  const { upload_url, s3_key } = await requestUploadUrl(file.name);
  await uploadFileToS3(upload_url, file, onProgress);
  return { s3_key, filename: file.name };
}
