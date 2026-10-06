# -*- coding: utf-8 -*-
"""joint.py —— 目标驱动的联合求解（含赤金影子价格二分）

流程：
  1. 按目标给出的槽位优先级排序（要玉先排玉站/碎片站，要币先排钱站/金站）
  2. 逐槽位生成 Top-K 候选（**多种排序混合**：原始产出 / 产出−惩罚 / 产出耗金比），
     再把候选并入当前装配，用**全局目标**择优
  3. 用新装配重建体系资源（不动点），迭代 rounds 轮
  4. 若目标含赤金净收支约束 → 二分赤金影子价格 λ，使净收支落到要求区间
  5. 最后一轮 2-opt 局部交换收尾
"""
import collections
from core.engine import Ctx, shift_output, RATE
from core.dataset import Dataset, load_box
from .pool import eligible_pool, score_team
from .beam import beam_search
from . import objectives

FIXED_BASE = {
    '控制中枢': ['阿米娅', '凯尔希', '令', '重岳', '维什戴尔'],
    '宿舍': ['菲亚梅塔', '杜林', '车尔尼', '爱丽丝'],
}
# 计划阶段才会用到的轮换/替补干员：求解时必须预留，否则会出现“同一个人被排进两个房间”
RESERVED = {'夕', '电弧', '摩根', '戴菲恩', '焰影苇草', '跃跃', '逻各斯', '机械师', '陈',
            # 固定房间候选（办公室/会客室/加工站）
            '伊内丝', '红', '虎狼丸', '伺夜', '余', '望', '斥罪', '絮雨', '深律', '遥', '黍', '深海色'}
FIXED_PRESETS = {
    '人力办公室': {'斥罪': ['斥罪'], '絮雨': ['絮雨'], '深律': ['深律'], '遥': ['遥']},
    '会客室': {'线索(伊内丝+红)': ['伊内丝', '红'], '体系占数(余+望)': ['余', '望'],
             '线索(虎狼丸+伺夜)': ['虎狼丸', '伺夜']},
    '加工站': {'黍(岁占数)': ['黍'], '深海色': ['深海色'], '空置': []},
}


def fast_kpi(assign, fixed, ctx, ds, hours=12.0):
    """每**天**口径（A/B 各 12h）的产出汇总 + 玉/赤金收支"""
    k = collections.Counter()
    for key in list(assign):
        room, i, grp = key
        product, level, team = assign[key]
        out, _ = shift_output(room, level, product, list(team), ctx, hours, ds)
        for kk, vv in out.items():
            k[kk] += vv
    # 无人机：**每座发电站**效率 = 有人 +5% + 技能加成，三站相加（用户口径）
    per_grp = {}
    for key in list(assign):
        room, i, grp = key
        if room != '发电站':
            continue
        product, level, team = assign[key]
        _, rep = shift_output(room, level, product, list(team), ctx, hours, ds)
        per_grp.setdefault(grp, []).append(rep.get('charge', 0.0))
    rates = [sum((10.0 / 3.0) * (1 + (5.0 + b) / 100.0) for b in bs) for bs in per_grp.values()]
    drones = (sum(rates) / len(rates)) * 24.0 if rates else 0.0
    k['drones'] = drones
    k['charge_bonus'] = (sum(sum(bs) for bs in per_grp.values()) / max(1, len(per_grp))) if per_grp else 0.0
    k['gold_net'] = k.get('gold', 0.0) - k.get('gold_cost', 0.0)
    k['shard_net'] = k.get('shard', 0.0) - k.get('shard_cost', 0.0)
    # 与报告口径一致：yu 只算玉站产出，无人机收益统一由 solve/drones.py 计入
    k['yu'] = k.get('orundum', 0.0)
    # 会客室线索产出（若固定房间里有会客室）
    mt = fixed.get('会客室')
    if mt:
        try:
            from core.meeting import speed as _ms
            k['clue'] = _ms(list(mt), ds, box=getattr(ds, '_box', None), hours=hours)['clue_per_day']
        except Exception:
            k['clue'] = 0.0
    k['min_morale'] = 99.0
    return k


def rebuild_ctx(ctx, fixed, assign, dorm_occ=20):
    ctx.by_room = {}
    for room, ops in fixed.items():
        ctx.by_room.setdefault(room, []).extend(ops)
    for (room, i, grp), (product, level, team) in assign.items():
        if grp == 'A':
            ctx.by_room.setdefault(room, []).extend(team)
    ctx.staffed = [o for ops in ctx.by_room.values() for o in ops]
    ctx.dorm_occ = dorm_occ
    return ctx


