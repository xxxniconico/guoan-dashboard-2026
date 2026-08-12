#!/usr/bin/env python3
"""
国安仪表盘主构建器 — 拉取 CSL 数据 → 过滤国安 → 富化 → 输出 guoan_embed.json。
纯 Python stdlib，零外部依赖。
"""
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from collections import defaultdict

# 本地模块
from .opponent_tiers import classify_opponent_tier, get_tier_label, get_tier_color
from .form_utils import (
    compute_form, form_before_match, get_opponent_form,
    get_opponent_top_scorers, get_opponent_recent_matches,
    last_completed_date, first_upcoming_date
)
from .guoan_context import get_guoan_matches, detect_ctx, CONTEXT_SIGNAL_LABELS, normalize_club
from .h2h_builder import load_season_matches, build_h2h, _normalize_venue
from .player_analyzer import (
    analyze_goal_times, compute_goal_time_distribution,
    compute_rank_progression, analyze_player_performance
)

ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "data"
CONFIG_DIR = ROOT / "config"
WEB_DIR = ROOT / "docs"

# 在线 CSL 数据源 URL
CSL_SOURCE_URL = os.environ.get(
    "CSL_DASHBOARD_SOURCE_URL",
    "https://xxxniconico.github.io/csl-dashboard-2026/dashboard_embed.json"
)

# 本地 CSL 数据路径（fallback）
LOCAL_CSL_EMBED = DATA_DIR / "dashboard_embed.json"


def fetch_csl_data() -> dict:
    """拉取 CSL 仪表盘 embed JSON（优先在线，fallback 本地缓存）。"""
    # 优先在线拉取
    try:
        from urllib.request import urlopen, Request
        print(f"[guoan_builder] 在线拉取: {CSL_SOURCE_URL}")
        req = Request(CSL_SOURCE_URL, headers={
            "User-Agent": "guoan-dashboard-builder/1.0",
            "Cache-Control": "no-cache",
        })
        with urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            # 缓存到本地
            LOCAL_CSL_EMBED.parent.mkdir(parents=True, exist_ok=True)
            LOCAL_CSL_EMBED.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            print(f"[guoan_builder] 已缓存到本地: {LOCAL_CSL_EMBED}")
            return data
    except Exception as e:
        print(f"[guoan_builder] 在线拉取失败: {e}")
        # Fallback 本地缓存
        if LOCAL_CSL_EMBED.exists():
            print(f"[guoan_builder] Fallback 本地缓存: {LOCAL_CSL_EMBED}")
            return json.loads(LOCAL_CSL_EMBED.read_text(encoding="utf-8"))
        raise RuntimeError("无法获取 CSL 数据（在线失败且本地无缓存）")



