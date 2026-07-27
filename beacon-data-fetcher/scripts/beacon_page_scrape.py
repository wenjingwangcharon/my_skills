#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
灯塔(Beacon)页面数据抓取脚本 — 通过拦截 API 响应 + 解析 DOM 获取数据。

适用场景: 灯塔页面可直接展示的数据 (API 拦截模式)。
支持页面类型:
  - TV 模式 (PanelMax): 通过"探索分析→天数→确定"修改时间
  - 敏捷分析模式 (Analytics_Mode): 通过"时间设置→天数→立即分析"修改时间
  - 自动检测: 根据 URL 自动判断页面类型
支持抓取: 表格数据、ECharts 图表数据、API 响应中的 JSON 数据。

使用方法:
  # 基础用法：直接抓取页面默认数据 (自动检测页面类型)
  python3 beacon_page_scrape.py \\
    --auth /path/to/beacon_auth_state.json \\
    --url "https://beacon.woa.com/datainsight/..." \\
    --output-dir /path/to/output \\
    --wait 10

  # TV 模式修改天数
  python3 beacon_page_scrape.py \\
    --auth /path/to/beacon_auth_state.json \\
    --url "https://beacon.woa.com/datainsight/.../PanelMax/..." \\
    --output-dir /path/to/output \\
    --days 180 \\
    --poll-timeout 300

  # 敏捷分析模式修改天数
  python3 beacon_page_scrape.py \\
    --auth /path/to/beacon_auth_state.json \\
    --url "https://beacon.woa.com/datainsight/.../Analytics_Mode/..." \\
    --output-dir /path/to/output \\
    --days 120

  # 强制指定页面类型 (覆盖自动检测)
  python3 beacon_page_scrape.py \\
    --auth /path/to/beacon_auth_state.json \\
    --url "https://beacon.woa.com/datainsight/..." \\
    --output-dir /path/to/output \\
    --page-type analytics \\
    --days 180

参数:
  --auth, -a         认证状态文件路径 (由 beacon_login.py 生成)
  --url, -u          灯塔数据页面 URL
  --output-dir, -o   输出目录 (默认: ./beacon_output)
  --wait, -w         页面加载等待秒数 (默认: 10)
  --screenshot       是否保存截图 (默认: True)
  --days, -d         修改查询天数 (如 180)。不指定则使用页面默认天数
  --page-type        页面展示类型: auto/tv/analytics (默认: auto, 根据URL自动检测)
  --poll-timeout     修改天数后等待查询结果的超时秒数 (默认: 300)
  --step-screenshots 是否在修改天数流程中每步都截图 (默认: True)
