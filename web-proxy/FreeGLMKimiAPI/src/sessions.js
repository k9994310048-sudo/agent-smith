export class SessionStore {
  constructor({ ttlMs = 2 * 60 * 60 * 1000, maxDepth = 100 } = {}) {
    this.ttlMs = ttlMs; this.maxDepth = maxDepth; this.sessions = new Map();
  }
  get(agentId='default', provider='kimi') {
    const key = `${provider}:${agentId || 'default'}`;
    let s = this.sessions.get(key);
    const now = Date.now();
    if (!s) s = { key, provider, agentId, providerSessionId:'', parentMessageId:'', createdAt:now, messageCount:0, history:[] };
    if ((now - s.createdAt > this.ttlMs) || s.messageCount >= this.maxDepth) {
      s.providerSessionId=''; s.parentMessageId=''; s.createdAt=now; s.messageCount=0;
    }
    this.sessions.set(key,s); return s;
  }
  update(s, { providerSessionId, parentMessageId } = {}) {
    if (providerSessionId) s.providerSessionId = providerSessionId;
    if (parentMessageId) s.parentMessageId = parentMessageId;
    s.messageCount += 1; this.sessions.set(s.key,s); return s;
  }
  dump() { return [...this.sessions.values()].map(s => ({...s, history: undefined})); }
}