def fetch_cfl_all_data() -> list:
    """从 CFL 官方 API 获取全联赛比赛数据，返回 match dict 列表。
    用于补充 CSL Dashboard 可能缺失的最新轮次数据。"""
    from urllib.request import urlopen, Request
    from urllib.error import URLError
    import json as _json

    API_BASE = "https://api.cfl-china.cn/frontweb/api"
    CALENDAR_ID = "e6818x4pwankpph8awr91m1hw"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://www.cfl-china.cn/",
    }

    result = []
    try:
        for week in range(1, 31):
            url = f"{API_BASE}/matches/page?tournament_calendar_id={CALENDAR_ID}&competition_code=CSL&week={week}&size=50"
            req = Request(url, headers=headers)
            try:
                with urlopen(req, timeout=20) as resp:
                    data = _json.loads(resp.read().decode("utf-8"))
            except Exception:
                continue

            for m in data.get("data", {}).get("dataList", []):
                home = m.get("home_contestant_name", "")
                away = m.get("away_contestant_name", "")
                date = m.get("local_date", "")
                cfl_status = str(m.get("match_status", "")).lower()
                hs = m.get("ft_home_score")
                aws = m.get("ft_away_score")

                entry = {
                    "home_club": home,
                    "away_club": away,
                    "date": date,
                    "status": "finished" if cfl_status == "played" else
                             "postponed" if cfl_status == "postponed" else
                             "scheduled",
                    "score": {"home": int(hs), "away": int(aws)} if hs is not None and aws is not None else {},
                    "events": [],
                    "match_id": m.get("id", ""),
                }

                # Only fetch events for Guoan matches (keep it lightweight)
                is_guoan = "国安" in home or "国安" in away
                match_id = m.get("id", "")
                if is_guoan and match_id and cfl_status == "played":
                    try:
                        goals_url = f"{API_BASE}/matches/match/event/goals?match_id={match_id}"
                        req_g = Request(goals_url, headers=headers)
                        with urlopen(req_g, timeout=15) as resp_g:
                            goals_data = _json.loads(resp_g.read().decode("utf-8"))
                        cards_url = f"{API_BASE}/matches/match/event/cards?match_id={match_id}"
                        try:
                            req_c = Request(cards_url, headers=headers)
                            with urlopen(req_c, timeout=15) as resp_c:
                                cards_data = _json.loads(resp_c.read().decode("utf-8"))
                        except Exception:
                            cards_data = {}
                        events = []
                        for side in ("home", "away"):
                            for g in goals_data.get("data", {}).get(side, []):
                                events.append({
                                    "type": "goal", "minute": g.get("time_min", 0),
                                    "player": g.get("player_name", "未知"),
                                    "player_name": g.get("player_name", "未知"),
                                    "team_name": home if side == "home" else away,
                                    "is_own_goal": False,
                                })
                        for side in ("home", "away"):
                            for c in cards_data.get("data", {}).get(side, []):
                                ct = str(c.get("card_type", "")).upper()
                                events.append({
                                    "type": "yellow_card" if ct == "YC" else "red_card",
                                    "minute": c.get("time_min", 0),
                                    "player": c.get("player_name", "未知"),
                                    "player_name": c.get("player_name", "未知"),
                                    "team_name": home if side == "home" else away,
                                })
                        events.sort(key=lambda e: e.get("minute", 0))
                        entry["events"] = events
                    except Exception:
                        pass

                result.append(entry)

        print(f"[guoan_builder] CFL API: 获取到 {len(result)} 场全联赛比赛数据")
    except Exception as e:
        print(f"[guoan_builder] CFL API 拉取失败: {e}")

    return result



