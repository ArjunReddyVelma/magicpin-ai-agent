import {
  AuthResponse,
  MerchantProfile,
  ContextItem,
  ContextListResponse,
  ContextCreatePayload,
  ContextUpdatePayload,
  Conversation,
  ConversationListResponse,
  MessageListResponse,
  ChatResponse,
  HealthzResponse,
  ReadyzResponse,
  ApiErrorResponse,
  SuggestedAction,
  ActionListResponse,
  WhatsAppAccountStatus,
  WhatsAppInboxMessage,
} from '../types/api';

export class ApiClientError extends Error {
  public statusCode: number;
  public code: string;
  public details?: Record<string, unknown> | Array<Record<string, unknown>>;

  constructor(statusCode: number, code: string, message: string, details?: Record<string, unknown> | Array<Record<string, unknown>>) {
    super(message);
    this.name = 'ApiClientError';
    this.statusCode = statusCode;
    this.code = code;
    this.details = details;
  }
}

/**
 * Resolves and normalizes the backend API base URL.
 *
 * Expected formats for VITE_API_BASE_URL:
 * - Unset or empty: defaults to '/v1' (compatible with local Vite proxy and Render rewrite rules).
 * - Full origin without path: 'https://backend.example.com' -> 'https://backend.example.com/v1'
 * - Full origin with '/v1': 'https://backend.example.com/v1' -> 'https://backend.example.com/v1'
 * - Relative base: '/custom-api' -> '/custom-api/v1' (or '/custom-api/v1' -> '/custom-api/v1')
 *
 * Automatically prevents double '/v1/v1' and removes trailing slashes.
 */
export function resolveBaseUrl(envUrl?: string): string {
  if (!envUrl || !envUrl.trim()) {
    return '/v1';
  }
  const cleaned = envUrl.trim().replace(/\/+$/, '');
  if (cleaned.endsWith('/v1')) {
    return cleaned;
  }
  return `${cleaned}/v1`;
}

export class ApiClient {
  private baseUrl: string;
  private csrfToken: string | null = null;
  private onUnauthorized: (() => void) | null = null;

  constructor(customBaseUrl?: string) {
    const envUrl = typeof import.meta !== 'undefined' && import.meta.env
      ? import.meta.env.VITE_API_BASE_URL
      : undefined;
    this.baseUrl = customBaseUrl ? resolveBaseUrl(customBaseUrl) : resolveBaseUrl(envUrl);
  }

  public getBaseUrl(): string {
    return this.baseUrl;
  }

  public setCsrfToken(token: string | null) {
    this.csrfToken = token;
  }

  public getCsrfToken(): string | null {
    return this.csrfToken;
  }

  public setOnUnauthorized(callback: () => void) {
    this.onUnauthorized = callback;
  }

  private async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
    const url = `${this.baseUrl}${endpoint}`;
    const headers = new Headers(options.headers || {});

    // Ensure JSON accept
    if (!headers.has('Accept')) {
      headers.set('Accept', 'application/json');
    }

    // Attach CSRF token on state-changing methods
    const method = (options.method || 'GET').toUpperCase();
    if (['POST', 'PATCH', 'PUT', 'DELETE'].includes(method) && this.csrfToken) {
      if (!headers.has('X-CSRF-Token')) {
        headers.set('X-CSRF-Token', this.csrfToken);
      }
    }

    // Include credentials for httpOnly session cookies
    const config: RequestInit = {
      ...options,
      headers,
      credentials: 'include',
    };

    let response: Response;
    try {
      response = await fetch(url, config);
    } catch (networkErr: unknown) {
      throw new ApiClientError(
        0,
        'NETWORK_ERROR',
        'Unable to connect to backend server. Please verify your connection.'
      );
    }

    if (response.status === 401 && this.onUnauthorized) {
      this.onUnauthorized();
    }

