import fs from 'fs';
import os from 'os';
import path from 'path';

const selected = process.argv[2] || 'hermes';
const base = process.env.BASE_URL || `http://127.0.0.1:${process.env.PORT || 9766}`;
const model = process.env.MODEL || 'glm-5';
const tmpRoot = fs.mkdtempSync(path.join(os.tmpdir(), `fgk-agent-${selected}-`));

const profiles = {
  hermes: {
    protocol: 'openai',
    tools: [
      { type:'function', function:{ name:'terminal', description:'Run a shell command', parameters:{ type:'object', required:['command'], properties:{ command:{type:'string'} } } } },
      { type:'function', function:{ name:'write_file', description:'Write a text file', parameters:{ type:'object', required:['path','content'], properties:{ path:{type:'string'}, content:{type:'string'} } } } },
      { type:'function', function:{ name:'read_file', description:'Read a text file', parameters:{ type:'object', required:['path'], properties:{ path:{type:'string'} } } } }
    ],
    prompt: `Hermes agent smoke. First call a tool. Use terminal with command "printf HERMES_TOOL_USE_OK" or write/read a file under ${tmpRoot}. Do not answer in prose before tool call.`
  },
  opencode: {
    protocol: 'openai',
    tools: [
      { type:'function', function:{ name:'bash', description:'Execute shell command', parameters:{ type:'object', required:['command'], properties:{ command:{type:'string'} } } } },
      { type:'function', function:{ name:'edit', description:'Create or edit file', parameters:{ type:'object', required:['path','content'], properties:{ path:{type:'string'}, content:{type:'string'} } } } }
    ],
    prompt: `OpenCode build-agent smoke. First call a tool. Prefer bash with command "printf OPENCODE_TOOL_USE_OK". Do not answer in prose before tool call.`
  },
  openclaw: {
    protocol: 'openai',
    tools: [
      { type:'function', function:{ name:'run_shell', description:'Run shell command', parameters:{ type:'object', required:['command'], properties:{ command:{type:'string'} } } } },
      { type:'function', function:{ name:'save_file', description:'Save a file', parameters:{ type:'object', required:['path','content'], properties:{ path:{type:'string'}, content:{type:'string'} } } } }
    ],
    prompt: `OpenClaw-style local agent smoke. First call a tool. Prefer run_shell with command "printf OPENCLAW_TOOL_USE_OK". Do not answer in prose before tool call.`
  },
  claude: {
    protocol: 'anthropic',
    tools: [
      { name:'Bash', description:'Run shell command', input_schema:{ type:'object', required:['command'], properties:{ command:{type:'string'} } } },
      { name:'Write', description:'Write file', input_schema:{ type:'object', required:['file_path','content'], properties:{ file_path:{type:'string'}, content:{type:'string'} } } }
    ],
    prompt: `Claude Code smoke. First use a tool. Prefer Bash with command "printf CLAUDE_TOOL_USE_OK". Do not answer in prose before tool use.`
  }
};

function parseArgs(raw='{}') { try { return JSON.parse(raw || '{}'); } catch { return { raw }; } }
function toolName(tc) { return tc?.function?.name || tc?.name || ''; }
function toolArgs(tc) { return parseArgs(tc?.function?.arguments || JSON.stringify(tc?.input || {})); }
function resultFor(name, args, marker) {
  const lower = String(name).toLowerCase();
  if (lower.includes('write') || lower.includes('edit') || lower.includes('save')) {
    const p = path.resolve(tmpRoot, path.basename(args.path || args.file_path || 'smoke.txt'));
    fs.writeFileSync(p, String(args.content || marker));
    return `wrote ${p}`;
  }
  if (lower.includes('read')) {
    const p = path.resolve(tmpRoot, path.basename(args.path || args.file_path || 'smoke.txt'));
    return fs.existsSync(p) ? fs.readFileSync(p, 'utf8') : marker;
  }
  return marker;
}
async function postOpenAI(profileName, profile, stream=false) {
  const messages = [{ role:'user', content: profile.prompt }];
  const resp = await fetch(`${base}/v1/chat/completions`, { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({ model, user:`agent-${profileName}`, messages, tools:profile.tools, tool_choice:'auto', stream }) });
  if (stream) {
    const raw = await resp.text();
    return { status: resp.status, raw, toolCalls: raw.includes('tool_calls') ? ['stream-tool-calls-present'] : [] };
  }
  const json = await resp.json();
  const calls = json.choices?.[0]?.message?.tool_calls || [];
  if (calls.length) {
    const marker = `${profileName.toUpperCase()}_TOOL_USE_OK`;
    const tc = calls[0];
    const output = resultFor(toolName(tc), toolArgs(tc), marker);
    messages.push({ role:'assistant', content:null, tool_calls:calls });
    messages.push({ role:'tool', tool_call_id:tc.id, content:output });
    const follow = await fetch(`${base}/v1/chat/completions`, { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({ model, user:`agent-${profileName}`, messages, tools:profile.tools, tool_choice:'auto' }) });
    const followJson = await follow.json();
    return { status: resp.status, finish_reason: json.choices?.[0]?.finish_reason, tool_calls: calls.map(c => ({ name: toolName(c), arguments: toolArgs(c) })), follow_status: follow.status, follow_finish_reason: followJson.choices?.[0]?.finish_reason, follow_content: followJson.choices?.[0]?.message?.content };
  }
  return { status: resp.status, finish_reason: json.choices?.[0]?.finish_reason, content: json.choices?.[0]?.message?.content, tool_calls: [] };
}
async function postAnthropic(profileName, profile) {
  const resp = await fetch(`${base}/v1/messages`, { method:'POST', headers:{'Content-Type':'application/json','x-api-key':'dummy','anthropic-version':'2023-06-01'}, body:JSON.stringify({ model, max_tokens:1024, messages:[{role:'user', content:profile.prompt}], tools:profile.tools, metadata:{user_id:`agent-${profileName}`} }) });
  const json = await resp.json();
  const uses = (json.content || []).filter(c => c.type === 'tool_use');
  return { status: resp.status, stop_reason: json.stop_reason, tool_uses: uses.map(u => ({ name:u.name, input:u.input })) };
}

const names = selected === 'all' ? Object.keys(profiles) : [selected];
const results = [];
for (const name of names) {
  const profile = profiles[name];
  if (!profile) throw new Error(`Unknown agent profile ${name}`);
  const result = profile.protocol === 'anthropic' ? await postAnthropic(name, profile) : await postOpenAI(name, profile, process.env.STREAM === '1');
  const ok = (result.tool_calls?.length || result.tool_uses?.length || result.toolCalls?.length) > 0;
  results.push({ kind:name, ok, ...result });
  if (!ok) process.exitCode = 1;
}
console.log(JSON.stringify({ model, base, tmpRoot, results }, null, 2));
