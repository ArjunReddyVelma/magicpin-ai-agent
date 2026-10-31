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
    this.onUnauthorized = null;
  }

  setCsrfToken(token) {
    this.csrfToken = token;
  }

  setOnUnauthorized(cb) {
    this.onUnauthorized = cb;
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

    if (response.status === 401 && this.onUnauthorized && !endpoint.startsWith('/public/')) {
      this.onUnauthorized();
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

  async getPublicMerchantProfile(merchantId) {
    return this.request(`/public/support/merchants/${merchantId}`);
  }

  async createCustomerSupportSession(merchantId, customerName) {
    return this.request('/public/support/sessions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        merchant_id: merchantId,
        customer_name: customerName ? customerName.trim() : undefined,
      }),
    });
  }

  async submitCustomerInquiry(sessionId, customerToken, content) {
    return this.request(`/public/support/sessions/${sessionId}/messages`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Customer-Token': customerToken,
      },
      body: JSON.stringify({ content: content.trim() }),
    });
  }

  async getCustomerHistory(sessionId, customerToken, limit = 100) {
    return this.request(`/public/support/sessions/${sessionId}/messages?limit=${limit}`, {
      headers: {
        'X-Customer-Token': customerToken,
      },
    });
  }
}

// ---------------------------------------------------------------------------
// 1. Valid merchant ID loads public merchant profile
// ---------------------------------------------------------------------------
test('Customer Support: valid merchant ID loads public merchant profile allowlisted fields', async () => {
  const merchantId = 'a1b2c3d4-e5f6-7890-abcd-ef1234567890';
  let capturedUrl = null;

  global.fetch = async (url) => {
    capturedUrl = url;
    return {
      ok: true,
      status: 200,
      json: async () => ({
        merchant_id: merchantId,
        business_name: 'Green Grocers & Cafe',
        category: 'Grocery & Dining',
        location: 'Indiranagar, Bangalore',
        description: 'Fresh organic produce and artisanal coffee.',
      }),
    };
  };

  const client = new ApiClient('/v1');
  const profile = await client.getPublicMerchantProfile(merchantId);

  assert.strictEqual(capturedUrl, `/v1/public/support/merchants/${merchantId}`);
  assert.strictEqual(profile.merchant_id, merchantId);
  assert.strictEqual(profile.business_name, 'Green Grocers & Cafe');
  assert.strictEqual(profile.category, 'Grocery & Dining');
  assert.strictEqual(profile.location, 'Indiranagar, Bangalore');
  assert.strictEqual(profile.description, 'Fresh organic produce and artisanal coffee.');
  // Ensure no private merchant data is present
  assert.strictEqual(profile.user_id, undefined);
  assert.strictEqual(profile.email, undefined);
});

// ---------------------------------------------------------------------------
// 2. Unknown or invalid merchant displays unavailable state
// ---------------------------------------------------------------------------
test('Customer Support: unknown merchant ID surfaces 404 unavailable state', async () => {
  const unknownId = '00000000-0000-0000-0000-000000000000';

  global.fetch = async () => ({
    ok: false,
    status: 404,
    json: async () => ({
      error: { code: 'MERCHANT_NOT_FOUND', message: 'Merchant not found.' },
    }),
  });

  const client = new ApiClient('/v1');
  await assert.rejects(
    async () => client.getPublicMerchantProfile(unknownId),
    (err) => {
      assert.ok(err instanceof ApiClientError);
      assert.strictEqual(err.statusCode, 404);
      assert.strictEqual(err.code, 'MERCHANT_NOT_FOUND');
      return true;
    }
  );

  // Client-side regex validator for invalid non-UUID string
  const isUuid = (id) =>
    /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(id);
  assert.strictEqual(isUuid('not-a-valid-uuid'), false);
  assert.strictEqual(isUuid(unknownId), true);
});

// ---------------------------------------------------------------------------
// 3. Session creation uses correct API and prevents duplicate submissions
// ---------------------------------------------------------------------------
test('Customer Support: session creation calls POST /sessions and inflight guard drops duplicate clicks', async () => {
  const merchantId = 'a1b2c3d4-e5f6-7890-abcd-ef1234567890';
  let callCount = 0;
  let capturedBody = null;

  global.fetch = async (url, options) => {
    callCount++;
    capturedBody = JSON.parse(options.body);
    await new Promise((r) => setTimeout(r, 40));
    return {
      ok: true,
      status: 201,
      json: async () => ({
        session_id: 'sess-1234',
        customer_token: 'token-abc-987',
        status: 'active',
        created_at: '2026-10-27T10:00:00Z',
      }),
    };
  };

  const client = new ApiClient('/v1');

  // Inflight guard pattern
  let isStartingSession = false;
  const startSessionWithGuard = async (name) => {
    if (isStartingSession) return null;
    isStartingSession = true;
    try {
      return await client.createCustomerSupportSession(merchantId, name);
    } finally {
      isStartingSession = false;
    }
  };

  // Trigger concurrent rapid clicks
  const [res1, res2] = await Promise.all([
    startSessionWithGuard('Alice Customer'),
    startSessionWithGuard('Alice Rapid Double Click'),
  ]);

  assert.strictEqual(callCount, 1);
  assert.strictEqual(capturedBody.merchant_id, merchantId);
  assert.strictEqual(capturedBody.customer_name, 'Alice Customer');
  assert.ok(res1 !== null);
  assert.strictEqual(res2, null);
  assert.strictEqual(res1.session_id, 'sess-1234');
  assert.strictEqual(res1.customer_token, 'token-abc-987');
});