    if (!response.ok) {
      let errorData: ApiErrorResponse | null = null;
      try {
        errorData = await response.json();
      } catch {
        // Non-JSON error body
      }

      const code = errorData?.error?.code || `HTTP_${response.status}`;
      const message = errorData?.error?.message || `Request failed with status ${response.status}`;
      const details = errorData?.error?.details;

      throw new ApiClientError(response.status, code, message, details);
    }

    // Empty response check (e.g. 204 or logout)
    if (response.status === 204) {
      return {} as T;
    }

    return response.json() as Promise<T>;
  }

  // Health
  public async getHealthz(): Promise<HealthzResponse> {
    return this.request<HealthzResponse>('/healthz');
  }

  public async getReadyz(): Promise<ReadyzResponse> {
    return this.request<ReadyzResponse>('/readyz');
  }

  // Authentication
  public async register(payload: {
    email: string;
    password: string;
    full_name: string;
    business_name: string;
    category?: string;
    location?: string;
  }): Promise<AuthResponse> {
    const res = await this.request<AuthResponse>('/auth/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    this.setCsrfToken(res.csrf_token);
    return res;
  }

  public async login(payload: { email: string; password: string }): Promise<AuthResponse> {
    const res = await this.request<AuthResponse>('/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    this.setCsrfToken(res.csrf_token);
    return res;
  }

  public async logout(): Promise<{ status: string }> {
    const res = await this.request<{ status: string }>('/auth/logout', {
      method: 'POST',
    });
    this.setCsrfToken(null);
    return res;
  }

  public async getMe(): Promise<AuthResponse> {
    const res = await this.request<AuthResponse>('/auth/me');
    this.setCsrfToken(res.csrf_token);
    return res;
  }

  public async deleteAccount(password: string): Promise<{ status: string; message: string }> {
    const res = await this.request<{ status: string; message: string }>('/auth/account', {
      method: 'DELETE',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password }),
    });
    this.setCsrfToken(null);
    return res;
  }

  // Merchant Profile
  public async getMerchantProfile(): Promise<MerchantProfile> {
    return this.request<MerchantProfile>('/merchant/profile');
  }

  public async updateMerchantProfile(payload: {
    business_name?: string;
    category?: string | null;
    location?: string | null;
    description?: string | null;
    timezone?: string;
  }): Promise<MerchantProfile> {
    return this.request<MerchantProfile>('/merchant/profile', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
  }

  // Context Items
  public async listContextItems(params?: {
    item_type?: string;
    is_active?: boolean;
    page?: number;
    page_size?: number;
  }): Promise<ContextListResponse> {
    const searchParams = new URLSearchParams();
    if (params?.item_type) searchParams.set('item_type', params.item_type);
    if (params?.is_active !== undefined) searchParams.set('is_active', String(params.is_active));
    if (params?.page) searchParams.set('page', String(params.page));
    if (params?.page_size) searchParams.set('page_size', String(params.page_size));

    const qs = searchParams.toString();
    return this.request<ContextListResponse>(`/context${qs ? `?${qs}` : ''}`);
  }

  public async createContextItem(payload: ContextCreatePayload): Promise<ContextItem> {
    return this.request<ContextItem>('/context', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
  }

  public async getContextItem(id: string): Promise<ContextItem> {
    return this.request<ContextItem>(`/context/${id}`);
  }

  public async updateContextItem(id: string, payload: ContextUpdatePayload): Promise<ContextItem> {
    return this.request<ContextItem>(`/context/${id}`, {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
        'If-Match': `"${payload.expected_version}"`,
      },
      body: JSON.stringify(payload),
    });
  }

  public async deleteContextItem(id: string): Promise<{ status: string; message: string }> {
    return this.request<{ status: string; message: string }>(`/context/${id}`, {
      method: 'DELETE',
    });
  }

  // Conversations & Chat
  public async listConversations(params?: {
    status?: string;
    query?: string;
    page?: number;
    page_size?: number;
  }): Promise<ConversationListResponse> {
    const searchParams = new URLSearchParams();
    if (params?.status) searchParams.set('status', params.status);
    if (params?.query) searchParams.set('query', params.query);
    if (params?.page) searchParams.set('page', String(params.page));
    if (params?.page_size) searchParams.set('page_size', String(params.page_size));

    const qs = searchParams.toString();
    return this.request<ConversationListResponse>(`/conversations${qs ? `?${qs}` : ''}`);
  }

  public async createConversation(title?: string): Promise<Conversation> {
    return this.request<Conversation>('/conversations', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: title || 'New Conversation' }),
    });
  }

  public async getConversation(id: string): Promise<Conversation> {
    return this.request<Conversation>(`/conversations/${id}`);
  }

  public async updateConversation(
    id: string,
    payload: { title?: string; status?: 'active' | 'archived' }
  ): Promise<Conversation> {
    return this.request<Conversation>(`/conversations/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
  }

  public async deleteConversation(id: string): Promise<{ status: string; message: string }> {
    return this.request<{ status: string; message: string }>(`/conversations/${id}`, {
      method: 'DELETE',
    });
  }

  public async listMessages(
    conversationId: string,
    params?: { page?: number; page_size?: number; before?: string }
  ): Promise<MessageListResponse> {
    const searchParams = new URLSearchParams();
    if (params?.page) searchParams.set('page', String(params.page));
    if (params?.page_size) searchParams.set('page_size', String(params.page_size));
    if (params?.before) searchParams.set('before', params.before);

    const qs = searchParams.toString();
    return this.request<MessageListResponse>(
      `/conversations/${conversationId}/messages${qs ? `?${qs}` : ''}`
    );
  }

  public async sendMessage(
    conversationId: string,
    payload: {
      content: string;
      idempotency_key?: string;
      retry_message_id?: string;
    }
  ): Promise<ChatResponse> {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    };
    if (payload.idempotency_key) {
      headers['Idempotency-Key'] = payload.idempotency_key;
    }

    return this.request<ChatResponse>(`/conversations/${conversationId}/messages`, {
      method: 'POST',
      headers,
      body: JSON.stringify(payload),
    });
  }

  public async getWhatsAppAccount(): Promise<WhatsAppAccountStatus> { return this.request<WhatsAppAccountStatus>('/whatsapp/account'); }
  public async saveWhatsAppAccount(payload: { phone_number_id: string; business_account_id?: string; access_token: string }): Promise<WhatsAppAccountStatus> { return this.request<WhatsAppAccountStatus>('/whatsapp/account', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) }); }
  public async listWhatsAppMessages(): Promise<{ items: WhatsAppInboxMessage[] }> { return this.request<{ items: WhatsAppInboxMessage[] }>('/whatsapp/messages'); }
  public async sendWhatsAppReply(id: string, reply_text: string): Promise<{ id: string; status: string; sent_at: string }> { return this.request<{ id: string; status: string; sent_at: string }>(`/whatsapp/messages/${id}/send`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ reply_text }) }); }

  // Suggested Actions
  public async listActions(params?: {
    status?: string;
    page?: number;
    page_size?: number;
  }): Promise<ActionListResponse> {
    const searchParams = new URLSearchParams();
    if (params?.status) searchParams.set('status', params.status);
    if (params?.page) searchParams.set('page', String(params.page));
    if (params?.page_size) searchParams.set('page_size', String(params.page_size));

    const qs = searchParams.toString();
    return this.request<ActionListResponse>(`/actions${qs ? `?${qs}` : ''}`);
  }

  public async getAction(id: string): Promise<SuggestedAction> {
    return this.request<SuggestedAction>(`/actions/${id}`);
  }

  public async approveAction(id: string): Promise<SuggestedAction> {
    return this.request<SuggestedAction>(`/actions/${id}/approve`, {
      method: 'POST',
    });
  }

  public async dismissAction(id: string): Promise<SuggestedAction> {
    return this.request<SuggestedAction>(`/actions/${id}/dismiss`, {
      method: 'POST',
    });
  }
}

export const api = new ApiClient();
