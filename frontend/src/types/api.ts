export interface HealthzResponse {
  status: 'ok';
}

export interface ReadyzResponse {
  status: 'ready';
  checks: Record<string, string>;
}

export interface User {
  id: string;
  email: string;
  full_name: string;
  is_active: boolean;
  created_at: string;
}

export interface MerchantProfile {
  id: string;
  business_name: string;
  category: string | null;
  location: string | null;
  description: string | null;
  timezone: string;
  created_at: string;
  updated_at: string;
}

export interface AuthResponse {
  user: User;
  merchant: MerchantProfile;
  csrf_token: string;
}

export interface ApiErrorDetail {
  code: string;
  message: string;
  details?: Record<string, unknown> | Array<Record<string, unknown>>;
}

export interface ApiErrorResponse {
  error: ApiErrorDetail;
}

export type ContextItemType = 'faq' | 'policy' | 'inventory' | 'deal' | 'general';

export interface ContextItem {
  id: string;
  merchant_id: string;
  item_type: ContextItemType;
  title: string;
  content: string;
  is_active: boolean;
  version: number;
  created_at: string;
  updated_at: string;
}

export interface ContextListResponse {
  items: ContextItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface ContextCreatePayload {
  item_type: ContextItemType;
  title: string;
  content: string;
  is_active?: boolean;
}

export interface ContextUpdatePayload {
  expected_version: number;
  item_type?: ContextItemType;
  title?: string;
  content?: string;
  is_active?: boolean;
}

export interface Conversation {
  id: string;
  merchant_id: string;
  title: string;
  status: 'active' | 'archived';
  last_message_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface ConversationListResponse {
  items: Conversation[];
  total: number;
  page: number;
  page_size: number;
}

export interface ContextUsedItem {
  context_id: string;
  title: string;
  item_type: string;
  version: number;
}

export interface Message {
  id: string;
  conversation_id: string;
  role: 'user' | 'assistant';
  content: string;
  status: 'complete' | 'failed';
  provider?: string | null;
  model?: string | null;
  input_tokens?: number | null;
  output_tokens?: number | null;
  context_metadata?: {
    sources?: ContextUsedItem[];
    raw?: Record<string, unknown>;
    idempotency_key?: string;
  } | null;
  created_at: string;
}

export interface MessageListResponse {
  items: Message[];
  total: number;
  page: number;
  page_size: number;
}

export interface ChatResponse {
  user_message: Message;
  assistant_message: Message;
  context_used: ContextUsedItem[];
}

