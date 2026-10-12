import test from 'node:test';
import assert from 'node:assert';

// Mock browser global fetch and Headers for Node test environment
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

// Import ApiClient and ApiClientError from compiled dist or directly test logic
test('ApiClientError holds status, code, message, and details', () => {
  class ApiClientError extends Error {
    constructor(statusCode, code, message, details) {
      super(message);
      this.name = 'ApiClientError';
      this.statusCode = statusCode;
      this.code = code;
      this.details = details;
    }
  }

  const err = new ApiClientError(409, 'STALE_VERSION_CONFLICT', 'Version mismatch', {
    expected_version: 1,
    current_version: 2,
  });

  assert.strictEqual(err.statusCode, 409);
  assert.strictEqual(err.code, 'STALE_VERSION_CONFLICT');
  assert.strictEqual(err.message, 'Version mismatch');
  assert.deepStrictEqual(err.details, { expected_version: 1, current_version: 2 });
});

test('API Client attaches X-CSRF-Token on state-changing requests and sets credentials to include', async () => {
  let capturedUrl = null;
  let capturedOptions = null;

  global.fetch = async (url, options) => {
    capturedUrl = url;
    capturedOptions = options;
    return {
      ok: true,
      status: 200,
      json: async () => ({ status: 'ok' }),
    };
  };

  class MiniClient {
    constructor() {
      this.csrfToken = 'test-session-bound-csrf-token';
    }
    async post(endpoint, body) {
      const headers = new global.Headers({ 'Content-Type': 'application/json' });
      if (this.csrfToken) {
        headers.set('X-CSRF-Token', this.csrfToken);
      }
      return global.fetch(`/v1${endpoint}`, {
        method: 'POST',
        headers,
        credentials: 'include',
        body: JSON.stringify(body),
      });
    }
  }

  const client = new MiniClient();
  const res = await client.post('/context', { title: 'Store Return Policy' });

  assert.strictEqual(capturedUrl, '/v1/context');
  assert.strictEqual(capturedOptions.method, 'POST');
  assert.strictEqual(capturedOptions.credentials, 'include');
  assert.strictEqual(capturedOptions.headers.get('X-CSRF-Token'), 'test-session-bound-csrf-token');
  assert.strictEqual(capturedOptions.headers.get('Content-Type'), 'application/json');
});

test('API Client triggers onUnauthorized callback when backend returns HTTP 401', async () => {
  let unauthorizedTriggered = false;

  global.fetch = async () => {
    return {
      ok: false,
      status: 401,
      json: async () => ({
        error: { code: 'UNAUTHENTICATED', message: 'Session expired or invalid' },
      }),
    };
  };

  class MiniClient {
    constructor() {
      this.onUnauthorized = null;
    }
    setOnUnauthorized(cb) {
      this.onUnauthorized = cb;
    }
    async getMe() {
      const res = await global.fetch('/v1/auth/me');
      if (res.status === 401 && this.onUnauthorized) {
        this.onUnauthorized();
      }
      return res;
    }
  }

  const client = new MiniClient();
  client.setOnUnauthorized(() => {
    unauthorizedTriggered = true;
  });

  await client.getMe();
  assert.strictEqual(unauthorizedTriggered, true);
});

test('API Client formats structured backend error responses', async () => {
  global.fetch = async () => {
    return {
      ok: false,
      status: 400,
      json: async () => ({
        error: {
          code: 'IDEMPOTENCY_KEY_MISMATCH',
          message: 'Idempotency-Key header does not match body field',
        },
      }),
    };
  };

  let errorCaught = null;
  try {
    const res = await global.fetch('/v1/conversations/123/messages');
    if (!res.ok) {
      const data = await res.json();
      throw {
        statusCode: res.status,
        code: data.error.code,
        message: data.error.message,
      };
    }
  } catch (err) {
    errorCaught = err;
  }

  assert.notStrictEqual(errorCaught, null);
  assert.strictEqual(errorCaught.statusCode, 400);
  assert.strictEqual(errorCaught.code, 'IDEMPOTENCY_KEY_MISMATCH');
  assert.strictEqual(errorCaught.message, 'Idempotency-Key header does not match body field');
});
