#!/usr/bin/env python3
"""
auto_auth.py — collect browser cookies for Web Proxy.
Decrypts Chrome/Chromium/Yandex cookies via secretstorage (GNOME Keyring).
"""

import os
import sys
import json
import sqlite3
import shutil
import tempfile
import subprocess
from pathlib import Path
from datetime import datetime

PROXY_DIR = Path(__file__).resolve().parent.parent / "web-proxy"


def _get_chrome_key():
    """Get Chrome/Chromium/Yandex encryption key from GNOME Keyring."""
    try:
        import secretstorage
        bus = secretstorage.dbus_init()
        collection = secretstorage.get_default_collection(bus)
        for item in collection.get_all_items():
            if "Chrome" in item.get_label() or "Chromium" in item.get_label() or "Yandex" in item.get_label():
                return item.get_secret()
    except Exception as e:
        print(f"  secretstorage error: {e}")
    # Fallback: try to get from local state
    local_state_paths = [
        Path("~/.config/google-chrome/Local State").expanduser(),
        Path("~/.config/chromium/Local State").expanduser(),
        Path("~/.config/yandex-browser/Local State").expanduser(),
    ]
    for ls_path in local_state_paths:
        if ls_path.exists():
            try:
                with open(ls_path) as f:
                    data = json.load(f)
                encrypted_key_b64 = data.get("os_crypt", {}).get("encrypted_key", "")
                if encrypted_key_b64:
                    import base64
                    encrypted_key = base64.b64decode(encrypted_key_b64)
                    # Remove DPAPI prefix
                    if encrypted_key[:5] == b"DPAPI":
                        encrypted_key = encrypted_key[5:]
                    # On Linux, use secretstorage or decrypt via dbus
                    print(f"  Found encrypted key in {ls_path.name}, need decryption")
            except Exception as e:
                print(f"  Local State error: {e}")
    return None


def _decrypt_cookie(encrypted_value, key):
    """Decrypt a Chrome/Chromium/Yandex cookie value."""
    if not key or not encrypted_value:
        return ""
    try:
        # Chrome 80+ uses AES-256-GCM with key derived from PBKDF2
        # v10/v11 prefix = AES-CBC with SHA1
        if encrypted_value[:3] == b"v10" or encrypted_value[:3] == b"v11":
            import hashlib
            from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
            from cryptography.hazmat.primitives import padding
            # Derive key using PBKDF2
            derived = hashlib.pbkdf2_hmac("sha1", key, b"saltysalt", 1, dk_len=16)
            iv = b" " * 16
            encrypted = encrypted_value[3:]
            cipher = Cipher(algorithms.AES(derived), modes.CBC(iv))
            decryptor = cipher.decryptor()
            decrypted = decryptor.update(encrypted) + decryptor.finalize()
            # Remove PKCS7 padding
            pad_len = decrypted[-1]
            if isinstance(pad_len, int) and 1 <= pad_len <= 16:
                decrypted = decrypted[:-pad_len]
            return decrypted.decode("utf-8", errors="replace")
        else:
            # Try direct decryption (older Chrome)
            return encrypted_value.decode("utf-8", errors="replace")
    except Exception as e:
        return ""


def _collect_cookies(db_path, domain, key):
    """Extract and decrypt cookies from a Chrome-like cookie DB."""
    tmp = Path(tempfile.mktemp(suffix=".db"))
    try:
        shutil.copy2(str(db_path), str(tmp))
        conn = sqlite3.connect(str(tmp))
        cur = conn.execute(
            "SELECT host_key, name, value, encrypted_value, is_secure, path, expires_utc "
            "FROM cookies WHERE host_key LIKE ?",
            (f"%{domain}%",),
        )
        rows = cur.fetchall()
        conn.close()
        cookies = []
        skipped = 0
        for host, name, value, enc_value, secure, path, expires in rows:
            if value:
                cookies.append({
                    "name": name,
                    "value": value,
                    "domain": f".{host}",
                    "path": path or "/",
                    "secure": bool(secure),
                })
            elif enc_value:
                decrypted = _decrypt_cookie(enc_value, key)
                if decrypted:
                    cookies.append({
                        "name": name,
                        "value": decrypted,
                        "domain": f".{host}",
                        "path": path or "/",
                        "secure": bool(secure),
                    })
                else:
                    skipped += 1
        if skipped:
            print(f"  {skipped} encrypted cookies could not be decrypted")
        return cookies
    finally:
        if tmp.exists():
            tmp.unlink()


