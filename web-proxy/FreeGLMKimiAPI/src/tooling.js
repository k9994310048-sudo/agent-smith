import crypto from 'crypto';

export const TOOL_WRAP_HINT = `
IMPORTANT: You are behind an OpenAI-compatible tool adapter. If you need to use a tool, respond with NOTHING except minified JSON:
{"tool_calls":[{"name":"tool_name","arguments":{}}]}
Or, if JSON is risky, use:
[function_calls]
[call:exact_tool_name]{"argument":"value"}[/call]
[/function_calls]
JSON must be compact and valid. Do not simulate tool results.`;

export function hasToolPromptInjected(messages = []) {
  const signatures = ['## Available Tools','[function_calls]','TOOL_WRAP_HINT','Tool Call Protocol'];
  return messages.some(m => typeof m.content === 'string' && signatures.some(s => m.content.includes(s)));
}

function compactJsonSchema(schema, depth = 0) {
  if (!schema || typeof schema !== 'object' || depth > 2) return schema;
  if (Array.isArray(schema)) return schema.slice(0, 20).map(item => compactJsonSchema(item, depth + 1));
  const out = {};
  for (const key of ['type', 'enum', 'required', 'default']) if (schema[key] !== undefined) out[key] = schema[key];
  if (schema.description) out.description = String(schema.description).slice(0, depth === 0 ? 180 : 90);
  if (schema.properties && typeof schema.properties === 'object') {
    out.properties = {};
    for (const [name, prop] of Object.entries(schema.properties)) out.properties[name] = compactJsonSchema(prop, depth + 1);
  }
  if (schema.items) out.items = compactJsonSchema(schema.items, depth + 1);
  return out;
}

export function toolsToPrompt(tools = [], simple = false) {
  if (!tools?.length) return '';
  const schemas = tools.map(t => {
    const fn = t.function || t;
    if (!fn?.name) return null;
    return {
      name: fn.name,
      description: String(fn.description || '').slice(0, 420),
      parameters: compactJsonSchema(fn.parameters || fn.input_schema || {type:'object',properties:{}})
    };
  }).filter(Boolean).sort((a,b) => a.name.localeCompare(b.name));
  if (!schemas.length) return '';
  const toolNames = schemas.map(s => s.name).join(', ');
  return `OPENAI-COMPATIBLE TOOL CALLING ADAPTER ACTIVE.
You are behind a proxy that converts your JSON into real OpenAI tool_calls. Native prose like "I will use X" is NOT a tool call.

Available tool names exactly:
${toolNames}

GENERAL TOOL RULES:
- When an action, lookup, file read/write, command, web search, calculation, or verification is needed, CALL A TOOL instead of describing the action.
- Never invent tool results. After tool results appear in the conversation, use them to continue.
- Use exact tool names from the list above. Tool names are CASE-SENSITIVE. Do not prefix names with namespaces unless the listed name includes the prefix.

TOOL CALL OUTPUT FORMAT — respond ONLY with minified JSON, no markdown, no prose:
{"tool_calls":[{"name":"tool_name","arguments":{}}]}

Multiple calls are allowed:
{"tool_calls":[{"name":"read_file","arguments":{"path":"package.json"}},{"name":"terminal","arguments":{"command":"npm test"}}]}

If JSON escaping is risky, use this DSML fallback exactly:
<|DSML|tool_calls><|DSML|invoke name="tool_name"><|DSML|parameter name="arg">value</|DSML|parameter></|DSML|invoke></|DSML|tool_calls>
Use CDATA for multiline/code/file content.

Compact tool schemas:
${JSON.stringify(schemas, null, 2)}

If no tool is needed, answer normally.`;
}

function extractBalancedJson(str, start = str.indexOf('{')) {
  if (start < 0) return null;
  let depth=0, inStr=false, esc=false;
  for (let i=start;i<str.length;i++) {
    const ch=str[i];
    if (esc) { esc=false; continue; }
    if (ch==='\\' && inStr) { esc=true; continue; }
    if (ch==='"') { inStr=!inStr; continue; }
    if (!inStr) {
      if (ch==='{') depth++;
      if (ch==='}') { depth--; if (depth===0) return str.slice(start,i+1); }
    }
  }
  return null;
}

