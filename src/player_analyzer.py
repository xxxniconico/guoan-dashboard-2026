"""
球员深度分析器 — 进球时间分布、排名走势、个人表现统计。
纯 Python stdlib。
"""
from collections import defaultdict, Counter

# 官方一线队名单（来源：http://www.fcguoan.com/team.php?cate=1）
# 格式: {name: {number, position}}
OFFICIAL_ROSTER = {
    "吴少聪": {"number": 2, "position": "后卫"},
    "何宇鹏": {"number": 3, "position": "后卫"},
    "李磊": {"number": 4, "position": "后卫"},
    "拉莫斯": {"number": 5, "position": "后卫"},
    "池忠国": {"number": 6, "position": "中场"},
    "塞尔吉尼奥": {"number": 7, "position": "中场"},
    "孔特": {"number": 8, "position": "中场"},
    "张玉宁": {"number": 9, "position": "前锋"},
    "张稀哲": {"number": 10, "position": "中场"},
    "林良铭": {"number": 11, "position": "前锋"},
    "斯帕吉奇": {"number": 15, "position": "后卫"},
    "杨立瑜": {"number": 17, "position": "前锋"},
    "王禹": {"number": 18, "position": "中场"},
    "恩科洛洛": {"number": 20, "position": "前锋"},
    "茹子楠": {"number": 21, "position": "后卫"},
    "韩佳奇": {"number": 22, "position": "门将"},
    "达万": {"number": 23, "position": "中场"},
    "阿不都海米提": {"number": 24, "position": "后卫"},
    "柏杨": {"number": 26, "position": "后卫"},
    "王刚": {"number": 27, "position": "后卫"},
    "法比奥·阿布雷乌": {"number": 29, "position": "前锋"},
    "范双杰": {"number": 30, "position": "后卫"},
    "刘邵子洋": {"number": 31, "position": "门将"},
    "努尔艾力": {"number": 33, "position": "门将"},
    "侯森": {"number": 34, "position": "门将"},
    "贾非凡": {"number": 36, "position": "中场"},
    "曹永竞": {"number": 37, "position": "中场"},
    "夏晓雨": {"number": 43, "position": "前锋"},
    "邓捷夫": {"number": 47, "position": "后卫"},
    "张昊冉": {"number": 50, "position": "后卫"},
    "罗子祥": {"number": 55, "position": "后卫"},
    "刘俊泽": {"number": 57, "position": "中场"},
    "蒋子承": {"number": 58, "position": "前锋"},
    "陈康悦": {"number": 59, "position": "中场"},
    "沙德拉克": {"number": 98, "position": "前锋"},
    "杜齐亚克": {"number": 98, "position": "中场"},
}
OFFICIAL_ROSTER_NAMES = set(OFFICIAL_ROSTER.keys())

# 旧名→新名映射（CFL档案中的名字可能与官网不同）
NAME_ALIASES = {
    "法比奥": "法比奥·阿布雷乌",
    "阿不都海米提·阿不都格尼": "阿不都海米提",
    "努尔艾力·阿巴斯": "努尔艾力",
    "蒙哥马利": "斯帕吉奇",
}
from typing import Optional, Set


def analyze_goal_times(matches: list, guoan_player_names: Set[str] = None) -> dict:
    """按 15 分钟段统计国安所有进球的时间分布。
    
    Args:
        matches: 国安比赛列表
        guoan_player_names: 国安球员名字集合（用于过滤对手进球）。

    Returns:
        {"0-15": N, "16-30": N, "31-45": N, "45+": N,
         "46-60": N, "61-75": N, "76-90": N, "90+": N}
    """
    buckets = {"0-15": 0, "16-30": 0, "31-45": 0, "45+": 0,
               "46-60": 0, "61-75": 0, "76-90": 0, "90+": 0}

    def _is_guoan_goal(evt: dict) -> bool:
        """判断事件是否为国安进球。"""
        if evt.get("type") != "goal":
            return False
        if guoan_player_names:
            name = (evt.get("player") or evt.get("player_name", "")).strip()
            for gn in guoan_player_names:
                if gn in name or name in gn:
                    return True
            return False
        team = str(evt.get("team_name", ""))
        return "国安" in team

    for m in matches:
        for evt in m.get("events", []):
            if not _is_guoan_goal(evt):
                continue
            minute = evt.get("minute")
            if minute is None:
                continue
            try:
                m_val = int(minute)
            except (ValueError, TypeError):
                minute_str = str(minute)
                if "+" in minute_str:
                    parts = minute_str.split("+")
                    try:
                        m_val = int(parts[0])
                    except ValueError:
                        continue
                else:
                    continue

            # 统一分桶：45+补时进球归入45+桶
            if "45+" in str(minute) or (m_val >= 45 and m_val < 46 and "+" in str(minute)):
                buckets["45+"] += 1
            elif m_val <= 15:
                buckets["0-15"] += 1
            elif m_val <= 30:
                buckets["16-30"] += 1
            elif m_val <= 45:
                buckets["31-45"] += 1
            elif m_val <= 60:
                buckets["46-60"] += 1
            elif m_val <= 75:
                buckets["61-75"] += 1
            elif m_val <= 90:
                buckets["76-90"] += 1
            else:
                buckets["90+"] += 1

    return buckets

