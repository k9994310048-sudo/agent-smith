import { contentToText, preparePrompt } from '../message.js';

const BASE='https://www.kimi.com';
const HEADERS={ Accept:'*/*','Cache-Control':'no-cache',Pragma:'no-cache',Origin:BASE,'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131 Safari/537.36','X-Msh-Platform':'web' };
function ts(){return Math.floor(Date.now()/1000)}
function jwtPayload(token){ try { return JSON.parse(Buffer.from(token.split('.')[1], 'base64url').toString('utf8')); } catch { return {}; } }
function frameJson(obj){ const b=Buffer.from(JSON.stringify(obj)); const f=Buffer.alloc(5+b.length); f.writeUInt8(0,0); f.writeUInt32BE(b.length,1); b.copy(f,5); return f; }
export function parseKimiFrames(buffer){
  const out=[]; let off=0;
  while (off+5<=buffer.length) { const len=buffer.readUInt32BE(off+1); if (off+5+len>buffer.length) break; const raw=buffer.slice(off+5,off+5+len).toString('utf8'); try { out.push(JSON.parse(raw)); } catch {} off += 5+len; }
  return out;
}
export class KimiProvider {
  constructor(account){ this.account=account; this.token=account.token || account.accessToken || account.refreshToken || account.refresh_token; if(!this.token) throw new Error('Kimi token missing'); }
  async complete({ messages, modelCfg, tools, session }) {
    const prompt=preparePrompt(messages, tools, { simpleTools:true, isMultiTurn: !!session.providerSessionId });
    const payload={ scenario:'SCENARIO_K2D5', chat_id:session.providerSessionId || '', tools:modelCfg.webSearch ? [{type:'TOOL_TYPE_SEARCH',search:{}}] : [], message:{ parent_id:session.parentMessageId || '', role:'user', blocks:[{message_id:'', text:{content:prompt}}], scenario:'SCENARIO_K2D5' }, options:{ thinking: !!modelCfg.thinking } };
    const resp=await fetch(`${BASE}/apiv2/kimi.gateway.chat.v1.ChatService/Chat`, { method:'POST', headers:{...HEADERS,Authorization:`Bearer ${this.token}`,'Content-Type':'application/connect+json'}, body:frameJson(payload) });
    if (!resp.ok) throw new Error(`Kimi HTTP ${resp.status}: ${(await resp.text()).slice(0,200)}`);
    const arr=Buffer.from(await resp.arrayBuffer());
    const frames=parseKimiFrames(arr);
    let text='', reasoning='', chatId='', parentId='';
    for (const d of frames) {
      chatId ||= d.chat_id || d.chatId || d.message?.chat_id || d.message?.chatId || '';
      parentId ||= d.message_id || d.messageId || d.message?.message_id || d.message?.id || '';
      if (d.error) throw new Error(`Kimi API Error: ${d.error.message || JSON.stringify(d.error)}`);
      const parts=[d.block?.text?.content,d.text?.content,d.message?.text?.content,d.message?.content,d.content,d.delta?.content].filter(Boolean);
      if ((d.op === 'set' || d.op === 'append') || parts.length) text += parts.join('');
      reasoning += d.reasoning_content || d.thinking?.content || '';
    }
    return { text, reasoning, providerSessionId: chatId, parentMessageId: parentId, prompt };
  }
}