function tryJson(s) { try { return JSON.parse(s); } catch { return null; } }
function normalize(name, args, index=0) {
  if (!name) return null;
  if (typeof args === 'string') args = tryJson(args) ?? { raw: args };
  if (args == null || typeof args !== 'object' || Array.isArray(args)) args = { value: args };
  return { index, id: `call_${crypto.randomUUID().replace(/-/g,'').slice(0,24)}`, type: 'function', function: { name, arguments: JSON.stringify(args) } };
}

function decodeEntityText(value='') {
  return String(value)
    .replace(/^<!\[CDATA\[([\s\S]*?)\]\]>$/m, '$1')
    .replace(/&quot;/g, '"').replace(/&apos;/g, "'")
    .replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&')
    .trim();
}

export function parseToolCallsFromText(text='') {
  const calls=[];
  let content=String(text || '');
  const dsmlInvokeRe=/<\|DSML\|invoke\s+name=["']([^"']+)["']\s*>([\s\S]*?)<\/\|DSML\|invoke>/gi;
  let dm;
  while ((dm=dsmlInvokeRe.exec(content))) {
    const args={};
    const params=dm[2];
    const paramRe=/<\|DSML\|parameter\s+name=["']([^"']+)["']\s*>([\s\S]*?)<\/\|DSML\|parameter>/gi;
    let pm;
    while ((pm=paramRe.exec(params))) args[pm[1]] = decodeEntityText(pm[2]);
    calls.push(normalize(dm[1], args, calls.length));
  }
  const blockRe=/\[function_calls\]([\s\S]*?)(?:\[\/function_calls\]|$)/gi;
  let bm;
  while ((bm=blockRe.exec(content))) {
    const block=bm[1];
    const callRe=/\[call\s*[:=]?\s*([a-zA-Z0-9_:.\/-]+)\]([\s\S]*?)\[\/call\]/g;
    let cm;
    while ((cm=callRe.exec(block))) {
      const raw=cm[2].trim().replace(/^```(?:json)?\s*/i,'').replace(/\s*```$/,'');
      const parsed=tryJson(raw) ?? tryJson(extractBalancedJson(raw) || '');
      if (parsed) calls.push(normalize(cm[1], parsed, calls.length));
    }
  }
  const jsonObjCandidates=[];
  const fenceRe=/```(?:json)?\s*([\s\S]*?)```/gi;
  let fm; while((fm=fenceRe.exec(content))) jsonObjCandidates.push(fm[1].trim());
  const xml=content.match(/<tool_call[^>]*>([\s\S]*?)<\/tool_call>/i); if (xml) jsonObjCandidates.push(xml[1].trim());
  for (let i=0;i<content.length;i++) if (content[i]==='{') { const raw=extractBalancedJson(content,i); if (raw) jsonObjCandidates.push(raw); }
  for (const raw of jsonObjCandidates) {
    const obj=tryJson(raw); if (!obj) continue;
    const list = Array.isArray(obj.tool_calls) ? obj.tool_calls : [obj.tool_call || obj.function_call || obj.tool || (obj.name ? obj : null)].filter(Boolean);
    for (const item of list) {
      const fn=item.function || item;
      const call=normalize(fn.name || item.name, fn.arguments ?? item.arguments ?? item.input ?? {}, calls.length);
      if (call) calls.push(call);
    }
    if (calls.length) break;
  }
  const legacy=content.match(/TOOL_CALL:\s*([\w:.-]+)[\s\S]*?(\{[\s\S]*\})/i);
  if (!calls.length && legacy) {
    const raw=extractBalancedJson(legacy[2],0); const parsed=tryJson(raw || legacy[2]);
    if (parsed) calls.push(normalize(legacy[1], parsed, 0));
  }
  if (calls.length) content = content.replace(blockRe,'').replace(/<\|DSML\|tool_calls>[\s\S]*?<\|DSML\|\/tool_calls>/gi,'').trim();
  return { content, toolCalls: calls };
}

export function buildToolCallCompletion(toolCalls, model, prompt='') {
  return { id:`fgk-${Date.now()}`, object:'chat.completion', created:Math.floor(Date.now()/1000), model, choices:[{ index:0, message:{ role:'assistant', content:null, tool_calls:toolCalls }, finish_reason:'tool_calls' }], usage: usage(prompt,'') };
}
export function usage(prompt='', out='') { const p=Math.ceil(String(prompt).length/4), c=Math.ceil(String(out).length/4); return { prompt_tokens:p, completion_tokens:c, total_tokens:p+c }; }
