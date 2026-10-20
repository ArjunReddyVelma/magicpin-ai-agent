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

/**
 * Resolves and normalizes the backend API base URL.
 * Mirrors implementation in frontend/src/api/client.ts.
 */
function resolveBaseUrl(envUrl) {
  if (!envUrl || !envUrl.trim()) {
    return '/v1';
  }
  const cleaned = envUrl.trim().replace(/\/+$/, '');
  if (cleaned.endsWith('/v1')) {
    return cleaned;
  }
  return `${cleaned}/v1`;
}

class TestApiClient {
  constructor(customBaseUrl) {
    this.baseUrl = resolveBaseUrl(customBaseUrl);
  }
  getBaseUrl() {
    return this.baseUrl;
  }
  buildUrl(endpoint) {
    return `${this.baseUrl}${endpoint}`;
  }
}

test('resolveBaseUrl defaults to /v1 when envUrl is undefined, null, or empty', () => {
  assert.strictEqual(resolveBaseUrl(undefined), '/v1');
  assert.strictEqual(resolveBaseUrl(null), '/v1');
  assert.strictEqual(resolveBaseUrl(''), '/v1');
  assert.strictEqual(resolveBaseUrl('   '), '/v1');
});

test('resolveBaseUrl appends /v1 to bare origins without paths', () => {
  assert.strictEqual(resolveBaseUrl('https://api.example.com'), 'https://api.example.com/v1');
  assert.strictEqual(resolveBaseUrl('http://localhost:8000'), 'http://localhost:8000/v1');
});

test('resolveBaseUrl strips trailing slashes before appending /v1', () => {
  assert.strictEqual(resolveBaseUrl('https://api.example.com/'), 'https://api.example.com/v1');
  assert.strictEqual(resolveBaseUrl('https://api.example.com///'), 'https://api.example.com/v1');
});

test('resolveBaseUrl preserves existing /v1 suffix and avoids /v1/v1 duplication', () => {
  assert.strictEqual(resolveBaseUrl('https://api.example.com/v1'), 'https://api.example.com/v1');
  assert.strictEqual(resolveBaseUrl('https://api.example.com/v1/'), 'https://api.example.com/v1');
  assert.strictEqual(resolveBaseUrl('/v1'), '/v1');
  assert.strictEqual(resolveBaseUrl('/v1/'), '/v1');
});

test('resolveBaseUrl handles custom relative base paths correctly', () => {
  assert.strictEqual(resolveBaseUrl('/api'), '/api/v1');
  assert.strictEqual(resolveBaseUrl('/api/v1'), '/api/v1');
  assert.strictEqual(resolveBaseUrl('/api/v1/'), '/api/v1');
});

test('TestApiClient builds valid endpoint URLs for default and production bases', () => {
  const defaultClient = new TestApiClient();
  assert.strictEqual(defaultClient.getBaseUrl(), '/v1');
  assert.strictEqual(defaultClient.buildUrl('/healthz'), '/v1/healthz');
  assert.strictEqual(defaultClient.buildUrl('/auth/login'), '/v1/auth/login');
  assert.strictEqual(defaultClient.buildUrl('/conversations/123/messages'), '/v1/conversations/123/messages');

  const prodClient = new TestApiClient('https://magicpin-backend.onrender.com');
  assert.strictEqual(prodClient.getBaseUrl(), 'https://magicpin-backend.onrender.com/v1');
  assert.strictEqual(prodClient.buildUrl('/healthz'), 'https://magicpin-backend.onrender.com/v1/healthz');
  assert.strictEqual(prodClient.buildUrl('/auth/login'), 'https://magicpin-backend.onrender.com/v1/auth/login');
});
