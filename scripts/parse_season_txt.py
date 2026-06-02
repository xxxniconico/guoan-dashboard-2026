#!/usr/bin/env python3
"""解析 2024/2025 赛季完整比分 TXT → JSON。正确处理中文日期。"""
import json, re
from pathlib import Path
from collections import defaultdict

NAME_MAP = {
    "上海绿地申花": "上海申花", "河南酒祖杜康": "河南", "河南队": "河南",
    "浙江俱乐部": "浙江", "浙江队": "浙江",
    "北京国安": "北京国安", "上海海港": "上海海港", "成都蓉城": "成都蓉城",
    "山东泰山": "山东泰山", "天津津门虎": "天津津门虎",
    "云南玉昆": "云南玉昆", "青岛西海岸": "青岛西海岸",
    "大连英博": "大连英博", "大连人": "大连人",
    "深圳新鹏城": "深圳新鹏城", "青岛海牛": "青岛海牛",
    "武汉三镇": "武汉三镇", "梅州客家": "梅州客家", "长春亚泰": "长春亚泰",
    "南通支云": "南通支云", "沧州雄狮": "沧州雄狮",
    "深圳队": "深圳队", "浙江俱乐部绿城": "浙江",
}

def normalize(name):
    n = str(name).strip()
    return NAME_MAP.get(n, n)


def parse_chinese_date(text):
    """解析中文日期，返回 YYYY-MM-DD。

    支持: '2025年2月22-23日' → '2025-02-22'  (同月日区间)
          '2025年2月28日-3月3日' → '2025-02-28'  (跨月区间)
          '2025年11月22日' → '2025-11-22'
          '2025年2月22日' → '2025-02-22'
    """
    # Try full date first: YYYY年M月D日
    m = re.match(r'(\d{4})年(\d{1,2})月(\d{1,2})日', text)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return f"{y:04d}-{mo:02d}-{d:02d}"

    # Try day-range within same month: YYYY年M月D-D日  (like "2025年2月22-23日")
    m = re.match(r'(\d{4})年(\d{1,2})月(\d{1,2})\s*[-–]\s*\d{1,2}日', text)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return f"{y:04d}-{mo:02d}-{d:02d}"

    return None


def parse_round_date(line):
    """从轮次标题行提取日期。"""
    # Pattern: ## 第N轮 (YYYY年M月D日-range)
    m = re.search(r'\(([^)]+)\)', line)
    if m:
        date_part = m.group(1).strip()
        # Take the first date before any dash
        first_date = date_part.split('-')[0].split('–')[0].strip()
        return parse_chinese_date(first_date)
    return None


def parse_txt(filepath, default_season):
    """解析赛季 TXT 文件。"""
    text = Path(filepath).read_text(encoding="utf-8")
    matches = []
    current_round = ""
    round_date = ""
    # Track dates from header for interpolation
    round_dates = {}

    # First pass: collect all round dates from headers
    for line in text.split("\n"):
        line = line.strip()
        rm = re.match(r"##\s*第(\d+)轮", line)
        if rm:
            rnd_num = int(rm.group(1))
            d = parse_round_date(line)
            if d:
                round_dates[rnd_num] = d

    # Interpolate missing round dates (7 days per round)
    if round_dates:
        all_rnds = sorted(round_dates.keys())
        for i in range(len(all_rnds) - 1):
            r1, r2 = all_rnds[i], all_rnds[i+1]
            d1 = round_dates[r1]
            d2 = round_dates[r2]
            from datetime import datetime, timedelta
            dt1 = datetime.strptime(d1, "%Y-%m-%d")
            dt2 = datetime.strptime(d2, "%Y-%m-%d")
            days = (dt2 - dt1).days
            gap = r2 - r1
            for j in range(1, gap):
                r_mid = r1 + j
                if r_mid not in round_dates:
                    dt_mid = dt1 + timedelta(days=int(days * j / gap))
                    round_dates[r_mid] = dt_mid.strftime("%Y-%m-%d")

    print(f"  Round dates: {len(round_dates)} found+interpolated")

    # Second pass: parse matches
    for line in text.split("\n"):
        line = line.strip()

        rm = re.match(r"##\s*第(\d+)轮", line)
        if rm:
            rnd_num = int(rm.group(1))
            current_round = f"第{rnd_num}轮"
            round_date = round_dates.get(rnd_num, f"{default_season}-01-01")
            continue

        # Match table row: | 主队 | 比分 | 客队 |
        tm = re.match(r"\|\s*(.+?)\s*\|\s*(\d+)[–\-](\d+)\s*\|\s*(.+?)\s*\|", line)
        if tm and current_round:
            home_raw = tm.group(1).strip()
            away_raw = tm.group(4).strip()
            hg = int(tm.group(2))
            ag = int(tm.group(3))
            home = normalize(home_raw)
            away = normalize(away_raw)

            if home and away and home != "主队":
                matches.append({
                    "round": current_round,
                    "date": round_date,
                    "home": home,
                    "away": away,
                    "home_goals": hg,
                    "away_goals": ag,
                    "status": "finished",
                    "source": "season_txt",
                })
    return matches


if __name__ == "__main__":
    for season, fname in [("2024", "2024赛季中超联赛完整比分.txt"), ("2025", "2025赛季中超联赛完整比分.txt")]:
        path = f"/mnt/c/Users/xxxsu/OneDrive/文档/{fname}"
        print(f"\n=== {fname} ===")
        matches = parse_txt(path, season)
        print(f"  共 {len(matches)} 场比赛")

        # Check dates
        bad = sum(1 for m in matches if '01-01' in str(m['date']))
        print(f"  有效日期: {len(matches)-bad}, 缺日期: {bad}")

        # 国安
        guoan = [m for m in matches if "国安" in m["home"] or "国安" in m["away"]]
        print(f"  国安: {len(guoan)} 场")
        for m in guoan[:3]:
            print(f"    {m['round']} {m['date']} {m['home']} vs {m['away']} {m['home_goals']}:{m['away_goals']}")

        # Save
        out_data = {"season": season, "name": f"中超联赛 {season}", "matches": matches}
        out_path = Path(__file__).parent.parent / "data" / f"csl_{season}_all_matches.json"
        out_path.write_text(json.dumps(out_data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  → {out_path}")
