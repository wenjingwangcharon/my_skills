#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
灯塔(Beacon)扫码登录服务 — HTTP 优先启动 + 后台异步登录态检测。

设计目的:
  每次使用 skill 时，第一步总是启动 HTTP 服务并让 AI 调用 preview_url 打开预览窗口。
  HTTP 页面初始显示"登录态检查中..."，后台线程异步检测登录态，根据结果动态更新页面：
  - 登录有效 → 页面显示"登录有效，爬取任务即将开始..."
  - 登录失效 → 截取二维码，页面显示二维码等待用户扫码
  - 扫码成功 → 页面显示"登录成功！"

两种运行模式:
  --start: AI 调用入口。清理旧进程 → 启动 --serve 子进程 → 输出 HTTP_READY → 快速退出
  --serve: 作为子进程运行。HTTP 服务(五态页面) + 后台 Playwright CDP 登录检测线程

使用方法:
  python3 beacon_qr_server.py --start \
    --auth /path/to/beacon_auth_state.json \
    --url "https://beacon.woa.com/datainsight/..." \
    --port 18888

参数:
  --start              启动模式：清理旧资源 + 启动 HTTP 子进程 + 快速退出
  --serve              服务模式：HTTP 服务 + 后台登录检测（由 --start 自动启动，不需手动调用）
  --auth, -a           认证状态文件路径（默认: {SKILL_DIR}/runtime/beacon_auth_state.json）
  --url, -u            灯塔页面 URL（用于验证登录态）
  --port               HTTP 服务端口（默认: 18888）
  --cdp-port           Chromium CDP 远程调试端口（默认: 9222）
  --timeout            扫码超时秒数（默认: 300）

输出信号 (--start 模式):
  HTTP_READY           HTTP 服务已就绪
  HTTP_URL=X           HTTP 服务 URL

状态文件 ({SKILL_DIR}/runtime/.scan_status):
  checking             正在检查登录态
  auth_ok              登录态有效
  need_scan            需要扫码，二维码已就绪
  success              扫码成功，登录完成
  failed               扫码失败/超时