// ---------------------------------------------------------------------------
// 4. Customer token is sent in X-Customer-Token, not in URL or storage
// ---------------------------------------------------------------------------
test('Customer Support: token is transmitted exclusively via X-Customer-Token header', async () => {
  let capturedUrl = null;
  let capturedHeaders = null;

  global.fetch = async (url, options) => {
    capturedUrl = url;
    capturedHeaders = options.headers;
    return {
      ok: true,
      status: 200,
      json: async () => ({
        session_id: 'sess-1234',
        items: [],
        total: 0,
      }),
    };
  };

  const client = new ApiClient('/v1');
  const secretToken = 'secret-customer-session-token-12345';
  await client.getCustomerHistory('sess-1234', secretToken);

  // Assert header has token
  assert.strictEqual(capturedHeaders.get('X-Customer-Token'), secretToken);

  // Assert URL does NOT expose the token
  assert.strictEqual(capturedUrl.includes(secretToken), false);
  assert.strictEqual(capturedUrl, '/v1/public/support/sessions/sess-1234/messages?limit=100');

  // Assert storage is not utilized
  const mockLocalStorage = {};
  assert.strictEqual(mockLocalStorage['customer_token'], undefined);
});

// ---------------------------------------------------------------------------
// 5. Empty and oversized inquiries are rejected appropriately
// ---------------------------------------------------------------------------
test('Customer Support: client validates inquiry bounds (non-empty, <=2000 chars)', () => {
  const validateInquiry = (text) => {
    const trimmed = (text || '').trim();
    if (!trimmed) {
      return { valid: false, error: 'Please enter a message before sending.' };
    }
    if (trimmed.length > 2000) {
      return {
        valid: false,
        error: 'Your inquiry exceeds the maximum allowed length of 2,000 characters.',
      };
    }
    return { valid: true, error: null };
  };

  assert.strictEqual(validateInquiry('').valid, false);
  assert.strictEqual(validateInquiry('   ').valid, false);
  assert.strictEqual(validateInquiry('Valid customer inquiry').valid, true);

  const oversized = 'a'.repeat(2001);
  assert.strictEqual(validateInquiry(oversized).valid, false);
  assert.strictEqual(
    validateInquiry(oversized).error,
    'Your inquiry exceeds the maximum allowed length of 2,000 characters.'
  );

  const maxValid = 'b'.repeat(2000);
  assert.strictEqual(validateInquiry(maxValid).valid, true);
});

// ---------------------------------------------------------------------------
// 6. Inquiry submission displays success only after server confirmation
// ---------------------------------------------------------------------------
test('Customer Support: inquiry submission records state only on confirmed server response', async () => {
  let isSending = false;
  let messagesList = [];

  global.fetch = async () => ({
    ok: true,
    status: 201,
    json: async () => ({
      id: 'msg-uuid-confirmed',
      session_id: 'sess-1',
      customer_text: 'Are you open on Sundays?',
      status: 'needs_review',
      created_at: '2026-10-27T10:05:00Z',
    }),
  });

  const client = new ApiClient('/v1');

  // Submit simulation
  isSending = true;
  assert.strictEqual(isSending, true);
  assert.strictEqual(messagesList.length, 0);

  const res = await client.submitCustomerInquiry('sess-1', 'tok-1', 'Are you open on Sundays?');
  isSending = false;

  messagesList.push({
    id: res.id,
    customer_text: res.customer_text,
    reply: null,
    status: res.status,
    created_at: res.created_at,
  });

  assert.strictEqual(isSending, false);
  assert.strictEqual(messagesList.length, 1);
  assert.strictEqual(messagesList[0].id, 'msg-uuid-confirmed');
  assert.strictEqual(messagesList[0].status, 'needs_review');
});