def cfg_slots(cfg):
    slots = []
    for room, insts in cfg.items():
        if room == '固定' or room in ('控制中枢', '会客室', '人力办公室', '加工站'):
            continue
        for i, (product, level) in enumerate(insts):
            for grp in ('A', 'B'):
                slots.append((room, i, product, level, grp))
    return slots


def _candidates(room, level, product, pool, ctx, ds, width, topk, hours):
    """多排序混合候选，避免低耗金的平衡型队伍进不了候选。返回 [(score, team, rep, out)]"""
    ranks = [None]
    if room == '贸易站':
        ranks.append(lambda out, rep: out.get('lmd', 0) - 1e4 * out.get('gold_cost', 0)
                     - 1e3 * out.get('shard_cost', 0))
        ranks.append(lambda out, rep: (out.get('lmd', 0) / max(1e-6, out.get('gold_cost', 0))
                                       + out.get('orundum', 0) / max(1e-6, out.get('shard_cost', 0))))
        ranks.append(lambda out, rep: out.get('orundum', 0) - 1e3 * out.get('shard_cost', 0))
        ranks.append(lambda out, rep: -out.get('shard_cost', 0) - out.get('gold_cost', 0))
    elif room == '制造站':
        ranks.append(lambda out, rep: rep['eff'])
    out, seen = [], set()
    for rk in ranks:
        for sc, team, rep in beam_search(room, level, product, pool, ctx, ds, slots=3,
                                         width=width, hours=hours, topk=topk, rank=rk):
            key = tuple(sorted(team))
            if key in seen: continue
            seen.add(key)
            _, _, o = score_team(room, level, product, list(team), ctx, ds, hours)
            out.append((sc, team, rep, o))
    return out


def _drone_budget_est(assign, ctx, ds, hours):
    """估算无人机投放会带来的额外产出，用于预算修复时预留（否则修复后的方案在投放后会偏离约束）。"""
    drones = 0.0
    for key in list(assign):
        room, i, grp = key
        if room != '发电站':
            continue
        product, level, team = assign[key]
        _, rep = shift_output(room, level, product, list(team), ctx, hours, ds)
        drones += (10.0 / 3.0) * (1 + (5.0 + rep.get('charge', 0.0)) / 100.0) * 12.0
    return {'gold': drones * (180.0 / 4320.0), 'shard': drones * (180.0 / 3600.0)}


def _budget_repair(assign, cands_by_slot, kind='gold', drone_gain=None):
    """预算约束下的组合选择。
    关键事实：所有订单档的“龙门币/赤金”恒等于 500，所以给赤金定影子价格无法区分方案；
    真正有效的做法是把**赤金产出当作预算**，在候选集上挑“总耗金 ≤ 预算、总龙门币最大”的组合。
    kind='gold'：作用于 LMD 钱站；kind='shard'：作用于玉站（碎片预算）
    drone_gain：无人机会额外产出的资源（先算进来，避免修复后又被无人机打破约束）"""
    import itertools
    drone_gain = drone_gain or {}
    if kind == 'gold':
        slots = [k for k in assign if assign[k][0] == 'LMD']
        budget = 0.0
        for k in assign:
            if assign[k][0] == 'Pure Gold':
                for c in cands_by_slot.get(tuple(k), []):
                    if tuple(c[1]) == tuple(assign[k][2]):
                        budget += c[3].get('gold', 0.0); break
        budget += float(drone_gain.get('gold', 0.0))
        cost_key, val_key = 'gold_cost', 'lmd'
    else:
        slots = [k for k in assign if assign[k][0] == 'Orundum']
        budget = 0.0
        for k in assign:
            if assign[k][0] == 'Originium Shard':
                for c in cands_by_slot.get(tuple(k), []):
                    if tuple(c[1]) == tuple(assign[k][2]):
                        budget += c[3].get('shard', 0.0); break
        budget += float(drone_gain.get('shard', 0.0))
        cost_key, val_key = 'shard_cost', 'orundum'
    if not slots:
        return 0.0
    # 修复时仍需强制“跨槽位不重复”：先把**其他槽位 + 固定房间**的干员收集起来
    repair_keys = set(map(tuple, slots))
    used_elsewhere = set()
    for k, (p, l, t) in assign.items():
        if tuple(k) not in repair_keys:
            used_elsewhere |= set(t)
    for ops in FIXED_BASE.values():
        used_elsewhere |= set(ops)
    pools = []
    for k in slots:
        lst = [c for c in cands_by_slot.get(tuple(k), []) if not (set(c[1]) & used_elsewhere)]
        pools.append(lst if lst else [(0, list(assign[k][2]), None, {})])
    best, deficit_best = None, None
    for combo in itertools.product(*pools):
        seen_ops = set()
        clash = False
        for c in combo:
            if seen_ops & set(c[1]):
                clash = True; break
            seen_ops |= set(c[1])
        if clash:
            continue
        tc = sum(c[3].get(cost_key, 0.0) for c in combo)
        tv = sum(c[3].get(val_key, 0.0) for c in combo)
        if tc <= budget + 1e-9:
            if best is None or tv > best[0]:
                best = (tv, tc, combo)
        else:
            over = tc - budget
            if deficit_best is None or over < deficit_best[0] or (over == deficit_best[0] and tv > deficit_best[1]):
                deficit_best = (over, tv, combo)
    pick = best or deficit_best
    if not pick:
        return 0.0
    for k, c in zip(slots, pick[2]):
        assign[k] = (assign[k][0], assign[k][1], list(c[1]))
    return pick[1] - budget      # 返回剩余（负值为超支）