"""

import argparse
import base64
import json
import os
import signal
import subprocess
import sys
import time
import threading
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

# Skill 目录（scripts/ 的上级目录）
SKILL_DIR = Path(__file__).resolve().parent.parent
RUNTIME_DIR = SKILL_DIR / "runtime"


def log(msg: str):
    try:
        sys.stdout.write(msg + "\n")
        sys.stdout.flush()
    except UnicodeEncodeError:
        # Windows GBK 环境下 fallback：去除无法编码的 emoji
        safe_msg = msg.encode("ascii", errors="replace").decode("ascii")
        sys.stdout.write(safe_msg + "\n")
        sys.stdout.flush()


# ============================================================
# 状态管理：进程内共享变量 + 文件信号（供跨进程读取）
# ============================================================

class StatusManager:
    """管理登录检测状态。
    
    HTTP 服务和检测线程在同一进程内，通过类变量直接通信（简单可靠）。
    同时写入文件信号，供主爬取脚本跨进程读取。
    """
    _lock = threading.Lock()
    _status = "checking"       # checking / auth_ok / need_scan / success / failed
    _message = ""              # 附加消息
    _status_file = None        # Path to .scan_status
    _qr_image_path = None      # Path to qr_code.png

    @classmethod
    def init(cls, runtime_dir: Path):
        cls._status_file = runtime_dir / ".scan_status"
        cls._qr_image_path = runtime_dir / "qr_code.png"

    @classmethod
    def set(cls, status: str, message: str = ""):
        with cls._lock:
            cls._status = status
            cls._message = message
            # 同时写入文件信号（供跨进程读取）
            if cls._status_file:
                try:
                    cls._status_file.write_text(status, encoding="utf-8")
                except Exception:
                    pass
        log(f"[STATUS] {status}" + (f" - {message}" if message else ""))

    @classmethod
    def get(cls) -> dict:
        with cls._lock:
            return {
                "status": cls._status,
                "message": cls._message,
            }

    @classmethod
    def get_qr_path(cls) -> Path:
        return cls._qr_image_path


# ============================================================
# HTTP 服务
# ============================================================

class BeaconHTTPHandler(SimpleHTTPRequestHandler):
    """HTTP 请求处理器，支持五种状态的动态页面。"""

    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            self._serve_page()
        elif self.path == "/status":
            self._serve_status()
        elif self.path == "/qr.png":
            self._serve_qr_image()
        else:
            self.send_error(404)

    def _serve_page(self):
        html = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>灯塔登录状态</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
  display:flex;justify-content:center;align-items:center;min-height:100vh;
  background:linear-gradient(135deg,#667eea 0%,#764ba2 100%)}
.card{background:#fff;border-radius:20px;padding:40px 48px;
  box-shadow:0 20px 60px rgba(0,0,0,.15);text-align:center;max-width:460px;width:90%}
h2{color:#333;margin-bottom:8px;font-size:22px}
.sub{color:#999;margin-bottom:24px;font-size:14px;line-height:1.5}
.qr-wrap{display:none;margin:20px auto}
.qr-wrap img{width:260px;height:260px;border:2px solid #eee;border-radius:12px}
.status-box{margin-top:20px;padding:16px 20px;border-radius:12px;font-size:15px;line-height:1.6;transition:all .3s}
.checking{background:#e6f7ff;color:#1890ff}
.auth_ok{background:#f6ffed;color:#52c41a}
.need_scan{background:#fff7e6;color:#fa8c16}
.success{background:#f6ffed;color:#52c41a}
.failed{background:#fff1f0;color:#f5222d}
.spinner{display:inline-block;width:20px;height:20px;border:3px solid #1890ff;
  border-radius:50%;border-top-color:transparent;animation:spin 1s linear infinite;
  vertical-align:middle;margin-right:8px}
@keyframes spin{to{transform:rotate(360deg)}}
.check-icon{font-size:48px;margin-bottom:12px}
</style></head><body>
<div class="card">
  <div id="icon" class="check-icon">🔐</div>
  <h2 id="title">灯塔登录状态</h2>
  <p id="sub" class="sub">正在检查认证状态...</p>
  <div id="qr" class="qr-wrap"><img src="/qr.png?t=0" alt="QR Code"></div>
  <div id="st" class="status-box checking"><span class="spinner"></span>正在检查登录态...</div>
</div>
<script>
let prevStatus = '';
async function poll(){
  try{
    const r = await fetch('/status');
    const d = await r.json();
    if(d.status === prevStatus) return;
    prevStatus = d.status;
    const st = document.getElementById('st');
    const qr = document.getElementById('qr');
    const icon = document.getElementById('icon');
    const title = document.getElementById('title');
    const sub = document.getElementById('sub');
    
    switch(d.status){
      case 'checking':
        st.className='status-box checking';
        st.innerHTML='<span class="spinner"></span>正在检查登录态...';
        qr.style.display='none';
        icon.textContent='🔐';
        title.textContent='灯塔登录状态';
        sub.textContent='正在检查认证状态...';
        break;
      case 'auth_ok':
        st.className='status-box auth_ok';
        st.innerHTML='✅ 登录态有效，爬取任务即将自动开始...';
        qr.style.display='none';
        icon.textContent='✅';
        title.textContent='登录态有效';
        sub.textContent='认证状态正常，无需重新登录';
        break;
      case 'need_scan':
        st.className='status-box need_scan';
        st.innerHTML='📱 请使用 iOA Mobile 3.2+ 扫描下方二维码';
        qr.style.display='block';
        if(d.qr_base64){
          qr.querySelector('img').src='data:image/png;base64,'+d.qr_base64;
        }else{
          qr.querySelector('img').src='/qr.png?t='+Date.now();
        }
        icon.textContent='📱';
        title.textContent='扫码登录';
        sub.textContent='登录态已失效，请扫码重新认证';
        break;
      case 'success':
        st.className='status-box success';
        st.innerHTML='✅ 登录成功！爬取任务即将自动开始...';
        qr.style.display='none';
        icon.textContent='🎉';
        title.textContent='登录成功';
        sub.textContent='认证状态已更新，可以关闭此页面';
        break;
      case 'failed':
        st.className='status-box failed';
        st.innerHTML='❌ '+(d.message||'登录失败或超时，请重新运行');
        qr.style.display='none';
        icon.textContent='❌';
        title.textContent='登录失败';
        sub.textContent=d.message||'请重新尝试';
        break;
    }
  }catch(e){}
}
setInterval(poll, 1000);
poll();
</script></body></html>"""
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))

    def _serve_status(self):
        data = StatusManager.get()
        # 在 need_scan 状态下，附带 base64 编码的二维码图片
        # 这样前端可以直接用 data URL 显示，避免 iframe 安全策略阻止图片请求
        if data["status"] == "need_scan":
            qr_path = StatusManager.get_qr_path()
            if qr_path and qr_path.exists():
                try:
                    qr_b64 = base64.b64encode(qr_path.read_bytes()).decode("ascii")
                    data["qr_base64"] = qr_b64
                except Exception:
                    pass
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode("utf-8"))

    def _serve_qr_image(self):
        qr_path = StatusManager.get_qr_path()
        if qr_path and qr_path.exists():
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(qr_path.read_bytes())
        else:
            self.send_error(404, "QR image not ready")

    def log_message(self, format, *args):
        pass  # 静默 HTTP 日志


