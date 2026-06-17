#!/usr/bin/env node
import fs from 'fs';
import { ZaiProvider } from '../src/providers/zai.js';
import { closeZaiBrowserClient } from '../src/providers/zaiBrowser.js';

const authPath = process.env.AUTH_PATH || './auth.json';
const model = process.env.MODEL || 'glm-5';
const prompt = process.env.PROMPT || 'Reply exactly: GLM_REAL_OK';

function decodeJwt(token) {
  try {
    const [, payload] = token.split('.');
    return JSON.parse(Buffer.from(payload, 'base64url').toString('utf8'));
  } catch { return null; }
}

function readAccount() {
  const raw = JSON.parse(fs.readFileSync(authPath, 'utf8'));
  const account = (raw.accounts || [raw]).find(a => a.provider === 'glm' && (a.token || a.access_token || a.accessToken));
  if (!account) throw new Error(`No GLM/Z.ai token in ${authPath}; set GLM_TOKEN or auth.json account`);
  return account;
}

async function main() {
  const account = process.env.GLM_TOKEN
    ? { id: 'env', provider: 'glm', backend: 'zai', token: process.env.GLM_TOKEN, captcha_verify_param: process.env.ZAI_CAPTCHA_VERIFY_PARAM, browser_fallback: process.env.ZAI_BROWSER_FALLBACK }
    : readAccount();
  const token = account.token || account.access_token || account.accessToken;
  const payload = decodeJwt(token);
  const provider = new ZaiProvider(account);
  try {
    const result = await provider.complete({
      messages: [{ role: 'user', content: prompt }],
      modelCfg: { id: model, provider: 'glm', thinking: false, webSearch: false },
      tools: [],
      session: {}
    });
    const ok = /GLM_REAL_OK|OK/i.test(result.text || '');
    console.log(JSON.stringify({
      ok,
      completion: true,
      model,
      tokenPayload: payload ? { id: payload.id || payload.sub || payload.user_id, email: payload.email, exp: payload.exp } : null,
      providerSessionId: result.providerSessionId || null,
      parentMessageId: result.parentMessageId || null,
      textPreview: String(result.text || '').slice(0, 500)
    }, null, 2));
    if (!ok) process.exitCode = 4;
  } catch (err) {
    const msg = err?.message || String(err);
    console.error(JSON.stringify({
      ok: false,
      completion: true,
      model,
      tokenPayload: payload ? { id: payload.id || payload.sub || payload.user_id, email: payload.email, exp: payload.exp } : null,
      error: msg
    }, null, 2));
    if (/401|unauthorized/i.test(msg)) {
      console.error('\nDiagnosis: Z.ai rejected this token. Run npm run auth:browser to refresh the browser-backed token.');
      process.exitCode = 2;
      return;
    }
    if (/captcha|verify|验证/i.test(msg)) {
      console.error('\nDiagnosis: Z.ai completion endpoint requires browser verification. Run npm run auth:browser once, then retry with ZAI_BROWSER_FALLBACK=1 ZAI_BROWSER_HEADLESS=0.');
      process.exitCode = 3;
      return;
    }
    process.exitCode = 1;
  } finally {
    await closeZaiBrowserClient();
  }
}

main().catch(e => { console.error(e); process.exit(1); });
