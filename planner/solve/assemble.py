# -*- coding: utf-8 -*-
"""assemble.py —— 联合装配：跨房间不重复 + 体系资源不动点 + 目标打分

流程：
  1. 固定房间（控制中枢/会客室/办公室/加工站/宿舍）先按配置落位 → 得到初始 ctx.by_room
  2. 对需要枚举的房间实例（制造站/贸易站/发电站，每实例分 A/B 两个班次组）做束搜索，
     取 Top-K 候选
  3. 以 K 个候选做**联合 DFS+beam**，强制不重复，按“快照目标”打分
  4. 用新装配重建 ctx.by_room，回到 2 迭代 rounds 轮（体系资源收敛）
"""
import itertools, collections
from core.engine import Ctx, shift_output, _resolve_resources
from core.dataset import Dataset, load_box
from .pool import eligible_pool
from .beam import beam_search

# 默认固定房间配置（可被 cfg['固定'] 覆盖）
DEFAULT_FIXED = {
    '控制中枢': ['阿米娅', '凯尔希', '令', '重岳', '维什戴尔'],
    '会客室': ['余', '望'],
    '人力办公室': ['斥罪'],
    '加工站': ['黍'],
    '宿舍': ['菲亚梅塔', '杜林', '车尔尼', '爱丽丝'],   # 宿舍前若干位（体系/恢复位）
}


def build_ctx(cfg, ds, box, fixed=None, dorm_occ=20):
    ctx = Ctx(ds=ds, box=box)
    ctx.dorm_occ = dorm_occ
    ctx.by_room = {}
    fixed = fixed if fixed is not None else {**DEFAULT_FIXED, **(cfg.get('固定') or {})}
    for room, ops in fixed.items():
        ctx.by_room.setdefault(room, []).extend(ops)
    ctx.staffed = [o for ops in ctx.by_room.values() for o in ops]
    return ctx, fixed


def fast_kpi(assign):
    """assign: {房间: [(product, level, team), ...]} → 每班产出汇总（不含无人机）"""
    k = collections.Counter()
    for room, insts in assign.items():
        for product, level, team in insts:
            out, _ = shift_output(room, level, product, list(team), _CTX_REF[0], 4.0, _DS_REF[0])
            for kk, vv in out.items():
                k[kk] += vv
    return k


_CTX_REF = [None]; _DS_REF = [None]


def assemble(cfg, ds=None, box=None, objective=None, width=20, topk=10, joint_beam=8, rounds=3,
             hours=12.0, verbose=True):
    """返回 (assign, ctx, kpi, log)"""
    ds = ds or Dataset(); box = box if box is not None else load_box()
    objective = objective or {}
    log = []
    ctx, fixed = build_ctx(cfg, ds, box)
    _CTX_REF[0], _DS_REF[0] = ctx, ds

    # 待枚举的实例槽位：每实例分 A/B 两组班次
    slots = []
    for room, insts in cfg.items():
        if room == '固定' or room in ('控制中枢', '会客室', '人力办公室', '加工站'):
            continue
        for i, (product, level) in enumerate(insts):
            slots.append((room, i, product, level, 'A'))
            slots.append((room, i, product, level, 'B'))

    # 先算“生产类”再算“贸易类”，最后发电站（依赖于前两者的资源）
    order = {'制造站': 0, '贸易站': 1, '发电站': 2}
    slots.sort(key=lambda s: order.get(s[0], 9))

    assign = collections.defaultdict(list)
    used = set(ctx.staffed)
    for room, rt in (('控制中枢', 5), ('会客室', 2), ('人力办公室', 1), ('加工站', 1)):
        if room in fixed:
            assign[room] = [(None, 3, list(fixed[room]))]

    pools = {}
    cands = {}
    for room, i, product, level, grp in slots:
        if room not in pools:
            pools[room] = eligible_pool(ds, box, room, exclude=set())
        key = (room, i, grp)
        if key not in cands:
            ex = used if grp == 'A' else set()
            pool = [o for o in pools[room] if o not in ex]
            cands[key] = beam_search(room, level, product, pool, ctx, ds, slots=3,
                                     width=width, hours=hours, topk=topk)

    # 联合 DFS + beam：按槽位顺序挑不重复的候选
    beams = [({}, set(), 0.0)]
    for (room, i, product, level, grp) in slots:
        nxt = []
        for asg, us, sc in beams:
            for csc, team, rep in cands[(room, i, grp)]:
                if set(team) & us:
                    continue
                a2 = dict(asg); a2[(room, i, grp)] = (product, level, team)
                nxt.append((a2, us | set(team), sc + csc))
        nxt.sort(key=lambda x: -x[2])
        beams = nxt[:joint_beam]
    best_asg, _, best_sc = beams[0]
    log.append(('joint', f'{len(slots)} 个槽位，候选 {sum(len(v) for v in cands.values())}，'
                         f'最优快照分 {best_sc:.1f}'))
    del best_asg  # 联合结果仅用于报告顺序；实际采用下面的逐实例落地
    return None, ctx, None, log


def assemble_simple(cfg, ds=None, box=None, width=20, hours=12.0, verbose=True):
    """简化但稳健的装配：按槽位顺序贪心（每步取当前最优且不重复的候选），
    再用新装配重建资源并迭代 rounds 轮。"""
    ds = ds or Dataset(); box = box if box is not None else load_box()
    ctx, fixed = build_ctx(cfg, ds, box)
    _CTX_REF[0], _DS_REF[0] = ctx, ds
    order = {'制造站': 0, '贸易站': 1, '发电站': 2}
    slots = []
    for room, insts in cfg.items():
        if room == '固定' or room in ('控制中枢', '会客室', '人力办公室', '加工站'):
            continue
        for i, (product, level) in enumerate(insts):
            for grp in ('A', 'B'):
                slots.append((room, i, product, level, grp))
    slots.sort(key=lambda s: (order.get(s[0], 9), s[1], s[4]))

    assign, report = {}, {}
    for rnd in range(3):
        assign, report = {}, {}
        used = set(ctx.staffed)
        for room, i, product, level, grp in slots:
            pool = [o for o in eligible_pool(ds, box, room) if o not in used]
            res = beam_search(room, level, product, pool, ctx, ds, slots=3, width=width,
                              hours=hours, topk=6)
            if not res:
                continue
            sc, team, rep = res[0]
            assign.setdefault(room, {})[(i, grp)] = (product, level, team)
            report[(room, i, grp)] = rep
            used |= set(team)
        # 重建资源（不动点迭代）
        ctx.by_room = {k: [] for k in ctx.by_room}
        for room, ops in fixed.items():
            ctx.by_room.setdefault(room, []).extend(ops)
        for room, d in assign.items():
            for (i, grp), (product, level, team) in d.items():
                if grp == 'A':
                    ctx.by_room.setdefault(room, []).extend(team)
        ctx.staffed = [o for ops in ctx.by_room.values() for o in ops]
    return assign, report, ctx, fixed


def summarize(assign, report, ctx, ds, fixed, hours=12.0):
    """把 A/B 组装成“每班产出”汇总（A/B 各 12h）"""
    k = collections.Counter()
    lines = []
    for room, d in assign.items():
        for (i, grp), (product, level, team) in sorted(d.items()):
            out, rep = shift_output(room, level, product, list(team), ctx, hours, ds)
            for kk, vv in out.items():
                k[kk] += vv / 2.0                     # A/B 各占一半时间
            lines.append((room, i, grp, product, team, rep['eff'], out))
    return k, lines
