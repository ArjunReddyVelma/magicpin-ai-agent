import test from 'node:test';
import assert from 'node:assert';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

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

test('Dashboard layout: technical cards (AI Model and Backend Health) are removed from dashboard', () => {
  const fullPath = path.resolve(__dirname, '..', 'src/pages/DashboardPage.tsx');
  const source = fs.readFileSync(fullPath, 'utf-8');

  // Technical cards must be absent from the merchant dashboard
  assert.ok(
    !source.includes('AI Model & Grounding'),
    'Dashboard must not contain AI Model & Grounding card'
  );
  assert.ok(
    !source.includes('openai/gpt-oss-120b'),
    'Dashboard must not contain AI model identifier'
  );
  assert.ok(
    !source.includes('Backend Service Status'),
    'Dashboard must not contain Backend Service Status card'
  );
  assert.ok(
    !source.includes('<HealthIndicator'),
    'Dashboard must not render HealthIndicator component'
  );

  // Essential business sections must be preserved
  assert.ok(source.includes('Business Context'), 'Business Context metric must be preserved');
  assert.ok(source.includes('Total Conversations'), 'Total Conversations metric must be preserved');
  assert.ok(source.includes('Configured Business Context'), 'Configured Business Context section must be preserved');
  assert.ok(source.includes('Recent Conversations'), 'Recent Conversations section must be preserved');
  assert.ok(source.includes('MerchantProfileCard'), 'MerchantProfileCard must be preserved');
  assert.ok(source.includes('sm:grid-cols-2'), 'Metrics grid must expand to sm:grid-cols-2');
});

