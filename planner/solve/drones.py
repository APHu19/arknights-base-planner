# -*- coding: utf-8 -*-
"""drones.py —— 无人机逐目标最优分配

事实基础（《全机制.md》）：**1 架无人机 = 减少 3 分钟基础耗时**。
因此每种设施“每架无人机”的直接产出是确定的：

  设施            每架产出（基础耗时口径）              备注
  制造站·赤金      180/4320 = 0.04167 枚赤金           赤金价值取决于是否受赤金约束
  制造站·碎片      180/3600 = 0.05 片                  碎片价值 = 它能换到的玉
  制造站·作战记录   180/10800 = 0.01667 个中级记录（≈16.7 经验）
  贸易站·龙门币    180s 的订单时间 → 按该站订单结构折算龙门币（并附带赤金消耗）
  贸易站·源石订单   180/7200 = 0.025 单 → 0.5 玉（消耗 0.05 片）
  发电站          不消耗无人机（它是充能端）

分配策略：给资源定**影子价值**（由该资源当前是否受限决定），再按“每架无人机的目标口径收益”排序，
把一天的无人机按收益从高到低投放到具体设施；写 MAA 时按班次轮转（协议里每个计划只能填一个目标）。
"""
from core.engine import shift_output, RATE
from core.orders import profile

SHARD_TO_YU = 0.5 / 0.05          # 1 片 → 10 玉（20 玉 = 2 片）


def uses(assign, ctx, ds, hours=12.0):
    """列出所有可加速设施及其“每架无人机”的产出"""
    out = []
    for (room, i, grp), (product, level, team) in assign.items():
        rep = None
        if room == '制造站':
            if product == 'Pure Gold':
                out.append(dict(key=(room, i, grp), maa_room='manufacture', index=i + 1,
                                gain={'gold': 180 / 4320.0}, label=f'制造站#{i+1} 赤金'))
            elif product == 'Originium Shard':
                out.append(dict(key=(room, i, grp), maa_room='manufacture', index=i + 1,
                                gain={'shard': 180 / 3600.0}, label=f'制造站#{i+1} 源石碎片'))
            elif product == 'Battle Record':
                out.append(dict(key=(room, i, grp), maa_room='manufacture', index=i + 1,
                                gain={'exp': 180 / 10800.0 * 1000}, label=f'制造站#{i+1} 作战记录'))
        elif room == '贸易站':
            pr = profile(list(team), ds, hours)
            sec_per_order = pr['hours_per_order'] * 3600.0
            if product == 'LMD':
                n = 180.0 / sec_per_order
                out.append(dict(key=(room, i, grp), maa_room='trading', index=i + 1,
                                gain={'lmd': n * pr['lmd_per_order'],
                                      'gold_cost': n * pr['gold_per_order']},
                                label=f'贸易站#{i+1} 龙门币'))
            elif product == 'Orundum':
                n = 180.0 / sec_per_order
                out.append(dict(key=(room, i, grp), maa_room='trading', index=i + 1,
                                gain={'orundum': n * 20.0, 'shard_cost': n * 2.0},
                                label=f'贸易站#{i+1} 源石订单'))
    return out


def shadow_prices(kpi, objective):
    """资源影子价值（目标口径）：
       · 赤金：若钱站在吃金（总耗金 ≥ 产金）→ 多产 1 枚赤金能多换 500 龙门币
       · 碎片：若玉站受限（碎片净收支 ≤ 0）→ 多产 1 片能多换 10 玉（= SHARD_TO_YU 玉）
    """
    w = objective.get('w') or {}
    w_lmd = float(w.get('lmd', 0.0))
    w_yu = float(w.get('yu', 0.0))
    gold_bound = kpi.get('gold_cost', 0.0) >= kpi.get('gold', 0.0) - 1e-9
    # 碎片只在“已经不够用”时才有影子价值；够用时投碎片只是堆库存（价值 0）
    shard_short = kpi.get('shard_cost', 0.0) - kpi.get('shard', 0.0)
    return {'gold': (500.0 * w_lmd) if gold_bound else 0.0,
            'shard': (SHARD_TO_YU * w_yu) if shard_short > 1e-9 else 0.0}


