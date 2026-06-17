import { loadAccounts, MOCK_PROVIDER, MODELS } from '../src/config.js';
console.log(JSON.stringify({ node:process.version, mock:MOCK_PROVIDER, models:Object.keys(MODELS), accounts:loadAccounts().map(a=>({id:a.id,provider:a.provider,hasToken:!!(a.token||a.refresh_token||a.refreshToken||a.accessToken)})) }, null, 2));