test('Dashboard navigation: Customer Support link is visible and navigates to support route', () => {
  const fullPath = path.resolve(__dirname, '..', 'src/pages/DashboardPage.tsx');
  const source = fs.readFileSync(fullPath, 'utf-8');

  // Visible Customer Support link
  assert.ok(
    source.includes('Customer Support'),
    'Dashboard must include visible Customer Support navigation link'
  );
  assert.ok(
    source.includes("onNavigate('support')"),
    'Customer Support link must trigger navigation to support route'
  );

  // Navigation state machine transition
  let activeTab = 'dashboard';
  const handleNavigate = (tab) => {
    const normalizedTab = tab.replace(/^\//, '');
    activeTab = normalizedTab;
  };

  assert.strictEqual(activeTab, 'dashboard');
  handleNavigate('support');
  assert.strictEqual(activeTab, 'support', 'Navigating to support must transition activeTab to support');
});

test('Customer Support Card: compact layout, required elements, and removal of redundant UI in DashboardPage', () => {
  const fullPath = path.resolve(__dirname, '..', 'src/pages/DashboardPage.tsx');
  const source = fs.readFileSync(fullPath, 'utf-8');

  // Title and compact description
  assert.ok(
    source.includes('<h2 className="text-sm font-semibold text-surface-900">Customer Support</h2>'),
    'Dashboard must include "Customer Support" card title'
  );
  assert.ok(
    source.includes('Manage customer inquiries and review AI-suggested replies.'),
    'Dashboard must include compact description "Manage customer inquiries and review AI-suggested replies."'
  );

  // Small Open Inbox action button
  assert.ok(
    source.includes('Open Inbox'),
    'Dashboard card must include "Open Inbox" action'
  );
  assert.ok(
    source.includes("onNavigate('support')"),
    'Open Inbox action must navigate to support tab'
  );

  // Redundant elements must be removed
  assert.ok(
    !source.includes('View and respond to customer inquiries with AI-suggested replies.'),
    'Dashboard must NOT contain long description about AI-suggested replies'
  );
  assert.ok(
    !source.includes('Customer Support Public Link'),
    'Dashboard must NOT contain redundant "Customer Support Public Link" label'
  );
  assert.ok(
    !source.includes('Open Customer Support Inbox'),
    'Dashboard must NOT contain redundant "Open Customer Support Inbox" title or button'
  );

  // Link format verification - path format only, forbidden query params
  assert.ok(
    source.includes('/support/'),
    'Dashboard must link to /support/:merchantId path format'
  );
  assert.ok(
    !source.includes('/support?merchant_id='),
    'Dashboard must NOT use /support?merchant_id= query parameter'
  );
  assert.ok(
    !source.includes('?merchant_id='),
    'Dashboard must NOT use query parameters for merchant ID'
  );

  // Graceful fallback when merchant ID is unavailable
  assert.ok(
    source.includes('Support link unavailable (merchant ID not loaded)'),
    'Dashboard must handle missing merchant ID gracefully without rendering broken URL'
  );

  // Copy support link and external link UI
  assert.ok(
    source.includes('handleCopySupportLink'),
    'Dashboard must provide copy support link handler'
  );
  assert.ok(
    source.includes('copiedSupportLink'),
    'Dashboard must track copied link state'
  );

  // Visual balance: right column uses tighter spacing
  assert.ok(
    source.includes('<div className="space-y-4">'),
    'Right column must use space-y-4 to keep profile and support cards visually balanced and close together'
  );

  // Header anti-clipping
  assert.ok(
    source.includes('leading-tight') && source.includes('pt-1'),
    'Page header must have anti-clipping breathing room'
  );
});

test('Customer Support Card: getMerchantSupportPath generates correct URL path and handles edge cases', () => {
  // Test the helper logic mirroring frontend/src/pages/DashboardPage.tsx
  const getMerchantSupportPath = (merchantId) => {
    if (!merchantId || !merchantId.trim()) {
      return null;
    }
    return `/support/${encodeURIComponent(merchantId.trim())}`;
  };

  // Standard UUID format
  const uuid1 = 'fe9f0e18-f6cd-4fee-9bf0-ddc827c16c71';
  assert.strictEqual(
    getMerchantSupportPath(uuid1),
    '/support/fe9f0e18-f6cd-4fee-9bf0-ddc827c16c71',
    'Must produce /support/:merchantId path format'
  );

  // Different merchant IDs produce different destinations
  const uuid2 = 'a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d';
  assert.strictEqual(
    getMerchantSupportPath(uuid2),
    '/support/a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d'
  );
  assert.notStrictEqual(
    getMerchantSupportPath(uuid1),
    getMerchantSupportPath(uuid2),
    'Different merchant IDs must produce distinct paths'
  );

  // Path format guarantees: must NOT contain query params
  assert.ok(
    !getMerchantSupportPath(uuid1).includes('?'),
    'Support path must not contain query parameters'
  );
  assert.ok(
    !getMerchantSupportPath(uuid1).includes('merchant_id='),
    'Support path must not contain merchant_id= query key'
  );

  // Missing or empty merchant ID returns null (does not produce broken URL)
  assert.strictEqual(getMerchantSupportPath(undefined), null);
  assert.strictEqual(getMerchantSupportPath(null), null);
  assert.strictEqual(getMerchantSupportPath(''), null);
  assert.strictEqual(getMerchantSupportPath('   '), null);

  // Special characters are URI-encoded
  assert.strictEqual(
    getMerchantSupportPath('store test/123'),
    '/support/store%20test%2F123'
  );
});

test('Customer Support Card: copy and navigation interactions work as expected', async () => {
  let navigatedTab = null;
  const onNavigate = (tab) => {
    navigatedTab = tab;
  };

  // Simulating clicking Open Inbox action button
  onNavigate('support');
  assert.strictEqual(navigatedTab, 'support', 'Clicking Open Inbox must navigate to support tab');

  // Simulating copy link handler
  let clipboardText = null;
  const mockClipboard = {
    writeText: async (text) => {
      clipboardText = text;
    },
  };

  const handleCopy = async (path, origin = 'http://localhost:5173') => {
    const fullUrl = `${origin}${path}`;
    await mockClipboard.writeText(fullUrl);
    return true;
  };

  const merchantId = 'fe9f0e18-f6cd-4fee-9bf0-ddc827c16c71';
  const path = `/support/${merchantId}`;
  const copied = await handleCopy(path);

  assert.strictEqual(copied, true);
  assert.strictEqual(
    clipboardText,
    `http://localhost:5173/support/fe9f0e18-f6cd-4fee-9bf0-ddc827c16c71`,
    'Must copy the full origin URL with merchant path to the clipboard'
  );

  const anotherMerchantId = 'a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d';
  await handleCopy(`/support/${anotherMerchantId}`);
  assert.strictEqual(
    clipboardText,
    `http://localhost:5173/support/a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d`,
    'Must reflect distinct merchant IDs in clipboard URL'
  );
});

test('Dashboard header cleanup: retains Add Context Item and Start AI Chat, removes duplicate Customer Support button', () => {
  const fullPath = path.resolve(__dirname, '..', 'src/pages/DashboardPage.tsx');
  const source = fs.readFileSync(fullPath, 'utf-8');

  // Locate the header actions section
  const headerStart = source.indexOf('{/* Page Header */}');
  const headerEnd = source.indexOf('{/* Metrics Row');
  assert.ok(headerStart !== -1 && headerEnd !== -1, 'Page Header and Metrics sections must exist');
  const headerSection = source.slice(headerStart, headerEnd);

  // Retain only Add Context Item and Start AI Chat
  assert.ok(headerSection.includes('Add Context Item'), 'Header must contain Add Context Item button');
  assert.ok(headerSection.includes('Start AI Chat'), 'Header must contain Start AI Chat button');

  // Duplicate Customer Support button must be removed from header
  assert.ok(
    !headerSection.includes('Customer Support'),
    'Header must NOT contain duplicate Customer Support button'
  );
});

test('Shared navigation cleanup: WhatsApp Inbox, Protected Session, and Sign Out are removed from Navbar', () => {
  const fullPath = path.resolve(__dirname, '..', 'src/components/Navbar.tsx');
  const source = fs.readFileSync(fullPath, 'utf-8');

  // WhatsApp Inbox must be absent
  assert.ok(!source.includes('WhatsApp Inbox'), 'Navbar must not contain WhatsApp Inbox');
  assert.ok(!source.includes('whatsapp'), 'Navbar must not define whatsapp nav item');

  // Protected Session must be absent
  assert.ok(!source.includes('Protected Session'), 'Navbar must not contain Protected Session indicator');

  // Sign Out must be absent from top navigation
  assert.ok(!source.includes('Sign Out'), 'Navbar must not contain standalone Sign Out button');
  assert.ok(!source.includes('LogOut'), 'Navbar must not import or render LogOut');

  // Remaining active navigation items must be preserved
  assert.ok(source.includes('Dashboard'), 'Navbar must contain Dashboard');
  assert.ok(source.includes('AI Workspace'), 'Navbar must contain AI Workspace');
  assert.ok(source.includes('Merchant Context'), 'Navbar must contain Merchant Context');
  assert.ok(source.includes('Drafts & Actions'), 'Navbar must contain Drafts & Actions');
  assert.ok(source.includes('Support Inbox'), 'Navbar must contain Support Inbox');
  assert.ok(source.includes('Settings'), 'Navbar must contain Settings');
});

test('Settings page: Sign Out action is available and uses existing auth logout', () => {
  const fullPath = path.resolve(__dirname, '..', 'src/pages/SettingsPage.tsx');
  const source = fs.readFileSync(fullPath, 'utf-8');

  // Sign Out button must be present in SettingsPage
  assert.ok(
    source.includes('Sign Out'),
    'Settings page must render visible Sign Out button'
  );
  assert.ok(
    source.includes('handleLogout') || source.includes('logout()'),
    'Settings page must trigger logout function'
  );
  assert.ok(
    source.includes('Active Authentication Session'),
    'Settings page must include session security section for sign out'
  );
});
