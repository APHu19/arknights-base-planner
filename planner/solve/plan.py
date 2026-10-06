# -*- coding: utf-8 -*-
"""plan.py —— 由装配结果生成六班计划 + 寝室分配（恢复债）+ 菲亚梅塔目标 + 14 天复核"""
import collections
import math
from core.engine import Ctx, simulate_shifts, drain_of, dorm_rooms_recovery, MAX_MORALE
from core.dataset import Dataset, load_box
from solve import schedule as SCN

# 控制中枢 A/B 两组与第 6 班轮休替补
CTRL_A = ['阿米娅', '凯尔希', '令', '重岳', '维什戴尔']
CTRL_B = ['阿米娅', '凯尔希', '夕', '电弧', '重岳']
# 三人组（阿米娅/凯尔希/重岳）24h 在岗会红脸（重岳自身 +0.5/h），必须**两段轮休**：第 3 班与第 6 班
SUB3 = {'阿米娅': '逻各斯', '凯尔希': '机械师', '重岳': '陈'}
SUB6 = {'阿米娅': '摩根', '凯尔希': '戴菲恩', '重岳': '焰影苇草', '夕': '跃跃'}
FIA = '菲亚梅塔'
FIA_SWAPS_PER_DAY = 2          # 游戏机制：菲亚梅塔每天最多交换 2 次
# 固定房间的 A/B 轮换搭档：**绝不能同一批人排满 6 班**（否则 24h 连轴必红脸）
ROTATION = {
    '会客室': {('伊内丝', '红'): ['虎狼丸', '伺夜'], ('虎狼丸', '伺夜'): ['伊内丝', '红'],
             ('余', '望'): ['伊内丝', '红'], ('伊内丝', '红', '虎狼丸', '伺夜'): ['余', '望']},
    '人力办公室': {('斥罪',): ['遥'], ('遥',): ['斥罪'], ('絮雨',): ['深律'], ('深律',): ['絮雨']},
    '加工站': {('黍',): ['深海色'], ('深海色',): ['黍'], (): []},
}
DORM_LEADS = [FIA, '杜林', '车尔尼', '爱丽丝']      # 1 号寝室放菲亚梅塔（首位 + 严格排序）


def _partner(room, ops):
    """给定房间与 A 班组，返回 B 班轮换搭档"""
    table = ROTATION.get(room) or {}
    return list(table.get(tuple(ops), []))


# ---------------------------------------------------------------- window 路径（干员级窗口排班）
def _ctrl_pool():
    """控制中枢候选集：保 KPI 的元老（A/B 两组）+ 轮休替补，全部是求解器算过的已知好人。"""
    pool = list(CTRL_A)
    for o in CTRL_B + list(SUB3.values()) + list(SUB6.values()):
        if o not in pool:
            pool.append(o)
    return pool


def _fixed_pools():
    """固定房间（会客室/人力办公室/加工站）的可用替补：固定队 + 所有轮换搭档。"""
    out = {}
    for room, table in ROTATION.items():
        ops = set(train for pair in table for train in pair)
        for v in table.values():
            ops |= set(v)
        out[room] = sorted(ops)
    return out


def build_window_shifts(assign, fixed, ds=None, hours=4.0, policy='steady', park_leads=0,
                        table=None):
    """window 路径：把装配结果排成对**判据 A（长期稳态）**可行的一天。

    与 ab 路径的区别：不再用"A 组/B 组整段轮换 + 恢复债分寝室"，
    而是按**真实时间区间**逐个 (房间,区间) 用增量可行性判定选人（见 solve/schedule.py）。
    返回 (shifts, DayState, 排班结果)

    park_leads：常驻宿舍的恢复技干员人数。**默认 0**——他们只吃床位名额、不为生产出力，
    而本布局的算术已经卡满：6 班 × 36 人在岗 = 216 岗位，每人最多 4 班（16h，8h 休息才够稳态），
    ⇒ 需要 54 人，而在册上限 = 20 床 + 36 在岗 = 56。多停一个恢复干员就少一个能排班的人。
    """
    from solve import schedule as SCN
    ds = ds or Dataset()
    box = load_box()
    owned = sorted(n for n, v in box.items() if v.get('own', True))
    spec = SCN.build_spec(assign, fixed, ctrl_pool=_ctrl_pool(), fixed_pools=_fixed_pools(),
                          ctrl_need=len(CTRL_A), fallback=owned)
    n_shifts = len(table) if table else max(1, int(round(24.0 / float(hours or 4.0))))
    onduty = sum(int(it['need']) for it in spec)
    used = {o for it in spec for o in it['primary']}
    parked = []
    if park_leads:
        parked = [o for _b, o in SCN.dorm_leads(ds, [n for n in owned if n not in used])][:int(park_leads)]
    st = SCN.DayState([hours] * n_shifts, ds=ds, policy=policy, parked=parked,
                      targets={i: onduty for i in range(n_shifts)}, table=table)
    res = SCN.schedule_base(st, spec)
    SCN.pack_dorms(st, ds, leads=parked)
    res['parked'] = parked
    res['spec'] = spec
    res['roster'] = len(st.roster())
    res['onduty'] = onduty
    return SCN.to_shifts(st), st, res