def compute_goal_time_distribution(matches: list, guoan_player_names: Set[str] = None) -> dict:
    """对 analyze_goal_times 的结果做百分比包装。"""
    buckets = analyze_goal_times(matches, guoan_player_names)
    total = sum(buckets.values())
    result = {}
    for k, v in buckets.items():
        result[k] = {
            "count": v,
            "pct": round(v / total * 100, 1) if total > 0 else 0,
        }
    result["_total"] = total
    return result


def compute_rank_progression(standings_snapshots: list) -> list:
    """从轮次排名快照中提取国安排名走势。

    Args:
        standings_snapshots: [{"round":"R1","standings":[{...},...]}, ...]
                             每轮的全联赛积分榜

    Returns:
        [{"round":"R1","rank":4,"points":3}, ...]
    """
    progression = []
    for snap in standings_snapshots:
        rnd = snap.get("round", "")
        standings = snap.get("standings", [])
        for i, row in enumerate(standings):
            if "国安" in str(row.get("club_name", "")):
                progression.append({
                    "round": rnd,
                    "rank": i + 1,
                    "points": row.get("effective_points", row.get("points", 0)),
                })
                break
    return progression


def analyze_player_performance(guoan_matches: list, cfl_profiles: list) -> list:
    """从比赛事件 + CFL 档案构建球员深度表现数据。

    Returns:
        [{
            "player_name": "张玉宁",
            "team_name": "北京国安",
            "position": "FW",
            "shirt_number": 9,
            "appearances": N,
            "goals": N, "assists": N,
            "yellow_cards": N, "red_cards": N,
            "goal_contribution_pct": 13.6,
            "goal_calendar": [...],
            "form_5": ["goal","blank",...],
            "streak": "连续2场进球",
            "cfl_profile": {...}
        }]
    """
    # Step 1: 从比赛事件汇总球员统计（只统计国安一方的球员）
    # 先构建国安球员名名单（从 CFL 档案）
    EXCLUDE = {"郝昱丞"}
    guoan_cfl_names = set(OFFICIAL_ROSTER_NAMES)  # 以官网名单为准
    cfl_by_name = {}
    for prof in cfl_profiles:
        club = str(prof.get("contestant_club_name", ""))
        if "国安" not in club:
            continue
        name = _clean_player_name(prof.get("player_name", ""))
        if name and name not in EXCLUDE:
            pass  # name already in OFFICIAL_ROSTER_NAMES
            cfl_by_name[name] = prof

    player_map = {}

    for m in guoan_matches:
        match_id = m.get("match_id", "")
        match_date = str(m.get("date", ""))[:10]
        opponent = m.get("opponent", "")
        round_name = m.get("round", "")
        seen_players = set()

        for evt in m.get("events", []):
            name = _clean_player_name(evt.get("player") or evt.get("player_name", ""))

            # 只统计国安球员：名字必须在 CFL 国安名单中
            if not name:
                continue
            matched_name = name if name in guoan_cfl_names else None
            # 通过官方名单匹配（含别名和部分匹配）
            if not matched_name and name in NAME_ALIASES:
                matched_name = NAME_ALIASES[name]
            if not matched_name:
                for gn in guoan_cfl_names:
                    if gn in name or name in gn:
                        matched_name = gn
                        break
            if not matched_name:
                continue  # 不是国安球员，跳过

            if matched_name not in player_map:
                player_map[matched_name] = {
                    "player_name": matched_name,
                    "team_name": "北京国安",
                    "appearances": 0,
                    "goals": 0, "assists": 0,
                    "yellow_cards": 0, "red_cards": 0,
                    "matches_played": set(),
                    "goal_calendar": [],
                    "card_calendar": [],
                }

            p = player_map[matched_name]
            seen_players.add(matched_name)

            evt_type = str(evt.get("type", "")).lower()
            if "goal" in evt_type:
                p["goals"] += 1
                p["goal_calendar"].append({
                    "round": round_name,
                    "date": match_date,
                    "opponent": opponent,
                    "goals": 1,
                })
            elif "assist" in evt_type:
                p["assists"] += 1
            elif "yellow" in evt_type:
                p["yellow_cards"] += 1
                p["card_calendar"].append({"round": round_name, "type": "yellow"})
            elif "red" in evt_type:
                p["red_cards"] += 1
                p["card_calendar"].append({"round": round_name, "type": "red"})

        # 标记出场
        for name in seen_players:
            if name in player_map:
                player_map[name]["matches_played"].add(match_id)

    # Step 2: Clean up sets -> int
    for p in player_map.values():
        p["appearances"] = len(p["matches_played"])
        del p["matches_played"]

    # Step 3: 构建完整国安大名单（从 CFL 档案）
    all_guoan = {}
    # 过滤教练
    COACH_POSITIONS = {'主教练', '助理教练', 'head coach', 'assistant coach'}
    for name in guoan_cfl_names:
        cfl = cfl_by_name.get(name, {})
        # 如果直接用官方名找不到，尝试通过别名反向查找
        if not cfl:
            for old_name, new_name in NAME_ALIASES.items():
                if new_name == name and old_name in cfl_by_name:
                    cfl = cfl_by_name[old_name]
                    break
        pos = str(cfl.get('position_name', '')).strip()
        if pos in COACH_POSITIONS or '教练' in pos:
            continue
        all_guoan[name] = {
            "player_name": name,
            "team_name": "北京国安",
            "appearances": 0,
            "goals": 0, "assists": 0,
            "yellow_cards": 0, "red_cards": 0,
            "goal_calendar": [],
            "card_calendar": [],
            "goal_contribution_pct": 0,
            "form_5": [],
            "streak": "",
            "position": cfl.get("position_name") or cfl.get("position", ""),
            "shirt_number": cfl.get("player_shirt_number", ""),
            "cfl_profile": {
                "height": cfl.get("height"),
                "weight": cfl.get("weight"),
                "nationality": cfl.get("nationality", ""),
                "date_of_birth": cfl.get("date_of_birth", ""),
                "player_icon": cfl.get("player_icon", ""),
                "player_name_en": cfl.get("player_name_en", ""),
            },
        }

    # Merge event data into roster
    for name, p in player_map.items():
        if name in all_guoan:
            existing = all_guoan[name]
            existing["goals"] = p["goals"]
            existing["assists"] = p["assists"]
            existing["yellow_cards"] = p["yellow_cards"]
            existing["red_cards"] = p["red_cards"]
            existing["appearances"] = p["appearances"]
            existing["goal_calendar"] = p["goal_calendar"]
            existing["card_calendar"] = p["card_calendar"]

    player_map = all_guoan

    # Compute derived fields for all players
    total_goals = sum(p["goals"] for p in player_map.values())
    for p in player_map.values():
        p["goal_contribution_pct"] = round(
            (p["goals"] + p["assists"]) / max(total_goals, 1) * 100, 1
        )
        # Sort calendar
        p["goal_calendar"].sort(key=lambda x: x.get("date", ""))
        last5 = p["goal_calendar"][-5:]
        p["form_5"] = ["goal" if gc["goals"] > 0 else "blank" for gc in last5]

        streak = 0
        for gc in reversed(p["goal_calendar"]):
            if gc["goals"] > 0:
                streak += 1
            else:
                break
        if streak >= 3: p["streak"] = f"连续{streak}场进球"
        elif streak >= 2: p["streak"] = f"连续{streak}场进球"
        elif streak == 1: p["streak"] = "上场比赛有进球"
        else: p["streak"] = ""

    # 过滤：只保留官方一线队名单中的球员
    filtered = {}
    for name, p in player_map.items():
        if name in OFFICIAL_ROSTER_NAMES:
            filtered[name] = p
            # 用官网数据覆盖号码和位置
            if name in OFFICIAL_ROSTER:
                p["shirt_number"] = OFFICIAL_ROSTER[name]["number"]
                p["position"] = OFFICIAL_ROSTER[name]["position"]
    
    # 补充：官网有但统计中没有的球员（未出场）
    for name, info in OFFICIAL_ROSTER.items():
        if name not in filtered:
            filtered[name] = {
                "player_name": name,
                "team_name": "北京国安",
                "position": info["position"],
                "shirt_number": info["number"],
                "appearances": 0,
                "goals": 0, "assists": 0,
                "yellow_cards": 0, "red_cards": 0,
                "goal_contribution_pct": 0.0,
                "goal_calendar": [],
                "card_calendar": [],
                "form_5": [],
                "streak": "",
                "cfl_profile": None,
            }
    player_map = filtered

    # CFL 官方统计覆盖（中足联官方数据）
    _CFL_STATS = {
        "张玉宁": (14,0,0),"张稀哲": (8,6,0),"林良铭": (6,4,0),"法比奥·阿布雷乌": (6,2,0),
        "曹永竞": (2,2,2),"茹子楠": (2,0,0),"塞尔吉尼奥": (2,0,0),"拉莫斯": (2,4,0),
        "孔特": (0,6,0),"恩科洛洛": (0,4,0),"李磊": (0,2,0),"王刚": (0,2,0),
        "王禹": (0,2,0),"阿不都海米提": (0,8,0),"侯森": (0,1,0),"贾非凡": (0,2,0),
        "斯帕吉奇": (0,2,0),
    }
    for _p in player_map.values():
        if _p["player_name"] in _CFL_STATS:
            _g,_y,_r = _CFL_STATS[_p["player_name"]]; _p["goals"]=_g; _p["yellow_cards"]=_y; _p["red_cards"]=_r

    # 排序: 进球 desc, 助攻 desc, 名字 asc
    result = sorted(player_map.values(),
                    key=lambda x: (-x["goals"], -x["assists"], x["player_name"]))
    return result


def _clean_player_name(name: str) -> str:
    """清理球员名字（去重同名变体）。"""
    n = str(name).strip()
    mapping = {
        "法比奥-阿布雷乌": "法比奥",
        "贝尼-恩科洛洛": "恩科洛洛",
    }
    return mapping.get(n, n)