# ============================================================
# 后台登录态检测线程
# ============================================================

def auth_check_thread(auth_path: str, url: str, cdp_port: int, timeout: int):
    """后台线程：Playwright CDP 检测登录态 + 扫码等待。
    
    - 登录有效 → 写 .scan_status='auth_ok'
    - 登录失效 → 截取二维码 → 写 .scan_status='need_scan' → 轮询等待扫码
                → 写 'success'/'failed'
    """
    # 延迟导入 playwright，避免在 --start 模式下不必要的加载
    from playwright.sync_api import sync_playwright

    # 导入 beacon_login 中的公共函数
    scripts_dir = Path(__file__).resolve().parent
    sys.path.insert(0, str(scripts_dir))
    from beacon_login import is_login_page, DEFAULT_VERIFY_URL

    auth = Path(auth_path).resolve()
    runtime_dir = RUNTIME_DIR
    qr_image_path = StatusManager.get_qr_path()
    verify_url = url or DEFAULT_VERIFY_URL

    log("[检测线程] 启动...")
    time.sleep(1)  # 等 HTTP 服务先就绪

    # 检查认证文件是否存在且有效
    need_fresh_login = False
    if not auth.exists():
        log("[检测线程] 认证文件不存在，需要扫码登录")
        need_fresh_login = True
    else:
        try:
            content = auth.read_text(encoding="utf-8").strip()
            if content in ("", "{}", "null"):
                log("[检测线程] 认证文件为空，需要扫码登录")
                need_fresh_login = True
        except Exception:
            need_fresh_login = True

    # 杀掉可能占用 CDP 端口的旧进程
    _kill_port_process(cdp_port)
    time.sleep(0.5)

    with sync_playwright() as p:
        # 启动独立浏览器（带 CDP 端口，方便调试）
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-gpu",
                "--disable-dev-shm-usage",
                f"--remote-debugging-port={cdp_port}",
            ],
        )

        if need_fresh_login:
            # 没有有效认证，直接走扫码流程
            context = browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0.0.0 Safari/537.36",
            )
            page = context.new_page()

            log("[检测线程] 打开灯塔触发登录页...")
            try:
                page.goto("https://beacon.woa.com", wait_until="domcontentloaded", timeout=30000)
            except Exception:
                pass
            time.sleep(5)

            _do_qr_scan_flow(page, context, browser, auth, qr_image_path, verify_url, timeout)
            return

        # 有认证文件，检测是否有效
        context = browser.new_context(
            storage_state=str(auth),
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0.0.0 Safari/537.36",
        )
        page = context.new_page()

        log(f"[检测线程] 打开页面检测登录态: {verify_url}")
        try:
            page.goto(verify_url, wait_until="domcontentloaded", timeout=60000)
        except Exception as e:
            log(f"[检测线程] 页面加载超时: {e}")

        time.sleep(3)  # 等待可能的重定向

        if is_login_page(page):
            log("[检测线程] 登录态已失效，启动扫码流程...")
            _do_qr_scan_flow(page, context, browser, auth, qr_image_path, verify_url, timeout)
        else:
            log("[检测线程] ✅ 登录态有效!")
            StatusManager.set("auth_ok")
            # 保持一段时间让前端显示状态
            time.sleep(5)
            browser.close()


