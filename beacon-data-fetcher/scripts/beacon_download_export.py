#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
灯塔(Beacon)下载管理导出脚本 — 通过操作灯塔 UI 的下载管理功能导出数据集。

适用场景: 所有需要下载完整原始数据的场景，不论数据量大小。
支持页面类型:
  - TV 模式 (PanelMax): 通过"探索分析→天数→确定"修改时间后下载
  - 敏捷分析模式 (Analytics_Mode): 通过"时间设置→天数→立即分析"修改时间后下载
  - 自动检测: 根据 URL 自动判断页面类型

工作流程:
  1. 打开灯塔页面，等待数据加载完成
  2. (可选) 根据页面类型修改查询天数
  3. 点击表格工具栏中的"导出/下载"按钮触发导出
  4. 根据数据量自动判断下载方式:
     - 小文件 (< 5000行): 点击导出后浏览器直接下载文件，立即完成
     - 大文件 (≥ 5000行): 点击导出后创建下载任务，需要:
       a. 展开右侧"快捷工具"侧边栏
       b. 点击"下载管理"打开下载任务列表对话框
       c. 等待任务状态变为"完成"
       d. 点击"下载"按钮保存文件

使用方法:
  # 方式 A: 直接下载 (使用页面默认时间范围)
  python3 beacon_download_export.py \\
    --auth /path/to/beacon_auth_state.json \\
    --url "https://beacon.woa.com/datainsight/..." \\
    --output-dir /path/to/output \\
    --trigger-export

  # 方式 B: 修改天数后下载 (TV 模式，自动检测)
  python3 beacon_download_export.py \\
    --auth /path/to/beacon_auth_state.json \\
    --url "https://beacon.woa.com/datainsight/.../PanelMax/..." \\
    --output-dir /path/to/output \\
    --days 180 \\
    --trigger-export

  # 方式 C: 修改天数后下载 (敏捷分析模式)
  python3 beacon_download_export.py \\
    --auth /path/to/beacon_auth_state.json \\
    --url "https://beacon.woa.com/datainsight/.../Analytics_Mode/..." \\
    --output-dir /path/to/output \\
    --days 120 \\
    --trigger-export

  # 方式 D: 仅从下载管理中下载已有任务 (不触发新导出)
  python3 beacon_download_export.py \\
    --auth /path/to/beacon_auth_state.json \\
    --url "https://beacon.woa.com/datainsight/..." \\
    --output-dir /path/to/output

参数:
  --auth, -a           认证状态文件路径
  --url, -u            灯塔页面 URL
  --output-dir, -o     输出目录 (默认: ./beacon_downloads)
  --trigger-export     是否先触发导出 (点击 download.png 按钮)
  --task-name          用于匹配下载任务的名称关键词 (可选)
  --days, -d           修改查询天数 (如 180)。不指定则使用页面默认天数
  --page-type          页面展示类型: auto/tv/analytics (默认: auto)
  --wait-load          页面加载等待秒数 (默认: 30)
  --wait-export        导出任务等待秒数 (默认: 30)
  --wait-download      文件下载等待秒数 (默认: 120)
  --wait-query         修改天数后等待查询完成秒数 (默认: 120)
