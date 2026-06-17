import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { AccountManager } from '../src/accounts.js';

function tmpAuth(content) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'fgk-auth-'));
  const file = path.join(dir, 'auth.json');
  if (content !== undefined) fs.writeFileSync(file, JSON.stringify(content, null, 2));
  return { dir, file };
}

test('AccountManager loads accounts from auth.json and env', () => {
  const { file } = tmpAuth({ accounts: [
    { id: 'glm-file', provider: 'glm', refresh_token: 'r1' },
    { id: 'kimi-file', provider: 'kimi', token: 'k1' }
  ] });
  const manager = new AccountManager({
    authPath: file,
    env: { GLM_REFRESH_TOKEN: 'r-env', KIMI_TOKEN: 'k-env' }
  });

  assert.deepEqual(manager.list().map(a => [a.id, a.provider]), [
    ['glm-file', 'glm'],
    ['kimi-file', 'kimi'],
    ['glm-env', 'glm'],
    ['kimi-env', 'kimi']
  ]);
  assert.equal(manager.list()[0].hasToken, true);
  assert.equal('token' in manager.list()[0], false);
  assert.equal('refresh_token' in manager.list()[0], false);
});

test('AccountManager can add/delete accounts and persist auth.json without leaking tokens', () => {
  const { file } = tmpAuth({ accounts: [] });
  const manager = new AccountManager({ authPath: file, env: {} });

  const safe = manager.add({ id: 'kimi-new', provider: 'kimi', token: 'secret-token' }, { persist: true });
  assert.deepEqual(safe, {
    id: 'kimi-new',
    provider: 'kimi',
    ok: true,
    hasToken: true,
    requestCount: 0,
    failCount: 0,
    lastError: '',
    cooldownUntil: 0
  });

  const raw = JSON.parse(fs.readFileSync(file, 'utf8'));
  assert.equal(raw.accounts[0].token, 'secret-token');
  assert.equal(manager.list()[0].token, undefined);

  assert.equal(manager.delete('kimi-new', { persist: true }), true);
  assert.deepEqual(JSON.parse(fs.readFileSync(file, 'utf8')), { accounts: [] });
});

test('AccountManager uses sticky account per agent and skips cooled-down failures', () => {
  const { file } = tmpAuth({ accounts: [
    { id: 'kimi-a', provider: 'kimi', token: 'a' },
    { id: 'kimi-b', provider: 'kimi', token: 'b' }
  ] });
  const now = { value: 1000 };
  const manager = new AccountManager({ authPath: file, env: {}, now: () => now.value, cooldownMs: 5000 });

  const s1 = { agentId: 'agent-1' };
  const first = manager.select('kimi', s1);
  assert.equal(first.id, 'kimi-a');
  assert.equal(s1.accountId, 'kimi-a');
  assert.equal(manager.select('kimi', s1).id, 'kimi-a');

  manager.markFailure('kimi-a', new Error('Kimi HTTP 429: limit'));
  const next = manager.select('kimi', { agentId: 'agent-2' });
  assert.equal(next.id, 'kimi-b');
  assert.equal(manager.list().find(a => a.id === 'kimi-a').ok, false);

  now.value += 6000;
  assert.equal(manager.select('kimi', { agentId: 'agent-3' }).id, 'kimi-a');
});

test('AccountManager reload rereads auth.json', () => {
  const { file } = tmpAuth({ accounts: [{ id: 'old', provider: 'glm', refresh_token: 'r' }] });
  const manager = new AccountManager({ authPath: file, env: {} });
  fs.writeFileSync(file, JSON.stringify({ accounts: [{ id: 'new', provider: 'kimi', token: 'k' }] }));

  assert.deepEqual(manager.reload().map(a => a.id), ['new']);
});
