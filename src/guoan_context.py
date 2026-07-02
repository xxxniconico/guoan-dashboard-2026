"""
国安比赛情境检测 — 6 种情境信号。
从 ticket-pricing/src/csl_context.py 迁移，纯 Python stdlib。
"""
from datetime import datetime, timedelta
from typing import Optional
from .opponent_tiers import classify_opponent_tier, PROMOTED_BIG_CITY

# ═══════════════════════════════════════════
# 俱乐部名称归一化 — CSL 上游数据存在多名变体
# ═══════════════════════════════════════════
_CLUB_NAME_NORMALIZE = {
    "浙江俱乐部绿城": "浙江",
    "大连英博海发": "大连英博",
    "辽宁铁人楠波湾": "辽宁铁人",
    "河南俱乐部彩陶坊": "河南",
    "河南俱乐部酒祖杜康": "河南",
    "河南队俱乐部彩陶坊": "河南",
}


def normalize_club(name: str) -> str:
    """将俱乐部名称变体归一化为标准名。"""
    n = str(name).strip()
    for variant, canonical in _CLUB_NAME_NORMALIZE.items():
        if variant in n:
            return canonical
    return n


def get_guoan_matches(matches: list) -> list:
    """从所有比赛中提取国安比赛，标注 is_home 和 opponent。
    自动去重：CSL 上游数据可能存在同一场比赛的多条记录（俱乐部名变体导致）。
    """
    guoan = []
    seen_dates = {}  # date_str -> set of normalized opponents (用于去重)
    for m in matches:
        home = normalize_club(str(m.get("home_club", "")))
        away = normalize_club(str(m.get("away_club", "")))
        if "国安" not in home and "国安" not in away:
            continue
        is_home = "国安" in home
        opponent = away if is_home else home

        # 去重：同一天 + 同一对手 → 只保留第一条（优先有 score 的）
        date_str = str(m.get("date", ""))[:10]
        if date_str not in seen_dates:
            seen_dates[date_str] = {}
        if opponent in seen_dates[date_str]:
            # 已有记录：如果新记录有比分而旧记录没有，则替换
            existing = seen_dates[date_str][opponent]
            new_has_score = (m.get("score", {}).get("home") is not None
                             and m.get("score", {}).get("away") is not None)
            old_has_score = (existing.get("score", {}).get("home") is not None
                             and existing.get("score", {}).get("away") is not None)
            if new_has_score and not old_has_score:
                # 替换为有比分的记录
                for i, gm in enumerate(guoan):
                    if (str(gm.get("date", ""))[:10] == date_str
                            and normalize_club(str(gm.get("opponent", ""))) == opponent):
                        guoan[i] = {**m, "is_home": is_home, "opponent": opponent,
                                    "home_club": home, "away_club": away}
                        seen_dates[date_str][opponent] = guoan[i]
                        break
            continue

        entry = {**m, "is_home": is_home, "opponent": opponent,
                 "home_club": home, "away_club": away}
        guoan.append(entry)
        seen_dates[date_str][opponent] = entry

    return guoan


def parse_date(d: str) -> Optional[datetime]:
    """解析日期字符串。"""
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(str(d)[:19], fmt)
        except (ValueError, IndexError):
            continue
    return None


def detect_ctx(match: dict, guoan_all: list) -> dict:
    """检测单场比赛的情境上下文。

    Args:
        match: 当前比赛 dict，含 is_home, opponent, date 等
        guoan_all: 国安所有比赛（含当前之前的历史）

    Returns:
        {"away_winless": bool, "away_winless_losses": bool,
         "lost_bottom": bool, "consecutive_home_losses": bool,
         "heavy_home_loss": bool, "short_rest": bool,
         "unbeaten_3": bool}
    """
    ctx = {}
    md = parse_date(match.get("date", ""))
    if md is None:
        return ctx

    # 当前比赛之前的历史
    prev = [m for m in guoan_all
            if m.get("status") in ("finished", "completed", "ft")
            and parse_date(m.get("date", "")) is not None
            and parse_date(m.get("date", "")) < md]
    last3 = prev[-3:] if len(prev) >= 3 else prev

    # --- away_winless: 最近3场中2+个客场，0个客场胜利 ---
    away3 = [m for m in last3 if not m.get("is_home")]
    if len(away3) >= 2:
        away_wins = sum(1 for m in away3 if _is_win(m))
        if away_wins == 0:
            ctx["away_winless"] = True
            away_losses = sum(1 for m in away3 if _is_loss(m))
            if away_losses == len(away3):
                ctx["away_winless_losses"] = True

    # --- lost_bottom: 最近3场输给 C 级且排名 >=12 的对手 ---
    for m in last3:
        if not _is_loss(m):
            continue
        opp = m.get("opponent", "")
        if opp in PROMOTED_BIG_CITY:
            continue
        tier = classify_opponent_tier(opp)
        if tier == "C":
            ctx["lost_bottom"] = True
            break

    # --- consecutive_home_losses: 最近2个主场全输 ---
    hp_all = sorted(
        [m for m in prev if m.get("is_home") and m.get("score", {}).get("home") is not None],
        key=lambda x: str(x.get("date", ""))
    )
    if len(hp_all) >= 2:
        last_two = hp_all[-2:]
        if all(_is_loss(m) for m in last_two):
            ctx["consecutive_home_losses"] = True

    # --- heavy_home_loss: 主场输2+球，且后面无胜利洗刷 ---
    for i, m in enumerate(last3):
        if not m.get("is_home"):
            continue
        hs = m.get("score", {}).get("home")
        aw = m.get("score", {}).get("away")
        if hs is None or aw is None:
            continue
        if hs < aw and abs(hs - aw) >= 2:
            later = last3[i + 1:]
            if not any(_is_win(lm) for lm in later):
                ctx["heavy_home_loss"] = True

    # --- short_rest: 距上次主场 <=4 天 ---
    hp = [m for m in prev if m.get("is_home")]
    if hp:
        last_home_date = parse_date(hp[-1].get("date", ""))
        if last_home_date and (md - last_home_date).days <= 4:
            ctx["short_rest"] = True

    # --- unbeaten_3: 最近3场不败 ---
    if len(last3) >= 3:
        if all(not _is_loss(m) for m in last3):
            ctx["unbeaten_3"] = True

    return ctx


def _is_win(m: dict) -> bool:
    """国安在此比赛中是否获胜。"""
    hs = m.get("score", {}).get("home")
    aw = m.get("score", {}).get("away")
    if hs is None or aw is None:
        return False
    is_home = m.get("is_home", False)
    return (is_home and hs > aw) or (not is_home and aw > hs)


def _is_loss(m: dict) -> bool:
    """国安在此比赛中是否失利。"""
    hs = m.get("score", {}).get("home")
    aw = m.get("score", {}).get("away")
    if hs is None or aw is None:
        return False
    is_home = m.get("is_home", False)
    return (is_home and hs < aw) or (not is_home and aw < hs)


CONTEXT_SIGNAL_LABELS = {
    "away_winless": "客场无胜",
    "away_winless_losses": "客场全败",
    "lost_bottom": "输下游队",
    "consecutive_home_losses": "主场连败",
    "heavy_home_loss": "主场惨败",
    "short_rest": "短休",
    "unbeaten_3": "3场不败",
}
