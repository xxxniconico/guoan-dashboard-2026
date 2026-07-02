"""
球员深度分析器 — 进球时间分布、排名走势、个人表现统计。
纯 Python stdlib。
"""
from collections import defaultdict, Counter
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
    guoan_cfl_names = set()
    cfl_by_name = {}
    for prof in cfl_profiles:
        club = str(prof.get("contestant_club_name", ""))
        if "国安" not in club:
            continue
        name = _clean_player_name(prof.get("player_name", ""))
        if name and name not in EXCLUDE:
            guoan_cfl_names.add(name)
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
    for name in guoan_cfl_names:
        cfl = cfl_by_name.get(name, {})
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