def compute_standings_from_matches(all_matches: list, deductions: dict = None) -> list:
    """从比赛结果实时计算积分榜（仿 CSL 仪表盘前端 buildLiveStandingsRows 逻辑）。
    自动合并俱乐部名变体（如 浙江俱乐部绿城 → 浙江）。
    优先保留 finished 版本（scheduled 重复记录会被跳过）。
    """
    def _n(v): x = float(v) if v is not None else 0; return int(x) if x == int(x) else x

    # Load penalty points from deductions (normalize keys)
    penalty = {}
    if deductions:
        dbc = deductions.get("deductions_by_club", {})
        if isinstance(dbc, dict):
            for club, pts in dbc.items():
                penalty[normalize_club(str(club))] = _n(pts)

    # 排序：finished 优先，有比分的优先
    def _sort_key(m):
        status = str(m.get("status","")).lower()
        is_finished = 1 if status in ("finished","completed","ft") else 0
        sc = m.get("score", {})
        if isinstance(sc, dict):
            has_score = 1 if (sc.get("home") is not None and sc.get("away") is not None) else 0
        else:
            has_score = 0
        return (-is_finished, -has_score, str(m.get("date","")))
    
    sorted_matches = sorted(all_matches, key=_sort_key)

    # Stats per club (normalized names)
    stats = {}
    seen = {}  # key -> match dict (保存最优版本)
    _processed = set()
    for m in sorted_matches:
        h_norm = normalize_club(str(m.get("home_club","")))
        a_norm = normalize_club(str(m.get("away_club","")))
        
        # 去重：match_id + 归一化日期/主客队 双重 key
        mid = str(m.get("match_id",""))
        if mid:
            key = f"id:{mid}"
        else:
            key = f"{m.get('date','')}|{h_norm}|{a_norm}"
        dedup_key = f"norm:{m.get('date','')[:10]}|{h_norm}|{a_norm}"
        
        if key in seen or dedup_key in seen:
            # 如果已有记录是 scheduled 而新纪录是 finished，替换
            existing = seen.get(key) or seen.get(dedup_key)
            if existing:
                old_status = str(existing.get("status","")).lower()
                new_status = str(m.get("status","")).lower()
                if old_status not in ("finished","completed","ft") and new_status in ("finished","completed","ft"):
                    # 替换旧记录：从未处理集中移除旧 key，用新纪录
                    if key in seen: del seen[key]
                    if dedup_key in seen: del seen[dedup_key]
                    # 回退旧记录的积分贡献（简单做法：跳过，让新纪录计入）
                else:
                    continue
        seen[key] = m
        seen[dedup_key] = m

        status = str(m.get("status","")).lower()
        if status not in ("finished","completed","ft"): continue

        h = h_norm
        a = a_norm
        if not h or not a: continue

        sc = m.get("score",{})
        if isinstance(sc, dict):
            try: hs, aws = int(sc.get("home",0)), int(sc.get("away",0))
            except: continue
        elif isinstance(sc, str) and ':' in sc:
            try:
                parts = sc.split(':')
                hs, aws = int(parts[0]), int(parts[1])
            except: continue
        else:
            continue

        if h not in stats: stats[h] = {"played":0,"w":0,"d":0,"l":0,"gf":0,"ga":0,"pts":0}
        if a not in stats: stats[a] = {"played":0,"w":0,"d":0,"l":0,"gf":0,"ga":0,"pts":0}

        stats[h]["played"]+=1; stats[a]["played"]+=1
        stats[h]["gf"]+=hs; stats[h]["ga"]+=aws
        stats[a]["gf"]+=aws; stats[a]["ga"]+=hs
        if hs > aws:   stats[h]["w"]+=1; stats[a]["l"]+=1; stats[h]["pts"]+=3
        elif hs < aws: stats[a]["w"]+=1; stats[h]["l"]+=1; stats[a]["pts"]+=3
        else:          stats[h]["d"]+=1; stats[a]["d"]+=1; stats[h]["pts"]+=1; stats[a]["pts"]+=1

    rows = []
    for club, s in stats.items():
        pen = _n(penalty.get(club, 0))
        mp = s["pts"]
        eff = mp - pen
        gd = s["gf"] - s["ga"]
        rows.append({"club_name":club,"played":s["played"],"wins":s["w"],"draws":s["d"],"losses":s["l"],
                     "goals_for":s["gf"],"goals_against":s["ga"],"goal_difference":gd,
                     "match_points":mp,"penalty_points":pen,"effective_points":eff})

    rows.sort(key=lambda r: (-r["effective_points"], -r["goal_difference"], -r["goals_for"]))
    return rows


def extract_guoan_standing(standings: list, all_matches: list = None, deductions: dict = None) -> dict:
    """从全联赛积分榜中提取国安排名。
    优先使用实时计算（all_matches），fallback 到原始 standings。
    """
    rows = compute_standings_from_matches(all_matches, deductions) if all_matches else None

    # Find Guoan position
    for i, row in enumerate(rows or standings):
        club = str(row.get("club_name", ""))
        if "国安" in club:
            wdl = [row.get("wins",0), row.get("draws",0), row.get("losses",0)]
            return {
                "club_name": "北京国安",
                "played": row.get("played", 0),
                "wins": wdl[0], "draws": wdl[1], "losses": wdl[2],
                "goals_for": row.get("goals_for", 0),
                "goals_against": row.get("goals_against", 0),
                "goal_difference": row.get("goal_difference", 0),
                "match_points": row.get("match_points", 0),
                "penalty_points": row.get("penalty_points", 0),
                "effective_points": row.get("effective_points", 0),
                "position": i + 1,
            }
    return {}