def _do_qr_scan_flow(page, context, browser, auth: Path,
                     qr_image_path: Path, verify_url: str, timeout: int):
    """执行扫码登录流程：截取二维码 → 等待扫码 → 保存认证。"""
    from beacon_login import is_login_page

    # 确保在登录页面上
    current_url = page.url.lower()
    login_keywords = ["login", "passport", "auth", "signin", "sso", "cas"]
    if not any(kw in current_url for kw in login_keywords):
        # 可能需要重新导航到登录页
        log("[扫码流程] 导航到灯塔触发登录跳转...")
        try:
            page.goto("https://beacon.woa.com", wait_until="domcontentloaded", timeout=30000)
        except Exception:
            pass
        time.sleep(5)

    # 检测是否处于 iOA 快捷登录模式，如果是则切换到扫码登录
    _switch_to_qr_login_if_needed(page)

    # 截取二维码
    log("[扫码流程] 截取二维码...")
    qr_captured = _capture_qr(page, qr_image_path)
    if not qr_captured:
        StatusManager.set("failed", "无法截取二维码")
        browser.close()
        return

    # 更新状态为 need_scan
    StatusManager.set("need_scan")

    # 轮询等待用户扫码（快速轮询，减少延迟）
    log(f"[扫码流程] 等待扫码 (超时: {timeout}s)...")
    start = time.time()
    login_success = False
    last_log_elapsed = -1

    while time.time() - start < timeout:
        elapsed = int(time.time() - start)
        if elapsed % 5 == 0 and elapsed != last_log_elapsed:
            last_log_elapsed = elapsed
            log(f"[扫码流程] ⏳ 等待中... {elapsed}/{timeout}s")

        # 检测是否已经离开登录页
        try:
            if not is_login_page(page):
                log(f"[扫码流程] ✅ 检测到已离开登录页! URL: {page.url}")
                login_success = True
                break
        except Exception:
            pass

        # 检测扫码成功提示文本
        try:
            body = page.inner_text("body")
            if any(kw in body for kw in ["扫码成功", "登录成功", "认证成功", "scan success"]):
                log("[扫码流程] ✅ 检测到扫码成功提示!")
                # 等页面完成跳转（用 waitForNavigation 替代固定等待）
                try:
                    page.wait_for_url("**/datainsight/**", timeout=8000)
                    log(f"[扫码流程] 页面已跳转: {page.url}")
                except Exception:
                    time.sleep(2)  # fallback: 短暂等待
                login_success = True
                break
        except Exception:
            pass

        time.sleep(0.5)  # 0.5秒轮询（原来是2秒）

    if not login_success:
        # 最后检查一次：导航到验证页面
        try:
            page.goto(verify_url, wait_until="domcontentloaded", timeout=30000)
            time.sleep(3)
            if not is_login_page(page):
                login_success = True
                log("[扫码流程] ✅ 验证页面确认登录成功!")
        except Exception:
            pass

    if login_success:
        # 导航到验证页面确保 cookies 完整
        try:
            if verify_url not in page.url:
                page.goto(verify_url, wait_until="domcontentloaded", timeout=30000)
                time.sleep(2)  # 等待页面加载（原来是5秒，缩短到2秒）
        except Exception:
            pass

        # 保存认证状态（不需要额外等待）
        storage = context.storage_state()
        auth.parent.mkdir(parents=True, exist_ok=True)
        auth.write_text(json.dumps(storage, ensure_ascii=False, indent=2), encoding="utf-8")
        log(f"[扫码流程] 💾 认证状态已保存: {auth}")
        StatusManager.set("success")
    else:
        log("[扫码流程] ❌ 扫码超时！")
        StatusManager.set("failed", "扫码超时，请重新运行")

    # 短暂保持让前端显示结果
    time.sleep(2)
    browser.close()