def _value(gain, objective, price):
    """一架无人机的目标口径收益（注意 gain 用 orundum，权重用 yu，需要映射）"""
    w = objective.get('w') or {}
    KEYMAP = {'orundum': 'yu', 'gold': 'gold', 'shard': 'shard', 'lmd': 'lmd', 'exp': 'exp'}
    v = 0.0
    for k, amount in gain.items():
        if k in ('gold_cost', 'shard_cost'):
            base = k.replace('_cost', '')
            v -= amount * price.get(base, 0.0)          # 消耗资源按影子价扣减
        else:
            v += amount * float(w.get(KEYMAP.get(k, k), 0.0))
    for k in ('gold', 'shard'):
        if k in gain:
            v += gain[k] * price.get(k, 0.0)
    return v


def rank(assign, ctx, ds, objective, kpi, hours=12.0, verbose=False):
    """按每架无人机收益排序，返回 [(value, use), ...]"""
    price = shadow_prices(kpi, objective)
    rows = []
    for u in uses(assign, ctx, ds, hours):
        rows.append((_value(u['gain'], objective, price), u))
    rows.sort(key=lambda r: -r[0])
    if verbose:
        for v, u in rows[:8]:
            print(f"    无人机→{u['label']:<22} 每架收益 {v:8.2f}　{u['gain']}")
    return rows


def allocate(assign, ctx, ds, objective, kpi, shifts=6, hours=12.0, verbose=False):
    """按目标把一天的无人机投放到具体设施。
    **不做余量封顶**（按用户口径：余量/净消耗由 14 天模拟的结果如实显示即可）：
    按“每架无人机的目标口径收益”排序，只取收益为正的项，按收益比例分配到 6 个班次。"""
    price = shadow_prices(kpi, objective)
    rows = rank(assign, ctx, ds, objective, kpi, hours, verbose=False)
    total = kpi.get('drones', 0.0)
    pos = [(v, u) for v, u in rows if v > 1e-9]
    if not pos:
        pos = rows[:1]
    # 按收益比例分配无人机量（收益为 0 的项不投）
    wsum = sum(v for v, _ in pos) or 1.0
    per_shift = total / max(1, shifts)
    seq = []
    for v, u in pos:
        n = max(1, int(round(total * (v / wsum) / per_shift))) if per_shift else 1
        seq += [u] * n
    while len(seq) < shifts:
        seq.append(pos[0][1])
    targets = seq[:shifts]
    detail = {'drones_per_day': total, 'per_shift': per_shift,
              'chosen': [(round(v, 3), u['label']) for v, u in rows[:6]],
              'plan': [(u['label'], round(total * (v / wsum), 1)) for v, u in pos],
              'shadow': price}
    return targets, detail


def apply_to_kpi(kpi, targets, assign, ctx, ds, objective, hours=12.0):
    """按实际投放重算无人机带来的产出（替换原先“全部投玉”的乐观假设）"""
    if not targets:
        return kpi
    per_shift = kpi.get('drones', 0.0) / max(1, len(targets))
    by_key = {}
    for u in uses(assign, ctx, ds, hours):
        by_key[(u['key'], u['label'])] = u
    k = dict(kpi)
    gain = {}
    for t in targets:
        if not t: continue
        for kk, amount in t['gain'].items():
            gain[kk] = gain.get(kk, 0.0) + amount * per_shift
    for kk, amount in gain.items():
        k[kk] = k.get(kk, 0.0) + amount
    k['drone_gain'] = {kk: round(v, 2) for kk, v in gain.items()}
    k['gold_net'] = k.get('gold', 0.0) - k.get('gold_cost', 0.0)
    k['shard_net'] = k.get('shard', 0.0) - k.get('shard_cost', 0.0)
    k['yu'] = k.get('orundum', 0.0)      # orundum 已含无人机投放带来的部分
    return k