def build_opponent_info(match: dict, all_matches: list, standings: list) -> dict:
    """为一场比赛构建对手档案。"""
    opponent = match.get("opponent", "")
    if not opponent:
        return {}

    # 从积分榜找对手排名
    rank = "-"
    gf = 0
    ga_ = 0
    for row in standings:
        if opponent in str(row.get("club_name", "")):
            eff = row.get("effective_points", row.get("points", 0) - row.get("penalty_points", 0))
            gd = row.get("goal_difference", 0)
            all_rows = []
            for r in standings:
                e = r.get("effective_points", r.get("points", 0) - r.get("penalty_points", 0))
                d = r.get("goal_difference", 0)
                all_rows.append((str(r.get("club_name", "")), e, d))
            all_rows.sort(key=lambda x: (-x[1], -x[2]))
            rank = next((i + 1 for i, (n, _, _) in enumerate(all_rows) if opponent in n), "-")
            gf = row.get("summary", {}).get("goals_for", 0)
            ga_ = row.get("summary", {}).get("goals_against", 0)
            break

    # 对手近期形态
    form = get_opponent_form(all_matches, opponent)

    # 对手核心射手
    scorers = get_opponent_top_scorers(all_matches, opponent)

    # 对手等级
    tier = classify_opponent_tier(opponent)

    recent_matches = get_opponent_recent_matches(all_matches, opponent)
    return {
        "current_rank": rank,
        "current_form": form,
        "goals_for": gf,
        "goals_against": ga_,
        "top_scorers": scorers[:3],
        "tier": tier,
        "recent_matches": recent_matches,
    }


def _backfill_rounds(guoan_matches: list) -> list:
    """补全缺失的轮次：按日期排序后从第1轮开始递增编号。"""
    # 先按日期排序
    sorted_ms = sorted(guoan_matches, key=lambda m: str(m.get("date", "")))
    round_idx = 1
    for m in sorted_ms:
        rnd = str(m.get("round", "")).strip()
        if not rnd or rnd == "MISSING":
            m["round"] = f"第{round_idx}轮"
        round_idx += 1
    return sorted_ms


def enrich_guoan_matches(guoan_matches: list, all_league_matches: list,
                         standings: list) -> list:
    """富化所有国安比赛：补全轮次、添加对手等级、情境信号、赛前形态、阵型。"""
    # 先补全缺失轮次
    guoan_matches = _backfill_rounds(guoan_matches)
    enriched = []

    for m in guoan_matches:
        opponent = m.get("opponent", "")
        date_str = str(m.get("date", ""))[:10]

        # 对手等级
        tier = classify_opponent_tier(opponent)

        # 比赛结果
        hs = m.get("score", {}).get("home")
        aw = m.get("score", {}).get("away")
        is_home = m.get("is_home", False)
        if hs is not None and aw is not None:
            try:
                hg, ag = int(hs), int(aw)
                if hg == ag:
                    result = "D"
                elif (is_home and hg > ag) or (not is_home and ag > hg):
                    result = "W"
                else:
                    result = "L"
                guoan_goals = hg if is_home else ag
                opp_goals = ag if is_home else hg
            except (ValueError, TypeError):
                result = "?"
                guoan_goals = 0
                opp_goals = 0
        else:
            result = "?"
            guoan_goals = 0
            opp_goals = 0

        # 赛前形态
        form_before = form_before_match(guoan_matches, date_str) if result != "?" else ""

        # 情境信号（仅已完赛的）
        ctx = {}
        if result != "?":
            ctx = detect_ctx(m, guoan_matches)

        # 对手信息
        opp_info = build_opponent_info(m, all_league_matches, standings)

        # 阵型
        formation = {
            "home": m.get("home_formation_used", ""),
            "away": m.get("away_formation_used", ""),
        }

        enriched.append({
            "match_id": m.get("match_id", ""),
            "round": m.get("round", ""),
            "date": m.get("date", ""),
            "venue": _normalize_venue(m.get("venue")),
            "opponent": opponent,
            "is_home": is_home,
            "home_club": m.get("home_club", "北京国安" if is_home else opponent),
            "away_club": m.get("away_club", opponent if is_home else "北京国安"),
            "status": m.get("status", "scheduled"),
            "score": m.get("score", {}),
            "guoan_goals": guoan_goals,
            "opp_goals": opp_goals,
            "result": result,
            "events": m.get("events", []),
            "formation": formation,
            "opponent_tier": tier,
            "context_signals": ctx,
            "form_before": form_before,
            "opponent_info": opp_info,
        })

    return enriched


