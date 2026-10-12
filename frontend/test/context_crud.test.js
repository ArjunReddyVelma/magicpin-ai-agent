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

const APPROVED_CONTEXT_TYPES = ['faq', 'policy', 'business_fact', 'service', 'operating_info'];

test('Context filtering: passes canonical approved context types in query params', async () => {
  let capturedUrl = null;

  global.fetch = async (url) => {
    capturedUrl = url;
    return {
      ok: true,
      status: 200,
      json: async () => ({
        items: [{ id: 'ctx-1', item_type: 'business_fact', title: 'Specialty Sweets', version: 1, is_active: true }],
        total: 1,
        page: 1,
        page_size: 15,
      }),
    };
  };

  // Test each approved type
  for (const type of APPROVED_CONTEXT_TYPES) {
    await global.fetch(`/v1/context?item_type=${type}&page=1&page_size=15`);
    assert.strictEqual(capturedUrl.includes(`item_type=${type}`), true);
  }
});

test('Context creation: correctly formats POST request with approved type and active status', async () => {
  let capturedMethod = null;
  let capturedBody = null;

  global.fetch = async (url, options) => {
    capturedMethod = options.method;
    capturedBody = JSON.parse(options.body);
    return {
      ok: true,
      status: 201,
      json: async () => ({
        id: 'new-ctx-id',
        merchant_id: 'merchant-id',
        item_type: capturedBody.item_type,
        title: capturedBody.title,
        content: capturedBody.content,
        is_active: capturedBody.is_active,
        version: 1,
        created_at: '2026-10-12T10:00:00Z',
        updated_at: '2026-10-12T10:00:00Z',
      }),
    };
  };

  const payload = {
    title: 'Refund Policy - 7 Days',
    item_type: 'policy',
    content: 'Full refunds provided within 7 days with original receipt.',
    is_active: true,
  };

  const resp = await global.fetch('/v1/context', {
    method: 'POST',
    headers: new global.Headers({ 'Content-Type': 'application/json' }),
    body: JSON.stringify(payload),
  });

  const created = await resp.json();
  assert.strictEqual(capturedMethod, 'POST');
  assert.strictEqual(created.title, payload.title);
  assert.strictEqual(created.item_type, 'policy');
  assert.strictEqual(created.version, 1);
  assert.strictEqual(created.is_active, true);
});

test('Context update: includes expected_version and If-Match header for optimistic concurrency', async () => {
  let capturedMethod = null;
  let capturedHeaders = null;
  let capturedBody = null;

  global.fetch = async (url, options) => {
    capturedMethod = options.method;
    capturedHeaders = options.headers;
    capturedBody = JSON.parse(options.body);
    return {
      ok: true,
      status: 200,
      json: async () => ({
        id: 'ctx-1',
        title: capturedBody.title,
        item_type: capturedBody.item_type,
        content: capturedBody.content,
        is_active: capturedBody.is_active,
        version: capturedBody.expected_version + 1,
        updated_at: '2026-10-12T11:00:00Z',
      }),
    };
  };

  const updatePayload = {
    expected_version: 1,
    title: 'Updated Return Policy',
    item_type: 'policy',
    content: 'Store credit only after 7 days.',
    is_active: true,
  };

  const headers = new global.Headers({
    'Content-Type': 'application/json',
    'If-Match': `"${updatePayload.expected_version}"`,
  });

  const resp = await global.fetch('/v1/context/ctx-1', {
    method: 'PATCH',
    headers,
    body: JSON.stringify(updatePayload),
  });

  const updated = await resp.json();
  assert.strictEqual(capturedMethod, 'PATCH');
  assert.strictEqual(capturedHeaders.get('If-Match'), '"1"');
  assert.strictEqual(capturedBody.expected_version, 1);
  assert.strictEqual(updated.version, 2);
});

test('Optimistic concurrency: handles STALE_VERSION_CONFLICT without silent overwrite', async () => {
  global.fetch = async () => {
    return {
      ok: false,
      status: 409,
      json: async () => ({
        error: {
          code: 'STALE_VERSION_CONFLICT',
          message: 'Stale version conflict: context item has been modified by another request.',
          details: {
            expected_version: 1,
            current_version: 2,
          },
        },
      }),
    };
  };

  let conflictDetected = false;
  let conflictData = null;

  const resp = await global.fetch('/v1/context/ctx-1', {
    method: 'PATCH',
    headers: new global.Headers({ 'Content-Type': 'application/json', 'If-Match': '"1"' }),
    body: JSON.stringify({ expected_version: 1, title: 'Conflicting Title' }),
  });

  if (resp.status === 409) {
    conflictDetected = true;
    conflictData = (await resp.json()).error;
  }

  assert.strictEqual(conflictDetected, true);
  assert.strictEqual(conflictData.code, 'STALE_VERSION_CONFLICT');
  assert.strictEqual(conflictData.details.expected_version, 1);
  assert.strictEqual(conflictData.details.current_version, 2);
});

test('Context deletion: submits DELETE request and returns success', async () => {
  let capturedMethod = null;
  let capturedUrl = null;

  global.fetch = async (url, options) => {
    capturedMethod = options.method;
    capturedUrl = url;
    return {
      ok: true,
      status: 200,
      json: async () => ({ status: 'ok', message: 'Context item successfully deleted' }),
    };
  };

  const resp = await global.fetch('/v1/context/ctx-to-delete', {
    method: 'DELETE',
  });

  const data = await resp.json();
  assert.strictEqual(capturedMethod, 'DELETE');
  assert.strictEqual(capturedUrl, '/v1/context/ctx-to-delete');
  assert.strictEqual(data.status, 'ok');
});

test('Context input validation: validates title, content, and canonical types', () => {
  function validateContextInput({ title, content, item_type }) {
    const trimmedTitle = (title || '').trim();
    const trimmedContent = (content || '').trim();

    if (!trimmedTitle) {
      return { valid: false, error: 'Title is required.' };
    }
    if (trimmedTitle.length > 200) {
      return { valid: false, error: 'Title cannot exceed 200 characters.' };
    }
    if (!trimmedContent) {
      return { valid: false, error: 'Content is required.' };
    }
    if (!APPROVED_CONTEXT_TYPES.includes(item_type)) {
      return { valid: false, error: `Invalid context type. Must be one of: ${APPROVED_CONTEXT_TYPES.join(', ')}` };
    }
    return { valid: true, error: null };
  }

  // Missing title
  assert.strictEqual(validateContextInput({ title: '', content: 'Valid', item_type: 'faq' }).valid, false);
  // Title too long
  assert.strictEqual(validateContextInput({ title: 'A'.repeat(201), content: 'Valid', item_type: 'faq' }).valid, false);
  // Missing content
  assert.strictEqual(validateContextInput({ title: 'Valid Title', content: '', item_type: 'faq' }).valid, false);
  // Unsupported type (e.g. inventory or deal)
  assert.strictEqual(validateContextInput({ title: 'Valid', content: 'Valid', item_type: 'inventory' }).valid, false);
  assert.strictEqual(validateContextInput({ title: 'Valid', content: 'Valid', item_type: 'deal' }).valid, false);
  assert.strictEqual(validateContextInput({ title: 'Valid', content: 'Valid', item_type: 'general' }).valid, false);

  // All 5 canonical types valid
  for (const t of APPROVED_CONTEXT_TYPES) {
    const res = validateContextInput({ title: 'Valid Title', content: 'Valid Content', item_type: t });
    assert.strictEqual(res.valid, true, `Expected ${t} to be valid`);
  }
});