"""

import argparse
import csv
import json
import re
import shutil
import sys
import time
from pathlib import Path
from datetime import datetime
from playwright.sync_api import sync_playwright

# 导入 beacon_login 中的登录失效检测函数
_SCRIPTS_DIR = Path(__file__).resolve().parent
_SKILL_DIR = _SCRIPTS_DIR.parent
_RUNTIME_DIR = _SKILL_DIR / "runtime"
sys.path.insert(0, str(_SCRIPTS_DIR))
from beacon_login import is_login_page


def log(msg: str):
    sys.stdout.write(msg + "\n")
    sys.stdout.flush()


def wait_with_log(seconds: int, label: str = "等待"):
    """带日志输出的等待，防止 idle timeout"""
    for i in range(seconds):
        time.sleep(1)
        if i % 5 == 0:
            log(f"   {label} {i}/{seconds}s")


def find_and_click_element(page, js_code: str, fallback_coords: tuple = None, label: str = "元素"):
    """通过 JS 查找元素坐标并点击，失败时使用备用坐标"""
    coords = page.evaluate(js_code)
    if coords:
        page.mouse.click(coords[0], coords[1])
        log(f"   ✅ {label} ({coords[0]},{coords[1]})")
        return True
    elif fallback_coords:
        page.mouse.click(fallback_coords[0], fallback_coords[1])
        log(f"   ⚠️ {label} 使用备用坐标 ({fallback_coords[0]},{fallback_coords[1]})")
        return True
    else:
        log(f"   ❌ {label} 未找到")
        return False


def trigger_export_button(page):
    """
    触发表格工具栏中的导出按钮。
    灯塔的导出按钮是一个 img 元素，src 中包含 'download.png'。
    对于长页面，先滚动到导出按钮位置再点击。
    """
    log("   查找导出按钮 (download.png)...")
    # 先尝试滚动到导出按钮位置（处理长页面场景）
    scrolled = page.evaluate("""() => {
        const imgs = document.querySelectorAll('img');
        for (const img of imgs) {
            if (img.src && img.src.toLowerCase().includes('download')) {
                if (img.offsetParent !== null && img.getBoundingClientRect().width > 0) {
                    img.scrollIntoView({behavior: 'instant', block: 'center'});
                    return true;
                }
            }
        }
        return false;
    }""")
    if scrolled:
        log("   📜 已滚动到导出按钮位置")
        time.sleep(1)  # 等待滚动完成和渲染
    
    return find_and_click_element(page, """() => {
        const imgs = document.querySelectorAll('img');
        for (const img of imgs) {
            if (img.src && img.src.toLowerCase().includes('download')) {
                const r = img.getBoundingClientRect();
                if (r.width > 0 && img.offsetParent !== null)
                    return [Math.round(r.x + r.width/2), Math.round(r.y + r.height/2)];
            }
        }
        return null;
    }""", label="导出按钮")


def open_quick_tools_sidebar(page):
    """
    展开右侧"快捷工具"侧边栏。
    触发元素: class 包含 'tool_jt' 的按钮。
    """
    log("   展开快捷工具侧边栏...")
    return find_and_click_element(page, """() => {
        const els = document.querySelectorAll('[class*="tool_jt"]');
        for (const el of els) {
            const r = el.getBoundingClientRect();
            if (r.width > 0 && r.x > 1000)
                return [Math.round(r.x + r.width/2), Math.round(r.y + r.height/2)];
        }
        return null;
    }""", label="快捷工具按钮")


def click_download_manager(page):
    """
    在侧边栏中点击"下载管理"。
    """
    log("   查找下载管理...")
    return find_and_click_element(page, """() => {
        const els = document.querySelectorAll('*');
        for (const el of els) {
            const t = (el.innerText || '').trim();
            if (t === '下载管理') {
                const r = el.getBoundingClientRect();
                if (r.width > 0 && el.offsetParent !== null)
                    return [Math.round(r.x + r.width/2), Math.round(r.y + r.height/2)];
            }
        }
        return null;
    }""", label="下载管理")


def find_download_buttons_in_dialog(page, task_name: str = None):
    """
    在"下载任务列表"对话框中查找下载按钮。
    返回按钮信息列表和任务行信息。
    """
    info = page.evaluate("""() => {
        const wrappers = document.querySelectorAll('.el-dialog__wrapper');
        for (const w of wrappers) {
            if (window.getComputedStyle(w).display === 'none') continue;
            const d = w.querySelector('.el-dialog');
            if (!d) continue;
            const r = d.getBoundingClientRect();
            if (r.width < 300) continue;

            const title = (d.querySelector('.el-dialog__title') || {}).innerText || '';

            // 查找所有"下载"按钮
            const btns = [];
            const allEls = d.querySelectorAll('*');
            for (const el of allEls) {
                const t = (el.innerText || '').trim();
                if (t === '下载' && el.children.length === 0 && el.offsetParent !== null) {
                    const br = el.getBoundingClientRect();
                    if (br.width > 0) btns.push({
                        tag: el.tagName,
                        x: Math.round(br.x + br.width/2),
                        y: Math.round(br.y + br.height/2),
                        href: el.href || ''
                    });
                }
            }

            // 提取表格行信息
            const rows = [];
            const trs = d.querySelectorAll('tbody tr');
            for (let i = 0; i < trs.length; i++) {
                const cells = trs[i].querySelectorAll('td');
                const row = [];
                for (const c of cells) row.push(c.innerText.trim().substring(0, 50));
                rows.push(row);
            }

            return { title, btns, rows };
        }
        return null;
    }""")
    return info


def close_any_dialog(page):
    """关闭可能弹出的对话框（如"保存到分析列表"等干扰弹窗）"""
    page.evaluate("""() => {
        const closeBtns = document.querySelectorAll('.el-dialog__headerbtn, .el-message-box__headerbtn');
        for (const btn of closeBtns) {
            const wrapper = btn.closest('.el-dialog__wrapper, .el-message-box__wrapper');
            if (wrapper && window.getComputedStyle(wrapper).display !== 'none') {
                btn.click();
            }
        }
    }""")


def detect_page_type(url: str) -> str:
    """根据 URL 自动检测灯塔页面展示类型。
    
    Returns:
        'tv' | 'analytics' | 'event'
    """
    url_lower = url.lower()
    if "panelmax" in url_lower:
        return "tv"
    elif "analytics_mode" in url_lower:
        return "analytics"
    elif "new_event_modify" in url_lower or "new_event_card" in url_lower:
        return "event"
    else:
        return "tv"


def change_days_tv_mode(page, days: int):
    """TV 模式下修改查询天数: 探索分析 → 天数 → 确定"""
    log(f"[TV模式-修改天数] 查找探索分析按钮...")
    
    # 隐藏sidebar
    page.evaluate("()=>{const s=document.querySelector('.main-app-sidebar');if(s)s.style.display='none'}")
    time.sleep(0.5)
    
    # 查找并点击"探索分析"
    explore_info = page.evaluate("""()=>{
        const results = [];
        const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_ELEMENT);
        while(walker.nextNode()){
            const el = walker.currentNode;
            if(el.offsetParent === null && el.tagName !== 'BODY') continue;
            const text = (el.innerText||el.textContent||'').trim().substring(0,20);
            if(text.includes('探索分析') || text.includes('探索')){
                const rect = el.getBoundingClientRect();
                results.push({
                    tag: el.tagName, text: text,
                    x: Math.round(rect.x), y: Math.round(rect.y),
                    w: Math.round(rect.width), h: Math.round(rect.height)
                });
            }
        }
        document.querySelectorAll('[class*="show_setting"],[class*="setting_btn"]').forEach(el=>{
            const rect = el.getBoundingClientRect();
            results.push({
                tag: el.tagName, text: (el.innerText||'').trim().substring(0,20),
                x: Math.round(rect.x), y: Math.round(rect.y),
                w: Math.round(rect.width), h: Math.round(rect.height),
                special: 'show_setting'
            });
        });
        return results;
    }""")
    log(f"   探索分析候选: {json.dumps(explore_info, ensure_ascii=False)}")
    
    clicked = False
    for item in sorted(explore_info, key=lambda x: x.get('w', 9999) * x.get('h', 9999)):
        if item.get('w', 0) > 0 and item.get('h', 0) > 0 and item.get('y', 0) < 200:
            cx = item['x'] + item['w'] // 2
            cy = item['y'] + item['h'] // 2
            log(f"   点击: ({cx}, {cy}) - {item.get('text', '')}")
            page.mouse.click(cx, cy)
            clicked = True
            break
    if not clicked:
        log("   备用：点击左上角区域 (110, 107)")
        page.mouse.click(110, 107)
    
    time.sleep(2)
    
    # 查找天数输入框
    panel_info = page.evaluate("""()=>{
        const inputs = [];
        document.querySelectorAll('input[type="number"],input.el-input__inner').forEach(el=>{
            if(el.offsetParent===null) return;
            const rect = el.getBoundingClientRect();
            inputs.push({
                type: el.type, val: el.value,
                x: Math.round(rect.x), y: Math.round(rect.y),
                w: Math.round(rect.width), h: Math.round(rect.height)
            });
        });
        const btns = [];
        document.querySelectorAll('button').forEach(el=>{
            if(el.offsetParent===null) return;
            const text = (el.innerText||'').trim();
            if(text === '确定' || text === '确 定'){
                const rect = el.getBoundingClientRect();
                btns.push({
                    text, x: Math.round(rect.x), y: Math.round(rect.y),
                    w: Math.round(rect.width), h: Math.round(rect.height)
                });
            }
        });
        return {inputs, btns};
    }""")
    
    # 找天数输入框
    day_input = None
    for inp in panel_info['inputs']:
        if inp.get('val') == '30' and inp.get('y', 999) < 300:
            day_input = inp
            break
    if not day_input:
        for inp in panel_info['inputs']:
            val = inp.get('val', '')
            if val.isdigit() and 1 <= int(val) <= 999 and inp.get('y', 999) < 300 and inp.get('x', 999) < 500:
                day_input = inp
                break
    
    if day_input:
        log(f"   天数输入框: val={day_input['val']} at ({day_input['x']},{day_input['y']})")
        # 使用键盘方式输入：三击全选 + 键入新值
        ix = day_input['x'] + day_input['w'] // 2
        iy = day_input['y'] + day_input['h'] // 2
        page.mouse.click(ix, iy, click_count=3)
        time.sleep(0.3)
        page.keyboard.press("Backspace")
        time.sleep(0.2)
        page.keyboard.type(str(days), delay=50)
        time.sleep(0.5)
        # 验证输入值
        new_val = page.evaluate("""(params)=>{
            const inputs = document.querySelectorAll('input[type="number"],input.el-input__inner');
            for(const el of inputs){
                if(el.offsetParent===null) continue;
                const rect = el.getBoundingClientRect();
                if(Math.abs(rect.x - params.x) < 5 && Math.abs(rect.y - params.y) < 5){
                    return el.value;
                }
            }
            return null;
        }""", {"x": day_input['x'], "y": day_input['y']})
        log(f"   输入后验证: val={new_val} (目标: {days})")
        time.sleep(0.5)
    else:
        log("   ⚠ 未找到天数输入框!")
    
    # 点击确定
    confirm_btn = None
    for btn in panel_info['btns']:
        if btn.get('w', 0) > 0 and btn.get('y', 0) < 300:
            confirm_btn = btn
            break
    if not confirm_btn and panel_info['btns']:
        confirm_btn = panel_info['btns'][0]
    
    if confirm_btn:
        cx = confirm_btn['x'] + confirm_btn['w'] // 2
        cy = confirm_btn['y'] + confirm_btn['h'] // 2
        log(f"   确定按钮: ({cx},{cy})")
        page.mouse.click(cx, cy)
    else:
        log("   ⚠ 未找到确定按钮! JS fallback...")
        page.evaluate("""()=>{
            const btns = document.querySelectorAll('button');
            for(const btn of btns){
                if(btn.offsetParent===null) continue;
                const text = (btn.innerText||'').trim();
                if(text === '确定' || text === '确 定'){ btn.click(); return; }
            }
        }""")
    
    log(f"[TV模式-修改天数] 确定已点击")


def change_days_analytics_mode(page, days: int):
    """敏捷分析模式下修改查询天数: 时间设置区域 → 天数 → 立即分析"""
    log(f"[敏捷分析-修改天数] 查找时间设置区域...")
    
    # 隐藏sidebar
    page.evaluate("()=>{const s=document.querySelector('.main-app-sidebar');if(s)s.style.display='none'}")
    time.sleep(0.5)
    
    # 查找时间设置区域
    time_setting_info = page.evaluate("""()=>{
        const results = {inputs: [], labels: [], buttons: []};
        
        document.querySelectorAll('input[type="number"],input.el-input__inner').forEach(el=>{
            if(el.offsetParent===null) return;
            const rect = el.getBoundingClientRect();
            if(rect.width <= 0) return;
            results.inputs.push({
                type: el.type, val: el.value,
                x: Math.round(rect.x), y: Math.round(rect.y),
                w: Math.round(rect.width), h: Math.round(rect.height)
            });
        });
        
        const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_ELEMENT);
        while(walker.nextNode()){
            const el = walker.currentNode;
            if(el.offsetParent===null && el.tagName!=='BODY') continue;
            const text = (el.innerText||el.textContent||'').trim();
            if(text === '时间设置' || text.startsWith('时间设置')){
                const rect = el.getBoundingClientRect();
                if(rect.width > 0 && rect.width < 200){
                    results.labels.push({
                        text: text.substring(0,20),
                        x: Math.round(rect.x), y: Math.round(rect.y),
                        w: Math.round(rect.width), h: Math.round(rect.height)
                    });
                }
            }
        }
        
        document.querySelectorAll('button').forEach(el=>{
            if(el.offsetParent===null) return;
            const text = (el.innerText||'').trim();
            if(text.includes('立即分析')){
                const rect = el.getBoundingClientRect();
                results.buttons.push({
                    text, cls: (el.className||'').toString().substring(0,80),
                    x: Math.round(rect.x), y: Math.round(rect.y),
                    w: Math.round(rect.width), h: Math.round(rect.height)
                });
            }
        });
        
        return results;
    }""")
    log(f"   时间设置: {json.dumps(time_setting_info['labels'], ensure_ascii=False)}")
    log(f"   输入框: {json.dumps(time_setting_info['inputs'], ensure_ascii=False)}")
    log(f"   立即分析: {json.dumps(time_setting_info['buttons'], ensure_ascii=False)}")
    
    # 定位天数输入框
    day_input = None
    if time_setting_info['labels']:
        label_y = time_setting_info['labels'][0]['y']
        for inp in time_setting_info['inputs']:
            if abs(inp.get('y', 9999) - label_y) < 30:
                val = inp.get('val', '')
                if val.isdigit() and 1 <= int(val) <= 999:
                    day_input = inp
                    break
    if not day_input:
        common_days = {'30', '60', '90', '120', '180', '365', '7', '14'}
        for inp in time_setting_info['inputs']:
            if inp.get('val', '') in common_days and inp.get('y', 9999) < 400:
                day_input = inp
                break
    if not day_input:
        for inp in time_setting_info['inputs']:
            val = inp.get('val', '')
            if val.isdigit() and 1 <= int(val) <= 999 and inp.get('y', 9999) < 400 and val not in ('1', '50'):
                day_input = inp
                break
    
    if day_input:
        log(f"   天数输入框: val={day_input['val']} at ({day_input['x']},{day_input['y']})")
        # 使用键盘方式输入：三击全选 + 退格 + 键入新值
        ix = day_input['x'] + day_input['w'] // 2
        iy = day_input['y'] + day_input['h'] // 2
        page.mouse.click(ix, iy, click_count=3)
        time.sleep(0.3)
        page.keyboard.press("Backspace")
        time.sleep(0.2)
        page.keyboard.type(str(days), delay=50)
        time.sleep(0.5)
        # 验证输入值
        new_val = page.evaluate("""(params)=>{
            const inputs = document.querySelectorAll('input[type="number"],input.el-input__inner');
            for(const el of inputs){
                if(el.offsetParent===null) continue;
                const rect = el.getBoundingClientRect();
                if(Math.abs(rect.x - params.x) < 5 && Math.abs(rect.y - params.y) < 5){
                    return el.value;
                }
            }
            return null;
        }""", {"x": day_input['x'], "y": day_input['y']})
        log(f"   输入后验证: val={new_val} (目标: {days})")
    else:
        log("   ⚠ 未找到天数输入框!")
    
    # 点击"立即分析"
    analyze_btn = None
    for btn in time_setting_info['buttons']:
        if 'primary' in btn.get('cls', ''):
            analyze_btn = btn
            break
    if not analyze_btn and time_setting_info['buttons']:
        analyze_btn = time_setting_info['buttons'][0]
    
    if analyze_btn:
        cx = analyze_btn['x'] + analyze_btn['w'] // 2
        cy = analyze_btn['y'] + analyze_btn['h'] // 2
        log(f"   立即分析按钮: ({cx},{cy})")
        page.mouse.click(cx, cy)
    else:
        log("   ⚠ 未找到立即分析按钮! JS fallback...")
        page.evaluate("""()=>{
            const btns = document.querySelectorAll('button');
            for(const btn of btns){
                if(btn.offsetParent===null) continue;
                const text = (btn.innerText||'').trim();
                if(text.includes('立即分析')){ btn.click(); return; }
            }
        }""")
    
    log(f"[敏捷分析-修改天数] 立即分析已点击")


def organize_downloaded_file(dl_path: Path, output_dir: Path, label: str = None) -> Path:
    """整理下载的 CSV 文件：复制到输出目录并使用友好文件名"""
    if not dl_path.exists():
        return dl_path
    suffix = dl_path.suffix
    label = label or "灯塔数据"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = output_dir / f"{label}_{timestamp}{suffix}"
    shutil.copy2(str(dl_path), str(dest))
    log(f"✅ 文件已整理: {dest}")

    # 基本数据概览
    if suffix.lower() == ".csv":
        try:
            with open(str(dest), "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                headers = reader.fieldnames
                row_count = sum(1 for _ in reader)
            log(f"   行数: {row_count:,}  字段: {headers}")
        except Exception as e:
            log(f"   ⚠️ 读取 CSV 失败: {e}")

    return dest


def run(auth_path: str, url: str, output_dir: str, trigger_export: bool = False,
        task_name: str = None, wait_load: int = 30, wait_export: int = 30,
        wait_download: int = 120, days: int = 0, page_type: str = "auto",
        wait_query: int = 120):
    """主下载流程
    
    Args:
        auth_path: 认证状态文件路径
        url: 灯塔页面 URL
        output_dir: 输出目录
        trigger_export: 是否先触发导出任务
        task_name: 匹配下载任务名称
        wait_load: 页面加载等待秒数
        wait_export: 导出任务等待秒数
        wait_download: 文件下载等待秒数
        days: 修改查询天数 (0 表示不修改)
        page_type: 页面展示类型 auto/tv/analytics
        wait_query: 修改天数后等待查询完成秒数
    """
    auth = Path(auth_path).resolve()
    out = Path(output_dir).resolve()
    dl_dir = out / "downloads"
    dl_dir.mkdir(parents=True, exist_ok=True)

    if not auth.exists():
        log(f"❌ 认证文件不存在: {auth}")
        sys.exit(1)

    log("=== 灯塔下载管理导出 ===")

    # 检测页面类型
    if page_type == "auto":
        detected_type = detect_page_type(url)
        log(f"   页面类型(自动检测): {detected_type}")
    else:
        detected_type = page_type
        log(f"   页面类型(手动指定): {detected_type}")

    downloaded_files = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = browser.new_context(
            storage_state=str(auth),
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 Chrome/130",
            accept_downloads=True,
        )

        # 注册下载事件
        def on_download(dl):
            log(f"🔔 下载开始: {dl.suggested_filename}")
            fname = dl.suggested_filename or "data.csv"
            path = dl_dir / fname
            dl.save_as(str(path))
            downloaded_files.append(str(path))
            log(f"✅ 已保存: {path} ({path.stat().st_size:,} bytes)")

        page = context.new_page()
        page.on("download", on_download)

        # Step 1: 打开页面
        log(f"1. 打开页面: {url}")
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=90000)
        except Exception as e:
            log(f"   ⚠️ 加载超时: {e}")

        # Step 1.5: 立即检测登录态是否失效（goto domcontentloaded 后无需长等待）
        time.sleep(1)  # 仅等1秒让可能的重定向完成
        if is_login_page(page):
            log("⚠️ 检测到登录态已失效，页面被重定向到登录页!")
            page.screenshot(path=str(out / "step1_login_expired.png"))
            log("WAITING_FOR_LOGIN")
            log("   登录服务应已启动扫码流程，等待登录完成...")
            
            # 等待登录态恢复 — 通过 runtime/.scan_status 信号文件
            login_restored = False
            login_wait_timeout = 300  # 最长等待5分钟
            status_file = _RUNTIME_DIR / ".scan_status"
            # 向后兼容：也检查旧的信号文件路径（跨平台）
            import tempfile
            old_status_file = Path(tempfile.gettempdir()) / "beacon_auth_status"
            
            for i in range(login_wait_timeout):
                time.sleep(1)
                if i % 5 == 0:
                    log(f"   ⏳ 等待登录... {i}/{login_wait_timeout}s")
                
                # 检查信号文件
                for sf in [status_file, old_status_file]:
                    if sf.exists():
                        try:
                            status = sf.read_text(encoding="utf-8").strip()
                            if status == "success" or status == "auth_ok":
                                log(f"   ✅ 检测到登录成功信号! (status={status})")
                                login_restored = True
                                break
                            elif status == "failed":
                                log("   ❌ 检测到登录失败信号!")
                                break
                        except Exception:
                            pass
                
                if login_restored:
                    break
                
                try:
                    if not is_login_page(page):
                        log(f"   ✅ 检测到页面已离开登录页! URL: {page.url}")
                        login_restored = True
                        break
                except Exception:
                    pass
            
            if not login_restored:
                log("❌ 等待登录超时！请重新运行。")
                browser.close()
                sys.exit(2)
            
            # 登录成功后，重新加载认证状态并打开目标页面
            log("🔄 登录成功，重新加载页面...")
            browser.close()
            
            browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
            context = browser.new_context(
                storage_state=str(auth),
                viewport={"width": 1920, "height": 1080},
                user_agent="Mozilla/5.0 Chrome/130",
                accept_downloads=True,
            )
            
            page = context.new_page()
            page.on("download", on_download)
            
            log(f"   重新打开页面: {url}")
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=90000)
            except Exception as e:
                log(f"   ⚠️ 重新加载超时: {e}")

        # Step 2: 等待页面数据加载 (智能检测)
        log(f"2. 等待页面加载...")
        page.screenshot(path=str(out / "step2_page_opened.png"))
        for i in range(wait_load):
            time.sleep(1)
            status = page.evaluate("""() => {
                const table = document.querySelector('.el-table__body');
                const rows = table ? table.querySelectorAll('tr').length : 0;
                // 检测查询进度弹窗
                const allText = document.body.innerText || '';
                const querying = allText.includes('放弃此查询') || allText.includes('检查语法')
                    || allText.includes('校验查询请求');
                // 检测耗时标签
                const hasElapsed = /\\d{2}:\\d{2}:\\d{2}/.test(allText);
                return { tableRows: rows, querying: querying, hasElapsed: hasElapsed };
            }""")
            if status.get('tableRows', 0) >= 5 and not status.get('querying', False):
                log(f"   ✅ 页面加载完成 ({i+1}s), 表格行数: {status['tableRows']}")
                break
            if i % 5 == 0:
                log(f"   页面加载 {i}/{wait_load}s, 行数={status.get('tableRows',0)}, 查询中={status.get('querying')}")
        page.screenshot(path=str(out / "step2_page_loaded.png"))

        # 提取页面标题（用于后续在下载管理中匹配正确的任务）
        page_title = page.evaluate("""() => {
            // 尝试多种方式获取页面/面板标题
            // 方式1: 灯塔页面顶部的面板标题
            const titleEls = document.querySelectorAll('.panel-title, .card-title, .analysis-title, h1, h2');
            for (const el of titleEls) {
                const t = (el.innerText || '').trim();
                if (t && t.length > 2 && t.length < 100) return t;
            }
            // 方式2: 文档标题
            const dt = document.title || '';
            if (dt && dt.length > 2) return dt;
            return '';
        }""")
        log(f"   📋 页面标题: {page_title}")
        # 记录导出触发时间，用于在下载管理中校验
        export_trigger_time = datetime.now()

        # Step 3: (可选) 修改查询天数
        if days > 0:
            log(f"3. 修改查询天数为 {days} (页面类型: {detected_type})...")
            page.screenshot(path=str(out / "step3a_before_days_change.png"))
            if detected_type == "analytics":
                change_days_analytics_mode(page, days)
            else:
                change_days_tv_mode(page, days)
            page.screenshot(path=str(out / "step3b_after_click_analyze.png"))
            
            # 智能等待查询完成：检测查询进度弹窗是否消失 + 表格数据是否刷新
            # 灯塔查询时会弹出一个进度面板(校验查询请求→智能解析查询→动态资源评估→融合引擎查询)
            log(f"   等待查询完成 (最长 {wait_query}s)...")
            query_started = False
            for i in range(wait_query):
                time.sleep(1)
                qstatus = page.evaluate("""() => {
                    // 检测查询进度弹窗 (包含"放弃此查询"/"检查语法"/"校验查询请求"等关键词)
                    const allText = document.body.innerText || '';
                    const hasQueryProgress = allText.includes('放弃此查询') || allText.includes('检查语法')
                        || allText.includes('校验查询请求') || allText.includes('智能解析查询')
                        || allText.includes('动态资源评估') || allText.includes('融合引擎查询');
                    // 检测查询耗时标签是否可见（格式: "00:00:XX"），说明查询已完成
                    const hasElapsed = /\\d{2}:\\d{2}:\\d{2}/.test(allText);
                    // 检测表格/图表数据区域
                    const table = document.querySelector('.el-table__body');
                    const rows = table ? table.querySelectorAll('tr').length : 0;
                    return { queryProgress: hasQueryProgress, hasElapsed: hasElapsed, tableRows: rows };
                }""")
                is_querying = qstatus.get('queryProgress', False)
                if is_querying:
                    query_started = True
                if i % 5 == 0:
                    log(f"   查询 {i}/{wait_query}s 进度弹窗={qstatus.get('queryProgress')}, 耗时标签={qstatus.get('hasElapsed')}, 行数={qstatus.get('tableRows',0)}")
                if i % 10 == 0:
                    page.screenshot(path=str(out / f"step3c_query_{i}s.png"))
                # 查询已开始且进度弹窗消失 → 查询完成
                if query_started and not is_querying:
                    log(f"   ✅ 查询完成 ({i+1}s), 进度弹窗已消失, 行数: {qstatus.get('tableRows',0)}")
                    break
                # 检测到耗时标签出现（如 00:00:06）→ 查询已完成
                if qstatus.get('hasElapsed') and not is_querying and i > 3:
                    log(f"   ✅ 查询完成 ({i+1}s), 检测到耗时标签, 行数: {qstatus.get('tableRows',0)}")
                    break
                # 如果一直没检测到查询进度，但表格有足够数据，等几秒确认
                if not query_started and i > 10 and qstatus.get('tableRows', 0) >= 5:
                    log(f"   ✅ 未检测到查询进度弹窗，表格已有数据 ({i+1}s), 行数: {qstatus.get('tableRows',0)}")
                    break
            
            page.screenshot(path=str(out / "step3d_query_done.png"))
            # 查询完成后再等2秒让UI稳定
            time.sleep(2)
            log("   ✅ 天数修改并查询完成")

        # Step 4: (可选) 触发导出
        if trigger_export:
            page.screenshot(path=str(out / "step4a_before_export.png"))
            log("4. 触发导出...")
            if trigger_export_button(page):
                page.screenshot(path=str(out / "step4b_after_click_export.png"))
                log("   导出已触发，等待判断下载方式...")
                # 点击导出后，根据数据量有两种响应:
                # < 5000 行: 浏览器直接触发 download 事件（通常1-3秒）
                # >= 5000 行: 页面顶部弹出蓝色提示条（"已发起下载任务"等），不触发 download
                #
                # 策略: 最多等10秒，期间检测:
                #   1) download 事件触发 → 小文件模式
                #   2) 页面出现"下载任务"相关提示 → 大文件模式
                #   3) 超时仍无 → 判定为大文件模式
                export_detect_wait = min(10, wait_export)
                big_file_detected = False
                for i in range(export_detect_wait):
                    time.sleep(1)
                    if downloaded_files:
                        break
                    # 检测页面是否出现大文件模式的提示（蓝色提示条）
                    hint = page.evaluate("""() => {
                        const allText = document.body.innerText || '';
                        // 灯塔大文件导出后会在顶部显示"已发起下载任务"/"导出任务已创建"等提示
                        const keywords = ['下载任务', '导出任务', '已发起', '后台下载', '下载管理中查看'];
                        for (const kw of keywords) {
                            if (allText.includes(kw)) return kw;
                        }
                        return null;
                    }""")
                    if hint:
                        log(f"   📋 检测到大文件提示 ({i+1}s): \"{hint}\"")
                        big_file_detected = True
                        page.screenshot(path=str(out / "step4c_bigfile_hint.png"))
                        break
                    if i % 3 == 0:
                        log(f"   判断下载方式 {i}/{export_detect_wait}s...")

                if downloaded_files:
                    log("   ✅ 小文件模式: 浏览器已直接下载文件，跳过下载管理流程")
                else:
                    if big_file_detected:
                        log("   📋 大文件模式: 检测到导出任务提示，进入下载管理流程")
                    else:
                        log(f"   📋 大文件模式: 等待 {export_detect_wait}s 未检测到直接下载，进入下载管理流程")
                    page.screenshot(path=str(out / "step4d_no_direct_download.png"))
                    # 关闭可能弹出的干扰对话框（提示条等）
                    close_any_dialog(page)
            else:
                log("   ⚠️ 未找到导出按钮，跳过触发步骤")
                page.screenshot(path=str(out / "step4_error_no_export_btn.png"))

        # Step 5 & 6: 仅在"大文件模式"(未直接下载)时才进入下载管理流程
        if not downloaded_files:
            log("5. 打开下载管理...")
            if not open_quick_tools_sidebar(page):
                log("   ❌ 无法展开快捷工具侧边栏")
                page.screenshot(path=str(out / "error_no_sidebar.png"))
                browser.close()
                sys.exit(1)

            time.sleep(3)

            if not click_download_manager(page):
                log("   ❌ 无法找到下载管理入口")
                rt = page.evaluate("""() => {
                    const r = [];
                    const els = document.querySelectorAll('*');
                    for (const el of els) {
                        const rect = el.getBoundingClientRect();
                        const t = (el.innerText || '').trim();
                        if (rect.x > 1700 && t.length > 0 && t.length < 30 && el.children.length < 3)
                            r.push(t);
                    }
                    return [...new Set(r)];
                }""")
                log(f"   右侧文本: {rt}")
                page.screenshot(path=str(out / "error_no_dm.png"))
                browser.close()
                sys.exit(1)

            time.sleep(3)

            # Step 6: 循环刷新下载管理，查找并点击下载按钮
            # 灯塔的下载管理列表不会自动刷新，需要关闭弹窗→重新展开侧边栏→重新点击"下载管理"来刷新
            log(f"6. 查找下载任务 (最长等待 {wait_download}s, 每8s刷新一次)...")
            log(f"   🔍 匹配规则: 页面标题=\"{page_title}\", 触发时间={export_trigger_time.strftime('%H:%M')}")
            refresh_interval = 8  # 每8秒刷新一次
            max_attempts = max(1, wait_download // refresh_interval)
            
            for attempt in range(max_attempts):
                # 读取当前对话框中的任务列表
                info = find_download_buttons_in_dialog(page, task_name)
                
                if info:
                    if attempt == 0:
                        log(f"   对话框标题: {info['title']}")
                    log(f"   [第{attempt+1}次] 下载按钮数: {len(info['btns'])}")
                    for idx, row in enumerate(info.get('rows', [])[:5]):
                        log(f"   任务{idx}: {' | '.join(row)}")
                    page.screenshot(path=str(out / f"step6_attempt_{attempt}.png"))

                    # === 智能匹配：找到与页面标题一致且时间临近的任务 ===
                    matched_row_idx = -1
                    if info.get('rows') and len(info['rows']) > 0:
                        for idx, row in enumerate(info['rows']):
                            row_text = ' '.join(row)
                            
                            # 检查1: 标题匹配 — 任务名称需包含页面标题的关键词
                            title_match = False
                            if page_title:
                                # 从页面标题中提取关键词（去掉常见前后缀）
                                title_keywords = page_title.replace('-', ' ').replace('_', ' ').strip()
                                # 尝试完整匹配或关键词匹配
                                if title_keywords in row_text:
                                    title_match = True
                                else:
                                    # 取标题前几个有意义的词做模糊匹配
                                    for kw in title_keywords.split():
                                        if len(kw) >= 2 and kw in row_text:
                                            title_match = True
                                            break
                            if task_name and task_name in row_text:
                                title_match = True
                            # 如果没有标题信息，默认匹配第一个
                            if not page_title and not task_name:
                                title_match = True
                            
                            # 检查2: 时间临近 — 任务创建时间应在导出触发前后10分钟内
                            time_match = False
                            # 灯塔下载管理中的时间格式通常为 "YYYY-MM-DD HH:MM:SS" 或 "HH:MM"
                            time_patterns = re.findall(r'(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})', row_text)
                            if not time_patterns:
                                time_patterns = re.findall(r'(\d{2}:\d{2}:\d{2})', row_text)
                            
                            if time_patterns:
                                for tp in time_patterns:
                                    try:
                                        if len(tp) > 10:
                                            task_time = datetime.strptime(tp, "%Y-%m-%d %H:%M:%S")
                                        else:
                                            task_time = datetime.now().replace(
                                                hour=int(tp[:2]), minute=int(tp[3:5]), second=int(tp[6:8]))
                                        diff_seconds = abs((task_time - export_trigger_time).total_seconds())
                                        if diff_seconds < 600:  # 10分钟以内
                                            time_match = True
                                            log(f"   ⏰ 任务{idx} 时间匹配: {tp} (差{diff_seconds:.0f}s)")
                                            break
                                    except Exception:
                                        pass
                            else:
                                # 没有解析到时间，对于第一个任务宽松处理
                                if idx == 0:
                                    time_match = True
                            
                            # 检查3: 排除未完成的任务
                            is_processing = any(kw in row_text for kw in ['计算中', '处理中', '等待', '排队'])
                            
                            log(f"   任务{idx} 匹配: 标题={title_match}, 时间={time_match}, 处理中={is_processing}")
                            
                            if title_match and time_match and not is_processing:
                                matched_row_idx = idx
                                log(f"   ✅ 匹配到任务{idx}: {' | '.join(row)}")
                                break
                            elif title_match and is_processing:
                                log(f"   ⏳ 任务{idx} 标题匹配但仍在处理中...")
                                matched_row_idx = -2  # 标记为"找到但未完成"
                    
                    if matched_row_idx == -2:
                        log(f"   ⏳ 目标任务仍在计算中，等待刷新...")
                    elif matched_row_idx >= 0 and info['btns']:
                        # 点击匹配行对应的下载按钮
                        # 按钮通常和行是一一对应的（第0行对应第0个按钮）
                        btn_idx = min(matched_row_idx, len(info['btns']) - 1)
                        btn = info['btns'][btn_idx]
                        log(f"   点击下载按钮{btn_idx} ({btn['x']},{btn['y']})")
                        page.mouse.click(btn['x'], btn['y'])

                        # 等待几秒看是否触发了下载事件
                        for w in range(15):
                            time.sleep(1)
                            if downloaded_files:
                                log(f"   ✅ 文件下载完成! (第{attempt+1}次尝试, 等待{w+1}s)")
                                break
                        
                        if downloaded_files:
                            break
                        else:
                            log(f"   ⏳ 点击下载后未触发下载事件...")
                    elif matched_row_idx == -1 and info['btns']:
                        log(f"   ⚠️ 未匹配到标题/时间一致的任务，等待刷新...")
                
                if downloaded_files:
                    break
                    
                if attempt < max_attempts - 1:
                    # 关闭当前弹窗，等待后重新展开侧边栏并点击下载管理以刷新列表
                    log(f"   🔄 关闭弹窗，{refresh_interval}s后刷新下载管理...")
                    close_any_dialog(page)
                    time.sleep(refresh_interval)
                    # 关闭弹窗后侧边栏也会收起，必须先重新展开侧边栏
                    if not open_quick_tools_sidebar(page):
                        log("   ⚠️ 重新展开侧边栏失败，尝试直接点击下载管理...")
                    time.sleep(1)
                    # 然后点击下载管理
                    if not click_download_manager(page):
                        log("   ⚠️ 点击下载管理失败，重试...")
                        time.sleep(2)
                        open_quick_tools_sidebar(page)
                        time.sleep(2)
                        click_download_manager(page)
                    time.sleep(3)
            
            if not downloaded_files:
                log(f"   ⚠️ 等待 {wait_download}s 后仍未收到下载事件")
                page.screenshot(path=str(out / "step6_timeout.png"))
        else:
            log("5. 跳过下载管理 (文件已通过直接下载获取)")

        page.screenshot(path=str(out / "final_state.png"))
        browser.close()

    # 整理结果
    log("\n=== 结果 ===")
    if downloaded_files:
        for f in downloaded_files:
            fp = Path(f)
            log(f"✅ {fp.name} ({fp.stat().st_size:,} bytes)")
            organize_downloaded_file(fp, out, task_name or "灯塔导出数据")
    else:
        log("⚠️ 未下载到任何文件")
        log("   可能原因:")
        log("   1. 下载任务尚未完成，请稍后重试 (不带 --trigger-export)")
        log("   2. 认证状态已过期，请重新运行 beacon_login.py")
        log("   3. 页面结构变化，需要调试")

    log(f"\n输出目录: {out}")
    return downloaded_files


def main():
    parser = argparse.ArgumentParser(description="灯塔下载管理导出")
    parser.add_argument("--auth", "-a", required=True, help="认证状态文件路径")
    parser.add_argument("--url", "-u", required=True, help="灯塔页面 URL")
    parser.add_argument("--output-dir", "-o", default="./beacon_downloads", help="输出目录")
    parser.add_argument("--trigger-export", action="store_true", help="先触发导出任务")
    parser.add_argument("--task-name", type=str, default=None, help="匹配下载任务名称关键词")
    parser.add_argument("--days", "-d", type=int, default=0,
                        help="修改查询天数 (如 180)。不指定或为 0 则使用页面默认天数")
    parser.add_argument("--page-type", type=str, default="auto",
                        choices=["auto", "tv", "analytics"],
                        help="页面展示类型: auto=自动检测, tv=TV模式(PanelMax), analytics=敏捷分析模式")
    parser.add_argument("--wait-load", type=int, default=30, help="页面加载等待秒数")
    parser.add_argument("--wait-export", type=int, default=30, help="导出任务等待秒数")
    parser.add_argument("--wait-download", type=int, default=120, help="文件下载等待秒数")
    parser.add_argument("--wait-query", type=int, default=120, help="修改天数后等待查询完成秒数")
    args = parser.parse_args()

    run(args.auth, args.url, args.output_dir, args.trigger_export,
        args.task_name, args.wait_load, args.wait_export, args.wait_download,
        args.days, args.page_type, args.wait_query)


if __name__ == "__main__":
    main()