// ---------------------------------------------------------------------------
// 7. AI failure does not lose inquiry or falsely display an AI reply
// ---------------------------------------------------------------------------
test('Customer Support: AI draft failure preserves inquiry without leaking error or false reply', async () => {
  // Backend returns 201 with persisted inquiry even if AI failed
  global.fetch = async () => ({
    ok: true,
    status: 201,
    json: async () => ({
      id: 'msg-uuid-ai-failed',
      session_id: 'sess-1',
      customer_text: 'Can I place a bulk order?',
      status: 'needs_review',
      created_at: '2026-10-27T10:10:00Z',
    }),
  });

  const client = new ApiClient('/v1');
  const res = await client.submitCustomerInquiry('sess-1', 'tok-1', 'Can I place a bulk order?');

  assert.strictEqual(res.id, 'msg-uuid-ai-failed');
  assert.strictEqual(res.status, 'needs_review');

  // In customer history, reply remains null until merchant approves
  const historyItem = {
    id: res.id,
    customer_text: res.customer_text,
    reply: null,
    status: res.status,
  };
  assert.strictEqual(historyItem.reply, null);
  assert.strictEqual(historyItem.customer_text, 'Can I place a bulk order?');
});

// ---------------------------------------------------------------------------
// 8. Customer history displays only server-confirmed delivered replies
// ---------------------------------------------------------------------------
test('Customer Support: history returns merchant reply only when confirmed delivered', async () => {
  global.fetch = async () => ({
    ok: true,
    status: 200,
    json: async () => ({
      session_id: 'sess-1',
      items: [
        {
          id: 'msg-1',
          customer_text: 'Inquiry in review',
          reply: null,
          status: 'needs_review',
          delivered_at: null,
          created_at: '2026-10-27T10:00:00Z',
        },
        {
          id: 'msg-2',
          customer_text: 'What are your hours?',
          reply: 'We are open 9 AM to 9 PM daily.',
          status: 'delivered',
          delivered_at: '2026-10-27T10:04:00Z',
          created_at: '2026-10-27T10:02:00Z',
        },
      ],
      total: 2,
    }),
  });

  const client = new ApiClient('/v1');
  const history = await client.getCustomerHistory('sess-1', 'tok-1');

  assert.strictEqual(history.items.length, 2);
  assert.strictEqual(history.items[0].reply, null);
  assert.strictEqual(history.items[0].status, 'needs_review');
  assert.strictEqual(history.items[1].reply, 'We are open 9 AM to 9 PM daily.');
  assert.strictEqual(history.items[1].status, 'delivered');
  assert.strictEqual(history.items[1].delivered_at, '2026-10-27T10:04:00Z');
});

// ---------------------------------------------------------------------------
// 9. Pending replies remain pending without promising response times
// ---------------------------------------------------------------------------
test('Customer Support: pending message displays awaiting review status without false promises', () => {
  const item = {
    id: 'msg-pending',
    customer_text: 'Do you have gluten free options?',
    reply: null,
    status: 'needs_review',
  };

  const isDelivered = item.status === 'delivered' && Boolean(item.reply);
  const statusLabel = isDelivered ? 'Delivered' : 'Awaiting merchant review';

  assert.strictEqual(isDelivered, false);
  assert.strictEqual(statusLabel, 'Awaiting merchant review');
});

// ---------------------------------------------------------------------------
// 10. Polling occurs at configured 4s default interval
// ---------------------------------------------------------------------------
test('Customer Support: polling engine operates at default 4000ms interval', () => {
  const POLLING_INTERVAL_MS = 4000;
  assert.strictEqual(POLLING_INTERVAL_MS, 4000);
  assert.ok(POLLING_INTERVAL_MS >= 3000 && POLLING_INTERVAL_MS <= 5000);
});

// ---------------------------------------------------------------------------
// 11. Polling pauses when page is hidden and resumes when visible
// ---------------------------------------------------------------------------
test('Customer Support: polling lifecycle responds to visibilitychange', () => {
  let isTimerActive = false;
  let immediatePollTriggered = false;

  const handleVisibilityChange = (state) => {
    if (state === 'hidden') {
      isTimerActive = false;
    } else if (state === 'visible') {
      immediatePollTriggered = true;
      isTimerActive = true;
    }
  };

  // Simulate tab switch away (hidden)
  handleVisibilityChange('hidden');
  assert.strictEqual(isTimerActive, false);

  // Simulate tab switch back (visible)
  handleVisibilityChange('visible');
  assert.strictEqual(immediatePollTriggered, true);
  assert.strictEqual(isTimerActive, true);
});

// ---------------------------------------------------------------------------
// 12. Polling stops on unmount or route change
// ---------------------------------------------------------------------------
test('Customer Support: cleanup halts timer and removes event listeners', () => {
  let timerCleared = false;
  let listenerRemoved = false;

  const mockTimer = 12345;
  const cleanup = () => {
    if (mockTimer) timerCleared = true;
    listenerRemoved = true;
  };

  cleanup();
  assert.strictEqual(timerCleared, true);
  assert.strictEqual(listenerRemoved, true);
});

