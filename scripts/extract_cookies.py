#!/usr/bin/env python3
"""Extract cookies from Yandex Browser for Web Proxy auth."""
import sqlite3, shutil, tempfile, json, sys
from pathlib import Path
from datetime import datetime

DB = Path.home() / ".config/yandex-browser/Default/Cookies"
PROXY_DIR = Path(__file__).resolve().parent / "web-proxy"

DOMAINS = {
    "deepseek.com": ("FreeDeepseekAPI/deepseek-auth.json", "DeepSeek"),
    "z.ai": ("FreeGLMKimiAPI/auth.json", "GLM/z.ai"),
    "moonshot.cn": ("FreeGLMKimiAPI/kimi-auth.json", "Kimi/moonshot"),
    "kimi.ai": ("FreeGLMKimiAPI/kimi-auth.json", "Kimi"),
    "tongyi.aliyun.com": ("FreeQwenApi/qwen-auth.json", "Qwen"),
    "qwen.ai": ("FreeQwenApi/qwen-auth.json", "Qwen"),
}

tmp = Path(tempfile.mktemp(suffix=".db"))
shutil.copy2(str(DB), str(tmp))

conn = sqlite3.connect(str(tmp))
conn.row_factory = sqlite3.Row

# Get all cookies
cur = conn.execute("SELECT host_key, name, value, encrypted_value, is_secure, path, expires_utc FROM cookies")
all_rows = cur.fetchall()
conn.close()
tmp.unlink()

print(f"Total cookies in DB: {len(all_rows)}")

# Filter by domain
found = {}
for row in all_rows:
    host = row["host_key"]
    for domain, (out_path, label) in DOMAINS.items():
        if domain in host:
            if domain not in found:
                found[domain] = {"label": label, "out": out_path, "cookies": []}
            cookie = {
                "name": row["name"],
                "value": row["value"],
                "domain": f".{host}",
                "secure": bool(row["is_secure"]),
                "path": row["path"] or "/",
            }
            if row["encrypted_value"]:
                cookie["encrypted_value"] = row["encrypted_value"].hex()
            found[domain]["cookies"].append(cookie)

# Save
for domain, data in found.items():
    out = PROXY_DIR / data["out"]
    out.parent.mkdir(parents=True, exist_ok=True)
    
    cookies = data["cookies"]
    plain = [c for c in cookies if c.get("value")]
    encrypted = [c for c in cookies if not c.get("value") and c.get("encrypted_value")]
    
    result = {
        "cookies": plain,
        "cookie": "; ".join(f"{c['name']}={c['value']}" for c in plain),
        "extracted_at": datetime.now().isoformat(),
        "domain": domain,
        "total": len(cookies),
        "plain": len(plain),
        "encrypted": len(encrypted),
    }
    
    with open(out, "w") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    
    status = "OK" if plain else "ENCRYPTED ONLY"
    print(f"[{status}] {data['label']}: {len(plain)} plain, {len(encrypted)} encrypted -> {out.name}")

# Summary
print("\n=== Summary ===")
for domain, (out_path, label) in DOMAINS.items():
    out = PROXY_DIR / out_path
    if out.exists():
        with open(out) as f:
            d = json.load(f)
        print(f"  [OK] {label}: {d.get('plain', 0)} cookies")
    else:
        print(f"  [MISSING] {label}: no cookies found")
