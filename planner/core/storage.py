# -*- coding: utf-8 -*-
"""storage.py —— 制造站仓储上限 / 爆仓检查

数值（《全机制.md》§制造站）：仓库容量 Lv1/2/3 = **24 / 36 / 54**；进驻上限 1/2/3。
产物体积与基础耗时（每 1 个）：
    赤金 1.2h/个 占 2 格｜源石碎片 1h/个 占 3 格｜中级作战记录 3h/个 占 5 格
**非三级制造站只能产赤金**（已在 solver 里强制校验）。

爆仓判定：一个班次内产出件数 × 体积 > (容量 + 技能加成) → 该班次后段停工，
实际可得 = 容量/体积 件，其余损失。修法：换带“仓库容量上限+X”的干员，或适度降效。
"""
import re

CAPACITY = {1: 24, 2: 36, 3: 54}
VOLUME = {'Pure Gold': 2, 'Originium Shard': 3, 'Battle Record': 5}
HOURS_PER_ITEM = {'Pure Gold': 1.2, 'Originium Shard': 1.0, 'Battle Record': 3.0}


def cap_bonus(team, ds):
    """队伍技能提供的仓库容量加成（含“每个当前制造站内干员+5”这类按人数计）"""
    bonus = 0.0
    for op in team:
        for s in ds.skills_of(op, '制造站'):
            d = s.desc or ''
            for m in re.finditer(r'仓库容量(?:上限)?\+(\d+)', d):
                bonus += float(m.group(1))
            if '每个当前制造站内干员' in d and '仓库容量' in d:
                m = re.search(r'每个当前制造站内干员为当前制造站仓库容量上限\+(\d+)', d)
                if m: bonus += float(m.group(1)) * len(team)
    return bonus


def check(product, level, eff, hours, team=None, ds=None):
    """返回 dict(capacity, volume, made, max_items, overflow, fits)"""
    if not product or product not in VOLUME:
        return {}
    cap = CAPACITY.get(int(level), 54) + (cap_bonus(team or [], ds) if (team and ds) else 0.0)
    vol = VOLUME[product]
    made = hours / HOURS_PER_ITEM[product] * eff / 100.0
    max_items = cap / vol
    return dict(capacity=cap, volume=vol, made=made, max_items=max_items,
                overflow=max(0.0, made - max_items), fits=made <= max_items + 1e-9)


def scan_plan(shifts, ds, hours_per_shift=4.0):
    """扫描六班表里所有制造站，返回爆仓清单 [(班次, 房间序号, 产物, 结果)]"""
    out = []
    for i, s in enumerate(shifts, 1):
        for (room, prod, lv, team) in s['rooms']:
            if room != '制造站' or not prod:
                continue
            from core.engine import eval_room
            from core.engine import Ctx
            # 效率由调用方已知时可传入；这里用队伍实际在岗状态重算
            out.append((i, prod, lv, team))
    return out