def _switch_to_qr_login_if_needed(page):
    """检测是否处于 iOA 快捷登录模式，如果是则点击"账号密码"切换到扫码登录页面。
    
    当用户本地安装了 iOA 时，灯塔登录页会显示"快速登录"界面（含用户头像、
    "检测到当前已登录账号"提示和"快速登录"按钮），而不是直接展示扫码二维码。
    需要点击页面顶部的"账号密码"链接，切换到包含扫码二维码的登录页面。
    """
    try:
        body_text = page.inner_text("body")
    except Exception:
        return

    # 检测快捷登录模式的特征文本（中英文）
    quick_login_indicators = [
        "快速登录", "快捷登录", "检测到当前已登录账号",
        "iOA Mobile", "Send verification request", "verification request",
    ]
    is_quick_login = any(indicator in body_text for indicator in quick_login_indicators)

    if not is_quick_login:
        log("[扫码流程] 未检测到 iOA 快捷登录模式，直接截取二维码")
        return

    log("[扫码流程] ⚠️ 检测到 iOA 快捷登录模式，尝试切换到扫码登录...")

    # 尝试点击"账号密码"或"Account"链接来切换到扫码登录页面
    switched = False

    # 策略1：通过文本内容查找切换链接（中英文）
    account_pwd_selectors = [
        "text=账号密码",
        "a:has-text('账号密码')",
        "span:has-text('账号密码')",
        "div:has-text('账号密码') >> nth=0",
        "[class*='tab']:has-text('账号密码')",
        "[class*='link']:has-text('账号密码')",
        "text=Account",
        "a:has-text('Account')",
        "span:has-text('Account')",
        "[class*='tab']:has-text('Account')",
        "[class*='link']:has-text('Account')",
    ]
    for sel in account_pwd_selectors:
        try:
            el = page.locator(sel).first
            if el.is_visible(timeout=2000):
                el.click()
                log(f"[扫码流程] ✅ 点击了 '{sel}'，等待页面切换...")
                time.sleep(3)
                switched = True
                break
        except Exception:
            continue

    if not switched:
        # 策略2：通过 XPath 查找包含切换文本的可点击元素（中英文）
        try:
            el = page.locator("xpath=//a[contains(text(), '账号密码')] | //span[contains(text(), '账号密码')] | //div[contains(text(), '账号密码')] | //a[contains(text(), 'Account')] | //span[contains(text(), 'Account')] | //div[contains(text(), 'Account')]").first
            if el.is_visible(timeout=2000):
                el.click()
                log("[扫码流程] ✅ 通过 XPath 点击了切换tab，等待页面切换...")
                time.sleep(3)
                switched = True
        except Exception:
            pass

    if not switched:
        log("[扫码流程] ⚠️ 未能找到切换按钮，尝试直接截取当前页面")

    # 切换后，检查是否出现了"扫码登录"tab，需要再点击一下确保进入扫码模式
    try:
        body_text_after = page.inner_text("body")
        if "扫码登录" in body_text_after or "QR" in body_text_after:
            scan_selectors = [
                "text=扫码登录",
                "a:has-text('扫码登录')",
                "span:has-text('扫码登录')",
                "[class*='tab']:has-text('扫码登录')",
                "text=QR",
                "[class*='tab']:has-text('QR')",
            ]
            for sel in scan_selectors:
                try:
                    el = page.locator(sel).first
                    if el.is_visible(timeout=2000):
                        el.click()
                        log(f"[扫码流程] ✅ 点击了 '{sel}'，等待二维码加载...")
                        time.sleep(3)
                        break
                except Exception:
                    continue
    except Exception:
        pass


def _capture_qr(page, qr_image_path: Path) -> bool:
    """截取登录页面上的二维码图片。"""
    qr_image_path.parent.mkdir(parents=True, exist_ok=True)
    qr_selectors = [
        "img[id*='qr']", "img[class*='qr']", "img[src*='qr']",
        "img[id*='QR']", "img[class*='QR']", "img[src*='QR']",
        "#qrcode img", ".qrcode img", "[class*='qrcode'] img",
        "canvas",
    ]
    for sel in qr_selectors:
        try:
            el = page.query_selector(sel)
            if el:
                box = el.bounding_box()
                if box and box["width"] > 50 and box["height"] > 50:
                    el.screenshot(path=str(qr_image_path))
                    log(f"[截取二维码] ✅ (selector: {sel})")
                    return True
        except Exception:
            continue
    # fallback: 截取整个页面
    try:
        page.screenshot(path=str(qr_image_path))
        log("[截取二维码] ⚠️ 未找到独立二维码元素，已截取整个登录页面")
        return True
    except Exception as e:
        log(f"[截取二维码] ❌ 失败: {e}")
        return False