def _solve_once(cfg, props, ds, box, width, topk, rounds, hours, local_search, price=None):
    slots = cfg_slots(cfg)
    slots.sort(key=lambda s: (objectives.slot_priority(props, s[2], s[0]), s[1], s[4]))
    ctx = Ctx(ds=ds, box=box)
    fixed = dict(FIXED_BASE)
    best_overall = None
    for rnd in range(rounds):
        assign, used = {}, set(o for ops in fixed.values() for o in ops) | set(RESERVED)
        cands_by_slot = {}
        for si, (room, i, product, level, grp) in enumerate(slots, 1):
            pool = [o for o in eligible_pool(ds, box, room) if o not in used]
            cands = _candidates(room, level, product, pool, ctx, ds, width, topk, hours)
            cands_by_slot[(room, i, grp)] = cands
            best = None
            for sc, team, rep, out in cands:
                trial = dict(assign); trial[(room, i, grp)] = (product, level, list(team))
                v = objectives.score(fast_kpi(trial, fixed, ctx, ds, hours), props, price)
                if best is None or v > best[0]:
                    best = (v, list(team), rep)
            if best is None:
                continue
            assign[(room, i, grp)] = (product, level, best[1])
            used |= set(best[1])
            print(f'      [{si}/{len(slots)}] {room}#{i+1}-{grp} {product or "":<16} '
                  f'{"+".join(best[1])}  eff {best[2]["eff"]:.0f}%', flush=True)
        # 预算约束修复：把 LMD 钱站 / 玉站的组合拉到预算内（赤金产出、碎片产出即预算）
        cons = props.get('cons') or {}
        dg = _drone_budget_est(assign, ctx, ds, hours)
        if 'gold_net' in cons:
            _budget_repair(assign, cands_by_slot, 'gold', dg)
        if cons.get('shard_ge_trade'):
            _budget_repair(assign, cands_by_slot, 'shard', dg)
        rebuild_ctx(ctx, fixed, assign)
        v = objectives.score(fast_kpi(assign, fixed, ctx, ds, hours), props, price)
        if best_overall is None or v > best_overall[0]:
            best_overall = (v, dict(assign))
    _, assign = best_overall
    if local_search:
        improved = True
        while improved:
            improved = False
            for key in list(assign):
                product, level, team = assign[key]
                room = key[0]
                used = set(o for ops in FIXED_BASE.values() for o in ops)
                for kk, (p2, l2, t2) in assign.items():
                    if kk != key: used |= set(t2)
                base_v = objectives.score(fast_kpi(assign, FIXED_BASE, ctx, ds, hours), props, price)
                for idx in range(len(team)):
                    for cand in eligible_pool(ds, box, room):
                        if cand in used or cand in team: continue
                        nt = list(team); nt[idx] = cand
                        trial = dict(assign); trial[key] = (product, level, nt)
                        v2 = objectives.score(fast_kpi(trial, FIXED_BASE, ctx, ds, hours), props, price)
                        if v2 > base_v + 1e-9:
                            assign[key] = (product, level, nt); base_v = v2; improved = True
    rebuild_ctx(ctx, FIXED_BASE, assign)
    k = fast_kpi(assign, FIXED_BASE, ctx, ds, hours)
    return dict(assign=assign, fixed=FIXED_BASE, kpi=k, ctx=ctx)


def joint_solve(cfg, objective, ds=None, box=None, width=16, topk=8, rounds=2, hours=12.0,
                local_search=True, verbose=True, price_gold=None, bisect=0):
    """目标驱动求解。
    说明：**影子价格对赤金无效**（所有订单档的 币/赤金 恒为 500，定价只是等比缩放），
    因此赤金/碎片这类“资源预算”约束改用 `_budget_repair` 在候选集上做组合选择。"""
    ds = ds or Dataset(); box = box if box is not None else load_box()
    props = objectives.get(objective) if isinstance(objective, str) else objective
    return _solve_once(cfg, props, ds, box, width, topk, rounds, hours, local_search,
                       price=({'gold': price_gold} if price_gold is not None else None))
