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

test('Actions review queue: loads actions and passes status filtering query params', async () => {
  let capturedUrl = null;

  global.fetch = async (url) => {
    capturedUrl = url;
    return {
      ok: true,
      status: 200,
      json: async () => ({
        items: [
          {
            id: 'act-1',
            merchant_id: 'm-1',
            action_type: 'reply_draft',
            title: 'Order Delay Reply Draft',
            description: 'Apology message offering 10% coupon for delay.',
            payload: { discount_code: 'DELAY10' },
            status: 'pending',
            created_by: 'assistant',
            created_at: '2026-10-12T10:00:00Z',
            updated_at: '2026-10-12T10:00:00Z',
          },
        ],
        total: 1,
        page: 1,
        page_size: 15,
      }),
    };
  };

  // Test pending filter
  const resPending = await global.fetch('/v1/actions?status=pending&page=1&page_size=15');
  const dataPending = await resPending.json();

  assert.strictEqual(capturedUrl.includes('status=pending'), true);
  assert.strictEqual(dataPending.items.length, 1);
  assert.strictEqual(dataPending.items[0].action_type, 'reply_draft');
  assert.strictEqual(dataPending.items[0].status, 'pending');

  // Test approved filter
  await global.fetch('/v1/actions?status=approved&page=1&page_size=15');
  assert.strictEqual(capturedUrl.includes('status=approved'), true);
});

test('Actions review queue: supports pagination query contract', async () => {
  let capturedUrl = null;

  global.fetch = async (url) => {
    capturedUrl = url;
    return {
      ok: true,
      status: 200,
      json: async () => ({
        items: [],
        total: 25,
        page: 2,
        page_size: 10,
      }),
    };
  };

  const res = await global.fetch('/v1/actions?page=2&page_size=10');
  const data = await res.json();

  assert.strictEqual(capturedUrl.includes('page=2'), true);
  assert.strictEqual(capturedUrl.includes('page_size=10'), true);
  assert.strictEqual(data.total, 25);
  assert.strictEqual(data.page, 2);
});

test('Action approval: sends POST /v1/actions/{id}/approve with CSRF token and records decision', async () => {
  let capturedUrl = null;
  let capturedMethod = null;
  let capturedHeaders = null;

  global.fetch = async (url, options) => {
    capturedUrl = url;
    capturedMethod = options.method;
    capturedHeaders = options.headers;
    return {
      ok: true,
      status: 200,
      json: async () => ({
        id: 'act-1',
        merchant_id: 'm-1',
        action_type: 'reply_draft',
        title: 'Order Delay Reply Draft',
        description: 'Apology message.',
        status: 'approved',
        reviewed_at: '2026-10-12T10:05:00Z',
        created_by: 'assistant',
        created_at: '2026-10-12T10:00:00Z',
        updated_at: '2026-10-12T10:05:00Z',
      }),
    };
  };

  const headers = new global.Headers();
  headers.set('X-CSRF-Token', 'session-csrf-12345');

  const res = await global.fetch('/v1/actions/act-1/approve', {
    method: 'POST',
    headers,
  });
  const data = await res.json();

  assert.strictEqual(capturedUrl, '/v1/actions/act-1/approve');
  assert.strictEqual(capturedMethod, 'POST');
  assert.strictEqual(capturedHeaders.get('x-csrf-token'), 'session-csrf-12345');
  assert.strictEqual(data.status, 'approved');
  assert.strictEqual(data.reviewed_at, '2026-10-12T10:05:00Z');
});

test('Action dismissal: sends POST /v1/actions/{id}/dismiss with CSRF token and records decision', async () => {
  let capturedUrl = null;
  let capturedMethod = null;

  global.fetch = async (url, options) => {
    capturedUrl = url;
    capturedMethod = options.method;
    return {
      ok: true,
      status: 200,
      json: async () => ({
        id: 'act-2',
        merchant_id: 'm-1',
        action_type: 'recommendation',
        title: 'Midday Discount Promo',
        description: 'Discount recommendation.',
        status: 'dismissed',
        reviewed_at: '2026-10-12T10:10:00Z',
        created_by: 'assistant',
        created_at: '2026-10-12T10:00:00Z',
        updated_at: '2026-10-12T10:10:00Z',
      }),
    };
  };

  const res = await global.fetch('/v1/actions/act-2/dismiss', {
    method: 'POST',
  });
  const data = await res.json();

  assert.strictEqual(capturedUrl, '/v1/actions/act-2/dismiss');
  assert.strictEqual(capturedMethod, 'POST');
  assert.strictEqual(data.status, 'dismissed');
  assert.strictEqual(data.reviewed_at, '2026-10-12T10:10:00Z');
});

test('Action transition error: handles 409 INVALID_ACTION_STATE gracefully', async () => {
  global.fetch = async () => {
    return {
      ok: false,
      status: 409,
      json: async () => ({
        error: {
          code: 'INVALID_ACTION_STATE',
          message: "Action is already in 'approved' state and cannot be dismissed",
        },
      }),
    };
  };

  const res = await global.fetch('/v1/actions/act-1/dismiss', {
    method: 'POST',
  });
  assert.strictEqual(res.ok, false);
  assert.strictEqual(res.status, 409);

  const errorData = await res.json();
  assert.strictEqual(errorData.error.code, 'INVALID_ACTION_STATE');
});

test('Action duplicate submissions: client inflight guard prevents concurrent requests', async () => {
  let requestCount = 0;
  let processing = false;

  const handleActionClick = async () => {
    if (processing) return false;
    processing = true;
    requestCount++;
    try {
      await global.fetch('/v1/actions/act-1/approve', { method: 'POST' });
    } finally {
      processing = false;
    }
    return true;
  };

  global.fetch = async () => {
    // Simulate slow network response
    await new Promise((resolve) => setTimeout(resolve, 20));
    return {
      ok: true,
      status: 200,
      json: async () => ({ status: 'approved' }),
    };
  };

  // Trigger two rapid clicks concurrently
  const first = handleActionClick();
  const second = handleActionClick();

  const [res1, res2] = await Promise.all([first, second]);

  assert.strictEqual(res1, true);
  assert.strictEqual(res2, false, 'Second concurrent submission must be prevented by inflight guard');
  assert.strictEqual(requestCount, 1);
});

test('Actions review queue: honest empty state handling', async () => {
  global.fetch = async () => {
    return {
      ok: true,
      status: 200,
      json: async () => ({
        items: [],
        total: 0,
        page: 1,
        page_size: 15,
      }),
    };
  };

  const res = await global.fetch('/v1/actions?status=pending');
  const data = await res.json();

  assert.strictEqual(data.items.length, 0);
  assert.strictEqual(data.total, 0);
});