def build_shifts(assign, fixed, ds=None, hours=4.0, table=None):
    """assign: {(房间,i,grp): (product, level, team)}；fixed: {房间: [干员]}
    班次数由时长决定：**24h / 班次时长**（4h→6 班、6h→4 班、8h→3 班、12h→2 班），A/B 交替；
    也可传 `table`（core.shiftplan 自定义班次表，可不等长）——此时班次数与各班长短都来自表。
    控制中枢的两段轮休（第 3、6 班）只在 6 班结构下按原样套用。"""
    ds = ds or Dataset()
    if table:
        hl = [float(t['hours']) for t in table]
    else:
        hl = [float(hours or 4.0)] * max(1, int(round(24.0 / float(hours or 4.0))))
    n_shifts = len(hl)
    shifts = []
    for i in range(n_shifts):
        grp = 'A' if i % 2 == 0 else 'B'
        rooms = []
        for (room, ri, g), (product, level, team) in assign.items():
            if g != grp: continue
            rooms.append((room, product, level, list(team)))
        ctrl = list(CTRL_A if i % 2 == 0 else CTRL_B)
        is_a = (i % 2 == 0)
        def pick(room):
            ops = list(fixed.get(room) or [])
            if not ops: return []
            return ops if is_a else (_partner(room, ops) or ops)
        hire = pick('人力办公室')
        meet = pick('会客室')
        work = pick('加工站')
        if n_shifts == 6 and i in (2, 5):   # 6 班结构：三人组两段轮休（第 3、6 班）
            sub = SUB3 if i == 2 else SUB6
            ctrl = [sub.get(o, o) for o in ctrl]
            hire = [sub.get(o, o) for o in hire]
        elif n_shifts < 6 and i == n_shifts - 1:
            # 少班次（4/3/2 班，每班 ≥6h）：末班让三人组轮休即可（单次休息 6~12h 足够回满）
            ctrl = [SUB6.get(o, o) for o in ctrl]
            hire = [SUB6.get(o, o) for o in hire]
        rooms.append(('控制中枢', None, 3, ctrl))
        if meet: rooms.append(('会客室', None, 3, meet))
        if hire: rooms.append(('人力办公室', None, 3, hire))
        if work: rooms.append(('加工站', None, 3, work))
        item = dict(rooms=rooms, dorm=[], fia={}, hours=hl[i])
        if table:
            t = table[i]
            item.update(name=f"第{t['index']}班（{t['start']}-{t['end']}）",
                        period=[t['start'], t['end']], duration=int(t['minutes']),
                        clock=(t['start'], t['end']))
        shifts.append(item)
    return shifts