def _save_auth(out_path, cookies, extra=None):
    """Save cookies in the format expected by ForgetMeAI proxies."""
    cookie_str = "; ".join(f"{c['name']}={c['value']}" for c in cookies)
    data = {
        "cookies": cookies,
        "cookie": cookie_str,
        "extracted_at": datetime.now().isoformat(),
    }
    if extra:
        data.update(extra)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"  Saved {len(cookies)} cookies -> {out_path.name}")


def main():
    print("=" * 60)
    print("Web Proxy Auto-Auth: collect & decrypt browser cookies")
    print("=" * 60)

    # Find cookie DBs
    cookie_dbs = []
    for pattern in [
        "~/.config/google-chrome/Default/Cookies",
        "~/.config/chromium/Default/Cookies",
        "~/.config/yandex-browser/Default/Cookies",
        "~/.config/BraveSoftware/Brave-Browser/Default/Cookies",
    ]:
        p = Path(pattern).expanduser()
        if p.exists():
            cookie_dbs.append(p)

    if not cookie_dbs:
        print("ERROR: No browser cookie database found!")
        print("Make sure you're logged into DeepSeek/GLM/Qwen in your browser.")
        sys.exit(1)

    print(f"Found cookie DBs: {[str(p) for p in cookie_dbs]}")

    # Get encryption key
    print("\nGetting encryption key...")
    key = _get_chrome_key()
    if key:
        print(f"  Key obtained: {len(key)} bytes")
    else:
        print("  WARNING: Could not get encryption key, trying without...")

    # Collect for each service
    services = [
        ("deepseek.com", "FreeDeepseekAPI/deepseek-auth.json", "DeepSeek"),
        ("z.ai", "FreeGLMKimiAPI/auth.json", "GLM / z.ai"),
        ("moonshot.cn", "FreeGLMKimiAPI/kimi-auth.json", "Kimi / moonshot"),
        ("tongyi.aliyun.com", "FreeQwenApi/qwen-auth.json", "Qwen / tongyi"),
    ]

    for domain, out_name, label in services:
        print(f"\n--- {label} ({domain}) ---")
        all_cookies = []
        for db in cookie_dbs:
            cookies = _collect_cookies(db, domain, key)
            if cookies:
                all_cookies.extend(cookies)
                print(f"  From {db.parent.parent.name}: {len(cookies)} cookies")
        if all_cookies:
            out = PROXY_DIR / out_name
            _save_auth(out, all_cookies)
        else:
            print(f"  No cookies found for {domain}")

    # Summary
    print("\n=== Summary ===")
    for name, path in [
        ("DeepSeek", PROXY_DIR / "FreeDeepseekAPI" / "deepseek-auth.json"),
        ("GLM", PROXY_DIR / "FreeGLMKimiAPI" / "auth.json"),
        ("Kimi", PROXY_DIR / "FreeGLMKimiAPI" / "kimi-auth.json"),
        ("Qwen", PROXY_DIR / "FreeQwenApi" / "qwen-auth.json"),
    ]:
        if path.exists():
            with open(path) as f:
                d = json.load(f)
            print(f"  [OK] {name}: {len(d.get('cookies', []))} cookies")
        else:
            print(f"  [MISSING] {name}")


if __name__ == "__main__":
    main()