"""

import argparse
import csv
import json
import re
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


def extract_table_data(page) -> list:
    """从页面 DOM 中提取所有表格数据"""
    tables = []
    try:
        table_elements = page.query_selector_all("table")
        for idx, table in enumerate(table_elements):
            rows = table.query_selector_all("tr")
            table_rows = []
            for row in rows:
                cells = row.query_selector_all("td, th")
                row_data = [cell.inner_text().strip() for cell in cells]
                if row_data:
                    table_rows.append(row_data)
            if table_rows:
                tables.append(table_rows)
                log(f"   📋 表格{idx + 1}: {len(table_rows)} 行 x {len(table_rows[0])} 列")
    except Exception as e:
        log(f"   ⚠️ 提取表格失败: {e}")
    return tables


def extract_echarts_data(page) -> list:
    """通过 JavaScript 获取 ECharts 图表底层数据"""
    chart_data = []
    try:
        result = page.evaluate("""() => {
            const results = [];
            try {
                const canvases = document.querySelectorAll('canvas');
                for (const canvas of canvases) {
                    const chart = typeof echarts !== 'undefined' && echarts.getInstanceByDom(canvas.parentElement);
                    if (chart) {
                        const option = chart.getOption();
                        results.push({
                            type: 'echarts',
                            series: option.series ? option.series.map(s => ({
                                name: s.name, type: s.type, data: s.data
                            })) : [],
                            xAxis: option.xAxis ? option.xAxis.map(x => ({ data: x.data })) : [],
                            legend: option.legend ? option.legend.map(l => ({ data: l.data })) : [],
                        });
                    }
                }
            } catch(e) {}
            return results;
        }""")
        if result:
            chart_data.extend(result)
            log(f"   📈 获取到 {len(result)} 组图表数据")
    except Exception as e:
        log(f"   ⚠️ 提取图表数据失败: {e}")
    return chart_data


def extract_from_api_response(data) -> list:
    """递归从 API 响应 JSON 中提取数据行。
    
    灯塔 API 响应结构多种多样，常见路径:
    - data.data.rows / data.data.result / data.data.records  (事件分析)
    - data.result.objects  (PanelMax 面板卡片)
    - data.result.data     (查询结果)
    """
    rows = []
    if isinstance(data, dict):
        # 路径一: data.xxx (原始逻辑)
        data_fields = ["data", "result", "results", "rows", "records", "list", "items", "series", "objects"]
        for field in data_fields:
            if field in data:
                inner = data[field]
                if isinstance(inner, list):
                    for item in inner:
                        if isinstance(item, dict):
                            rows.append(item)
                        elif isinstance(item, list):
                            for sub in item:
                                if isinstance(sub, dict):
                                    rows.append(sub)
                elif isinstance(inner, dict):
                    rows.extend(extract_from_api_response(inner))
    return rows


def echarts_to_rows(chart: dict) -> list:
    """将 ECharts 数据转为行列式数据"""
    rows = []
    try:
        x_data = []
        if chart.get("xAxis"):
            for x in chart["xAxis"]:
                if x.get("data"):
                    x_data = x["data"]
                    break
        for series in chart.get("series", []):
            name = series.get("name", "unknown")
            for i, val in enumerate(series.get("data", [])):
                row = {"指标名称": name}
                if i < len(x_data):
                    row["日期"] = str(x_data[i])
                else:
                    row["日期"] = str(i)
                if isinstance(val, (int, float)):
                    row["值"] = val
                elif isinstance(val, dict):
                    row["值"] = val.get("value", val)
                elif isinstance(val, list) and len(val) >= 2:
                    row["日期"] = str(val[0])
                    row["值"] = val[1]
                else:
                    row["值"] = str(val)
                rows.append(row)
    except Exception as e:
        log(f"   ⚠️ 解析 ECharts 数据失败: {e}")
    return rows


def save_csv(rows: list, path: Path) -> bool:
    """将字典列表保存为 CSV"""
    if not rows:
        return False
    all_keys = []
    seen = set()
    for row in rows:
        for k in row.keys():
            if k not in seen:
                all_keys.append(k)
                seen.add(k)
    with open(str(path), "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=all_keys)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    log(f"✅ CSV 已保存: {path} ({len(rows)} 行, {len(all_keys)} 列)")
    return True


def detect_page_type(url: str) -> str:
    """根据 URL 自动检测灯塔页面展示类型。
    
    灯塔 URL 格式:
    - TV 模式: .../PanelMax/...  (如 /PanelMax/98034/New_event_Card_Max/633824)
    - 敏捷分析模式: .../Analytics_Mode/...  (如 /Analytics_Mode/98034/New_Event_Card_Modify/633824)
    - 事件分析: .../New_Event_Modify/...  (不含 PanelMax 或 Analytics_Mode)
    
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
        return "tv"  # 默认使用 TV 模式


