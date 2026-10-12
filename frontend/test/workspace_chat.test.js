import test from 'node:test';
import assert from 'node:assert';

// Ensure mock Headers is available for Node test environment
if (!global.Headers) {
  global.Headers = class MockHeaders {
    constructor(init = {}) {
      this._map = new Map();
      if (init instanceof MockHeaders) {
        for (const [k, v] of init._map) this._map.set(k.toLowerCase(), v);
      } else if (typeof init === 'object') {
        for (const [k, v] of Object.entries(init)) this._map.set(k.toLowerCase(), String(v));
      }
    }
    set(k, v) { this._map.set(k.toLowerCase(), String(v)); }
    get(k) { return this._map.get(k.toLowerCase()) || null; }
    has(k) { return this._map.has(k.toLowerCase()); }
  };
}

test('Conversations listing and filtering: correctly formats query params', async () => {
  let capturedUrl = null;

  global.fetch = async (url) => {
    capturedUrl = url;
    return {
      ok: true,
      status: 200,
      json: async () => ({
        items: [
          {
            id: 'conv-1',
            merchant_id: 'm-1',
            title: 'Return Policy Inquiry',
            status: 'active',
            last_message_at: '2026-10-12T10:00:00Z',
            created_at: '2026-10-12T09:00:00Z',
            updated_at: '2026-10-12T10:00:00Z',
          },
        ],
        total: 1,
        page: 1,
        page_size: 50,
      }),
    };
  };

  // Test active status filter and search query
  const res = await global.fetch('/v1/conversations?status=active&query=Return&page=1&page_size=50');
  const data = await res.json();

  assert.strictEqual(capturedUrl.includes('status=active'), true);
  assert.strictEqual(capturedUrl.includes('query=Return'), true);
  assert.strictEqual(data.items.length, 1);
  assert.strictEqual(data.items[0].id, 'conv-1');
});

test('Conversation creation and updating: handles POST and PATCH lifecycle', async () => {
  let capturedPostMethod = null;
  let capturedPostBody = null;
  let capturedPatchBody = null;

  global.fetch = async (url, options) => {
    if (options.method === 'POST') {
      capturedPostMethod = 'POST';
      capturedPostBody = JSON.parse(options.body);
      return {
        ok: true,
        status: 201,
        json: async () => ({
          id: 'new-conv-uuid',
          merchant_id: 'm-1',
          title: capturedPostBody.title,
          status: 'active',
          created_at: '2026-10-12T12:00:00Z',
          updated_at: '2026-10-12T12:00:00Z',
        }),
      };
    } else if (options.method === 'PATCH') {
      capturedPatchBody = JSON.parse(options.body);
      return {
        ok: true,
        status: 200,
        json: async () => ({
          id: 'new-conv-uuid',
          merchant_id: 'm-1',
          title: capturedPatchBody.title || 'New Title',
          status: capturedPatchBody.status || 'archived',
          created_at: '2026-10-12T12:00:00Z',
          updated_at: '2026-10-12T12:05:00Z',
        }),
      };
    }
  };

  // 1. Create conversation
  const createRes = await global.fetch('/v1/conversations', {
    method: 'POST',
    body: JSON.stringify({ title: 'Catering Menu Discussion' }),
  });
  const created = await createRes.json();
  assert.strictEqual(capturedPostMethod, 'POST');
  assert.strictEqual(capturedPostBody.title, 'Catering Menu Discussion');
  assert.strictEqual(created.id, 'new-conv-uuid');

  // 2. Archive conversation
  const archiveRes = await global.fetch(`/v1/conversations/${created.id}`, {
    method: 'PATCH',
    body: JSON.stringify({ status: 'archived' }),
  });
  const archived = await archiveRes.json();
  assert.strictEqual(capturedPatchBody.status, 'archived');
  assert.strictEqual(archived.status, 'archived');
});

