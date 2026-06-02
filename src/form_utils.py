"""
形态计算工具 — 近期战绩、形态字符串、赛前形态。
纯 Python stdlib，从 ticket-pricing/src/data_feeds.py 精简迁移。
"""
from datetime import date, timedelta
from typing import Optional


def compute_form(matches: list, club_name: str = "北京国安", n: int = 5) -> str:
    """最近 N 场形态，返回 W/D/L 字符串。"""
    finished = [m for m in matches if m.get("status") in ("finished", "completed", "ft")]
    related = [m for m in finished if m.get("home_club") == club_name or m.get("away_club") == club_name]
    related.sort(key=lambda m: str(m.get("date", "")), reverse=True)
    results = []
    for m in related[:n]:
        hs = m.get("score", {}).get("home")
        aw = m.get("score", {}).get("away")
        if hs is None or aw is None:
            continue
        is_home = m.get("home_club") == club_name
        if hs == aw:
            results.append("D")
        elif (is_home and hs > aw) or (not is_home and aw > hs):
            results.append("W")
        else:
            results.append("L")
    return "".join(results)


def form_before_match(matches: list, target_date: str, club_name: str = "北京国安", n: int = 5) -> str:
    """计算某场比赛之前最近 N 场的形态。"""
    finished = [m for m in matches
                if m.get("status") in ("finished", "completed", "ft")
                and str(m.get("date", ""))[:10] < str(target_date)[:10]]
    related = [m for m in finished if m.get("home_club") == club_name or m.get("away_club") == club_name]
    related.sort(key=lambda m: str(m.get("date", "")), reverse=True)
    results = []
    for m in related[:n]:
        hs = m.get("score", {}).get("home")
        aw = m.get("score", {}).get("away")
        if hs is None or aw is None:
            continue
        is_home = m.get("home_club") == club_name
        if hs == aw:
            results.append("D")
        elif (is_home and hs > aw) or (not is_home and aw > hs):
            results.append("W")
        else:
            results.append("L")
    return "".join(results)


def get_opponent_form(matches: list, opponent: str, n: int = 5) -> str:
    """获取对手的最近 N 场形态。"""
    finished = [m for m in matches if m.get("status") in ("finished", "completed", "ft")]
    related = [m for m in finished if m.get("home_club") == opponent or m.get("away_club") == opponent]
    related.sort(key=lambda m: str(m.get("date", "")), reverse=True)
    results = []
    for m in related[:n]:
        hs = m.get("score", {}).get("home")
        aw = m.get("score", {}).get("away")
        if hs is None or aw is None:
            continue
        is_home = m.get("home_club") == opponent
        if hs == aw:
            results.append("D")
        elif (is_home and hs > aw) or (not is_home and aw > hs):
            results.append("W")
        else:
            results.append("L")
    return "".join(results)


def get_opponent_top_scorers(matches: list, opponent: str, top_n: int = 3) -> list:
    """提取对手 TOP N 射手。"""
    from collections import Counter
    goals = Counter()
    for m in matches:
        if m.get("home_club") != opponent and m.get("away_club") != opponent:
            continue
        for evt in m.get("events", []):
            if evt.get("type") != "goal":
                continue
            team = evt.get("team_name", "")
            if opponent not in team:
                continue
            player = evt.get("player") or evt.get("player_name", "")
            if player:
                goals[player] += 1
    return [{"name": p, "goals": g} for p, g in goals.most_common(top_n)]


def last_completed_date(matches: list) -> Optional[str]:
    """最近一场已完成比赛的日期。"""
    finished = [m for m in matches if m.get("status") in ("finished", "completed", "ft")]
    if not finished:
        return None
    finished.sort(key=lambda m: str(m.get("date", "")), reverse=True)
    return str(finished[0].get("date", ""))[:10]


def first_upcoming_date(matches: list) -> Optional[str]:
    """下一场未赛日期。"""
    today = date.today().isoformat()
    upcoming = [m for m in matches
                if m.get("status") not in ("finished", "completed", "ft", "cancelled", "canceled", "postponed")
                and str(m.get("date", ""))[:10] >= today]
    upcoming.sort(key=lambda m: str(m.get("date", "")))
    if upcoming:
        return str(upcoming[0].get("date", ""))[:10]
    return None