def solve_dorms(shifts, ds, days=21, off_cap=20, allow_swaps=None, hours=4.0, table=None):
    """恢复债驱动的寝室分配：每班把“累计消耗−累计恢复”最大者优先安排进宿舍。
    allow_swaps：允许菲亚梅塔交换的班次集合（None = 先全开以采集需求，再按每天 2 次收敛）。
    各班长短取自 `s['hours']`（自定义班次表可不等长）；无该键时退回统一的 hours。
    返回 (每班寝室列表, 最终心情, 心情最低值)"""
    if allow_swaps is None:
        allow_swaps = set(range(len(shifts)))
    roster = set()
    for s in shifts:
        for _, _, _, ops in s['rooms']: roster |= set(ops)
    roster |= set(DORM_LEADS)
    mor = {o: MAX_MORALE for o in roster}
    debt = {o: 0.0 for o in roster}
    lows = collections.defaultdict(lambda: MAX_MORALE)
    need = {}
    last = None
    for day in range(days):
        for sh, s in enumerate(shifts):
            h = float(s.get('hours') or hours)          # 自定义班次可不等长
            ctrl = next((ops for r, p, lv, ops in s['rooms'] if r == '控制中枢'), [])
            c0 = Ctx(ds=ds); c0.by_room = {}
            for r, p, lv, ops in s['rooms']:
                c0.by_room.setdefault(r, []).extend(ops)
            c0.staffed = [o for r, p, lv, ops in s['rooms'] for o in ops]
            from core.engine import _resolve_resources
            res = _resolve_resources(c0, c0.staffed, c0.base_resources(), ds)
            for r, p, lv, ops in s['rooms']:
                for o, v in drain_of(r, ops, ctrl, res.get('人间烟火', 0.0), ds).items():
                    mor[o] = max(0.0, mor[o] - v * h); debt[o] += v * h
            working = {o for r, p, lv, ops in s['rooms'] for o in ops}
            rest = [o for o in roster if o not in working and o not in DORM_LEADS]
            rest.sort(key=lambda o: -debt[o])
            rooms = [[FIA], ['杜林'], ['车尔尼'], ['爱丽丝']]
            for k in (0, 1, 2, 3):
                while len(rooms[k]) < 5 and rest:
                    rooms[k].append(rest.pop(0))
            for r in rooms:
                rr = dorm_rooms_recovery([r], ds)[0]
                for o in r:
                    mor[o] = min(MAX_MORALE, mor[o] + rr * h); debt[o] -= rr * h
            # 菲亚梅塔：只给“最缺心情的在岗者”且受每天 2 次限制
            if sh in allow_swaps and mor[FIA] >= 20.0:
                cands = [o for o in working if o not in DORM_LEADS]
                if cands:
                    t = min(cands, key=lambda o: mor[o])
                    if mor[t] < 22.0:
                        mor[FIA], mor[t] = mor[t], mor[FIA]
                        s['fia'] = dict(enable=True, target=t)
                        nd = MAX_MORALE - mor[t]
                        if nd > need.get(sh, (0, None))[0]: need[sh] = (nd, t)
                    else:
                        s['fia'] = {}
            for o in mor: lows[o] = min(lows[o], mor[o])
            if day >= days - 4: last = last or {}; last[sh] = [list(r) for r in rooms]
    # 收敛到“每天最多 2 次”：取需求最大的 2 个班次
    top = sorted(need.items(), key=lambda kv: -kv[1][0])[:FIA_SWAPS_PER_DAY]
    keep = {sh: t for sh, (nd, t) in top if nd > 1.0}
    for sh, s in enumerate(shifts):
        s['fia'] = dict(enable=True, target=keep[sh]) if sh in keep else {}
    for sh, s in enumerate(shifts):
        s['dorm'] = (last or {}).get(sh) or [[FIA], ['杜林'], ['车尔尼'], ['爱丽丝']]
    return shifts, mor, dict(lows)