def change_query_days_analytics(page, days: int, timestamp: str, out: Path, step_screenshots: bool = True):
    """敏捷分析模式下修改查询天数。
    
    流程: 找到时间设置区域 → 修改天数输入框 → 点击"立即分析"按钮
    
    敏捷分析模式的时间设置 UI 布局:
      时间设置  [相对时间 v]  过去  [-] [120] [+]  [天 v]   □ 对比 ?
      [立即分析] [后台分析] [查看SQL]
    
    Args:
        page: Playwright page 对象
        days: 目标天数 (如 180)
        timestamp: 时间戳字符串
        out: 输出目录
        step_screenshots: 是否每步截图
    """
    step_idx = [0]
    
    def step_screenshot(label):
        if step_screenshots:
            step_idx[0] += 1
            fname = f"analytics_step{step_idx[0]:02d}_{label}_{timestamp}.png"
            page.screenshot(path=str(out / fname))
            log(f"   📸 截图: {fname}")

    # --- 隐藏sidebar避免遮挡 ---
    page.evaluate("()=>{const s=document.querySelector('.main-app-sidebar');if(s)s.style.display='none'}")
    time.sleep(0.5)

    # --- 查找时间设置区域中的天数输入框 ---
    log(f"[敏捷分析-修改天数] 查找时间设置区域...")
    
    # 敏捷分析模式的输入框查找逻辑:
    # 时间设置区域通常在页面顶部，包含"时间设置"文字、"相对时间"下拉、天数输入框、"天"单位
    time_setting_info = page.evaluate("""()=>{
        const results = {inputs: [], labels: [], buttons: []};
        
        // 1. 查找所有可见的 input 元素
        document.querySelectorAll('input[type="number"],input.el-input__inner').forEach(el=>{
            if(el.offsetParent===null) return;
            const rect = el.getBoundingClientRect();
            if(rect.width <= 0) return;
            results.inputs.push({
                tag: el.tagName, type: el.type, val: el.value,
                x: Math.round(rect.x), y: Math.round(rect.y),
                w: Math.round(rect.width), h: Math.round(rect.height),
                placeholder: el.placeholder||'',
                cls: (el.className||'').toString().substring(0,60)
            });
        });
        
        // 2. 查找"时间设置"标签位置 (用于定位同行的输入框)
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
        
        // 3. 查找"立即分析"按钮
        document.querySelectorAll('button').forEach(el=>{
            if(el.offsetParent===null) return;
            const text = (el.innerText||'').trim();
            if(text.includes('立即分析')){
                const rect = el.getBoundingClientRect();
                results.buttons.push({
                    text: text, cls: (el.className||'').toString().substring(0,80),
                    x: Math.round(rect.x), y: Math.round(rect.y),
                    w: Math.round(rect.width), h: Math.round(rect.height)
                });
            }
        });
        
        return results;
    }""")
    log(f"   时间设置标签: {json.dumps(time_setting_info['labels'], ensure_ascii=False)}")
    log(f"   输入框: {json.dumps(time_setting_info['inputs'], ensure_ascii=False)}")
    log(f"   立即分析按钮: {json.dumps(time_setting_info['buttons'], ensure_ascii=False)}")
    step_screenshot("time_setting_scan")

    # --- 定位天数输入框 ---
    log(f"[敏捷分析-修改天数] 定位天数输入框...")
    day_input = None
    
    # 策略1: 在"时间设置"标签同行 (y坐标接近) 找纯数字输入框
    if time_setting_info['labels']:
        label_y = time_setting_info['labels'][0]['y']
        same_row_inputs = [
            inp for inp in time_setting_info['inputs']
            if abs(inp.get('y', 9999) - label_y) < 30  # 同行：y坐标差值 < 30px
        ]
        for inp in same_row_inputs:
            val = inp.get('val', '')
            if val.isdigit() and 1 <= int(val) <= 999:
                day_input = inp
                log(f"   策略1(时间设置同行): val={val}")
                break
    
    # 策略2: 找值为常见天数的输入框 (30, 60, 90, 120, 180)
    if not day_input:
        common_days = {'30', '60', '90', '120', '180', '365', '7', '14'}
        for inp in time_setting_info['inputs']:
            val = inp.get('val', '')
            if val in common_days and inp.get('y', 9999) < 400:
                day_input = inp
                log(f"   策略2(常见天数): val={val}")
                break

    # 策略3: 页面上半部分(y<400)的 type=number 输入框
    if not day_input:
        for inp in time_setting_info['inputs']:
            if inp.get('type') == 'number' and inp.get('y', 9999) < 400:
                day_input = inp
                log(f"   策略3(number类型): val={inp.get('val','')}")
                break

    # 策略4: 页面上半部分任何纯数字输入框 (宽松匹配)
    if not day_input:
        for inp in time_setting_info['inputs']:
            val = inp.get('val', '')
            if (val.isdigit() and 1 <= int(val) <= 999
                    and inp.get('y', 9999) < 400
                    and val not in ('1', '50')):  # 排除页码
                day_input = inp
                log(f"   策略4(宽松匹配): val={val}")
                break

    if day_input:
        cx = day_input['x'] + day_input['w'] // 2
        cy = day_input['y'] + day_input['h'] // 2
        log(f"   天数输入框: val={day_input['val']} at ({cx},{cy})")
        
        # 使用键盘方式输入：三击全选 + 退格 + 键入新值
        # nativeSetter 在输入框已有非默认值时可能无法触发框架响应
        page.mouse.click(cx, cy, click_count=3)
        time.sleep(0.3)
        page.keyboard.press("Backspace")
        time.sleep(0.2)
        page.keyboard.type(str(days), delay=50)
        time.sleep(0.5)
        
        # 验证值已更改
        new_val = page.evaluate("""(selector)=>{
            const inputs = document.querySelectorAll('input[type="number"],input.el-input__inner');
            for(const el of inputs){
                if(el.offsetParent===null) continue;
                const rect = el.getBoundingClientRect();
                if(Math.abs(rect.x - selector.x) < 5 && Math.abs(rect.y - selector.y) < 5){
                    return el.value;
                }
            }
            return 'NOT_FOUND';
        }""", {"x": day_input['x'], "y": day_input['y']})
        log(f"   输入后验证: val={new_val} (目标: {days})")
    else:
        log("   ⚠ 未找到天数输入框!")

    step_screenshot("after_input_days")

    # --- 点击"立即分析"按钮 ---
    log(f"[敏捷分析-修改天数] 点击立即分析...")
    analyze_btn = None
    
    # 优先选择 el-button--primary 类型的"立即分析"按钮
    for btn in time_setting_info['buttons']:
        if 'primary' in btn.get('cls', ''):
            analyze_btn = btn
            break
    # 退而求其次：任何"立即分析"按钮
    if not analyze_btn and time_setting_info['buttons']:
        analyze_btn = time_setting_info['buttons'][0]

    if analyze_btn:
        cx = analyze_btn['x'] + analyze_btn['w'] // 2
        cy = analyze_btn['y'] + analyze_btn['h'] // 2
        log(f"   立即分析按钮: ({cx},{cy}) - {analyze_btn.get('text','')}")
        page.mouse.click(cx, cy)
    else:
        log("   ⚠ 未找到立即分析按钮! 尝试通过 JS 点击...")
        clicked_js = page.evaluate("""()=>{
            const btns = document.querySelectorAll('button');
            for(const btn of btns){
                if(btn.offsetParent===null) continue;
                const text = (btn.innerText||'').trim();
                if(text.includes('立即分析')){
                    btn.click(); return 'clicked: ' + text;
                }
            }
            // 备用：找 el-button--primary el-button--mini 按钮
            for(const btn of btns){
                if(btn.offsetParent===null) continue;
                if(btn.classList.contains('el-button--primary') && btn.classList.contains('el-button--mini')){
                    const text = (btn.innerText||'').trim();
                    btn.click(); return 'primary-mini: ' + text;
                }
            }
            return false;
        }""")
        log(f"   JS 点击结果: {clicked_js}")

    time.sleep(3)
    step_screenshot("after_analyze_click")
    log(f"[敏捷分析-修改天数] 立即分析已点击，等待查询...")


