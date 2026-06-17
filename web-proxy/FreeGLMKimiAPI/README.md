# FreeGLMKimiAPI

OpenAI/Anthropic-compatible локальный прокси для бесплатных web-аккаунтов **GLM/Z.ai**, legacy **chatglm.cn** и **Kimi**. По духу — как FreeQwenApi / FreeDeepseekAPI, но отдельным проектом и с эмуляцией tool use для AI-агентов.

## Навигация

- [Что умеет](#что-умеет)
- [Быстрый старт](#быстрый-старт)
- [Модели](#модели)
- [Как добавить аккаунты](#как-добавить-аккаунты)
- [Как получить токены](#как-получить-токены)
  - [GLM / Z.ai через браузер — рекомендуемый способ](#glm--zai-через-браузер--рекомендуемый-способ)
  - [GLM / Z.ai вручную из DevTools](#glm--zai-вручную-из-devtools)
  - [Legacy GLM / chatglm.cn](#legacy-glm--chatglmcn)
  - [Kimi](#kimi)
- [Примеры запросов](#примеры-запросов)
- [Tool use для агентов](#tool-use-для-агентов)
- [Диагностика](#диагностика)
- [Ограничения](#ограничения)

## Что умеет

- `/v1/chat/completions` — OpenAI-compatible chat, streaming и non-streaming.
- `/v1/messages` — минимальный Anthropic Messages shim для Claude Code и похожих клиентов.
- `/v1/models`, `/health`, `/sessions`.
- GLM через два backend-а:
  - актуальный `chat.z.ai` / Z.ai;
  - legacy `chatglm.cn` через `GLM_BACKEND=chatglm`.
- Kimi через `kimi.com` gRPC-Web endpoint.
- Prompt-based эмуляция tool use:
  - прокси инжектит инструкции для function calling;
  - парсит `[function_calls]`, JSON, XML-ish и legacy `TOOL_CALL` ответы;
  - возвращает OpenAI-compatible `tool_calls`.
- Sticky-сессии по `user`/agent id.
- Round-robin по аккаунтам и cooldown после ошибок провайдера.
- `MOCK_PROVIDER=1` для локальных тестов без реальных токенов.

## Быстрый старт

```bash
git clone https://github.com/ForgetMeAI/FreeGLMKimiAPI.git
cd FreeGLMKimiAPI
npm install
cp .env.example .env
npm test
```

Запуск без реальных токенов, чтобы проверить API-обвязку:

```bash
MOCK_PROVIDER=1 PORT=9766 npm start
```

Проверка:

```bash
curl http://127.0.0.1:9766/health
curl http://127.0.0.1:9766/v1/models
node scripts/smoke.js
```

## Модели

GLM:

- `glm-5`
- `glm-5-thinking`
- `glm-5-search`
- `glm-5-deepresearch`

Kimi:

- `kimi-k2.5`
- `kimi-k2.5-thinking`
- `kimi-k2.5-search`

Выбор провайдера идёт по имени модели:

- `glm*` → GLM;
- `kimi*` → Kimi.

По умолчанию:

```env
DEFAULT_PROVIDER=kimi
DEFAULT_MODEL=kimi-k2.5
```

## Как добавить аккаунты

Токены — это секреты уровня пароля. Не коммить `auth.json`, не публикуй токены и не открывай сервис наружу без `API_KEYS`.

### Вариант 1: `auth.json` — удобнее для нескольких аккаунтов

Создай `auth.json` рядом с проектом:

```json
{
  "accounts": [
    { "id": "zai1", "provider": "glm", "token": "PASTE_ZAI_TOKEN_HERE" },
    { "id": "glm-cn1", "provider": "glm", "backend": "chatglm", "refresh_token": "PASTE_CHATGLM_REFRESH_TOKEN_HERE" },
    { "id": "kimi1", "provider": "kimi", "token": "PASTE_KIMI_TOKEN_HERE" }
  ]
}
```

И запусти:

```bash
npm start
```

Можно указать другой путь:

```bash
AUTH_PATH=/path/to/auth.json npm start
```

### Вариант 2: `.env` — проще для одного аккаунта

```env
# Kimi
KIMI_TOKEN=PASTE_KIMI_TOKEN_HERE

# GLM через Z.ai
GLM_BACKEND=zai
GLM_TOKEN=PASTE_ZAI_TOKEN_HERE

# Legacy GLM через chatglm.cn
# GLM_BACKEND=chatglm
# GLM_REFRESH_TOKEN=PASTE_CHATGLM_REFRESH_TOKEN_HERE
```

### Вариант 3: Admin API — добавить без рестарта

Если `API_KEYS` задан, admin-запросы тоже требуют HTTP-заголовок авторизации с твоим API key.

```bash
# список аккаунтов без секретов
curl http://127.0.0.1:9766/admin/accounts

# добавить Kimi временно, без записи в auth.json
curl -X POST http://127.0.0.1:9766/admin/accounts \
  -H 'Content-Type: application/json' \
  -d '{"id":"kimi2","provider":"kimi","token":"KIMI_TOKEN_HERE","persist":false}'

# добавить GLM/Z.ai и сохранить в auth.json
curl -X POST http://127.0.0.1:9766/admin/accounts \
  -H 'Content-Type: application/json' \
  -d '{"id":"zai2","provider":"glm","token":"ZAI_TOKEN_HERE","persist":true}'

# перечитать auth.json
curl -X POST http://127.0.0.1:9766/admin/accounts/reload -d '{}'
```

## Как получить токены

### GLM / Z.ai через браузер — рекомендуемый способ

Это самый простой путь для GLM. Скрипт сам откроет видимый браузер, дождётся логина, вытащит токен и сохранит `auth.json`.

```bash
cd FreeGLMKimiAPI
npm run auth:browser -- ./auth.json
```

Что делать дальше:

1. Откроется окно браузера с `chat.z.ai`.
2. Войди в свой аккаунт.
3. Если появится проверка/captcha — пройди её руками.
4. Отправь в чате короткое сообщение, например `hi`.
5. Вернись в терминал и дождись, пока скрипт сохранит `auth.json`.

Проверка:

```bash
ZAI_BROWSER_FALLBACK=1 MODEL=GLM-5.1 npm run smoke:zai
```

Запуск сервера через этот профиль:

```bash
ZAI_BROWSER_FALLBACK=1 MODEL=GLM-5.1 npm start
```

Важно:

- профиль браузера переиспользуется, поэтому логин не нужен каждый раз;
- если Z.ai снова просит проверку — повтори `npm run auth:browser -- ./auth.json` и пройди её в том же окне;
- скрипт игнорирует временные guest-токены вида `guest-...@guest.com` и ждёт реальный аккаунт;
- если обычный browser fallback ловит anti-bot, можно попробовать CloakBrowser:

```bash
ZAI_BROWSER_ENGINE=cloak \
ZAI_BROWSER_FALLBACK=1 \
ZAI_BROWSER_HEADLESS=0 \
ZAI_BROWSER_HUMANIZE=1 \
MODEL=GLM-5.1 npm run smoke:zai
```

Полезные переменные:

```env
ZAI_BROWSER_FALLBACK=1
ZAI_BROWSER_ENGINE=puppeteer # или cloak
ZAI_BROWSER_PROFILE_DIR=~/.free-glm-kimi-api/zai-browser-profile
ZAI_BROWSER_PROXY=http://user:pass@host:port
ZAI_BROWSER_LOCALE=ru-RU
ZAI_BROWSER_TIMEZONE=Europe/Samara
```

### GLM / Z.ai вручную из DevTools

Если браузерный скрипт не сработал, можно скопировать токен руками.

Простой вариант через Application:

1. Открой `https://chat.z.ai/` и залогинься.
2. Открой DevTools: `F12` или `Cmd+Option+I`.
3. Перейди в **Application**.
4. Проверь:
   - Local Storage → `https://chat.z.ai` → ключ `token`;
   - Cookies → `chat.z.ai` → cookie `token`.
5. Скопируй только значение токена, без `Bearer` и без `token=`.
6. Вставь в `auth.json`:

```json
{
  "accounts": [
    { "id": "zai1", "provider": "glm", "token": "PASTE_ZAI_TOKEN_HERE" }
  ]
}
```

Если Z.ai требует captcha/anti-bot, одного JWT может быть мало. Тогда проще вернуться к browser fallback. Для диагностики можно добавить cookie и captcha-параметр:

```json
{
  "accounts": [
    {
      "id": "zai1",
      "provider": "glm",
      "token": "PASTE_ZAI_TOKEN_HERE",
      "cookie": "cdn_sec_tc=...; acw_tc=...; ssxmod_itna=...; token=...",
      "captcha_verify_param": "PASTE_BASE64_CAPTCHA_VERIFY_PARAM_HERE"
    }
  ]
}
```

### Legacy GLM / chatglm.cn

Это отдельный старый backend. Токен от `chat.z.ai` сюда не подходит.

Нужно получить именно `chatglm.cn` refresh token:

1. Открой `https://chatglm.cn/` и залогинься.
2. Открой DevTools → **Application**.
3. Проверь Local Storage / Cookies для `chatglm.cn`.
4. Ищи `chatglm_refresh_token`, `refresh_token` или похожий refresh token.
5. Если не нашёл — DevTools → **Network**, отправь сообщение и найди запросы:
   - `/user-api/user/refresh`;
   - `/backend-api/assistant/stream`.
6. В заголовке `Authorization` скопируй только значение после слова `Bearer`.

Формат:

```json
{
  "accounts": [
    {
      "id": "glm-cn1",
      "provider": "glm",
      "backend": "chatglm",
      "refresh_token": "PASTE_CHATGLM_REFRESH_TOKEN_HERE"
    }
  ]
}
```

Запуск:

```bash
GLM_BACKEND=chatglm npm start
```

Проверка:

```bash
MODEL=glm-5 node scripts/smoke.js
```

Если видишь `40102 unauthorized user`, значит токен не от `chatglm.cn`, протух или скопирован не полностью.

### Kimi

Kimi использует Bearer/access JWT из `kimi.com`.

Самый надёжный способ:

1. Открой `https://www.kimi.com/` и залогинься.
2. DevTools → **Network**.
3. В фильтре введи `ChatService/Chat` или `kimi.gateway.chat`.
4. Отправь короткое сообщение в Kimi.
5. Открой запрос к `/apiv2/kimi.gateway.chat.v1.ChatService/Chat`.
6. В **Request Headers** найди заголовок `Authorization`.
7. Скопируй только часть после `Bearer `.

Формат:

```json
{
  "accounts": [
    { "id": "kimi1", "provider": "kimi", "token": "PASTE_KIMI_BEARER_TOKEN_HERE" }
  ]
}
```

Или через `.env`:

```env
KIMI_TOKEN=PASTE_KIMI_BEARER_TOKEN_HERE
```

Если получил `401` / `auth.token.invalid`, обнови страницу Kimi, отправь новое сообщение и скопируй свежий Bearer.

## Примеры запросов

Чтобы README не превращался в простыню, примеры вынесены отдельно:

- [docs/request-examples.md](docs/request-examples.md)

Там есть:

- health/models;
- обычный `/v1/chat/completions`;
- streaming;
- GLM smoke;
- OpenAI tools/function calling;
- `/v1/messages` Anthropic shape;
- Claude Code;
- OpenCode;
- локальные agent smoke-тесты.

## Tool use для агентов

Клиент отправляет обычные OpenAI `tools`. Если web-модель отвечает протокольным текстом, прокси превращает его в OpenAI-compatible `tool_calls`:

```json
{
  "choices": [
    {
      "message": {
        "role": "assistant",
        "content": null,
        "tool_calls": []
      },
      "finish_reason": "tool_calls"
    }
  ]
}
```

Локальные protocol-level agent smoke-тесты без реальных токенов:

```bash
MOCK_PROVIDER=1 PORT=9766 npm start
npm run agent:all
```

Отдельно:

```bash
npm run agent:hermes
npm run agent:claude
npm run agent:opencode
npm run agent:openclaw
```

## Диагностика

```bash
npm test
node scripts/doctor.js
curl http://127.0.0.1:9766/health
curl http://127.0.0.1:9766/admin/accounts
```

Реальный smoke Z.ai:

```bash
ZAI_BROWSER_FALLBACK=1 MODEL=GLM-5.1 npm run smoke:zai
```

Импорт successful browser curl для диагностики Z.ai:

```bash
pbpaste | node scripts/import_zai_curl.js /dev/stdin /tmp/freeglm-auth.json
AUTH_PATH=/tmp/freeglm-auth.json MODEL=GLM-5.1 npm run smoke:zai
```

Скрипты печатают только статус и наличие полей, сами секреты не выводят.

## Ограничения

- Это не официальный API. Web API GLM/Z.ai/Kimi могут меняться.
- Для настоящего E2E нужны живые web-токены.
- Z.ai может требовать captcha/anti-bot cookies; тогда лучше использовать browser fallback.
- `chat.z.ai` и `chatglm.cn` — разные backend-и, токены между ними не взаимозаменяемы.
- Tool use — эмуляция через prompt-протокол, а не нативный function calling web-модели.
- Реализация сверялась по Chat2API и покрыта локальными мок-тестами, но upstream может сломаться после очередного обновления фронта.
