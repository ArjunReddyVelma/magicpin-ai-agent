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

export type ContextItemType = 'faq' | 'policy' | 'business_fact' | 'service' | 'operating_info';

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

export type ActionType = 'reply_draft' | 'summary' | 'recommendation' | 'follow_up';
export type ActionStatus = 'pending' | 'approved' | 'dismissed';

export interface SuggestedAction {
  id: string;
  merchant_id: string;
  conversation_id: string | null;
  action_type: ActionType;
  title: string;
  description: string;
  payload: Record<string, unknown> | null;
  status: ActionStatus;
  created_by: string;
  reviewed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface ActionListResponse {
  items: SuggestedAction[];
  total: number;
  page: number;
  page_size: number;
}


export interface WhatsAppAccountStatus {
  connected: boolean;
  phone_number_id: string | null;
  business_account_id: string | null;
  created_at: string | null;
  mode?: 'live' | 'mock';
}

export interface WhatsAppInboxMessage {
  id: string;
  customer_wa_id: string;
  customer_name: string | null;
  inbound_text: string;
  suggested_reply: string;
  status: string;
  last_error: string | null;
  received_at: string;
  sent_at: string | null;
}

export interface SimulateInboundMessagePayload {
  customer_wa_id: string;
  customer_name?: string;
  message_text: string;
}

export type CustomerSupportStatus = 'needs_review' | 'delivered' | 'dismissed';
export type CustomerSupportAiStatus = 'pending' | 'generating' | 'completed' | 'failed' | 'skipped';

export interface CustomerSupportMessage {
  id: string;
  session_id: string;
  merchant_id: string;
  customer_name: string | null;
  customer_text: string;
  suggested_reply: string | null;
  approved_reply: string | null;
  status: CustomerSupportStatus;
  ai_status: CustomerSupportAiStatus;
  ai_error: string | null;
  reviewed_at: string | null;
  delivered_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface CustomerSupportListResponse {
  items: CustomerSupportMessage[];
  total: number;
  page: number;
  page_size: number;
}

export interface PublicMerchantProfile {
  merchant_id: string;
  business_name: string;
  category: string | null;
  location: string | null;
  description: string | null;
}

export interface CreateCustomerSessionResponse {
  session_id: string;
  customer_token: string;
  status: string;
  created_at: string;
}

export interface CustomerInquiryResponse {
  id: string;
  session_id: string;
  customer_text: string;
  status: string;
  created_at: string;
}

export interface CustomerHistoryItem {
  id: string;
  customer_text: string;
  reply: string | null;
  status: string;
  delivered_at: string | null;
  created_at: string;
}

export interface CustomerHistoryResponse {
  session_id: string;
  items: CustomerHistoryItem[];
  total: number;
}