def change_query_days(page, days: int, timestamp: str, out: Path, step_screenshots: bool = True):
    """通过探索分析面板修改查询天数。
    
    流程: 点击"探索分析"展开左侧面板 → 找到天数输入框(默认30) → 修改为目标天数 → 点击确定
    
    Args:
        page: Playwright page 对象
        days: 目标天数 (如 180)
        timestamp: 时间戳字符串
        out: 输出目录
        step_screenshots: 是否每步截图
    
    Returns:
        int: 点击确定前的 api_responses 数量偏移，用于后续轮询时判断新响应
    """
    step_idx = [0]
    
    def step_screenshot(label):
        if step_screenshots:
            step_idx[0] += 1
            fname = f"step{step_idx[0]:02d}_{label}_{timestamp}.png"
            page.screenshot(path=str(out / fname))
            log(f"   📸 截图: {fname}")

    # --- 隐藏sidebar避免遮挡 ---
    page.evaluate("()=>{const s=document.querySelector('.main-app-sidebar');if(s)s.style.display='none'}")
    time.sleep(0.5)

    # --- 查找并点击 "探索分析" 按钮 ---
    log(f"[修改天数] 查找探索分析按钮...")
    explore_info = page.evaluate("""()=>{
        const results = [];
        const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_ELEMENT);
        while(walker.nextNode()){
            const el = walker.currentNode;
            if(el.offsetParent === null && el.tagName !== 'BODY') continue;
            const text = el.innerText || el.textContent || '';
            const first20 = text.trim().substring(0,20);
            if(first20.includes('探索分析') || first20.includes('探索')){
                const rect = el.getBoundingClientRect();
                results.push({
                    tag: el.tagName, cls: (el.className||'').toString().substring(0,60),
                    text: first20, x: Math.round(rect.x), y: Math.round(rect.y),
                    w: Math.round(rect.width), h: Math.round(rect.height)
                });
            }
        }
        document.querySelectorAll('[class*="show_setting"],[class*="setting_btn"]').forEach(el=>{
            const rect = el.getBoundingClientRect();
            results.push({
                tag: el.tagName, cls: (el.className||'').toString().substring(0,60),
                text: (el.innerText||'').trim().substring(0,20),
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
    step_screenshot("after_explore_click")

    # --- 检查面板是否展开，找到天数输入框和确定按钮 ---
    log(f"[修改天数] 检查面板状态...")
    panel_info = page.evaluate("""()=>{
        const inputs = [];
        document.querySelectorAll('input[type="number"],input.el-input__inner').forEach(el=>{
            if(el.offsetParent===null) return;
            const rect = el.getBoundingClientRect();
            inputs.push({
                tag: el.tagName, type: el.type, val: el.value,
                x: Math.round(rect.x), y: Math.round(rect.y),
                w: Math.round(rect.width), h: Math.round(rect.height),
                placeholder: el.placeholder||''
            });
        });
        const btns = [];
        document.querySelectorAll('button').forEach(el=>{
            if(el.offsetParent===null) return;
            const text = (el.innerText||'').trim();
            const rect = el.getBoundingClientRect();
            if(text === '确定' || text === '确 定'){
                btns.push({
                    text, cls: (el.className||'').toString().substring(0,60),
                    x: Math.round(rect.x), y: Math.round(rect.y),
                    w: Math.round(rect.width), h: Math.round(rect.height)
                });
            }
        });
        return {inputs, btns};
    }""")
    log(f"   输入框: {json.dumps(panel_info['inputs'], ensure_ascii=False)}")
    log(f"   确定按钮: {json.dumps(panel_info['btns'], ensure_ascii=False)}")
    step_screenshot("panel_check")

    # --- 找到天数输入框并修改 ---
    log(f"[修改天数] 修改天数为 {days}...")
    day_input = None

    # 策略1: 优先找 val=30 的输入框（面板区域 y < 300）
    for inp in panel_info['inputs']:
        if inp.get('val') == '30' and inp.get('y', 999) < 300:
            day_input = inp
            break

    # 策略2: 找"相对时间"和"天"之间的纯数字输入框
    # 灯塔面板布局: [相对时间] [数字天数] [天] 三个输入框在同一行
    if not day_input:
        panel_inputs = [inp for inp in panel_info['inputs'] if inp.get('y', 999) < 300]
        # 按 x 坐标排序，找出同一行(y值接近)的输入框组
        for inp in panel_inputs:
            val = inp.get('val', '')
            # 天数输入框的特征: 值是纯数字(如 30, 60, 90, 180)，且不是页码等
            if val.isdigit() and 1 <= int(val) <= 999 and inp.get('x', 999) < 500:
                # 进一步确认: 在同一行附近有"相对时间"或"天"字样的输入框
                same_row = [i for i in panel_inputs
                            if abs(i.get('y', 0) - inp.get('y', 0)) < 10]
                has_time_hint = any(
                    '时间' in i.get('val', '') or '天' == i.get('val', '').strip()
                    for i in same_row
                )
                if has_time_hint:
                    day_input = inp
                    log(f"   策略2匹配: 同行有时间/天提示，val={val}")
                    break

    # 策略3: 面板区域内 type=number 的输入框
    if not day_input:
        for inp in panel_info['inputs']:
            if inp.get('type') == 'number' and inp.get('y', 999) < 300 and inp.get('x', 999) < 500:
                day_input = inp
                break

    # 策略4: 面板区域内值为纯数字的输入框（最宽松匹配）
    if not day_input:
        for inp in panel_info['inputs']:
            val = inp.get('val', '')
            if (val.isdigit() and 1 <= int(val) <= 999
                    and inp.get('y', 999) < 300 and inp.get('x', 999) < 500
                    and val not in ('1', '50')):  # 排除页码和每页条数
                day_input = inp
                log(f"   策略4匹配: 宽松数字匹配 val={val}")
                break

    if day_input:
        cx = day_input['x'] + day_input['w'] // 2
        cy = day_input['y'] + day_input['h'] // 2
        log(f"   天数输入框: val={day_input['val']} at ({cx},{cy})")

        # 使用键盘方式输入：三击全选 + 退格 + 键入新值
        # nativeSetter 在输入框已有非默认值时可能无法触发框架响应
        page.mouse.click(cx, cy, click_count=3)
        time.sleep(0.3)
        page.keyboard.press("Backspace")
        time.sleep(0.2)
        page.keyboard.type(str(days), delay=50)
        time.sleep(0.5)

        # 验证值已更改
        new_val = page.evaluate("""(selector)=>{
            const inputs = document.querySelectorAll('input[type="number"],input.el-input__inner');
            for(const el of inputs){
                if(el.offsetParent===null) continue;
                const rect = el.getBoundingClientRect();
                if(Math.abs(rect.x - selector.x) < 5 && Math.abs(rect.y - selector.y) < 5){
                    return el.value;
                }
            }
            return 'NOT_FOUND';
        }""", {"x": day_input['x'], "y": day_input['y']})
        log(f"   输入后验证: val={new_val} (目标: {days})")
    else:
        log("   ⚠ 未找到天数输入框!")
        all_inputs = page.evaluate("""()=>{
            const arr = [];
            document.querySelectorAll('input').forEach(el=>{
                if(el.offsetParent===null) return;
                const rect = el.getBoundingClientRect();
                arr.push({
                    type: el.type, val: el.value,
                    x: Math.round(rect.x), y: Math.round(rect.y),
                    w: Math.round(rect.width), h: Math.round(rect.height),
                    cls: (el.className||'').substring(0,40)
                });
            });
            return arr;
        }""")
        log(f"   所有可见input: {json.dumps(all_inputs, ensure_ascii=False)}")

    step_screenshot("after_input_days")

    # --- 点击确定按钮 ---
    log(f"[修改天数] 点击确定按钮...")
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
        log("   ⚠ 未找到确定按钮! 尝试通过 JS 点击...")
        clicked_js = page.evaluate("""()=>{
            const btns = document.querySelectorAll('button');
            for(const btn of btns){
                if(btn.offsetParent===null) continue;
                const text = (btn.innerText||'').trim();
                if(text === '确定' || text === '确 定'){
                    btn.click(); return true;
                }
            }
            for(const btn of btns){
                if(btn.offsetParent===null) continue;
                if(btn.classList.contains('el-button--primary') && btn.classList.contains('el-button--mini')){
                    btn.click(); return 'primary-mini';
                }
            }
            return false;
        }""")
        log(f"   JS 点击结果: {clicked_js}")

    time.sleep(3)
    step_screenshot("after_confirm_click")
    log(f"[修改天数] 确定按钮已点击，等待查询...")


def poll_query_result(api_responses: list, resp_offset: int, page, out: Path,
                      timestamp: str, poll_timeout: int = 300,
                      step_screenshots: bool = True) -> list:
    """轮询等待修改天数后的异步查询结果。
    
    Args:
        api_responses: 全局 API 响应列表（实时更新）
        resp_offset: 点击确定前的 api_responses 长度
        page: Playwright page 对象
        out: 输出目录
        timestamp: 时间戳字符串
        poll_timeout: 超时秒数
        step_screenshots: 是否定期截图
    
    Returns:
        list: 查询到的数据行列表
    """
    log(f"[轮询] 等待 async_query 返回数据 (超时 {poll_timeout}s)...")

    # 先等几秒看查询进度
    time.sleep(5)
    if step_screenshots:
        page.screenshot(path=str(out / f"query_progress_5s_{timestamp}.png"))

    best_data = []
    for waited in range(0, poll_timeout, 5):
        time.sleep(5)

        best_count = 0
        best_state = ""
        best_objects = []
        for r in api_responses[resp_offset:]:
            d = r.get("data", {})
            if not isinstance(d, dict):
                continue
            result = d.get("result", {})
            if not isinstance(result, dict):
                continue
            qs = result.get("query_state", "")
            objects = result.get("objects", [])
            if isinstance(objects, list) and len(objects) > best_count:
                best_count = len(objects)
                best_state = qs
                best_objects = objects

        log(f"   [{waited + 5}s] 总响应={len(api_responses)}, 新响应={len(api_responses) - resp_offset}, max_rows={best_count}, state={best_state}")

        if best_count >= 1 and best_state == "SUCCESS":
            best_data = best_objects
            log(f"   ✓ 数据就绪: {best_count} 行!")
            break

        # 每 30 秒截一张图
        if step_screenshots and (waited + 5) % 30 == 0:
            page.screenshot(path=str(out / f"polling_{waited + 5}s_{timestamp}.png"))

        # 60 秒还没新响应，警告
        if waited == 55 and len(api_responses) - resp_offset == 0:
            log("   ⚠ 60s 无新响应")
            if step_screenshots:
                page.screenshot(path=str(out / f"no_response_60s_{timestamp}.png"))

    if step_screenshots:
        page.screenshot(path=str(out / f"poll_final_{timestamp}.png"))

    return best_data


def run(auth_path: str, url: str, output_dir: str, wait_seconds: int = 10,
        screenshot: bool = True, days: int = 0, poll_timeout: int = 300,
        step_screenshots: bool = True, page_type: str = "auto"):
    """主抓取流程
    
    Args:
        auth_path: 认证状态文件路径
        url: 灯塔数据页面 URL
        output_dir: 输出目录
        wait_seconds: 页面加载等待秒数
        screenshot: 是否保存截图
        days: 修改查询天数 (0 表示不修改，使用页面默认)
        poll_timeout: 修改天数后等待查询结果的超时秒数
        step_screenshots: 是否在修改天数流程中每步截图
        page_type: 页面展示类型 auto/tv/analytics (默认 auto)
    """
    auth = Path(auth_path).resolve()
    out = Path(output_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)

    if not auth.exists():
        log(f"❌ 认证文件不存在: {auth}")
        log("   请先运行 beacon_login.py 生成认证状态")
        sys.exit(1)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    api_responses = []

    log("=== 灯塔页面数据抓取 ===")
    
    # 检测页面类型
    if page_type == "auto":
        detected_type = detect_page_type(url)
        log(f"   页面类型(自动检测): {detected_type}")
    else:
        detected_type = page_type
        log(f"   页面类型(手动指定): {detected_type}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = browser.new_context(
            storage_state=str(auth),
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 Chrome/130",
        )

        def on_response(resp):
            try:
                ct = resp.headers.get("content-type", "")
                if "json" in ct:
                    body = resp.json()
                    api_responses.append({
                        "url": resp.url, "status": resp.status, "data": body,
                        "time": datetime.now().isoformat()
                    })
            except Exception:
                pass

        page = context.new_page()
        page.on("response", on_response)

        log(f"1. 打开页面: {url}")
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=90000)
        except Exception as e:
            log(f"   ⚠️ 加载超时: {e}")

        # 1.5 立即检查登录态（goto domcontentloaded 后无需额外等待）
        time.sleep(1)  # 仅等1秒让可能的重定向完成
        if is_login_page(page):
            log("⚠️ 检测到登录态已失效，页面被重定向到登录页!")
            if screenshot:
                page.screenshot(path=str(out / f"login_expired_{timestamp}.png"))
            log("WAITING_FOR_LOGIN")
            log("   登录服务应已启动扫码流程，等待登录完成...")
            
            # 等待登录态恢复 — 通过 runtime/.scan_status 信号文件
            login_restored = False
            login_wait_timeout = 300  # 最长等待5分钟
            status_file = _RUNTIME_DIR / ".scan_status"
            # 向后兼容：也检查旧的信号文件路径
            old_status_file = Path("/tmp/beacon_auth_status")
            
            for i in range(login_wait_timeout):
                time.sleep(1)
                if i % 5 == 0:
                    log(f"   ⏳ 等待登录... {i}/{login_wait_timeout}s")
                
                # 检查信号文件（由 beacon_qr_server.py 写入）
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
                
                # 也检查页面本身是否已离开登录页
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
            
            # 用更新后的认证状态重新打开
            browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
            context = browser.new_context(
                storage_state=str(auth),
                viewport={"width": 1920, "height": 1080},
                user_agent="Mozilla/5.0 Chrome/130",
            )
            api_responses.clear()
            
            page = context.new_page()
            page.on("response", on_response)
            
            log(f"   重新打开页面: {url}")
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=90000)
            except Exception as e:
                log(f"   ⚠️ 重新加载超时: {e}")

        log(f"2. 等待数据加载 ({wait_seconds}s)...")
        for i in range(wait_seconds):
            time.sleep(1)
            if i % 5 == 0:
                log(f"   {i}/{wait_seconds}s — 已拦截 {len(api_responses)} 个 API 响应")

        log(f"   当前 URL: {page.url}")
        log(f"   拦截到 {len(api_responses)} 个 API 响应")

        if screenshot:
            ss_path = out / f"screenshot_{timestamp}.png"
            page.screenshot(path=str(ss_path))
            log(f"   📸 {ss_path}")

        # ===========================================================
        # 如果指定了 --days，根据页面类型选择修改天数的方式
        # ===========================================================
        days_csv_data = []
        if days > 0:
            log(f"\n=== 修改查询天数为 {days} (页面类型: {detected_type}) ===")
            resp_before = len(api_responses)
            
            if detected_type == "analytics":
                # 敏捷分析模式: 时间设置 → 天数 → 立即分析
                change_query_days_analytics(page, days, timestamp, out, step_screenshots)
            else:
                # TV 模式 / 事件分析: 探索分析 → 天数 → 确定
                change_query_days(page, days, timestamp, out, step_screenshots)
            
            days_csv_data = poll_query_result(
                api_responses, resp_before, page, out, timestamp,
                poll_timeout, step_screenshots
            )
            if days_csv_data:
                log(f"   ✅ 通过修改天数获取到 {len(days_csv_data)} 行数据")
                # 检查日期范围
                for k in ["dim_0", "ds", "date", "imp_date"]:
                    dates = sorted(set(str(r.get(k, "")) for r in days_csv_data if r.get(k)))
                    if dates:
                        log(f"   日期字段={k}, 范围: {dates[0]} ~ {dates[-1]} ({len(dates)} 天)")
                        break

        # 保存 API 响应
        api_path = out / f"api_responses_{timestamp}.json"
        api_path.write_text(json.dumps(api_responses, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        log(f"💾 API 响应: {api_path}")

        # 提取数据
        log("3. 提取数据...")
        csv_data = []

        # 从 API 响应提取 — 优先匹配已知的业务数据 API 路径
        biz_api_keywords = ["panel_card_result", "event_result", "query_result",
                            "funnel_result", "retention_result", "hue_result",
                            "sql_result", "chart_result", "/result"]
        # 跳过已知的配置/元数据 API
        skip_keywords = ["plugin/list", "plugin/conf", "commonConfig", "getUserInfo",
                         "feedback", "scopeSwitch", "upload/user", "msg/list",
                         "msg/config", "getCustomization", "getUserAdmin", "notice/get",
                         "role_with_module", "dict/plugin", "getBuList", "/role?",
                         "/category?", "/permission/", "data_resource/query",
                         "panel_card?", "panel_card/"]
        
        for resp in api_responses:
            resp_url = resp.get("url", "")
            
            # 跳过配置类 API
            if any(kw in resp_url for kw in skip_keywords):
                continue
            
            # 标记是否为已知的业务数据 API
            is_biz_api = any(kw in resp_url for kw in biz_api_keywords)
            
            extracted = extract_from_api_response(resp.get("data", {}))
            if extracted:
                if is_biz_api:
                    # 已知业务API，直接全部保留
                    csv_data.extend(extracted)
                    log(f"   📊 业务API匹配: {len(extracted)} 行 from {resp_url[:80]}")
                else:
                    # 未知API，用启发式判断：如果数据行包含日期字段(ds)或纯数值字段，则保留
                    valid_rows = []
                    for row in extracted:
                        keys = set(row.keys())
                        # 包含日期字段(ds/date/日期)或包含数量字段(*_cnt/*_num/count/amount)
                        has_date = bool(keys & {"ds", "date", "日期", "data_date", "stat_date"})
                        has_metric = any(k.endswith(("_cnt", "_num", "_count", "_amount", "_rate", "_uv", "_pv"))
                                        for k in keys)
                        if has_date or has_metric:
                            valid_rows.append(row)
                    if valid_rows:
                        csv_data.extend(valid_rows)
                        log(f"   📊 启发式匹配: {len(valid_rows)} 行 from {resp_url[:80]}")

        # 从 ECharts 提取
        charts = extract_echarts_data(page)
        for chart in charts:
            if chart.get("type") == "echarts":
                csv_data.extend(echarts_to_rows(chart))

        # 从表格提取
        tables = extract_table_data(page)
        for table in tables:
            if len(table) > 1:
                headers = table[0]
                for row in table[1:]:
                    row_dict = {headers[i]: row[i] for i in range(min(len(headers), len(row)))}
                    if row_dict:
                        csv_data.append(row_dict)

        # 保存页面文本 (备用)
        try:
            page_text = page.inner_text("body")
            text_path = out / f"page_text_{timestamp}.txt"
            text_path.write_text(page_text, encoding="utf-8")
        except Exception:
            pass

        browser.close()

    # 输出结果
    # 如果通过修改天数获取到了数据，优先使用
    if days_csv_data:
        csv_path = out / f"beacon_data_{timestamp}.csv"
        save_csv(days_csv_data, csv_path)
    elif csv_data:
        csv_path = out / f"beacon_data_{timestamp}.csv"
        save_csv(csv_data, csv_path)
    else:
        log("⚠️ 未能从 API/图表/表格中提取到结构化数据")
        log(f"   请检查 {api_path} 手动分析 API 响应")

    log(f"\n=== 完成 ===")
    log(f"输出目录: {out}")
    return str(out)


def main():
    parser = argparse.ArgumentParser(description="灯塔页面数据抓取")
    parser.add_argument("--auth", "-a", required=True, help="认证状态文件路径")
    parser.add_argument("--url", "-u", required=True, help="灯塔数据页面 URL")
    parser.add_argument("--output-dir", "-o", default="./beacon_output", help="输出目录")
    parser.add_argument("--wait", "-w", type=int, default=10, help="页面加载等待秒数")
    parser.add_argument("--no-screenshot", action="store_true", help="不保存截图")
    parser.add_argument("--days", "-d", type=int, default=0,
                        help="修改查询天数 (如 180)。不指定或为 0 则使用页面默认天数")
    parser.add_argument("--page-type", type=str, default="auto",
                        choices=["auto", "tv", "analytics"],
                        help="页面展示类型: auto=自动检测, tv=TV模式(PanelMax), analytics=敏捷分析模式")
    parser.add_argument("--poll-timeout", type=int, default=300,
                        help="修改天数后等待查询结果的超时秒数 (默认: 300)")
    parser.add_argument("--no-step-screenshots", action="store_true",
                        help="修改天数流程中不逐步截图")
    args = parser.parse_args()

    run(args.auth, args.url, args.output_dir, args.wait, not args.no_screenshot,
        args.days, args.poll_timeout, not args.no_step_screenshots, args.page_type)


if __name__ == "__main__":
    main()
