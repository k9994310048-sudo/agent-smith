import { parseToolCallsFromText } from './tooling.js';

export async function mockComplete({ prompt, model, tools }) {
  const m = prompt.match(/Reply exactly:\s*([^\n]+)/i) || prompt.match(/Ответь ровно:\s*([^\n]+)/i);
  if (m) return m[1].trim();
  if (/\[TOOL_RESULT for /i.test(prompt)) return 'done';
  if (tools?.length && /tool|file|read|write|create|созда|файл|команд|run|execute/i.test(prompt)) {
    const fn = tools[0].function || tools[0];
    let args = {};
    if (/bash|terminal|shell|run/i.test(fn.name || '') || /command|команд|run|execute/i.test(prompt)) args = { command: `printf ${String(fn.name || 'TOOL').toUpperCase().replace(/[^A-Z0-9]+/g, '_')}_OK` };
    else if (/write|edit|save/i.test(fn.name || '') || /create|созда/i.test(prompt)) args = { path: '/tmp/fgk_agent_tool.txt', file_path: '/tmp/fgk_agent_tool.txt', content: 'OK' };
    else if (/read/i.test(fn.name || '')) args = { path: '/tmp/fgk_agent_tool.txt', file_path: '/tmp/fgk_agent_tool.txt' };
    return `[function_calls]\n[call:${fn.name}]${JSON.stringify(args)}[/call]\n[/function_calls]`;
  }
  return `MOCK ${model}: ${prompt.slice(-300)}`;
}

export async function mockStream(args) {
  const text = await mockComplete(args);
  return text;
}