def build_opponent_summary(guoan_matches: list) -> dict:
    """构建对手一览表。"""
    summary = defaultdict(lambda: {
        "tier": "", "tier_label": "",
        "home_result": None, "away_result": None,
        "home_score": None, "away_score": None,
        "record": {"wins": 0, "draws": 0, "losses": 0},
    })

    for m in guoan_matches:
        opp = m.get("opponent", "")
        if not opp:
            continue
        tier = classify_opponent_tier(opp)
        summary[opp]["tier"] = tier
        summary[opp]["tier_label"] = get_tier_label(tier)

        if m.get("result", "?") == "?":
            continue

        if m["is_home"]:
            summary[opp]["home_result"] = m["result"]
            summary[opp]["home_score"] = f"{m['guoan_goals']}:{m['opp_goals']}"
        else:
            summary[opp]["away_result"] = m["result"]
            summary[opp]["away_score"] = f"{m['guoan_goals']}:{m['opp_goals']}"

        if m["result"] == "W":
            summary[opp]["record"]["wins"] += 1
        elif m["result"] == "D":
            summary[opp]["record"]["draws"] += 1
        elif m["result"] == "L":
            summary[opp]["record"]["losses"] += 1

    return dict(summary)


def build_form_streak(guoan_matches: list) -> list:
    """构建已完成比赛的形态序列。"""
    return [m["result"] for m in guoan_matches if m.get("result", "?") != "?"]


def build_round_progression(guoan_matches: list, all_standings: list) -> list:
    """构建逐轮积分走势（简化版，从比赛结果累加）。"""
    progression = []
    cum_pts = 0
    cum_gf = 0
    cum_ga = 0
    finished = [m for m in guoan_matches if m.get("result", "?") != "?"]

    for m in finished:
        if m["result"] == "W":
            cum_pts += 3
        elif m["result"] == "D":
            cum_pts += 1
        cum_gf += m.get("guoan_goals", 0)
        cum_ga += m.get("opp_goals", 0)
        progression.append({
            "round": m.get("round", ""),
            "opponent": m.get("opponent", ""),
            "result": m["result"],
            "score": f"{m['guoan_goals']}:{m['opp_goals']}",
            "cumulative_points": cum_pts,
            "gf_total": cum_gf,
            "ga_total": cum_ga,
        })

    return progression


def load_club_profile() -> dict:
    """加载国安球队资料。"""
    profile_path = CONFIG_DIR / "club_profile.json"
    if profile_path.exists():
        return json.loads(profile_path.read_text(encoding="utf-8"))
    return {}


def load_deductions() -> dict:
    """加载足协扣分配置。"""
    dpath = CONFIG_DIR / "csl_cfa_2026_official_deductions.json"
    if dpath.exists():
        return json.loads(dpath.read_text(encoding="utf-8"))
    return {}


