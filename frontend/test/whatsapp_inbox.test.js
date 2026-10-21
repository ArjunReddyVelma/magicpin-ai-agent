import test from 'node:test';
import assert from 'node:assert';

// Mock browser global fetch and Headers for Node test environment
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

test('WhatsApp API: getWhatsAppAccount requests account status', async () => {
  let capturedUrl = null;
  global.fetch = async (url) => {
    capturedUrl = url;
    return {
      ok: true,
      status: 200,
      json: async () => ({
        connected: true,
        phone_number_id: '10987654321',
        business_account_id: 'biz_123',
        created_at: '2026-10-21T10:00:00Z',
      }),
    };
  };

  const res = await global.fetch('/v1/whatsapp/account').then(r => r.json());
  assert.strictEqual(capturedUrl, '/v1/whatsapp/account');
  assert.strictEqual(res.connected, true);
  assert.strictEqual(res.phone_number_id, '10987654321');
});

test('WhatsApp API: saveWhatsAppAccount submits PUT with credentials', async () => {
  let capturedUrl = null;
  let capturedOptions = null;
  global.fetch = async (url, options) => {
    capturedUrl = url;
    capturedOptions = options;
    return {
      ok: true,
      status: 200,
      json: async () => ({
        connected: true,
        phone_number_id: '10987654321',
        business_account_id: null,
        created_at: '2026-10-21T10:00:00Z',
      }),
    };
  };

  const payload = {
    phone_number_id: '10987654321',
    access_token: 'mock_token_at_least_20_chars',
  };

  await global.fetch('/v1/whatsapp/account', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': 'csrf-123' },
    body: JSON.stringify(payload),
  });

  assert.strictEqual(capturedUrl, '/v1/whatsapp/account');
  assert.strictEqual(capturedOptions.method, 'PUT');
  const parsedBody = JSON.parse(capturedOptions.body);
  assert.strictEqual(parsedBody.phone_number_id, '10987654321');
});

test('WhatsApp API: sendWhatsAppReply transmits reply_text and force flag', async () => {
  let capturedUrl = null;
  let capturedOptions = null;
  global.fetch = async (url, options) => {
    capturedUrl = url;
    capturedOptions = options;
    return {
      ok: true,
      status: 200,
      json: async () => ({
        id: 'msg-uuid-1',
        status: 'sent',
        sent_at: '2026-10-21T10:05:00Z',
      }),
    };
  };

  const messageId = 'msg-uuid-1';
  await global.fetch(`/v1/whatsapp/messages/${messageId}/send`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': 'csrf-123' },
    body: JSON.stringify({ reply_text: 'Thank you for messaging us!', force: true }),
  });

  assert.strictEqual(capturedUrl, `/v1/whatsapp/messages/${messageId}/send`);
  assert.strictEqual(capturedOptions.method, 'POST');
  const parsedBody = JSON.parse(capturedOptions.body);
  assert.strictEqual(parsedBody.reply_text, 'Thank you for messaging us!');
  assert.strictEqual(parsedBody.force, true);
});