# ============================================================
# 工具函数
# ============================================================

def _kill_port_process(port: int):
    """杀掉占用指定端口的进程（跨平台）。"""
    if sys.platform == "win32":
        # Windows: 使用 netstat + taskkill
        try:
            result = subprocess.run(
                ["netstat", "-ano"],
                capture_output=True, text=True, timeout=5,
            )
            for line in result.stdout.strip().split("\n"):
                if f":{port}" in line and "LISTENING" in line:
                    parts = line.strip().split()
                    pid_str = parts[-1]
                    try:
                        pid = int(pid_str)
                        if pid != os.getpid() and pid > 0:
                            subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                                           capture_output=True, timeout=5)
                            log(f"[清理] 杀掉占用端口 {port} 的进程 {pid}")
                    except (ValueError, Exception):
                        pass
            time.sleep(0.5)
        except Exception:
            pass
    else:
        # Linux/macOS: 使用 lsof
        try:
            result = subprocess.run(
                ["lsof", "-ti", f":{port}"],
                capture_output=True, text=True, timeout=5,
            )
            if result.stdout.strip():
                for pid_str in result.stdout.strip().split("\n"):
                    try:
                        pid = int(pid_str.strip())
                        if pid != os.getpid():
                            os.kill(pid, signal.SIGKILL)
                            log(f"[清理] 杀掉占用端口 {port} 的进程 {pid}")
                    except (ValueError, ProcessLookupError):
                        pass
                time.sleep(0.5)
        except Exception:
            pass


def _cleanup_old_resources(port: int, cdp_port: int, runtime_dir: Path):
    """清理旧的进程和状态文件。"""
    # 杀掉旧 HTTP 服务进程
    _kill_port_process(port)
    # 杀掉旧 CDP 浏览器进程
    _kill_port_process(cdp_port)
    # 清除旧的状态文件
    status_file = runtime_dir / ".scan_status"
    if status_file.exists():
        try:
            status_file.unlink()
        except Exception:
            pass
    # 也清理旧的临时目录下的信号文件（向后兼容，跨平台）
    import tempfile
    old_signal = Path(tempfile.gettempdir()) / "beacon_auth_status"
    if old_signal.exists():
        try:
            old_signal.unlink()
        except Exception:
            pass


# ============================================================
# --start 模式：AI 调用入口
# ============================================================

def cmd_start(auth_path: str, url: str, port: int, cdp_port: int, timeout: int):
    """启动模式：清理旧资源 → 启动 --serve 子进程 → 输出 HTTP_READY → 退出。"""
    runtime_dir = RUNTIME_DIR
    runtime_dir.mkdir(parents=True, exist_ok=True)

    log("=== 灯塔登录服务启动 ===")

    # 1. 清理旧进程和文件
    log("1. 清理旧资源...")
    _cleanup_old_resources(port, cdp_port, runtime_dir)

    # 2. 写入初始状态
    status_file = runtime_dir / ".scan_status"
    status_file.write_text("checking", encoding="utf-8")

    # 3. 构建 --serve 命令（使用当前 Python 解释器，兼容 Windows）
    serve_cmd = [
        sys.executable, str(Path(__file__).resolve()),
        "--serve",
        "--auth", auth_path,
        "--url", url,
        "--port", str(port),
        "--cdp-port", str(cdp_port),
        "--timeout", str(timeout),
    ]

    # 4. 启动 --serve 子进程（脱离父进程会话）
    log("2. 启动 HTTP 服务子进程...")
    log_file_path = runtime_dir / "serve.log"
    log_file = open(str(log_file_path), "w", encoding="utf-8")
    # 设置子进程环境变量，确保 UTF-8 输出（Windows GBK 兼容）
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    # Windows 不支持 start_new_session，使用 CREATE_NEW_PROCESS_GROUP
    popen_kwargs = {
        "stdout": log_file,
        "stderr": log_file,
        "env": env,
    }
    if sys.platform == "win32":
        popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        popen_kwargs["start_new_session"] = True
    proc = subprocess.Popen(serve_cmd, **popen_kwargs)
    log(f"   PID: {proc.pid}")
    log(f"   日志: {log_file_path}")

    # 5. 等待 HTTP 服务就绪（最多 8 秒）
    log("3. 等待 HTTP 服务就绪...")
    import urllib.request
    for i in range(16):
        time.sleep(0.5)
        try:
            resp = urllib.request.urlopen(f"http://localhost:{port}/status", timeout=2)
            if resp.status == 200:
                log(f"   ✅ HTTP 服务就绪 ({(i+1)*0.5:.1f}s)")
                break
        except Exception:
            pass
    else:
        log("   ⚠️ HTTP 服务启动超时，但子进程已创建")

    # 6. 输出信号让 AI 调用 preview_url
    log("")
    log(f"HTTP_READY")
    log(f"HTTP_URL=http://localhost:{port}")
    log(f"HTTP_PID={proc.pid}")
    log("")
    log(f"请调用 preview_url 打开 http://localhost:{port} 查看登录状态。")

    sys.exit(0)


