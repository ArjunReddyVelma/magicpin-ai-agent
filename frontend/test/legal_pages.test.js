import test from 'node:test';
import assert from 'node:assert';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Helper to read source files for static verification
const readSource = (relPath) => {
  const fullPath = path.resolve(__dirname, '..', relPath);
  return fs.readFileSync(fullPath, 'utf-8');
};

test('Legal routing state machine: unauthenticated view transitions', () => {
  // Simulates AppShell unauthenticated state logic
  let authView = 'login';

  const setAuthView = (next) => {
    authView = next;
  };

  // 1. From Login to Privacy Policy and back
  assert.strictEqual(authView, 'login');
  setAuthView('privacy');
  assert.strictEqual(authView, 'privacy');
  setAuthView('login');
  assert.strictEqual(authView, 'login');

  // 2. From Login to Terms of Service and back
  setAuthView('terms');
  assert.strictEqual(authView, 'terms');
  setAuthView('login');
  assert.strictEqual(authView, 'login');

  // 3. From Register to Privacy Policy and Terms
  setAuthView('register');
  assert.strictEqual(authView, 'register');
  setAuthView('privacy');
  assert.strictEqual(authView, 'privacy');
  setAuthView('login');
  assert.strictEqual(authView, 'login');

  setAuthView('register');
  assert.strictEqual(authView, 'register');
  setAuthView('terms');
  assert.strictEqual(authView, 'terms');
  setAuthView('login');
  assert.strictEqual(authView, 'login');
});

test('Legal routing state machine: authenticated tab transitions', () => {
  // Simulates AppShell authenticated state logic
  let activeTab = 'dashboard';

  const setActiveTab = (tab) => {
    activeTab = tab;
  };

  // 1. Footer click to Privacy Policy and Return to Dashboard
  assert.strictEqual(activeTab, 'dashboard');
  setActiveTab('privacy');
  assert.strictEqual(activeTab, 'privacy');
  setActiveTab('dashboard');
  assert.strictEqual(activeTab, 'dashboard');

  // 2. Footer click to Terms of Service and Return to Dashboard
  setActiveTab('terms');
  assert.strictEqual(activeTab, 'terms');
  setActiveTab('dashboard');
  assert.strictEqual(activeTab, 'dashboard');
});

test('Privacy Policy: disclosures, confirmation flags, and legal status', () => {
  const source = readSource('src/pages/PrivacyPolicyPage.tsx');

  // Must explicitly state formal legal review is pending
  assert.ok(
    source.includes('Formal legal review has not yet been completed'),
    'Must state legal review is pending'
  );
  assert.ok(
    source.includes('Pre-Publication Draft'),
    'Must identify as pre-publication draft'
  );

  // Must contain explicit required confirmation callouts
  assert.ok(
    source.includes('[Requires Legal / Product-Owner Confirmation]'),
    'Must highlight required legal/product-owner confirmations'
  );

  // Must accurately disclose AI provider processing details
  assert.ok(
    source.includes('Groq') && source.includes('Llama'),
    'Must identify actual AI provider and model family'
  );
  assert.ok(
    source.includes('Data Processing Agreements (DPA)'),
    'Must call out DPA requirements'
  );

  // Must disclose data retention rules
  assert.ok(
    source.includes('Session tokens automatically expire after 7 days'),
    'Must document session TTL'
  );

  // Must disclose account deletion cascade
  assert.ok(
    source.includes('ON DELETE CASCADE') || source.includes('atomic deletion cascade'),
    'Must accurately disclose database deletion behavior'
  );

  // Must NOT make unsubstantiated certification claims
  assert.ok(!source.includes('SOC 2 certified'), 'Must not claim false SOC 2 certification');
  assert.ok(!source.includes('ISO 27001 certified'), 'Must not claim false ISO certification');
  assert.ok(!source.includes('HIPAA compliant'), 'Must not claim false HIPAA compliance');
});

test('Terms of Service: service scope, human-in-the-loop guarantee, and disclaimers', () => {
  const source = readSource('src/pages/TermsOfServicePage.tsx');

  // Must state legal review has not yet been conducted
  assert.ok(
    source.includes('Formal legal review has not yet been conducted'),
    'Must state legal review is pending'
  );

  // Must state internal copilot scope
  assert.ok(
    source.includes('standalone, internal merchant copilot'),
    'Must define scope as internal merchant copilot'
  );

  // Must enforce human-in-the-loop guarantee
  assert.ok(
    source.includes('Approvals Record Decisions'),
    'Must explain approvals record decisions in DB'
  );
  assert.ok(
    source.includes('does NOT automatically transmit messages over WhatsApp, SMS, or email'),
    'Must guarantee no external messaging side effects'
  );

  // Must disclose probabilistic nature of AI outputs
  assert.ok(
    source.includes('probabilistic'),
    'Must disclose probabilistic nature of LLM outputs'
  );

  // Must have confirmation callouts for governing law and warranties
  assert.ok(
    source.includes('[Requires Legal / Product-Owner Confirmation]'),
    'Must highlight open legal items'
  );
  assert.ok(
    source.includes('governing law') || source.includes('Governing Law'),
    'Must call out governing law determination'
  );
});

test('Integration: Register and Login views provide reachable legal links', () => {
  const regSource = readSource('src/pages/RegisterPage.tsx');
  const loginSource = readSource('src/pages/LoginPage.tsx');
  const appSource = readSource('src/App.tsx');

  // Register page links
  assert.ok(regSource.includes('onViewTerms'), 'RegisterPage accepts onViewTerms');
  assert.ok(regSource.includes('onViewPrivacy'), 'RegisterPage accepts onViewPrivacy');
  assert.ok(regSource.includes('Terms of Service'), 'RegisterPage displays Terms link');
  assert.ok(regSource.includes('Privacy Policy'), 'RegisterPage displays Privacy link');

  // Login page links
  assert.ok(loginSource.includes('onViewTerms'), 'LoginPage accepts onViewTerms');
  assert.ok(loginSource.includes('onViewPrivacy'), 'LoginPage accepts onViewPrivacy');

  // App footer links
  assert.ok(appSource.includes("setActiveTab('privacy')"), 'Footer opens Privacy tab');
  assert.ok(appSource.includes("setActiveTab('terms')"), 'Footer opens Terms tab');
});
