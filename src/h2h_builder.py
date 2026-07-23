"""
历史对战构建器 — 聚合 2024/2025/2026 三季的国安 H2H 记录。
纯 Python stdlib。
"""
import json
from pathlib import Path
from collections import defaultdict
from typing import Optional


def load_season_matches(filepath: str) -> list:
    """加载赛季比赛 JSON。支持两种格式。"""
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    # 格式1: 简单列表 [{"home":"国安", "away":"xxx", "home_goals":1, ...}]
    if isinstance(data, list):
        return data

    # 格式2: {"leagues":[{"matches":[...]}]} 或 {"matches":[...]}
    if isinstance(data, dict):
        if "leagues" in data:
            return data["leagues"][0].get("matches", [])
        if "matches" in data:
            return data["matches"]

    return []


def _normalize_venue(venue) -> str:
    """统一 venue 字段为字符串（处理 dict/None/str 三种输入）。"""
    if isinstance(venue, dict):
        return venue.get("name", "") or ""
    return str(venue) if venue else ""


def _normalize_club(name: str) -> str:
    """统一俱乐部名称用于匹配。"""
    n = str(name).strip()
    mapping = {
        "浙江俱乐部绿城": "浙江俱乐部",
        "浙江队": "浙江俱乐部",
        "浙江": "浙江俱乐部",
        "河南俱乐部彩陶坊": "河南俱乐部",
        "河南": "河南俱乐部",
        "河南俱乐部酒祖杜康": "河南俱乐部",
        "河南队俱乐部彩陶坊": "河南俱乐部",
        "河南队": "河南俱乐部",
        "辽宁铁人楠波湾": "辽宁铁人",
        "大连英博海发": "大连英博",
        "河南俱乐部酒祖杜康": "河南俱乐部",
        "河南队俱乐部彩陶坊": "河南俱乐部",
        "河南队": "河南俱乐部",
        "河南": "河南俱乐部",
        "大连英博海发": "大连英博",
        "辽宁铁人楠波湾": "辽宁铁人",
    }
    return mapping.get(n, n)


def _is_guoan_match(m: dict) -> bool:
    """判断比赛是否涉及北京国安。"""
    home = str(m.get("home", m.get("home_club", "")))
    away = str(m.get("away", m.get("away_club", "")))
    return "国安" in home or "国安" in away


def _parse_match(m: dict, season: str) -> Optional[dict]:
    """将各种格式的比赛 dict 统一为标准格式。"""
    home = str(m.get("home", m.get("home_club", "")))
    away = str(m.get("away", m.get("away_club", "")))
    is_home = "国安" in home
    opponent = _normalize_club(away if is_home else home)

    # 比分
    if "home_goals" in m:
        hg, ag = m["home_goals"], m["away_goals"]
    elif "score" in m and isinstance(m["score"], dict):
        hg, ag = m["score"].get("home"), m["score"].get("away")
    else:
        hg, ag = None, None

    # 结果
    if hg is not None and ag is not None:
        try:
            hg_i, ag_i = int(hg), int(ag)
            if hg_i == ag_i:
                result = "D"
            elif (is_home and hg_i > ag_i) or (not is_home and ag_i > hg_i):
                result = "W"
            else:
                result = "L"
            score = f"{hg_i}:{ag_i}"
            guoan_goals = hg_i if is_home else ag_i
            opp_goals = ag_i if is_home else hg_i
        except (ValueError, TypeError):
            result = "?"
            score = "?:?"
            guoan_goals = 0
            opp_goals = 0
    else:
        result = "?"
        score = "?:?"
        guoan_goals = 0
        opp_goals = 0

    # 场地
    venue = m.get("venue", {})
    venue_name = _normalize_venue(venue)

    return {
        "season": season,
        "round": str(m.get("round", "")),
        "date": str(m.get("date", ""))[:10],
        "venue": venue_name,
        "is_home": is_home,
        "opponent": opponent,
        "score": score,
        "result": result,
        "guoan_goals": guoan_goals,
        "opp_goals": opp_goals,
    }


def merge_player_names(events: list) -> list:
    """合并同名球员（如 法比奥/法比奥-阿布雷乌）。"""
    merged = defaultdict(int)
    for evt in events:
        name = evt.get("player") or evt.get("player_name", "")
        if not name:
            continue
        # 简化：取短名
        short = name.split("-")[0].strip()
        if evt.get("type") == "goal":
            merged[short] += 1
    return [{"name": k, "goals": v} for k, v in sorted(merged.items(), key=lambda x: -x[1])]


def build_h2h(season_matches_2023: list, season_matches_2024: list,
              season_matches_2025: list, season_matches_2026: list) -> dict:
    """构建完整 H2H 记录（2023~2026 四赛季）。

    Returns:
        {opponent: {
            "all_time": {"played":N, "wins":N, "draws":N, "losses":N, "gf":N, "ga":N},
            "matches": [...]
        }}
    """
    h2h = defaultdict(lambda: {"all_time": {"played": 0, "wins": 0, "draws": 0, "losses": 0, "gf": 0, "ga": 0}, "matches": []})

    # 2023 数据
    for m in season_matches_2023:
        if not _is_guoan_match(m):
            continue
        parsed = _parse_match(m, "2023")
        if parsed and parsed["result"] != "?":
            h2h[parsed["opponent"]]["matches"].append(parsed)

    # 2024 数据
    for m in season_matches_2024:
        if not _is_guoan_match(m):
            continue
        parsed = _parse_match(m, "2024")
        if parsed and parsed["result"] != "?":
            h2h[parsed["opponent"]]["matches"].append(parsed)

    # 2025 数据
    for m in season_matches_2025:
        if not _is_guoan_match(m):
            continue
        parsed = _parse_match(m, "2025")
        if parsed and parsed["result"] != "?":
            h2h[parsed["opponent"]]["matches"].append(parsed)

    # 2026 数据（guoan_matches 已富化但缺 season 字段，补充之）
    for m in season_matches_2026:
        if m.get("result", "?") == "?":
            continue
        opp = m.get("opponent", "")
        if opp:
            m["season"] = "2026"
            # Normalize score: ensure "X:Y" string format
            sc = m.get("score", {})
            if isinstance(sc, dict):
                hg = sc.get("home") if sc.get("home") is not None else sc.get("home", 0)
                ag = sc.get("away") if sc.get("away") is not None else sc.get("away", 0)
                try: m["score"] = f"{int(hg)}:{int(ag)}"
                except: pass
            # Normalize venue: dict/None -> str
            m["venue"] = _normalize_venue(m.get("venue"))
            h2h[opp]["matches"].append(m)

    # 计算汇总
    for opp in h2h:
        total = {"played": 0, "wins": 0, "draws": 0, "losses": 0, "gf": 0, "ga": 0}
        for m in h2h[opp]["matches"]:
            total["played"] += 1
            if m["result"] == "W":
                total["wins"] += 1
            elif m["result"] == "D":
                total["draws"] += 1
            elif m["result"] == "L":
                total["losses"] += 1
            total["gf"] += m.get("guoan_goals", 0)
            total["ga"] += m.get("opp_goals", 0)
        # 按日期排序
        h2h[opp]["matches"].sort(key=lambda x: x["date"])
        h2h[opp]["all_time"] = total

    return dict(h2h)
