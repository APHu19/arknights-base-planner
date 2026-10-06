# -*- coding: utf-8 -*-
"""fia.py —— 菲亚梅塔：**按班次**决定要不要交换（不再是一天固定 2 次）

技能原文（本机数据）：`患难之交`＝进驻宿舍时若自身满心情，则与**当前宿舍前一位进驻**的干员互换心情。
`自律`＝自身宿舍恢复 +2/h，且**无法获得其他来源的恢复**。

规则（自己推的，写成确定算法）
--------------------------------------------------
一次交换 = 把菲亚梅塔的"满心情"整体转移给目标 X（X 的心情变成菲亚梅塔的，菲亚梅塔接手 X 的）。
所以收益与代价分别是：
  · **收益**：X 因为心情被补满，能在**接下来的工作窗口里不被打穿**（不红脸 ⇒ 技能不失效），
    多干的小时数 = `min(缺口, 24 − X当前心情) / X的消耗率`；价值 = 该小时数 × X 所在房间的
    **每小时产出**（贸易=币/时、制造=件/时或经验/时、发电=架/时折算）。
    缺口 = 从本班开始到下一次"能靠休息回满"之前，X 累计消耗 − 累计恢复（>0 才需要救）。
  · **代价**：菲亚梅塔自己变成 X 的残值心情，且她**只能靠自律 +2/h 回血**（不能吃宿舍其他人的恢复）
    ⇒ 恢复满 24 需要 (24 − 残值)/2 小时；这段时间她不能再捐。
  · **决策**：枚举 (班次 i, 目标 X) 的收益，按收益降序贪心，受两个约束：
      ① 每天最多 2 次（游戏机制）；② 两次之间必须留出菲亚梅塔的回血时间（≥ (24−残值)/2 小时）。
  · 若最佳收益 ≤ 0（没人会红脸）→ 本班不交换（省下一次机会）。

与旧实现（`plan.solve_dorms` 固定 2 次、按"最缺心情"选人）的区别：
不再问"谁心情最低"，而问"**救了他能多产多少**"——低价值岗位的人不值得消耗交换次数。
"""
import collections


def _drain_rates(state):
    """{区间: {干员: 消耗/h}}（用内核已算好的 rate；缺的按休息 0）"""
    return {i: {op: state.rate.get((i, op), 0.0) for op in state.roster()} for i in range(state.n_slots)}


def _rest_rates(state):
    return {i: {op: state.rest_rate_of(i, op) for op in state.roster()} for i in range(state.n_slots)}


def _room_value(state, room, ops, ds):
    """目标所在房间的"每小时产出"，用于给"多干的小时"定价（统一折算成币/时）。"""
    from solve.systems import revenue
    try:
        if room == '贸易站':
            prod = None
            for (r, k, i), v in state.assign.items():
                if r == room and set(v['team']) == set(ops):
                    prod = v['product']; break
            v, metric, _n = revenue(ds, room, list(ops), prod or 'LMD',
                                    by_room={room: list(ops)})
            return v if metric == '币/时' else v * 500.0        # 件/经验/玉 也粗折成币
        if room == '制造站':
            v, metric, _n = revenue(ds, room, list(ops), 'Pure Gold', by_room={room: list(ops)})
            return v * 500.0                                    # 1 赤金 ≈ 500 币
        if room == '发电站':
            v, _m, _n = revenue(ds, room, list(ops), None, by_room={room: list(ops)})
            return v * (1 / 60.0) * 1000.0                      # 无人机折算（口径见注释）
    except Exception:
        pass
    return 0.0


def plan_fia(state, ds, max_swaps=2, min_gain=1.0):
    """决定菲亚梅塔在哪些班次交换、换给谁。返回 (决策dict, 说明list)；不改动 state。"""
    FIA = '菲亚梅塔'
    if FIA not in state.roster():
        return {}, ['菲亚梅塔不在名单里 → 不安排交换']
    roster = sorted(state.roster())
    rates = _drain_rates(state)
    rest = _rest_rates(state)
    # 默认心情轨迹（没有交换时），从 24 起算
    mor = {o: 24.0 for o in roster}
    timeline = []
    for i in range(state.n_slots):
        seg = {}
        for o in roster:
            before = mor[o]
            r = rates[i].get(o, 0.0)
            if r > 0:
                mor[o] = max(0.0, mor[o] - r * state.win[i][2])
            else:
                mor[o] = min(24.0, mor[o] + rest[i].get(o, 0.0) * state.win[i][2])
            seg[o] = (before, r)
        timeline.append(seg)
    decisions, notes = {}, []
    fia_mor = 24.0
    last_swap_t = -99.0
    t = 0.0
    for i in range(state.n_slots):
        h = state.win[i][2]
        on_duty = sorted(state.working(i))
        cands = []
        for o in on_duty:
            if o == FIA:
                continue
            before, r = timeline[i][o]
            if r <= 0:
                continue
            # 缺口：本班起往后，若不做任何事，会不会被打穿
            deficit = 0.0
            m = before
            for j in range(i, state.n_slots):
                rj = rates[j].get(o, 0.0)
                if rj > 0:
                    m -= rj * state.win[j][2]
                    if m < 0:
                        deficit = max(deficit, -m)
                else:
                    m = min(24.0, m + rest[j].get(o, 0.0) * state.win[j][2])
            if deficit <= 0:
                continue
            cover = min(deficit, 24.0 - before)
            hours = cover / max(1e-6, r)
            room = next((r0 for (r0, k, i0), v in state.assign.items()
                         if i0 == i and o in v['team']), '')
            ops = next((v['team'] for (r0, k, i0), v in state.assign.items()
                        if i0 == i and o in v['team']), [o])
            gain = hours * _room_value(state, room, ops, ds)
            cands.append((gain, o, deficit, hours, room))
        if not cands:
            t += h
            continue
        gain, target, deficit, hours, room = max(cands)
        # 菲亚梅塔回血约束（自律 +2/h，且不能吃别人恢复）＋每天 2 次
        refill = 0.0 if fia_mor >= 24.0 else (24.0 - fia_mor) / 2.0
        if gain < min_gain or len(decisions) >= max_swaps or (t - last_swap_t) < refill:
            t += h
            continue
        fia_after = timeline[i][target][0]
        decisions[i] = dict(enable=True, target=target)
        notes.append(f'第{i+1}班：把菲亚梅塔的心情换给 {target}（{room}）——缺 {deficit:.1f} 点、'
                     f'可多干 {hours:.1f}h、折算收益 {gain:.1f} 币；菲亚梅塔降为 {fia_after:.1f}，'
                     f'需 {max(0.0, (24 - fia_after) / 2):.1f}h 回满')
        fia_mor = fia_after
        last_swap_t = t
        t += h
    if not decisions:
        notes.append('本日无人会被打穿 → 不交换（省下次数）')
    return decisions, notes
