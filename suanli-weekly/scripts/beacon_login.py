#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
灯塔(Beacon)登录脚本 — Cookie 注入登录 + 公共函数。

此脚本提供:
  1. Cookie 注入登录功能 (login_with_cookie)
  2. 登录页面检测公共函数 (is_login_page)
  3. Cookie 字符串解析 (parse_cookie_string)

扫码登录功能已迁移至 beacon_qr_server.py。

使用方法:
  python3 beacon_login.py --cookie "key1=val1; key2=val2; ..." --output /path/to/auth_state.json
  python3 beacon_login.py --cookie-file /path/to/cookies.txt --output /path/to/auth_state.json

获取 Cookie 方法:
  1. 在本地浏览器打开 https://beacon.woa.com 并完成 OA 登录
  2. F12 → Network → 刷新页面 → 点击任意请求
  3. 在 Request Headers 中找到 Cookie: 行，复制完整值
"""

import argparse
import json
import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

# Skill 目录（scripts/ 的上级目录）
SKILL_DIR = Path(__file__).resolve().parent.parent
RUNTIME_DIR = SKILL_DIR / "runtime"


DEFAULT_VERIFY_URL = "https://beacon.woa.com/datainsight/pc_yyb_client"


def log(msg: str):
    try:
        sys.stdout.write(msg + "\n")
        sys.stdout.flush()
    except UnicodeEncodeError:
        safe_msg = msg.encode("ascii", errors="replace").decode("ascii")
        sys.stdout.write(safe_msg + "\n")
        sys.stdout.flush()


def parse_cookie_string(cookie_str: str) -> list:
    """解析 Cookie 字符串为 Playwright 格式的 cookie 列表"""
    cookies = []
    for pair in cookie_str.split(";"):
        pair = pair.strip()
        if "=" in pair:
            name, value = pair.split("=", 1)
            name, value = name.strip(), value.strip()
            if name and value:
                cookies.append({
                    "name": name,
                    "value": value,
                    "domain": ".woa.com",
                    "path": "/",
                })
    return cookies


def is_login_page(page) -> bool:
    """检测当前是否被重定向到了登录页面"""
    url = page.url.lower()
    login_keywords = ["login", "passport", "auth", "signin", "sso", "cas"]
    if any(kw in url for kw in login_keywords):
        return True
    try:
        body_text = page.inner_text("body")
        indicators = [
            "Account ID", "PIN + TOKEN", "Sign in", "登录", "验证码",
            "Scan the QR code", "iOA Mobile", "Tencent 腾讯"
        ]
        if sum(1 for ind in indicators if ind in body_text) >= 2:
            return True
    except Exception:
        pass
    return False


def login_with_cookie(cookie_str: str, output_path: Path, verify_url: str = None) -> bool:
    """通过 Cookie 注入登录灯塔并保存认证状态"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    verify_url = verify_url or DEFAULT_VERIFY_URL

    cookies = parse_cookie_string(cookie_str)
    if not cookies:
        log("❌ Cookie 解析失败，未找到有效的 Cookie 对")
        return False

    log(f"✅ 解析到 {len(cookies)} 个 Cookie")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-setuid-sandbox"])
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0.0.0 Safari/537.36",
        )

        page = context.new_page()
        log("🌐 建立连接...")
        try:
            page.goto("https://beacon.woa.com", wait_until="domcontentloaded", timeout=30000)
        except Exception:
            pass
        time.sleep(2)

        # 注入多域名 Cookie
        log("🍪 注入 Cookie...")
        all_cookies = []
        for domain in [".woa.com", "beacon.woa.com", ".beacon.woa.com"]:
            for c in cookies:
                all_cookies.append({**c, "domain": domain})
        try:
            context.add_cookies(all_cookies)
            log(f"   已注入 {len(all_cookies)} 条")
        except Exception:
            success = 0
            for c in all_cookies:
                try:
                    context.add_cookies([c])
                    success += 1
                except Exception:
                    pass
            log(f"   逐条注入成功 {success}/{len(all_cookies)}")

        # 验证登录态
        log(f"🌐 验证登录态: {verify_url}")
        try:
            page.goto(verify_url, wait_until="domcontentloaded", timeout=60000)
        except Exception as e:
            log(f"   ⚠️ 页面加载超时: {e}")
        time.sleep(8)

        if is_login_page(page):
            log("❌ 登录验证失败！仍在登录页。Cookie 可能已过期，请重新获取。")
            browser.close()
            return False

        log(f"✅ 登录验证成功！当前 URL: {page.url}")

        # 保存认证状态
        time.sleep(3)
        storage = context.storage_state()
        output_path.write_text(json.dumps(storage, ensure_ascii=False, indent=2), encoding="utf-8")
        log(f"💾 认证状态已保存: {output_path}")

        browser.close()

    return True


def main():
    parser = argparse.ArgumentParser(description="灯塔登录助手 (Cookie 注入)")
    parser.add_argument("--cookie", "-c", type=str, help="Cookie 字符串")
    parser.add_argument("--cookie-file", "-f", type=str, help="Cookie 文件路径")
    default_output = str(RUNTIME_DIR / "beacon_auth_state.json")
    parser.add_argument("--output", "-o", type=str, default=default_output,
                        help=f"认证状态输出路径 (默认: {default_output})")
    parser.add_argument("--verify-url", type=str, default=None,
                        help="验证登录态的 URL")
    args = parser.parse_args()

    output_path = Path(args.output).resolve()

    if args.cookie:
        cookie_str = args.cookie
    elif args.cookie_file:
        p = Path(args.cookie_file)
        if not p.exists():
            log(f"❌ Cookie 文件不存在: {p}")
            sys.exit(1)
        cookie_str = p.read_text(encoding="utf-8").strip()
    else:
        log("❌ 请通过 --cookie 或 --cookie-file 参数提供 Cookie")
        log("   扫码登录请使用 beacon_qr_server.py --start")
        sys.exit(1)

    # 清理可能复制到的前缀
    if cookie_str.lower().startswith("cookie:"):
        cookie_str = cookie_str[7:].strip()

    ok = login_with_cookie(cookie_str, output_path, args.verify_url)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
