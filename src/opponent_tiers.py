"""
对手分级模块 — S/A/B/C 四级 + 德比定义。
从 ticket-pricing/src/classify.py 迁移，纯 Python 无依赖。
"""

# 德比对手（含京沪、京鲁传统 rivalry）
DERBY_RIVALS = {"上海申花", "山东泰山"}

# S 级：争冠/传统死敌
TIER_S = {"上海申花"}

# A 级：强队/争亚冠
TIER_A = {"成都蓉城", "山东泰山", "天津津门虎"}

# B 级：中游球队
TIER_B = {
    "长春亚泰", "深圳新鹏城", "云南玉昆", "武汉三镇",
    "浙江俱乐部", "浙江", "浙江队", "浙江俱乐部绿城",
    "上海海港",
    "河南俱乐部", "河南", "河南队", "河南俱乐部酒祖杜康", "河南队俱乐部彩陶坊", "河南俱乐部彩陶坊",
    "梅州客家", "青岛西海岸",
}

# C 级：下游/升班马
TIER_C = {
    "大连英博", "大连英博海发",
    "辽宁铁人", "重庆铜梁龙",
    "青岛海牛", "沧州雄狮", "南通支云",
}

# 升班马中的大城市球队（情境检测中排除 lost_bottom）
PROMOTED_BIG_CITY = {"辽宁铁人", "重庆铜梁龙"}


def classify_opponent_tier(opponent: str) -> str:
    """模糊匹配对手名，返回 S/A/B/C。"""
    for t in TIER_S:
        if t in opponent or opponent in t:
            return "S"
    for t in TIER_A:
        if t in opponent or opponent in t:
            return "A"
    for t in TIER_B:
        if t in opponent or opponent in t:
            return "B"
    for t in TIER_C:
        if t in opponent or opponent in t:
            return "C"
    return "B"  # 未知默认 B


def get_tier_label(tier: str) -> str:
    return {"S": "争冠/死敌", "A": "强队", "B": "中游", "C": "下游"}.get(tier, "未知")


def get_tier_color(tier: str) -> str:
    return {"S": "#ef4444", "A": "#f97316", "B": "#3b82f6", "C": "#6b7280"}.get(tier, "#6b7280")
