import test from 'node:test';
import assert from 'node:assert/strict';
import { parseToolCallsFromText, toolsToPrompt } from '../src/tooling.js';

test('parses bracket tool call protocol', () => {
  const parsed=parseToolCallsFromText('[function_calls]\n[call:default_api:write_file]{"path":"a.txt","content":"hi"}[/call]\n[/function_calls]');
  assert.equal(parsed.toolCalls.length, 1);
  assert.equal(parsed.toolCalls[0].function.name, 'default_api:write_file');
  assert.deepEqual(JSON.parse(parsed.toolCalls[0].function.arguments), {path:'a.txt',content:'hi'});
});

test('parses json tool call protocol', () => {
  const parsed=parseToolCallsFromText('{"tool_call":{"name":"read_file","arguments":{"path":"/tmp/a"}}}');
  assert.equal(parsed.toolCalls[0].function.name, 'read_file');
});

test('tools prompt preserves exact prefixed names', () => {
  const prompt=toolsToPrompt([{type:'function',function:{name:'default_api:read_file',parameters:{type:'object'}}}]);
  assert.match(prompt, /CASE-SENSITIVE/);
  assert.match(prompt, /default_api:read_file/);
});
