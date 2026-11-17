// Shapes copied from docs/API.md. Offsets are Unicode code points.

export type Role = "user" | "assistant" | "merge";
export type BranchStatus = "open" | "merged" | "discarded";

export interface Attachment {
  id: number;
  kind: "image";
  mime: string;
  name: string;
  size: number;
}

export interface Message {
  id: number;
  branch_id: number | null;
  parent_id: number | null;
  role: Role;
  content: string;
  created_at: string;
  attachments: Attachment[];
}

/** An image sent with a new message: base64 without the "data:" prefix. */
export interface ImageUpload {
  name: string;
  mime: string;
  data: string;
}

export interface Point {
  id: number;
  branch_id: number;
  position: number;
  title: string;
  text_generated: string;
  text_final: string;
  included: boolean;
}

export interface Branch {
  id: number;
  anchor_message_id: number;
  anchor_start: number;
  anchor_end: number;
  anchor_quote: string;
  status: BranchStatus;
  merge_message_id: number | null;
  /** Last message of main when the branch was opened: merges up to it are known to the branch. */
  base_message_id: number | null;
  created_at: string;
  messages: Message[];
  points: Point[];
}

export interface ConversationSummary {
  id: number;
  title: string;
  created_at: string;
  open_branches: number;
}

export interface ConversationState {
  conversation: { id: number; title: string; created_at: string };
  main: Message[];
  branches: Branch[];
  pending_branch_ids: number[] | null;
}

export interface Settings {
  has_api_key: boolean;
  api_key_hint: string | null;
  api_key_from_env: boolean;
  spend_cap_usd: number;
  chat_model: string | null;
  takeaway_model: string | null;
  month_spend_usd: number;
  fake_llm: boolean;
}

export interface SettingsUpdate {
  api_key?: string;
  spend_cap_usd?: number;
  chat_model?: string;
  takeaway_model?: string | null;
}

export interface Health {
  ok: true;
  core: Record<string, boolean>;
}

export interface Model {
  id: string;
  name: string;
  context_length: number | null;
  images: boolean;
}

export interface OpenBranchRequest {
  anchor_message_id: number;
  start: number;
  end: number;
  quote: string;
}

export interface OpenBranchResponse {
  branch_id: number;
  state: ConversationState;
}

export interface PointUpdate {
  included?: boolean;
  text_final?: string;
}