def _drone_gold_fix(kpi_pre, kpi1, targets, assign, ctx, ds, objective, hours=4.0):
    """**赤金约束反馈**：若投放无人机后赤金净仍低于约束下限，就把**最少几个班次**的无人机从
    贸易站挪到赤金制造站，直到达标。返回 (新 targets, 说明)；无需调整时返回 (targets, None)。

    为什么需要：窗口排班让班组连续上班 → 贸易站订单品质吃满档 → 产量高于 ab，
    而求解器的赤字闸门是按 **ab 的产量**算的 ⇒ 赤金净被顶穿（实测 −1.22 ~ −15.31）。
    为什么用无人机：它是连续旋钮（1 架 = 180/4320 ≈ 0.0417 赤金），比"停掉整班贸易站"
    （一班 ≈ 6.9 赤金、还要丢 3000+ 龙门币）精确得多，而且不动队伍构成。
    """
    from solve import drones as DR
    cons = (objective or {}).get('cons') or {}
    rng = cons.get('gold_net')
    if not rng or rng[0] is None or not targets:
        return targets, None
    floor = float(rng[0])
    need = floor - float(kpi1.get('gold_net', 0.0))
    if need <= 1e-9:
        return targets, None
    rows = DR.uses(assign, ctx, ds, hours)
    gold_rows = [u for u in rows if (u.get('gain') or {}).get('gold')]
    if not gold_rows:
        return targets, None
    use = max(gold_rows, key=lambda u: u['gain']['gold'])
    per_shift = float(kpi_pre.get('drones', 0.0)) / max(1, len(targets))
    gain_gold = use['gain']['gold'] * per_shift - use['gain'].get('gold_cost', 0.0) * per_shift
    if gain_gold <= 0:
        return targets, None
    # 优先顶掉"投在贸易站（含龙门币收益）"的班次；按班次逐一累加收益，够了就停（不过量）
    order = [i for i, t in enumerate(targets) if t and 'lmd' in (t.get('gain') or {})]
    order += [i for i in range(len(targets)) if i not in order]
    new, moved, got = list(targets), [], 0.0
    for i in order:
        if got >= need:
            break
        t = new[i]
        before = ((t or {}).get('gain') or {})
        delta = gain_gold + before.get('gold_cost', 0.0) * per_shift
        new[i] = use
        moved.append(i + 1)
        got += delta
    return new, dict(moved_shifts=moved, to=use['label'],
                     per_drone_gold=round(use['gain']['gold'], 5),
                     need_gold=round(need, 2), gained_gold=round(got, 2),
                     drones_per_shift=round(per_shift, 1))


def build_plan(assign, fixed, ds=None, days=14, objective=None, hours=4.0, sched='ab', table=None):
    """sched='ab'（默认，现状）：A/B 六班 + 恢复债寝室；sched='window'：干员级窗口排班（判据 A）。
    table：`core.shiftplan` 的自定义班次表（可不等长，例 22:00/10:00/16:00 → 12h/6h/6h）。"""
    ds = ds or Dataset()
    window = wres = daycheck = None
    if sched == 'window':
        shifts, window, wres = build_window_shifts(assign, fixed, ds, hours=hours, table=table)
    else:
        shifts = build_shifts(assign, fixed, ds, hours=hours, table=table)
        shifts, mor, lows = solve_dorms(shifts, ds, hours=hours, table=table)
    kpi = simulate_shifts(shifts, days=days, hours=hours, ds=ds)
    detail = {}
    if objective:
        # 无人机逐目标最优分配：按“每架无人机的目标口径收益”投放（替换全投玉的乐观假设）
        from solve import drones as DR
        ctx = Ctx(ds=ds)
        rebuild = {}
        for room, ops in fixed.items():
            rebuild.setdefault(room, []).extend(ops)
        for (room, i, grp), (product, level, team) in assign.items():
            if grp == 'A':
                rebuild.setdefault(room, []).extend(team)
        ctx.by_room = rebuild
        ctx.staffed = [o for ops in rebuild.values() for o in ops]
        targets, detail = DR.allocate(assign, ctx, ds, objective, kpi)
        kpi1 = DR.apply_to_kpi(kpi, targets, assign, ctx, ds, objective)
        # —— 赤金约束反馈（窗口路径尤其需要）：把最少几个班次的无人机从贸易站挪到赤金制造站，
        #    直到赤金净 ≥ 约束下限。无人机是**连续旋钮**（1 架 = 180/4320 赤金），
        #    比"停掉整班贸易站"精确得多；且只动无人机，不破坏队伍构成。——
        targets, fix = _drone_gold_fix(kpi, kpi1, targets, assign, ctx, ds, objective)
        kpi = DR.apply_to_kpi(kpi, targets, assign, ctx, ds, objective) if fix else kpi1
        if fix:
            detail['gold_fix'] = fix
        for sh, s in enumerate(shifts):
            t = targets[sh] if sh < len(targets) else None
            s['drones'] = ({'room': t['maa_room'], 'index': t['index']} if t else None)
    if window is not None:
        rows = {r['op']: r for r in SCN.kernel_rows(window)}
        mor = {o: r['end'] for o, r in rows.items()}
        lows = {o: r['low'] for o, r in rows.items()}
        daycheck = SCN.verify(window, ds)
    return dict(shifts=shifts, mor=mor, lows=lows, kpi=kpi, drone_detail=detail,
                sched=sched, window=window, window_result=wres, daycheck=daycheck)
