# Примеры запросов

Все примеры ниже предполагают, что сервер запущен локально:

```bash
npm start
# по умолчанию: http://127.0.0.1:9766
```

Если включил `API_KEYS`, добавляй заголовок:

```bash
-H 'Authorization: Bearer YOUR_PROXY_API_KEY'
```

## Health и список моделей

```bash
curl http://127.0.0.1:9766/health
curl http://127.0.0.1:9766/v1/models
```

## Обычный OpenAI-compatible chat

```bash
curl http://127.0.0.1:9766/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "kimi-k2.5",
    "messages": [
      {"role": "user", "content": "Ответь одной фразой: привет"}
    ]
  }'
```

## Streaming

```bash
curl -N http://127.0.0.1:9766/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "kimi-k2.5",
    "stream": true,
    "messages": [
      {"role": "user", "content": "Коротко объясни, что такое MCP"}
    ]
  }'
```

## GLM через Z.ai

```bash
curl http://127.0.0.1:9766/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "glm-5",
    "messages": [
      {"role": "user", "content": "Reply exactly: GLM_OK"}
    ]
  }'
```

Если используешь browser fallback:

```bash
ZAI_BROWSER_FALLBACK=1 MODEL=GLM-5.1 npm run smoke:zai
```

## Tool use / function calling

Web-модели обычно не имеют нативных tools, поэтому прокси эмулирует tool calling через prompt-протокол и возвращает OpenAI-compatible `tool_calls`.

```bash
curl http://127.0.0.1:9766/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "kimi-k2.5",
    "messages": [
      {"role": "user", "content": "Создай файл hello.txt с текстом hello"}
    ],
    "tools": [
      {
        "type": "function",
        "function": {
          "name": "write_file",
          "description": "Write a text file",
          "parameters": {
            "type": "object",
            "properties": {
              "path": {"type": "string"},
              "content": {"type": "string"}
            },
            "required": ["path", "content"]
          }
        }
      }
    ],
    "tool_choice": "auto"
  }'
```

Ожидаемая форма ответа при вызове инструмента:

```json
{
  "choices": [
    {
      "message": {
        "role": "assistant",
        "content": null,
        "tool_calls": [
          {
            "type": "function",
            "function": {
              "name": "write_file",
              "arguments": "{\"path\":\"hello.txt\",\"content\":\"hello\"}"
            }
          }
        ]
      },
      "finish_reason": "tool_calls"
    }
  ]
}
```

## Anthropic Messages API / Claude Code shape

```bash
curl http://127.0.0.1:9766/v1/messages \
  -H 'Content-Type: application/json' \
  -H 'x-api-key: dummy' \
  -H 'anthropic-version: 2023-06-01' \
  -d '{
    "model": "kimi-k2.5",
    "max_tokens": 1024,
    "messages": [
      {"role": "user", "content": "Reply exactly: CLAUDE_SHAPE_OK"}
    ]
  }'
```

## Claude Code CLI

```bash
ANTHROPIC_BASE_URL=http://127.0.0.1:9766 \
ANTHROPIC_API_KEY=dummy \
ANTHROPIC_MODEL=kimi-k2.5 \
claude --bare -p 'Reply exactly: CLAUDE_SMOKE_OK' --model kimi-k2.5 --output-format json
```

## OpenCode

```bash
export OPENCODE_CONFIG_CONTENT='{"$schema":"https://opencode.ai/config.json","provider":{"free-glm-kimi":{"npm":"@ai-sdk/openai-compatible","name":"FreeGLMKimiAPI","options":{"baseURL":"http://127.0.0.1:9766/v1","apiKey":"dummy"},"models":{"kimi-k2.5":{"name":"kimi-k2.5"},"glm-5":{"name":"glm-5"}}}}}'

opencode run 'Reply exactly: OPENCODE_SMOKE_OK' \
  --model free-glm-kimi/kimi-k2.5 \
  --agent build
```

## Локальные smoke-тесты без реальных токенов

```bash
MOCK_PROVIDER=1 PORT=9766 npm start
npm run agent:all
npm run agent:hermes
npm run agent:claude
npm run agent:opencode
npm run agent:openclaw
```
