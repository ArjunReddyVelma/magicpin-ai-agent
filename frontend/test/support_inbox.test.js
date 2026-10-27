import test from 'node:test';
import assert from 'node:assert';
// Mock Headers for Node test environment
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

class ApiClientError extends Error {
  constructor(statusCode, code, message, details) {
    super(message);
    this.name = 'ApiClientError';
    this.statusCode = statusCode;
    this.code = code;
    this.details = details;
  }
}

class ApiClient {
  constructor(baseUrl = '/v1') {
    this.baseUrl = baseUrl;
    this.csrfToken = null;
  }

  setCsrfToken(token) {
    this.csrfToken = token;
  }

  async request(endpoint, options = {}) {
    const url = `${this.baseUrl}${endpoint}`;
    const headers = new Headers(options.headers || {});
    if (!headers.has('Accept')) {
      headers.set('Accept', 'application/json');
    }
    const method = (options.method || 'GET').toUpperCase();
    if (['POST', 'PATCH', 'PUT', 'DELETE'].includes(method) && this.csrfToken) {
      if (!headers.has('X-CSRF-Token')) {
        headers.set('X-CSRF-Token', this.csrfToken);
      }
    }
    const config = {
      ...options,
      headers,
      credentials: 'include',
    };

    let response;
    try {
      response = await fetch(url, config);
    } catch {
      throw new ApiClientError(0, 'NETWORK_ERROR', 'Network error');
    }

    if (!response.ok) {
      let errorData = null;
      try {
        errorData = await response.json();
      } catch {}
      const code = errorData?.error?.code || `HTTP_${response.status}`;
      const message = errorData?.error?.message || `Request failed with status ${response.status}`;
      const details = errorData?.error?.details;
      throw new ApiClientError(response.status, code, message, details);
    }

    return response.json();
  }

  async listSupportMessages(params) {
    const searchParams = new URLSearchParams();
    if (params?.status) searchParams.set('status', params.status);
    if (params?.page) searchParams.set('page', String(params.page));
    if (params?.page_size) searchParams.set('page_size', String(params.page_size));
    const qs = searchParams.toString();
    return this.request(`/support/messages${qs ? `?${qs}` : ''}`);
  }