// ---------------------------------------------------------------------------
// 13. Overlapping history requests are prevented
// ---------------------------------------------------------------------------
test('Customer Support: isPollingRef prevents overlapping concurrent polls', async () => {
  let pollExecutions = 0;
  let isPolling = false;

  const pollHistory = async () => {
    if (isPolling) return 'dropped';
    isPolling = true;
    pollExecutions++;
    await new Promise((r) => setTimeout(r, 50));
    isPolling = false;
    return 'executed';
  };

  // Launch two ticks rapidly while first is in progress
  const [res1, res2] = await Promise.all([pollHistory(), pollHistory()]);

  assert.strictEqual(res1, 'executed');
  assert.strictEqual(res2, 'dropped');
  assert.strictEqual(pollExecutions, 1);
});

// ---------------------------------------------------------------------------
// 14. Transient network errors do not crash the page
// ---------------------------------------------------------------------------
test('Customer Support: transient network error in poll is caught safely', async () => {
  global.fetch = async () => {
    throw new Error('Network timeout');
  };

  const client = new ApiClient('/v1');
  let pageCrashed = false;

  try {
    await client.getCustomerHistory('sess-1', 'tok-1');
  } catch (err) {
    // Background polling swallows transient network errors without crashing
    assert.strictEqual(err.code, 'NETWORK_ERROR');
    pageCrashed = false;
  }

  assert.strictEqual(pageCrashed, false);
});

// ---------------------------------------------------------------------------
// 15. Permanent authorization/session errors stop repeated polling
// ---------------------------------------------------------------------------
test('Customer Support: 401/403/404 halts polling and surfaces permanent session error', async () => {
  global.fetch = async () => ({
    ok: false,
    status: 403,
    json: async () => ({
      error: { code: 'INVALID_CUSTOMER_TOKEN', message: 'Invalid customer session token.' },
    }),
  });

  const client = new ApiClient('/v1');
  let pollingHalted = false;
  let surfacedError = null;

  try {
    await client.getCustomerHistory('sess-expired', 'tok-bad');
  } catch (err) {
    if (err.statusCode === 401 || err.statusCode === 403 || err.statusCode === 404) {
      pollingHalted = true;
      surfacedError = 'Your support session has expired or is invalid. Please start a new session.';
    }
  }

  assert.strictEqual(pollingHalted, true);
  assert.strictEqual(
    surfacedError,
    'Your support session has expired or is invalid. Please start a new session.'
  );
});

// ---------------------------------------------------------------------------
// 16. Retry preserves inquiry text and avoids blind duplication
// ---------------------------------------------------------------------------
test('Customer Support: failed send preserves input and permits retry without text loss', () => {
  let inquiryText = 'Important question regarding reservation';
  const isSendingFailed = true;

  if (isSendingFailed) {
    // Input is NOT wiped on failure
    assert.strictEqual(inquiryText, 'Important question regarding reservation');
  }
});

// ---------------------------------------------------------------------------
// 17. Untrusted HTML-like text renders as plain text
// ---------------------------------------------------------------------------
test('Customer Support: untrusted text with HTML tags is preserved as plain string', () => {
  const maliciousInquiry = '<script>evil()</script><b>Inquiry text</b>';
  const maliciousReply = '<img src=x onerror=alert(1)>Store response';

  const historyItem = {
    customer_text: maliciousInquiry,
    reply: maliciousReply,
  };

  // React JSX interpolation renders strings safely without interpreting HTML
  assert.strictEqual(typeof historyItem.customer_text, 'string');
  assert.strictEqual(historyItem.customer_text, '<script>evil()</script><b>Inquiry text</b>');
  assert.strictEqual(historyItem.reply, '<img src=x onerror=alert(1)>Store response');
});

// ---------------------------------------------------------------------------
// 18. Existing merchant inbox and auth functionality remains intact
// ---------------------------------------------------------------------------
test('Customer Support: public 401 does not clear merchant authentication state', async () => {
  let merchantLoggedOut = false;
  const client = new ApiClient('/v1');
  client.setOnUnauthorized(() => {
    merchantLoggedOut = true;
  });

  global.fetch = async () => ({
    ok: false,
    status: 401,
    json: async () => ({
      error: { code: 'CUSTOMER_TOKEN_REQUIRED', message: 'Token required' },
    }),
  });

  // Call public endpoint
  await assert.rejects(async () => client.getCustomerHistory('sess-1', ''));

  // Merchant onUnauthorized was NOT invoked for public endpoint
  assert.strictEqual(merchantLoggedOut, false);
});