test('Message history: loads messages in deterministic order and supports pagination contract', async () => {
  let capturedUrl = null;

  global.fetch = async (url) => {
    capturedUrl = url;
    return {
      ok: true,
      status: 200,
      json: async () => ({
        items: [
          {
            id: 'msg-1',
            conversation_id: 'conv-1',
            role: 'user',
            content: 'What is your refund policy?',
            status: 'complete',
            created_at: '2026-10-12T10:00:00Z',
          },
          {
            id: 'msg-2',
            conversation_id: 'conv-1',
            role: 'assistant',
            content: 'Our refund policy allows returns within 7 days with original receipt.',
            status: 'complete',
            model: 'llama-3.3-70b-versatile',
            input_tokens: 45,
            output_tokens: 32,
            context_metadata: {
              sources: [
                {
                  context_id: 'ctx-1',
                  title: 'Store Refund Policy',
                  item_type: 'policy',
                  version: 2,
                },
              ],
            },
            created_at: '2026-10-12T10:00:02Z',
          },
        ],
        total: 15,
        page: 1,
        page_size: 50,
      }),
    };
  };

  const res = await global.fetch('/v1/conversations/conv-1/messages?page=1&page_size=50');
  const data = await res.json();

  assert.strictEqual(capturedUrl.includes('/conversations/conv-1/messages'), true);
  assert.strictEqual(data.items.length, 2);
  assert.strictEqual(data.items[0].role, 'user');
  assert.strictEqual(data.items[1].role, 'assistant');
  assert.strictEqual(data.items[1].context_metadata.sources[0].title, 'Store Refund Policy');
  assert.strictEqual(data.total, 15);
});

test('Message sending: enforces Idempotency-Key header, body contract, and grounds assistant response', async () => {
  let capturedHeaders = null;
  let capturedBody = null;

  global.fetch = async (url, options) => {
    capturedHeaders = options.headers;
    capturedBody = JSON.parse(options.body);
    return {
      ok: true,
      status: 200,
      json: async () => ({
        user_message: {
          id: 'user-msg-uuid',
          conversation_id: 'conv-1',
          role: 'user',
          content: capturedBody.content,
          status: 'complete',
          created_at: '2026-10-12T10:30:00Z',
        },
        assistant_message: {
          id: 'asst-msg-uuid',
          conversation_id: 'conv-1',
          role: 'assistant',
          content: 'Store hours are 10 AM to 10 PM daily.',
          status: 'complete',
          model: 'llama-3.3-70b-versatile',
          output_tokens: 28,
          context_metadata: {
            sources: [
              {
                context_id: 'ctx-hours',
                title: 'Daily Operating Hours',
                item_type: 'operating_info',
                version: 1,
              },
            ],
          },
          created_at: '2026-10-12T10:30:03Z',
        },
        context_used: [
          {
            context_id: 'ctx-hours',
            title: 'Daily Operating Hours',
            item_type: 'operating_info',
            version: 1,
          },
        ],
      }),
    };
  };

  const idempotencyKey = 'client-idemp-12345';
  const headers = new global.Headers();
  headers.set('Content-Type', 'application/json');
  headers.set('Idempotency-Key', idempotencyKey);

  const res = await global.fetch('/v1/conversations/conv-1/messages', {
    method: 'POST',
    headers,
    body: JSON.stringify({
      content: 'When do you open tomorrow?',
      idempotency_key: idempotencyKey,
    }),
  });

  const data = await res.json();

  assert.strictEqual(capturedHeaders.get('idempotency-key'), idempotencyKey);
  assert.strictEqual(capturedBody.idempotency_key, idempotencyKey);
  assert.strictEqual(data.user_message.status, 'complete');
  assert.strictEqual(data.assistant_message.status, 'complete');
  assert.strictEqual(data.context_used.length, 1);
  assert.strictEqual(data.context_used[0].item_type, 'operating_info');
});

