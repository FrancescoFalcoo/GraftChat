import type {
  ConversationState,
  ConversationSummary,
  Health,
  ImageUpload,
  Model,
  OpenBranchRequest,
  OpenBranchResponse,
  PointUpdate,
  Settings,
  SettingsUpdate,
} from "./types";

/** Error thrown by every API call. `status` is 0 when the server was not reached. */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

export function toApiError(error: unknown): ApiError {
  if (error instanceof ApiError) return error;
  const message = error instanceof Error ? error.message : "Unexpected error.";
  return new ApiError(0, "unknown", message);
}

async function errorFromResponse(res: Response): Promise<ApiError> {
  let body: unknown = null;
  try {
    body = await res.json();
  } catch {
    body = null;
  }
  if (isRecord(body) && isRecord(body.error)) {
    const { code, message } = body.error;
    if (typeof code === "string" && typeof message === "string") {
      return new ApiError(res.status, code, message);
    }
  }
  if (isRecord(body) && typeof body.detail === "string") {
    return new ApiError(res.status, "http_error", body.detail);
  }
  return new ApiError(
    res.status,
    "http_error",
    `The server answered with an unexpected error (HTTP ${res.status}).`,
  );
}

export async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  let res: Response;
  try {
    const init: RequestInit = { method };
    if (body !== undefined) {
      init.headers = { "Content-Type": "application/json" };
      init.body = JSON.stringify(body);
    }
    res = await fetch(path, init);
  } catch {
    throw new ApiError(0, "network", "Cannot reach the GraftChat server. Is it running?");
  }
  if (!res.ok) throw await errorFromResponse(res);
  try {
    return (await res.json()) as T;
  } catch {
    throw new ApiError(res.status, "bad_response", "The server sent a response that is not JSON.");
  }
}

export function attachmentUrl(id: number): string {
  return `/api/attachments/${id}`;
}

export const api = {
  health: () => request<Health>("GET", "/api/health"),
  getSettings: () => request<Settings>("GET", "/api/settings"),
  putSettings: (update: SettingsUpdate) => request<Settings>("PUT", "/api/settings", update),
  deleteApiKey: () => request<Settings>("DELETE", "/api/settings/api-key"),
  models: async (): Promise<Model[]> =>
    (await request<{ models: Model[] }>("GET", "/api/models")).models,

  listConversations: async (): Promise<ConversationSummary[]> =>
    (await request<{ conversations: ConversationSummary[] }>("GET", "/api/conversations"))
      .conversations,
  createConversation: (title?: string) =>
    request<ConversationState>("POST", "/api/conversations", title ? { title } : {}),
  getConversation: (id: number) => request<ConversationState>("GET", `/api/conversations/${id}`),

  sendMessage: (
    conversationId: number,
    content: string,
    branchId: number | null,
    images: ImageUpload[] = [],
  ) =>
    request<ConversationState>("POST", `/api/conversations/${conversationId}/messages`, {
      content,
      branch_id: branchId,
      ...(images.length > 0 ? { images } : {}),
    }),
  generate: (conversationId: number, branchId: number | null) =>
    request<ConversationState>("POST", `/api/conversations/${conversationId}/generate`, {
      branch_id: branchId,
    }),
  deleteMessage: (messageId: number) =>
    request<ConversationState>("DELETE", `/api/messages/${messageId}`),

  openBranch: (conversationId: number, anchor: OpenBranchRequest) =>
    request<OpenBranchResponse>("POST", `/api/conversations/${conversationId}/branches`, anchor),
  discardBranch: (branchId: number) =>
    request<ConversationState>("POST", `/api/branches/${branchId}/discard`),
  takeaway: (branchId: number, regenerate: boolean) =>
    request<ConversationState>(
      "POST",
      `/api/branches/${branchId}/takeaway`,
      regenerate ? { regenerate: true } : {},
    ),
  patchPoint: (pointId: number, update: PointUpdate) =>
    request<ConversationState>("PATCH", `/api/points/${pointId}`, update),
  merge: (conversationId: number, branchIds: number[]) =>
    request<ConversationState>("POST", `/api/conversations/${conversationId}/merge`, {
      branch_ids: branchIds,
    }),
};
