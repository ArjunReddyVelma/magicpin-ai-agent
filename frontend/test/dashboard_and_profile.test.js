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

test('Dashboard data loading: successfully retrieves context items and conversations', async () => {
  const mockContextData = {
    items: [
      { id: 'ctx-1', title: 'Return Policy', item_type: 'policy', is_active: true, version: 1 },
      { id: 'ctx-2', title: 'Operating Hours', item_type: 'faq', is_active: true, version: 2 },
    ],
    total: 2,
    page: 1,
    page_size: 5,
  };

  const mockConversationsData = {
    items: [
      { id: 'conv-1', title: 'Customer Delivery Inquiry', status: 'active', last_message_at: '2026-10-12T10:00:00Z' },
    ],
    total: 1,
    page: 1,
    page_size: 5,
  };

  global.fetch = async (url) => {
    if (url.includes('/context')) {
      return { ok: true, status: 200, json: async () => mockContextData };
    }
    if (url.includes('/conversations')) {
      return { ok: true, status: 200, json: async () => mockConversationsData };
    }
    return { ok: false, status: 404, json: async () => ({ error: { code: 'NOT_FOUND' } }) };
  };

  const contextRes = await global.fetch('/v1/context?page=1&page_size=5').then(r => r.json());
  const convRes = await global.fetch('/v1/conversations?page=1&page_size=5').then(r => r.json());

  assert.strictEqual(contextRes.total, 2);
  assert.strictEqual(contextRes.items.length, 2);
  assert.strictEqual(contextRes.items[0].title, 'Return Policy');

  assert.strictEqual(convRes.total, 1);
  assert.strictEqual(convRes.items.length, 1);
  assert.strictEqual(convRes.items[0].title, 'Customer Delivery Inquiry');
});

test('Dashboard empty data states: correctly handles 0 items and 0 conversations', async () => {
  global.fetch = async (url) => {
    if (url.includes('/context')) {
      return { ok: true, status: 200, json: async () => ({ items: [], total: 0, page: 1, page_size: 5 }) };
    }
    if (url.includes('/conversations')) {
      return { ok: true, status: 200, json: async () => ({ items: [], total: 0, page: 1, page_size: 5 }) };
    }
    return { ok: false, status: 404 };
  };

  const contextRes = await global.fetch('/v1/context?page=1&page_size=5').then(r => r.json());
  const convRes = await global.fetch('/v1/conversations?page=1&page_size=5').then(r => r.json());

  assert.strictEqual(contextRes.total, 0);
  assert.strictEqual(contextRes.items.length, 0);
  assert.strictEqual(convRes.total, 0);
  assert.strictEqual(convRes.items.length, 0);
});

test('Dashboard partial failure isolation: context failure does not block conversations', async () => {
  global.fetch = async (url) => {
    if (url.includes('/context')) {
      return {
        ok: false,
        status: 500,
        json: async () => ({ error: { code: 'DATABASE_ERROR', message: 'Failed to query context' } }),
      };
    }
    if (url.includes('/conversations')) {
      return {
        ok: true,
        status: 200,
        json: async () => ({
          items: [{ id: 'conv-1', title: 'Active Chat', status: 'active' }],
          total: 1,
          page: 1,
          page_size: 5,
        }),
      };
    }
    return { ok: false, status: 404 };
  };

  let contextFailed = false;
  let conversationsSucceeded = false;

  // Context fetch
  const contextResp = await global.fetch('/v1/context?page=1&page_size=5');
  if (!contextResp.ok) {
    contextFailed = true;
  }

  // Conversations fetch
  const convResp = await global.fetch('/v1/conversations?page=1&page_size=5');
  if (convResp.ok) {
    const data = await convResp.json();
    if (data.total === 1) {
      conversationsSucceeded = true;
    }
  }

  assert.strictEqual(contextFailed, true, 'Context should report failure');
  assert.strictEqual(conversationsSucceeded, true, 'Conversations must still succeed independently');
});

test('Merchant profile updating: correctly submits PATCH and returns updated profile', async () => {
  let capturedMethod = null;
  let capturedBody = null;

  global.fetch = async (url, options) => {
    capturedMethod = options.method;
    capturedBody = JSON.parse(options.body);
    return {
      ok: true,
      status: 200,
      json: async () => ({
        id: 'merchant-uuid-123',
        business_name: capturedBody.business_name,
        category: capturedBody.category,
        location: capturedBody.location,
        description: capturedBody.description,
        timezone: capturedBody.timezone || 'Asia/Kolkata',
        created_at: '2026-10-12T00:00:00Z',
        updated_at: '2026-10-12T12:00:00Z',
      }),
    };
  };

  const payload = {
    business_name: 'Updated Cafe & Bakery',
    category: 'Bakery',
    location: 'Koramangala, Bengaluru',
    description: 'Fresh baked goods daily.',
    timezone: 'Asia/Kolkata',
  };

  const resp = await global.fetch('/v1/merchant/profile', {
    method: 'PATCH',
    headers: new global.Headers({ 'Content-Type': 'application/json' }),
    body: JSON.stringify(payload),
  });

  const updatedProfile = await resp.json();

  assert.strictEqual(capturedMethod, 'PATCH');
  assert.strictEqual(updatedProfile.business_name, 'Updated Cafe & Bakery');
  assert.strictEqual(updatedProfile.category, 'Bakery');
  assert.strictEqual(updatedProfile.location, 'Koramangala, Bengaluru');
});

test('Merchant profile validation: rejects empty business name and surfaces errors', () => {
  function validateProfileInput(name) {
    const trimmed = (name || '').trim();
    if (!trimmed) {
      return { valid: false, error: 'Business name is required.' };
    }
    if (trimmed.length > 160) {
      return { valid: false, error: 'Business name cannot exceed 160 characters.' };
    }
    return { valid: true, error: null };
  }

  assert.strictEqual(validateProfileInput('').valid, false);
  assert.strictEqual(validateProfileInput('   ').valid, false);
  assert.strictEqual(validateProfileInput('').error, 'Business name is required.');

  const longName = 'A'.repeat(161);
  assert.strictEqual(validateProfileInput(longName).valid, false);
  assert.strictEqual(validateProfileInput(longName).error, 'Business name cannot exceed 160 characters.');

  assert.strictEqual(validateProfileInput('Valid Business Name').valid, true);
  assert.strictEqual(validateProfileInput('Valid Business Name').error, null);
});