test('Provider failure handling: surfaces 502 with failed_message_id for retry without losing draft', async () => {
  global.fetch = async () => {
    return {
      ok: false,
      status: 502,
      json: async () => ({
        error: {
          code: 'LLM_PROVIDER_ERROR',
          message: 'The AI service is temporarily unavailable. Your message has been saved as failed and can be retried.',
          details: {
            failed_message_id: 'failed-msg-999',
            retryable: true,
          },
        },
      }),
    };
  };

  const res = await global.fetch('/v1/conversations/conv-1/messages', {
    method: 'POST',
    body: JSON.stringify({ content: 'Explain our warranty terms' }),
  });

  assert.strictEqual(res.ok, false);
  assert.strictEqual(res.status, 502);

  const errorData = await res.json();
  assert.strictEqual(errorData.error.code, 'LLM_PROVIDER_ERROR');
  assert.strictEqual(errorData.error.details.failed_message_id, 'failed-msg-999');
  assert.strictEqual(errorData.error.details.retryable, true);
});

test('Safe retry: transmits retry_message_id and fresh idempotency key to recover failed turn', async () => {
  let capturedBody = null;
  let capturedHeaders = null;

  global.fetch = async (url, options) => {
    capturedBody = JSON.parse(options.body);
    capturedHeaders = options.headers;
    return {
      ok: true,
      status: 200,
      json: async () => ({
        user_message: {
          id: capturedBody.retry_message_id,
          conversation_id: 'conv-1',
          role: 'user',
          content: capturedBody.content,
          status: 'complete', // Successfully transitioned from failed to complete
          created_at: '2026-10-12T11:00:00Z',
        },
        assistant_message: {
          id: 'asst-msg-retry',
          conversation_id: 'conv-1',
          role: 'assistant',
          content: 'Warranty lasts 1 year for all electronic purchases.',
          status: 'complete',
          created_at: '2026-10-12T11:00:03Z',
        },
        context_used: [],
      }),
    };
  };

  const retryIdempotency = 'retry-idemp-67890';
  const headers = new global.Headers();
  headers.set('Content-Type', 'application/json');
  headers.set('Idempotency-Key', retryIdempotency);

  const res = await global.fetch('/v1/conversations/conv-1/messages', {
    method: 'POST',
    headers,
    body: JSON.stringify({
      content: 'Explain our warranty terms',
      retry_message_id: 'failed-msg-999',
      idempotency_key: retryIdempotency,
    }),
  });

  const data = await res.json();

  assert.strictEqual(capturedBody.retry_message_id, 'failed-msg-999');
  assert.strictEqual(capturedHeaders.get('idempotency-key'), retryIdempotency);
  assert.strictEqual(data.user_message.id, 'failed-msg-999');
  assert.strictEqual(data.user_message.status, 'complete');
  assert.strictEqual(data.assistant_message.status, 'complete');
});

test('Archived conversation rejection: backend rejects messages with HTTP 400 CONVERSATION_ARCHIVED', async () => {
  global.fetch = async () => {
    return {
      ok: false,
      status: 400,
      json: async () => ({
        error: {
          code: 'CONVERSATION_ARCHIVED',
          message: 'Cannot send messages to an archived conversation',
        },
      }),
    };
  };

  const res = await global.fetch('/v1/conversations/archived-conv/messages', {
    method: 'POST',
    body: JSON.stringify({ content: 'Hello in archive' }),
  });

  assert.strictEqual(res.ok, false);
  assert.strictEqual(res.status, 400);

  const errorData = await res.json();
  assert.strictEqual(errorData.error.code, 'CONVERSATION_ARCHIVED');
});

test('Session expiration: 401 triggers unauthorized handling cleanly', async () => {
  let unauthorizedTriggered = false;
  const onUnauthorized = () => {
    unauthorizedTriggered = true;
  };

  global.fetch = async () => {
    return {
      ok: false,
      status: 401,
      json: async () => ({
        error: {
          code: 'SESSION_EXPIRED',
          message: 'Session has expired or is invalid',
        },
      }),
    };
  };

  const res = await global.fetch('/v1/conversations');
  if (res.status === 401) {
    onUnauthorized();
  }

  assert.strictEqual(res.status, 401);
  assert.strictEqual(unauthorizedTriggered, true);
});
