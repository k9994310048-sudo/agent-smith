# CloakBrowser notes for FreeGLMKimiAPI

Studied references:

- `https://github.com/CloakHQ/CloakBrowser` at `b06499b`
- `https://github.com/CloakHQ/CloakBrowser-Manager` at `a85b213`

## Useful ideas

1. **Use a real patched browser when anti-bot is the boundary.** CloakBrowser is not just JS stealth injection; it ships a patched Chromium binary and exposes Playwright-compatible `launchPersistentContext()`.
2. **Persistent non-incognito profiles matter.** CloakBrowser and Manager prefer persistent user data dirs, which keeps cookies/localStorage and avoids incognito-style detection penalties.
3. **Humanized UI interactions are part of the fallback.** Their `humanize` layer types/clicks/scrolls with realistic delays and trusted input paths. For Z.ai this is most relevant when direct browser-context `fetch()` falls into captcha/WAF and we must send through the visible UI.
4. **Locale/timezone/proxy consistency matters.** CloakBrowser routes timezone/locale via browser flags and can align them with a proxy IP (`geoip`). For Z.ai, this is exposed through env vars instead of hard-coding one fingerprint.
5. **Clean stale profile locks.** Manager removes `SingletonLock`, `SingletonCookie`, and `SingletonSocket` before launch so crashed browser sessions do not poison the profile.

## Applied in this project

- Added optional `ZAI_BROWSER_ENGINE=cloak` mode for browser fallback.
- Added `cloakbrowser` + `playwright-core` dependencies.
- Kept default engine as `puppeteer` to avoid forcing a 200MB CloakBrowser binary download on every user.
- Cloak mode uses a separate default profile (`~/.free-glm-kimi-api/zai-cloak-profile`) so it does not crash on a profile previously created by stock Chrome/Puppeteer.
- Cloak mode uses `launchPersistentContext()` with:
  - `userDataDir` = `ZAI_BROWSER_PROFILE_DIR` / default Z.ai profile
  - `humanize` default enabled
  - locale/timezone/proxy/geoip env support
  - persistent non-incognito profile
- Added stale lock cleanup for both engines.
- Changed UI fallback prompt entry from direct value assignment to click/select/type with randomized delays where supported.
- Expanded captcha/WAF classification for Aliyun/WAF markers.

## Runtime knobs

```bash
ZAI_BROWSER_ENGINE=cloak \
ZAI_BROWSER_FALLBACK=1 \
ZAI_BROWSER_HEADLESS=0 \
ZAI_BROWSER_HUMANIZE=1 \
MODEL=GLM-5.1 npm run smoke:zai
```

Optional:

- `ZAI_BROWSER_PROFILE_DIR=...`
- `ZAI_BROWSER_PROXY=http://user:pass@host:port` or `socks5://...`
- `ZAI_BROWSER_GEOIP=1`
- `ZAI_BROWSER_LOCALE=ru-RU`
- `ZAI_BROWSER_TIMEZONE=Europe/Samara`
- `ZAI_BROWSER_ARGS="--flag=value ..."`

## Caveat

CloakBrowser can reduce automation fingerprints and prevent some challenges, but it does not solve an already-triggered account/IP captcha by magic. If Z.ai requires manual verification, open the same persistent profile headed and pass the check once.