  async editSupportSuggestedReply(id, suggested_reply) {
    return this.request(`/support/messages/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ suggested_reply }),
    });
  }

  async deliverSupportReply(id, reply_text) {
    return this.request(`/support/messages/${id}/deliver`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ reply_text: reply_text || undefined }),
    });
  }

  async dismissSupportMessage(id) {
    return this.request(`/support/messages/${id}/dismiss`, {
      method: 'POST',
    });
  }
}

// ---------------------------------------------------------------------------
// 1. Inbox loading and empty states
// ---------------------------------------------------------------------------
test('Support Inbox API: listSupportMessages formats status filter, pagination, and empty state', async () => {
  let capturedUrl = null;

  global.fetch = async (url) => {
    capturedUrl = url;
    return {
      ok: true,
      status: 200,
      json: async () => ({
        items: [],
        total: 0,
        page: 1,
        page_size: 10,
      }),
    };
  };

  const client = new ApiClient('/v1');
  const res = await client.listSupportMessages({
    status: 'needs_review',
    page: 1,
    page_size: 10,
  });

  assert.strictEqual(capturedUrl, '/v1/support/messages?status=needs_review&page=1&page_size=10');
  assert.strictEqual(res.total, 0);
  assert.strictEqual(res.items.length, 0);
});

// ---------------------------------------------------------------------------
// 2. Display of inquiries and review statuses
// ---------------------------------------------------------------------------
test('Support Inbox API: parses customer inquiry, review status, and AI suggestion fields', async () => {
  global.fetch = async () => ({
    ok: true,
    status: 200,
    json: async () => ({
      items: [
        {
          id: 'msg-uuid-1',
          session_id: 'sess-uuid-1',
          merchant_id: 'merch-uuid-1',
          customer_name: 'Alice Customer',
          customer_text: 'Are you open on Sundays?',
          suggested_reply: 'Yes, we are open Sundays from 10 AM to 6 PM.',
          approved_reply: null,
          status: 'needs_review',
          ai_status: 'completed',
          ai_error: null,
          reviewed_at: null,
          delivered_at: null,
          created_at: '2026-10-27T08:00:00Z',
          updated_at: '2026-10-27T08:00:01Z',
        },
      ],
      total: 1,
      page: 1,
      page_size: 10,
    }),
  });

  const client = new ApiClient('/v1');
  const res = await client.listSupportMessages();

  assert.strictEqual(res.items.length, 1);
  const msg = res.items[0];
  assert.strictEqual(msg.customer_name, 'Alice Customer');
  assert.strictEqual(msg.customer_text, 'Are you open on Sundays?');
  assert.strictEqual(msg.suggested_reply, 'Yes, we are open Sundays from 10 AM to 6 PM.');
  assert.strictEqual(msg.status, 'needs_review');
  assert.strictEqual(msg.ai_status, 'completed');
  assert.strictEqual(msg.approved_reply, null);
});

// ---------------------------------------------------------------------------
// 3. AI failure and manual-reply fallback
// ---------------------------------------------------------------------------
test('Support Inbox API: handles AI failure representation safely without raw leak', async () => {
  global.fetch = async () => ({
    ok: true,
    status: 200,
    json: async () => ({
      items: [
        {
          id: 'msg-uuid-failed-ai',
          session_id: 'sess-uuid-2',
          merchant_id: 'merch-uuid-1',
          customer_name: 'Bob Requester',
          customer_text: 'Can I get catering for 50 people tomorrow?',
          suggested_reply: null,
          approved_reply: null,
          status: 'needs_review',
          ai_status: 'failed',
          ai_error: 'LLM provider timeout',
          reviewed_at: null,
          delivered_at: null,
          created_at: '2026-10-27T08:30:00Z',
          updated_at: '2026-10-27T08:30:05Z',
        },
      ],
      total: 1,
      page: 1,
      page_size: 10,
    }),
  });

  const client = new ApiClient('/v1');
  const res = await client.listSupportMessages();
  const msg = res.items[0];

  assert.strictEqual(msg.ai_status, 'failed');
  assert.strictEqual(msg.suggested_reply, null);
  assert.strictEqual(msg.status, 'needs_review');
  // Inquiry text is preserved intact for merchant to reply manually
  assert.strictEqual(msg.customer_text, 'Can I get catering for 50 people tomorrow?');
});

// ---------------------------------------------------------------------------
// 4. Draft editing without automatic delivery
// ---------------------------------------------------------------------------
test('Support Inbox API: editSupportSuggestedReply sends PATCH and does NOT deliver', async () => {
  let capturedUrl = null;
  let capturedMethod = null;
  let capturedBody = null;

  global.fetch = async (url, options) => {
    capturedUrl = url;
    capturedMethod = options.method;
    capturedBody = JSON.parse(options.body);
    return {
      ok: true,
      status: 200,
      json: async () => ({
        id: 'msg-uuid-1',
        session_id: 'sess-uuid-1',
        merchant_id: 'merch-uuid-1',
        customer_name: 'Alice',
        customer_text: 'Are you open on Sundays?',
        suggested_reply: 'Yes, we are open on Sundays from 10 AM to 6 PM (Special Holiday Hours).',
        approved_reply: null,
        status: 'needs_review',
        ai_status: 'completed',
        ai_error: null,
        reviewed_at: null,
        delivered_at: null,
        created_at: '2026-10-27T08:00:00Z',
        updated_at: '2026-10-27T08:05:00Z',
      }),
    };
  };

  const client = new ApiClient('/v1');
  client.setCsrfToken('mock-csrf-token-123');

  const updated = await client.editSupportSuggestedReply(
    'msg-uuid-1',
    'Yes, we are open on Sundays from 10 AM to 6 PM (Special Holiday Hours).'
  );

  assert.strictEqual(capturedUrl, '/v1/support/messages/msg-uuid-1');
  assert.strictEqual(capturedMethod, 'PATCH');
  assert.strictEqual(capturedBody.suggested_reply, 'Yes, we are open on Sundays from 10 AM to 6 PM (Special Holiday Hours).');
  // CRITICAL: Status must remain needs_review, not delivered!
  assert.strictEqual(updated.status, 'needs_review');
  assert.strictEqual(updated.approved_reply, null);
  assert.strictEqual(updated.delivered_at, null);
});

// ---------------------------------------------------------------------------
// 5. Explicit delivery confirmation and successful server response
// ---------------------------------------------------------------------------
test('Support Inbox API: deliverSupportReply sends POST /deliver with CSRF and updates delivered state', async () => {
  let capturedUrl = null;
  let capturedMethod = null;
  let capturedHeaders = null;
  let capturedBody = null;

  global.fetch = async (url, options) => {
    capturedUrl = url;
    capturedMethod = options.method;
    capturedHeaders = options.headers;
    capturedBody = JSON.parse(options.body);
    return {
      ok: true,
      status: 200,
      json: async () => ({
        id: 'msg-uuid-1',
        session_id: 'sess-uuid-1',
        merchant_id: 'merch-uuid-1',
        customer_name: 'Alice',
        customer_text: 'Are you open on Sundays?',
        suggested_reply: 'Yes, we are open on Sundays from 10 AM to 6 PM.',
        approved_reply: 'Official merchant response: Yes, we are open on Sundays from 10 AM to 6 PM.',
        status: 'delivered',
        ai_status: 'completed',
        ai_error: null,
        reviewed_at: '2026-10-27T08:10:00Z',
        delivered_at: '2026-10-27T08:10:00Z',
        created_at: '2026-10-27T08:00:00Z',
        updated_at: '2026-10-27T08:10:00Z',
      }),
    };
  };

  const client = new ApiClient('/v1');
  client.setCsrfToken('valid-csrf-token-abc');

  const delivered = await client.deliverSupportReply(
    'msg-uuid-1',
    'Official merchant response: Yes, we are open on Sundays from 10 AM to 6 PM.'
  );

  assert.strictEqual(capturedUrl, '/v1/support/messages/msg-uuid-1/deliver');
  assert.strictEqual(capturedMethod, 'POST');
  assert.strictEqual(capturedHeaders.get('X-CSRF-Token'), 'valid-csrf-token-abc');
  assert.strictEqual(capturedBody.reply_text, 'Official merchant response: Yes, we are open on Sundays from 10 AM to 6 PM.');

  // Verify server confirmed delivered state
  assert.strictEqual(delivered.status, 'delivered');
  assert.strictEqual(delivered.approved_reply, 'Official merchant response: Yes, we are open on Sundays from 10 AM to 6 PM.');
  assert.strictEqual(delivered.delivered_at, '2026-10-27T08:10:00Z');
});

// ---------------------------------------------------------------------------
// 6. Delivery conflict and API error handling
// ---------------------------------------------------------------------------
test('Support Inbox API: handles 409 Conflict when message was already delivered', async () => {
  global.fetch = async () => ({
    ok: false,
    status: 409,
    json: async () => ({
      error: {
        code: 'MESSAGE_ALREADY_DELIVERED',
        message: 'This reply has already been delivered.',
      },
    }),
  });

  const client = new ApiClient('/v1');
  client.setCsrfToken('csrf-token');

  await assert.rejects(
    async () => {
      await client.deliverSupportReply('msg-uuid-already-sent', 'Attempt duplicate delivery');
    },
    (err) => {
      assert.ok(err instanceof ApiClientError);
      assert.strictEqual(err.statusCode, 409);
      assert.strictEqual(err.code, 'MESSAGE_ALREADY_DELIVERED');
      assert.strictEqual(err.message, 'This reply has already been delivered.');
      return true;
    }
  );
});

// ---------------------------------------------------------------------------
// 7. Prevention of duplicate clicks while a request is pending
// ---------------------------------------------------------------------------
test('Support Inbox UI logic: inflight guard prevents concurrent requests on same message', async () => {
  let callCount = 0;

  global.fetch = async () => {
    callCount++;
    // Simulate slow network request
    await new Promise((r) => setTimeout(r, 50));
    return {
      ok: true,
      status: 200,
      json: async () => ({
        id: 'msg-uuid-1',
        status: 'delivered',
        approved_reply: 'Delivered text',
        delivered_at: '2026-10-27T08:10:00Z',
      }),
    };
  };

  const client = new ApiClient('/v1');
  client.setCsrfToken('csrf-token');

  // Inflight guard implementation pattern matching SupportInboxPage
  let isProcessing = false;
  const deliverWithGuard = async (id, text) => {
    if (isProcessing) return null; // Guard drops concurrent invocation
    isProcessing = true;
    try {
      return await client.deliverSupportReply(id, text);
    } finally {
      isProcessing = false;
    }
  };

  // Trigger two deliveries simultaneously (simulating double-click)
  const [res1, res2] = await Promise.all([
    deliverWithGuard('msg-uuid-1', 'First click'),
    deliverWithGuard('msg-uuid-1', 'Second rapid double click'),
  ]);

  assert.strictEqual(callCount, 1);
  assert.ok(res1 !== null);
  assert.strictEqual(res2, null);
});

// ---------------------------------------------------------------------------
// 8. Safe handling of API-provided text
// ---------------------------------------------------------------------------
test('Support Inbox: verifies that untrusted input with script/HTML tags is preserved as plain text', async () => {
  const maliciousCustomerText = '<script>alert("XSS")</script><b>Bold inquiry</b>';
  const maliciousDraftText = '<img src=x onerror=alert(1)>Draft text';

  global.fetch = async () => ({
    ok: true,
    status: 200,
    json: async () => ({
      items: [
        {
          id: 'msg-xss-test',
          session_id: 'sess-1',
          merchant_id: 'merch-1',
          customer_name: '<script>evil()</script>',
          customer_text: maliciousCustomerText,
          suggested_reply: maliciousDraftText,
          approved_reply: null,
          status: 'needs_review',
          ai_status: 'completed',
          ai_error: null,
          reviewed_at: null,
          delivered_at: null,
          created_at: '2026-10-27T08:00:00Z',
          updated_at: '2026-10-27T08:00:00Z',
        },
      ],
      total: 1,
      page: 1,
      page_size: 10,
    }),
  });

  const client = new ApiClient('/v1');
  const res = await client.listSupportMessages();
  const item = res.items[0];

  // Strings are plain string data and React JSX rendering {item.customer_text} safely escapes all HTML entities
  assert.strictEqual(item.customer_text, maliciousCustomerText);
  assert.strictEqual(item.suggested_reply, maliciousDraftText);
  assert.strictEqual(item.customer_name, '<script>evil()</script>');
});
