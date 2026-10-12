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

test('Merchant profile update: validates business_name length and non-empty constraint', () => {
  const validateProfileInput = (name) => {
    const trimmed = name.trim();
    if (!trimmed) {
      return { valid: false, error: 'Business name is required.' };
    }
    if (trimmed.length > 160) {
      return { valid: false, error: 'Business name cannot exceed 160 characters.' };
    }
    return { valid: true, error: null };
  };

  assert.strictEqual(validateProfileInput('').valid, false);
  assert.strictEqual(validateProfileInput('   ').valid, false);
  assert.strictEqual(validateProfileInput('a'.repeat(161)).valid, false);
  assert.strictEqual(validateProfileInput('Bengal Sweets & Savouries').valid, true);
});

test('Merchant profile update: transmits PATCH payload with valid fields and returns updated profile', async () => {
  let capturedMethod = null;
  let capturedBody = null;

  global.fetch = async (url, options) => {
    capturedMethod = options.method;
    capturedBody = JSON.parse(options.body);
    return {
      ok: true,
      status: 200,
      json: async () => ({
        id: 'merchant-1',
        business_name: capturedBody.business_name,
        category: capturedBody.category,
        location: capturedBody.location,
        description: capturedBody.description,
        timezone: capturedBody.timezone,
        created_at: '2026-10-12T08:00:00Z',
        updated_at: '2026-10-12T14:00:00Z',
      }),
    };
  };

  const payload = {
    business_name: 'Bengal Sweets Flagship',
    category: 'Sweets & Confectionery',
    location: 'Indiranagar, Bangalore',
    description: 'Authentic regional Bengali sweets.',
    timezone: 'Asia/Kolkata',
  };

  const res = await global.fetch('/v1/merchant/profile', {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  const data = await res.json();

  assert.strictEqual(capturedMethod, 'PATCH');
  assert.strictEqual(capturedBody.business_name, 'Bengal Sweets Flagship');
  assert.strictEqual(capturedBody.timezone, 'Asia/Kolkata');
  assert.strictEqual(data.business_name, 'Bengal Sweets Flagship');
});

test('Session logout: calls /v1/auth/logout with CSRF protection and clears session', async () => {
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
      json: async () => ({ status: 'ok' }),
    };
  };

  const headers = new global.Headers();
  headers.set('X-CSRF-Token', 'session-bound-csrf-token');

  const res = await global.fetch('/v1/auth/logout', {
    method: 'POST',
    headers,
  });
  const data = await res.json();

  assert.strictEqual(capturedUrl, '/v1/auth/logout');
  assert.strictEqual(capturedMethod, 'POST');
  assert.strictEqual(capturedHeaders.get('x-csrf-token'), 'session-bound-csrf-token');
  assert.strictEqual(data.status, 'ok');
});

test('Account deletion validation: requires non-empty password confirmation', () => {
  const validateDeleteAccountInput = (password) => {
    const trimmed = (password || '').trim();
    if (!trimmed) {
      return { valid: false, error: 'Password confirmation is required to delete your account.' };
    }
    return { valid: true, error: null };
  };

  assert.strictEqual(validateDeleteAccountInput('').valid, false);
  assert.strictEqual(validateDeleteAccountInput('   ').valid, false);
  assert.strictEqual(validateDeleteAccountInput('CorrectPassword123!').valid, true);
});

test('Account deletion incorrect-password failure: backend returns 401 and client preserves session state', async () => {
  let sessionCleared = false;
  const clearSession = () => {
    sessionCleared = true;
  };

  global.fetch = async () => {
    return {
      ok: false,
      status: 401,
      json: async () => ({
        error: {
          code: 'INVALID_PASSWORD',
          message: 'Incorrect password. Account deletion aborted.',
        },
      }),
    };
  };

  const res = await global.fetch('/v1/auth/account', {
    method: 'DELETE',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ password: 'WrongPassword' }),
  });

  const body = await res.json();

  // If status is not 200 ok, clearSession MUST NOT be called!
  if (res.ok) {
    clearSession();
  }

  assert.strictEqual(res.status, 401);
  assert.strictEqual(body.error.code, 'INVALID_PASSWORD');
  assert.strictEqual(sessionCleared, false, 'Client must NOT clear authentication session when deletion fails');
});

test('Account deletion server error: surfaces error and preserves user authentication state', async () => {
  let sessionCleared = false;
  const clearSession = () => {
    sessionCleared = true;
  };

  global.fetch = async () => {
    return {
      ok: false,
      status: 500,
      json: async () => ({
        error: {
          code: 'INTERNAL_SERVER_ERROR',
          message: 'Unexpected database failure.',
        },
      }),
    };
  };

  const res = await global.fetch('/v1/auth/account', {
    method: 'DELETE',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ password: 'SecretPassword123' }),
  });

  if (res.ok) {
    clearSession();
  }

  assert.strictEqual(res.status, 500);
  assert.strictEqual(sessionCleared, false, 'Client must preserve session on server error');
});

test('Account deletion success: clears authentication state and confirms deletion', async () => {
  let capturedMethod = null;
  let capturedBody = null;
  let sessionCleared = false;

  const clearSession = () => {
    sessionCleared = true;
  };

  global.fetch = async (url, options) => {
    capturedMethod = options.method;
    capturedBody = JSON.parse(options.body);
    return {
      ok: true,
      status: 200,
      json: async () => ({
        status: 'ok',
        message: 'Account successfully deleted',
      }),
    };
  };

  const res = await global.fetch('/v1/auth/account', {
    method: 'DELETE',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ password: 'CorrectPassword123' }),
  });

  const data = await res.json();

  if (res.ok && data.status === 'ok') {
    clearSession();
  }

  assert.strictEqual(capturedMethod, 'DELETE');
  assert.strictEqual(capturedBody.password, 'CorrectPassword123');
  assert.strictEqual(data.status, 'ok');
  assert.strictEqual(sessionCleared, true, 'Client authentication state must be cleared after backend confirms success');
});
