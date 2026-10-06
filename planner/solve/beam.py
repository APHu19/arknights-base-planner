# -*- coding: utf-8 -*-
"""beam.py —— 单房间束搜索（增量建队 + 宽度剪枝）

为什么不用全枚举：C(150,3) ≈ 55 万/房间，×3 房间类型 ×2 班次 ×多轮资源迭代不可接受；
束搜索在 3 格房间上与全枚举差距极小（宽度 40 时实测与全枚举 Top1 一致）。
"""
from .pool import score_team


def beam_search(room, level, product, pool, ctx, ds, slots=3, width=40, hours=12.0, topk=8,
                rank=None):
    """返回 [(score, team, report)]，按 score 降序。
    rank(out, rep)：自定义排序口径（默认用房间主指标）。用于让候选**多样化**：
    例如钱站同时取“原始产出最高”和“产出−惩罚/耗金最低”两类，否则低耗金的平衡型队伍
    永远进不了候选，全局赤金约束就无法生效。"""
    if not pool:
        return []
    def sc_of(team):
        main, rep, out = score_team(room, level, product, list(team), ctx, ds, hours)
        return (rank(out, rep) if rank else main), rep, out
    beams = [((), 0.0)]
    for depth in range(slots):
        cand = []
        for team, _ in beams:
            start = pool.index(team[-1]) + 1 if team else 0
            for op in pool[start:]:
                nt = team + (op,)
                s, rep, out = sc_of(nt)
                cand.append((s, nt))
        if not cand:
            break
        cand.sort(key=lambda x: -x[0])
        beams = [(t, s) for s, t in cand[:width]]
    out = []
    for team, s0 in beams:
        s, rep, _ = sc_of(team)
        out.append((s, list(team), rep))
    out.sort(key=lambda x: -x[0])
    return out[:topk]
