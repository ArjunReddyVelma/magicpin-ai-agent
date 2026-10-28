import test from 'node:test';
import assert from 'node:assert';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const distDir = path.resolve(__dirname, '../dist');

test('SPA Fallback contract: frontend/dist/index.html exists and contains valid mount point', () => {
  const indexHtmlPath = path.join(distDir, 'index.html');
  assert.ok(fs.existsSync(indexHtmlPath), 'dist/index.html must exist after build');
  const content = fs.readFileSync(indexHtmlPath, 'utf-8');
  assert.ok(content.includes('<div id="root"></div>'), 'index.html must contain #root container');
  assert.ok(content.includes('<script type="module"'), 'index.html must contain module script tag');
});

test('Client-side route matching: /support/:merchant_id regex matches valid support URLs', () => {
  // Regex from frontend/src/App.tsx line 135
  const supportRouteRegex = /^\/support(?:\/([^/?#]+))?\/?$/;

  // Valid /support cases
  const match1 = '/support'.match(supportRouteRegex);
  assert.ok(match1);
  assert.strictEqual(match1[1], undefined);

  const match2 = '/support/'.match(supportRouteRegex);
  assert.ok(match2);
  assert.strictEqual(match2[1], undefined);

  const uuid = '123e4567-e89b-12d3-a456-426614174000';
  const match3 = `/support/${uuid}`.match(supportRouteRegex);
  assert.ok(match3);
  assert.strictEqual(match3[1], uuid);

  const match4 = `/support/${uuid}/`.match(supportRouteRegex);
  assert.ok(match4);
  assert.strictEqual(match4[1], uuid);

  // Escaped / encoded merchant IDs
  const match5 = '/support/store%20one'.match(supportRouteRegex);
  assert.ok(match5);
  assert.strictEqual(decodeURIComponent(match5[1]), 'store one');

  // Should NOT match internal API routes
  assert.strictEqual('/v1/support'.match(supportRouteRegex), null);
  assert.strictEqual('/v1/support/messages'.match(supportRouteRegex), null);

  // Should NOT match other pages
  assert.strictEqual('/'.match(supportRouteRegex), null);
  assert.strictEqual('/dashboard'.match(supportRouteRegex), null);
  assert.strictEqual('/workspace'.match(supportRouteRegex), null);
  assert.strictEqual('/actions'.match(supportRouteRegex), null);
});

test('Render static site rewrite simulation: API vs SPA routing differentiation', () => {
  // Simulated Render rewrite rules from render.yaml
  const renderRoutes = [
    { type: 'rewrite', source: /^\/v1\/(.*)$/, destination: (m) => `https://magicpin-backend.onrender.com/v1/${m[1]}` },
    { type: 'rewrite', source: /^\/(.*)$/, destination: () => '/index.html' },
  ];

  function simulateRoute(requestPath) {
    for (const rule of renderRoutes) {
      const match = requestPath.match(rule.source);
      if (match) {
        return { matchedRule: rule.type, destination: rule.destination(match) };
      }
    }
    return { matchedRule: null, destination: null };
  }

  // API calls are proxied to backend preserving path
  assert.strictEqual(
    simulateRoute('/v1/healthz').destination,
    'https://magicpin-backend.onrender.com/v1/healthz'
  );
  assert.strictEqual(
    simulateRoute('/v1/readyz').destination,
    'https://magicpin-backend.onrender.com/v1/readyz'
  );
  assert.strictEqual(
    simulateRoute('/v1/support/merchants/test-id').destination,
    'https://magicpin-backend.onrender.com/v1/support/merchants/test-id'
  );

  // Direct client navigations and refreshes are served via SPA fallback /index.html
  assert.strictEqual(simulateRoute('/support/test-id').destination, '/index.html');
  assert.strictEqual(simulateRoute('/dashboard').destination, '/index.html');
  assert.strictEqual(simulateRoute('/workspace').destination, '/index.html');
  assert.strictEqual(simulateRoute('/privacy').destination, '/index.html');
  assert.strictEqual(simulateRoute('/terms').destination, '/index.html');
});