def main():
    """主构建流程。"""
    print("[guoan_builder] ====== 国安仪表盘数据构建开始 ======")

    # 1. 拉取 CSL 全量数据
    csl_bundle = fetch_csl_data()
    raw_data = csl_bundle.get("raw_data", csl_bundle)
    leagues = raw_data.get("leagues", [])
    league = leagues[0] if leagues else {}
    all_matches = league.get("matches", [])
    all_standings = league.get("standings", [])

    # CFL profiles
    cfl_profiles = csl_bundle.get("cfl_player_profiles", [])

    print(f"[guoan_builder] 全联赛: {len(all_matches)} 场比赛, "
          f"{len(all_standings)} 支球队, {len(cfl_profiles)} 份CFL档案")

    # 2. 筛选国安比赛（已自动去重俱乐部名变体）
    guoan_raw = get_guoan_matches(all_matches)
    print(f"[guoan_builder] 国安比赛: {len(guoan_raw)} 场（已去重）")

    # 3a. 扣分配置（积分计算前置）
    deductions = load_deductions()

    # 3. 积分榜（从比赛结果实时计算，使用归一化俱乐部名）
    computed_standings = compute_standings_from_matches(all_matches, deductions)

    # 4. 富化国安比赛（使用修正后的积分榜计算对手排名）
    guoan_matches = enrich_guoan_matches(guoan_raw, all_matches, computed_standings)

    # 4a. 从 CFL API 拉取全联赛最新比赛数据
    try:
        cfl_matches = fetch_cfl_all_data()
        # 构建 CFL 数据索引：{(date, home, away): match_dict}
        _cfl_index = {}
        for cm in cfl_matches:
            d = str(cm.get("date", ""))[:10]
            h = str(cm.get("home_club", ""))
            a = str(cm.get("away_club", ""))
            _cfl_index[(d, h, a)] = cm

        # 更新 guoan_matches（比分、事件、状态）
        _guoan_updated = 0
        # 构建多维度索引（用于匹配改期比赛）
        _cfl_by_id = {cm.get("match_id", ""): cm for cm in cfl_matches if cm.get("match_id")}
        # 按对手名+主客场构建索引（不依赖日期，支持改期）
        _cfl_by_opp = {}
        for cm in cfl_matches:
            h = cm.get("home_club", "")
            a = cm.get("away_club", "")
            for club in (h, a):
                if club:
                    _cfl_by_opp.setdefault(club, []).append(cm)
        for m in guoan_matches:
            date = str(m.get("date", ""))[:10]
            opp = m.get("opponent", "")
            is_home = m.get("is_home", False)
            # 优先通过 match_id 匹配（支持改期比赛）
            mid = m.get("match_id", "")
            cfl_match = _cfl_by_id.get(mid) if mid else None
            if cfl_match:
                # 直接用 match_id 匹配到的 CFL 数据
                cm = cfl_match
            else:
                cm = None
                for (cd, ch, ca), _cm in _cfl_index.items():
                    if cd == date and (opp in ch or opp in ca):
                        cm = _cm
                        break
            # 如果日期+对手和 match_id 都没匹配到，尝试对手名匹配（支持改期）
            if not cm:
                opp_candidates = _cfl_by_opp.get(opp, []) if opp else []
                if not opp_candidates:
                    # 尝试部分匹配（对手名包含关系）
                    for k, v in _cfl_by_opp.items():
                        if opp and (opp in k or k in opp):
                            opp_candidates = v
                            break
                # 选择日期最新的那场未完成比赛
                opp_candidates = [c for c in opp_candidates if c.get("status") != "finished"]
                opp_candidates.sort(key=lambda c: str(c.get("date", "")), reverse=True)
                if opp_candidates:
                    cm = opp_candidates[0]
                    if cm.get("date", "") != m.get("date", ""):
                        pass  # 日期不同是正常的（改期）
            if cm:
                    if cm["status"] == "finished" and m.get("result") == "?":
                        sc = cm.get("score", {})
                        hs = sc.get("home")
                        aws = sc.get("away")
                        if hs is not None and aws is not None:
                            m["status"] = "finished"
                            m["score"] = {"home": int(hs), "away": int(aws)}
                            m["guoan_goals"] = int(hs) if is_home else int(aws)
                            m["opp_goals"] = int(aws) if is_home else int(hs)
                            if hs == aws: m["result"] = "D"
                            elif (is_home and hs > aws) or (not is_home and aws > hs): m["result"] = "W"
                            else: m["result"] = "L"
                            m["formation"] = {"home": cm.get("home_formation", ""), "away": cm.get("away_formation", "")}
                            if cm.get("events"):
                                m["events"] = cm["events"]
                            _guoan_updated += 1
                    elif cm["status"] == "postponed" and m.get("status") == "scheduled":
                        m["status"] = "postponed"
                        _guoan_updated += 1
                    elif cm["status"] == "scheduled" and m.get("status") == "postponed":
                        new_date = cm.get("date", "")
                        if new_date and str(m.get("date", ""))[:10] != str(new_date)[:10]:
                            m["date"] = new_date
                        m["status"] = "scheduled"
                        m["result"] = "?"
                        m["guoan_goals"] = 0
                        m["opp_goals"] = 0
                        _guoan_updated += 1
                    # 通用日期同步：CFL 有更新日期时同步
                    new_date = cm.get("date", "")
                    if new_date and m.get("result") == "?" and str(m.get("date", ""))[:10] != str(new_date)[:10]:
                        m["date"] = new_date
                        _guoan_updated += 1
                    break
        if _guoan_updated:
            print(f"[guoan_builder] CFL API: 更新了 {_guoan_updated} 场国安比赛数据")

        # 用 CFL 全联赛数据更新 all_matches（用于完整积分榜）
        _csl_index = {}
        for am in all_matches:
            d = str(am.get("date", ""))[:10]
            h = str(am.get("home_club", ""))
            a = str(am.get("away_club", ""))
            key = (d, h, a)
            if key not in _csl_index:
                _csl_index[key] = am

        _cfl_added = 0
        for (cd, ch, ca), cm in _cfl_index.items():
            if (cd, ch, ca) in _csl_index:
                existing = _csl_index[(cd, ch, ca)]
                # 如果 CFL 有更优数据（finished vs scheduled），替换
                if cm["status"] == "finished" and str(existing.get("status","")).lower() not in ("finished","completed","ft"):
                    existing["status"] = cm["status"]
                    existing["score"] = cm.get("score", {})
                    _cfl_added += 1
                elif cm["status"] == "postponed" and str(existing.get("status","")).lower() == "scheduled":
                    existing["status"] = cm["status"]
                    _cfl_added += 1
                elif cm["status"] == "scheduled" and str(existing.get("status","")).lower() == "postponed":
                    new_date = cm.get("date", "")
                    if new_date:
                        existing["date"] = new_date
                    existing["status"] = cm["status"]
                    _cfl_added += 1
            else:
                # CFL 有新比赛（CSL 数据中没有）
                all_matches.append(cm)
                _cfl_added += 1

        if _cfl_added > 0:
            print(f"[guoan_builder] CFL API: 补充/更新了 {_cfl_added} 场全联赛比赛数据")

        # 用完整数据重建积分榜
        computed_standings = compute_standings_from_matches(all_matches, deductions)
        print(f"[guoan_builder] CFL 全联赛更新后积分榜: {len(computed_standings)} 队")

        # 用新积分榜刷新所有对手排名信息
        for m in guoan_matches:
            opp = m.get("opponent", "")
            if opp:
                m["opponent_info"] = build_opponent_info(m, all_matches, computed_standings)

    except Exception as e:
        print(f"[guoan_builder] CFL API 合并失败: {e}")

    # 比赛日期修正（CFL API 可能返回不同 match_id 导致匹配失败时的兜底）
    for m in guoan_matches:
        key = (m.get("round", ""), m.get("opponent", ""))
        # 申花客场改期：7/11 → 8/18
        if key == ("第18轮", "上海申花") and m.get("date", "")[:10] == "2026-07-11":
            m["date"] = "2026-08-18 19:35"
            m["status"] = "scheduled"
            m["result"] = "?"
            print("[guoan_builder] 已修正: 第18轮上海申花日期 7/11→8/18")

    # 4c. 数据完整性检测：日期已过但无结果的比赛（可能数据暂缺）
    from datetime import date as _date
    _today = _date.today().isoformat()
    _stale_matches = [
        m for m in guoan_matches
        if m.get("result", "?") == "?"
        and str(m.get("status", "")).lower() not in ("postponed", "cancelled", "canceled")
        and str(m.get("date", ""))[:10] < _today
    ]
    if _stale_matches:
        print(f"[guoan_builder] 数据暂缺: {len(_stale_matches)} 场比赛日期已过但无结果（非延期）:")
        for sm in _stale_matches:
            print(f"  - {sm.get('round','?')} vs {sm.get('opponent','?')} ({sm.get('date','')[:10]}) status={sm.get('status','?')}")

    guoan_standing = extract_guoan_standing(computed_standings, all_matches, deductions)
    guoan_standing["all_standings"] = computed_standings  # 完整实时积分榜

    # 5. 球员分析
    player_performance = analyze_player_performance(guoan_matches, cfl_profiles)
    print(f"[guoan_builder] 球员: {len(player_performance)} 人")

    # 6. 进球时间分布（传入国安球员名单以正确过滤）
    guoan_player_names = {p["player_name"] for p in player_performance}
    goal_times = analyze_goal_times(guoan_matches, guoan_player_names)

    # 7. 历史对战 H2H (2023~2026)
    h2h = {}
    try:
        matches_2023 = load_season_matches(str(DATA_DIR / "csl_2023_all_matches.json"))
        matches_2024 = load_season_matches(str(DATA_DIR / "csl_2024_all_matches.json"))
        matches_2025 = load_season_matches(str(DATA_DIR / "csl_2025_all_matches.json"))
        h2h = build_h2h(matches_2023, matches_2024, matches_2025, guoan_matches)
        print(f"[guoan_builder] H2H: {len(h2h)} 个对手")
    except Exception as e:
        print(f"[guoan_builder] H2H 构建警告: {e}")

    # 8. 对手汇总
    opponent_summary = build_opponent_summary(guoan_matches)

    # 9. 形态序列
    form_streak = build_form_streak(guoan_matches)

    # 10. 积分走势
    round_progression = build_round_progression(guoan_matches, all_standings)

    # 11. 球队资料
    club_profile = load_club_profile()

    # 12b. 队徽映射（从 CSL bundle 提取，补充归一化 key）
    team_logos = dict(csl_bundle.get("team_logos", {}))
    # 为归一化后的俱乐部名添加队标映射
    _logo_norm_map = {
        "大连英博海发": "大连英博",
        "河南俱乐部彩陶坊": "河南俱乐部",
        "河南俱乐部酒祖杜康": "河南俱乐部",
        "浙江俱乐部绿城": "浙江俱乐部",
        "辽宁铁人楠波湾": "辽宁铁人",
    }
    for orig_key, logo_path in list(team_logos.items()):
        for variant, canonical in _logo_norm_map.items():
            if variant in orig_key:
                if canonical not in team_logos:
                    team_logos[canonical] = logo_path

    # 13. 组装最终数据包
    embed = {
        "meta": {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "season": "2026",
            "last_match_round": guoan_matches[-1].get("round", "") if guoan_matches else "",
            "source": CSL_SOURCE_URL if not LOCAL_CSL_EMBED.exists() else str(LOCAL_CSL_EMBED),
        },
        "guoan": {
            "standing": guoan_standing,
            "matches": guoan_matches,
            "player_performance": player_performance,
            "h2h_records": h2h,
            "opponent_summary": opponent_summary,
            "form_streak": form_streak,
            "round_progression": round_progression,
            "goal_time_distribution": goal_times,
            "club_profile": club_profile,
        },
        "deductions": deductions,
        "team_logos": team_logos,
    }

    # 14. 写入文件
    WEB_DIR.mkdir(parents=True, exist_ok=True)
    output_path = WEB_DIR / "guoan_embed.json"
    output_path.write_text(
        json.dumps(embed, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8"
    )
    print(f"[guoan_builder] 输出: {output_path} "
          f"({output_path.stat().st_size / 1024:.1f} KB)")
    print("[guoan_builder] ====== 构建完成 ======")
    return embed


if __name__ == "__main__":
    main()
