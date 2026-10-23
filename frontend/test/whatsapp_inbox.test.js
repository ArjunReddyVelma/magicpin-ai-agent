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

test('WhatsApp API: simulateInboundWhatsAppMessage submits customer inquiry payload', async () => {
  let capturedUrl = null;
  let capturedOptions = null;
  global.fetch = async (url, options) => {
    capturedUrl = url;
    capturedOptions = options;
    return {
      ok: true,
      status: 201,
      json: async () => ({
        id: 'msg-sim-uuid-1',
        provider_message_id: 'wamid.sim_abcdef0123456789',
        customer_wa_id: '919876543210',
        customer_name: 'Simulated User',
        inbound_text: 'Do you offer delivery?',
        suggested_reply: 'Yes, we offer delivery within 5km.',
        status: 'needs_review',
        created_at: '2026-10-23T10:00:00Z',
      }),
    };
  };

  const payload = {
    customer_wa_id: '919876543210',
    customer_name: 'Simulated User',
    message_text: 'Do you offer delivery?',
  };

  const res = await global.fetch('/v1/whatsapp/mock/simulate-inbound', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': 'csrf-123' },
    body: JSON.stringify(payload),
  }).then(r => r.json());

  assert.strictEqual(capturedUrl, '/v1/whatsapp/mock/simulate-inbound');
  assert.strictEqual(capturedOptions.method, 'POST');
  const parsedBody = JSON.parse(capturedOptions.body);
  assert.strictEqual(parsedBody.customer_wa_id, '919876543210');
  assert.strictEqual(parsedBody.customer_name, 'Simulated User');
  assert.strictEqual(parsedBody.message_text, 'Do you offer delivery?');
  assert.strictEqual(res.id, 'msg-sim-uuid-1');
  assert.strictEqual(res.status, 'needs_review');
  assert.ok(res.provider_message_id.startsWith('wamid.sim_'));
});

test('WhatsApp API: simulateWhatsAppStatus submits status transition payload', async () => {
  let capturedUrl = null;
  let capturedOptions = null;
  global.fetch = async (url, options) => {
    capturedUrl = url;
    capturedOptions = options;
    return {
      ok: true,
      status: 200,
      json: async () => ({
        id: 'msg-sim-uuid-1',
        status: 'send_failed',
        last_error: 'Simulated provider error for testing retry',
      }),
    };
  };

  const messageId = 'msg-sim-uuid-1';
  const payload = {
    status: 'send_failed',
    last_error: 'Simulated provider error for testing retry',
  };

  const res = await global.fetch(`/v1/whatsapp/mock/messages/${messageId}/status`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': 'csrf-123' },
    body: JSON.stringify(payload),
  }).then(r => r.json());

  assert.strictEqual(capturedUrl, `/v1/whatsapp/mock/messages/${messageId}/status`);
  assert.strictEqual(capturedOptions.method, 'POST');
  const parsedBody = JSON.parse(capturedOptions.body);
  assert.strictEqual(parsedBody.status, 'send_failed');
  assert.strictEqual(parsedBody.last_error, 'Simulated provider error for testing retry');
  assert.strictEqual(res.status, 'send_failed');
});

test('WhatsApp API: getWhatsAppAccount reports mode when mock mode is enabled', async () => {
  global.fetch = async () => ({
    ok: true,
    status: 200,
    json: async () => ({
      connected: true,
      phone_number_id: 'mock-phone-123',
      business_account_id: 'mock-biz-456',
      mode: 'mock',
      created_at: '2026-10-23T10:00:00Z',
    }),
  });

  const res = await global.fetch('/v1/whatsapp/account').then(r => r.json());
  assert.strictEqual(res.connected, true);
  assert.strictEqual(res.mode, 'mock');
  assert.strictEqual(res.phone_number_id, 'mock-phone-123');
});
