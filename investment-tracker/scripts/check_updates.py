#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
投资追踪表更新检查脚本
功能：读取追踪表，检查哪些指标需要更新，输出更新建议清单

使用方法：
  python check_updates.py <追踪表文件路径> [--date 2026-07-05]
"""

import sys
import os
import re
from datetime import datetime, date

# 各层次的建议更新频率（天）
FREQUENCY_DAYS = {
    "第一层": 365 * 3,
    "第二层": 365,
    "第三层": 365 * 5,
    "第四层": 180,
    "第五层": 90,
    "第六层": 365,
    "第七层": 30,
}

# 层次关键词
SECTION_PATTERNS = [
    ("第一层", r"## 第一层"),
    ("第二层", r"## 第二层"),
    ("第三层", r"## 第三层"),
    ("第四层", r"## 第四层"),
    ("第五层", r"## 第五层"),
    ("第六层", r"## 第六层"),
    ("第七层", r"## 第七层"),
]


def parse_date(date_str):
    """尝试解析各种日期格式"""
    if not date_str or date_str.strip() in ("-", "待更新", "", "—"):
        return None
    date_str = date_str.strip()
    for fmt in ("%Y-%m-%d", "%Y-%m", "%Y/%m/%d", "%Y/%m"):
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue
    return None


def extract_last_update(lines, start_idx, end_idx):
    """
    从Markdown表格中提取（指标名称, 上次更新日期字符串）
    """
    results = []
    in_table = False
    header_found = False
    header_line = ""

    for i in range(start_idx, min(end_idx, len(lines))):
        line = lines[i].strip()
        if line.startswith("|") and "指标" in line and "上次更新" in line:
            in_table = True
            header_found = False
            header_line = line
            continue
        if in_table and line.startswith("|") and "---" not in line:
            if not header_found:
                header_found = True
                # 解析header，找到"上次更新"列的索引
                header_cells = [c.strip() for c in header_line.split("|")]
                date_col = -1
                for idx, h in enumerate(header_cells):
                    if "上次更新" in h:
                        date_col = idx
                        break
                name_col = 1  # 指标名称通常在第1列
                continue
            # 解析数据行
            cells = [c.strip() for c in line.split("|")]
            if len(cells) > max(name_col if 'name_col' in dir() else 1, date_col if 'date_col' in dir() and date_col > 0 else 5):
                name = cells[1] if len(cells) > 1 else ""
                date_str = ""
                if 'date_col' in dir() and date_col > 0 and date_col < len(cells):
                    date_str = cells[date_col]
                elif len(cells) >= 6:
                    # 尝试第6列（常见格式）
                    date_str = cells[5]
                if name and date_str:
                    results.append((name, date_str))
        elif in_table and not line.startswith("|"):
            in_table = False

    return results


def check_file(tracker_file, today):
    """检查追踪表文件，返回需要更新的项目"""
    if not os.path.exists(tracker_file):
        print("[错误] 文件不存在: " + tracker_file)
        sys.exit(1)

    with open(tracker_file, "r", encoding="utf-8") as f:
        lines = f.readlines()

    # 找到各层次的起始位置
    sections = {}
    for i, line in enumerate(lines):
        for sect_name, pattern in SECTION_PATTERNS:
            if re.search(pattern, line):
                sections[sect_name] = {"start": i, "end": len(lines)}

    # 调整结束位置
    sect_names = list(sections.keys())
    for idx in range(len(sect_names) - 1):
        curr_name = sect_names[idx]
        next_name = sect_names[idx + 1]
        sections[curr_name]["end"] = sections[next_name]["start"]

    # 检查每个层次
    results = {
        "needs_update": [],
        "recently_updated": [],
        "no_date": [],
    }

    for sect_name, sect_info in sections.items():
        freq_days = FREQUENCY_DAYS.get(sect_name, 365)
        freq_desc = {
            365 * 3: "3年",
            365: "1年",
            365 * 5: "5年",
            180: "6个月",
            90: "1季度",
            30: "1个月",
        }.get(freq_days, str(freq_days) + "天")

        items = extract_last_update(lines, sect_info["start"], sect_info["end"])
        for name, date_str in items:
            last_date = parse_date(date_str)
            if last_date is None:
                results["no_date"].append((sect_name, name, date_str))
            else:
                days_since = (today - last_date).days
                if days_since > freq_days:
                    results["needs_update"].append(
                        (sect_name, name, date_str, days_since, freq_desc)
                    )
                else:
                    results["recently_updated"].append(
                        (sect_name, name, date_str, days_since)
                    )

    return results


def print_report(results, today):
    """打印更新检查报告"""
    print("=" * 60)
    print("  投资追踪表更新检查报告")
    print("  检查日期: " + today.isoformat())
    print("=" * 60)

    if results["needs_update"]:
        print("\n[需要更新] 以下指标已超过建议更新周期：\n")
        current_sect = None
        # 按层次和过期天数排序
        sorted_items = sorted(results["needs_update"], key=lambda x: (x[0], -x[3]))
        for sect, name, date_str, days, freq in sorted_items:
            if sect != current_sect:
                if current_sect is not None:
                    print()
                print("  【" + sect + "】（建议频率：" + freq + "）")
                current_sect = sect
            print("    - " + name)
            print("      上次更新: " + date_str + "（已过去 " + str(days) + " 天）")
    else:
        print("\n[全部正常] 所有指标均在建议更新周期内。")

    if results["no_date"]:
        print("\n[缺少日期] 以下指标未填写'上次更新'日期：\n")
        for sect, name, date_str in results["no_date"]:
            print("  - [" + sect + "] " + name + "（当前值：" + date_str + "）")

    print("\n" + "=" * 60)
    print("  总结: " + str(len(results["needs_update"])) + " 项需要更新，"
          + str(len(results["no_date"])) + " 项缺少日期")
    print("=" * 60)


def main():
    if len(sys.argv) < 2:
        print("使用方法：")
        print("  python check_updates.py <追踪表文件路径> [--date YYYY-MM-DD]")
        print("\n示例：")
        print("  python check_updates.py investment_tracker.md")
        print("  python check_updates.py investment_tracker.md --date 2026-07-05")
        sys.exit(1)

    tracker_file = sys.argv[1]

    # 解析日期参数
    today = date.today()
    if "--date" in sys.argv:
        idx = sys.argv.index("--date")
        if idx + 1 < len(sys.argv):
            try:
                today = datetime.strptime(sys.argv[idx + 1], "%Y-%m-%d").date()
            except ValueError:
                print("[警告] 日期格式错误，使用今天日期")

    results = check_file(tracker_file, today)
    print_report(results, today)


if __name__ == "__main__":
    main()