# ============================================================
# --serve 模式：HTTP 服务 + 后台检测
# ============================================================

def cmd_serve(auth_path: str, url: str, port: int, cdp_port: int, timeout: int):
    """服务模式：HTTP 服务主循环 + 后台登录检测线程。"""
    runtime_dir = RUNTIME_DIR
    runtime_dir.mkdir(parents=True, exist_ok=True)

    # 初始化状态管理器
    StatusManager.init(runtime_dir)
    StatusManager.set("checking")

    # 启动后台登录检测线程
    detect_thread = threading.Thread(
        target=auth_check_thread,
        args=(auth_path, url, cdp_port, timeout),
        daemon=True,
    )
    detect_thread.start()

    # 启动 HTTP 服务
    server = HTTPServer(("0.0.0.0", port), BeaconHTTPHandler)
    log(f"[HTTP] 服务启动: http://0.0.0.0:{port}")

    # 超时自动退出（默认 timeout + 60 秒余量）
    max_serve_time = timeout + 60

    def auto_shutdown():
        time.sleep(max_serve_time)
        log(f"[HTTP] 超时 ({max_serve_time}s)，自动退出")
        server.shutdown()

    shutdown_timer = threading.Thread(target=auto_shutdown, daemon=True)
    shutdown_timer.start()

    # 优雅退出（Windows 仅支持 SIGINT/SIGBREAK）
    def on_signal(signum, frame):
        log(f"[HTTP] 收到信号 {signum}，退出")
        server.shutdown()

    signal.signal(signal.SIGINT, on_signal)
    if sys.platform != "win32":
        signal.signal(signal.SIGTERM, on_signal)
    else:
        try:
            signal.signal(signal.SIGBREAK, on_signal)
        except (AttributeError, OSError):
            pass

    try:
        server.serve_forever()
    except Exception:
        pass
    finally:
        log("[HTTP] 服务已停止")


# ============================================================
# 入口
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="灯塔扫码登录服务")
    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument("--start", action="store_true",
                            help="启动模式：清理旧资源 + 启动 HTTP 子进程 + 快速退出")
    mode_group.add_argument("--serve", action="store_true",
                            help="服务模式：HTTP 服务 + 后台登录检测")

    default_auth = str(RUNTIME_DIR / "beacon_auth_state.json")
    parser.add_argument("--auth", "-a", type=str, default=default_auth,
                        help=f"认证状态文件路径 (默认: {default_auth})")
    parser.add_argument("--url", "-u", type=str,
                        default="https://beacon.woa.com/datainsight/pc_yyb_client",
                        help="灯塔页面 URL")
    parser.add_argument("--port", type=int, default=18888,
                        help="HTTP 服务端口 (默认: 18888)")
    parser.add_argument("--cdp-port", type=int, default=9222,
                        help="Chromium CDP 端口 (默认: 9222)")
    parser.add_argument("--timeout", type=int, default=300,
                        help="扫码超时秒数 (默认: 300)")

    args = parser.parse_args()

    if args.start:
        cmd_start(args.auth, args.url, args.port, args.cdp_port, args.timeout)
    elif args.serve:
        cmd_serve(args.auth, args.url, args.port, args.cdp_port, args.timeout)


if __name__ == "__main__":
    main()
