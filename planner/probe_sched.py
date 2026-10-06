# -*- coding: utf-8 -*-
"""probe_sched.py —— window 调度器验收：**用户给的 6,6,12 三班用例**

三组场景（全部跑真实 daycheck，逐字贴输出）
  A. 6,6,12 @ literal      —— 字面判据（次日 00:00 回满）。尾班 [12,24) 从 12:00 干到 24:00，
                              **任何人**的 00:00 都 < 24 ⇒ 尾班无解（结构性，不是排班技巧问题）。
                              为让终检器给出真实数字，尾班按"强制补人"落位后再跑 daycheck。
  B. 6,6,12 @ next_window  —— 判据的可达化表述（每个工作窗口开始时满心情 + 全程不被打穿）。
                              尾班能排满，kernel 自检达标；daycheck 仍按字面报同一批人（对照）。
  C. 6,6,6,4 @ literal     —— 末段 [18,22) 在 22:00 结束，留出 2h 休息尾巴 ⇒ 字面判据应当通过。

坑位遵守：不用 `python -c` 内联；输出强制 UTF-8；只读 `_raw` 之外的仓库数据。
"""
import os
import sys
import time
import collections

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

from core.dataset import Dataset, load_box                    # noqa: E402
from core.engine import room_recovery                          # noqa: E402
from solve import schedule as SCH                              # noqa: E402

# 252 布局（2 发电 / 5 制造 / 2 贸易）：每格 (房间, 产物, 等级, 该格人数)
SPEC = [
    ('控制中枢', None, 5, 5),
    ('会客室', None, 3, 2),
    ('人力办公室', None, 3, 1),
    ('加工站', None, 3, 1),
    ('制造站', 'Pure Gold', 3, 3),
    ('制造站', 'Pure Gold', 3, 3),
    ('制造站', 'Pure Gold', 3, 3),
    ('制造站', 'Originium Shard', 3, 3),
    ('制造站', 'Originium Shard', 3, 3),
    ('贸易站', 'LMD', 3, 3),
    ('贸易站', 'LMD', 3, 3),
    ('发电站', None, 3, 1),
    ('发电站', None, 3, 1),
]

DEV = 0.9        # 3 人房间的典型消耗率 1−0.05×2（仅用于边界公式演示）
REST = 4.0       # 宿舍 Lv5 满氛围基础恢复 4.0/h


def recovery_leads(ds, pool, k=4):
    """找出**宿舍恢复技能**持有者（真实数据，不靠记忆）。"""
    out = []
    for op in pool:
        best = max([room_recovery(s.desc) for s in ds.skills_of(op, '宿舍')] or [0.0])
        if best > 0:
            out.append((best, op))
    out.sort(key=lambda t: (-t[0], t[1]))
    return out[:k]


def build_day(policy, hours, ds, pool, force_on_fail=False, leads=None, topn=8,
              topn_max=16, combo_cap=120, rest_slots=None):
    """按真实区间把整个基建排满一天（组合层只是"逐房间调用单房间排班"，不是求解器接线）。"""
    rest_slots = set(rest_slots or ())
    onduty = sum(n for _, _, _, n in SPEC)
    targets = {i: (0 if i in rest_slots else onduty) for i in range(len(hours))}
    st = SCH.DayState(hours, ds=ds, policy=policy, parked=list(leads or []), targets=targets,
                      rest_slots=rest_slots)
    fails, forced, pending = [], [], []
    seen = {}
    for room, product, level, need in SPEC:
        seen[room] = seen.get(room, 0) + 1     # 同名房间必须是**不同的格**（5 间制造站 = 5 个独立房间）
    # **区间优先**（先排满第 1 班，再排第 2 班…）：房间优先会让"必然排不出的尾班"先把床位名额吃光，
    # 反而把前面几班挤空（本轮实测）。房间内部再按 SPEC 的优先级（中枢 → 固定房 → 制造/贸易/发电）。
    order = [(slot, ri) for slot in range(st.n_slots) if slot not in rest_slots
             for ri in range(len(SPEC))]
    for slot, ri in order:
        room, product, level, need = SPEC[ri]
        inst = sum(1 for rj in range(ri) if SPEC[rj][0] == room)
        def rank(op, s, _room=room):
            # ① **先摊人**：当天还没上班的人优先（否则同几个人会被连排到 18h，后面区间反而没人可用
            #    ——这是本轮实测踩到的坑）
            # ② 同为 0 班时，已在册者优先（少占床位名额） ③ 再按技能多寡
            load = sum(1 for i in range(st.n_slots) if op in st.working(i))
            return (load, 0 if op in st.roster() else 1, -len(ds.skills_of(op, _room)), op)

        prod_slots = [j for j in range(st.n_slots) if j not in rest_slots]
        cap = st.beds + min(st.target(j) for j in prod_slots)

        def avail_filter(op, s, _st=st, _cap=cap, _k=need):
            # 在册名额要留给**整支队**：只剩不到 need 个空位时，新人一律不进候选（否则整队每次
            # 都被"第一个人占掉最后一个名额、第二个人床位超标"卡死——本轮实测）
            return True if op in _st.roster() else len(_st.roster()) + _k <= _cap

        r = SCH.schedule_room(st, room, inst=inst, product=product, level=level, need=need,
                              slots=[slot], pool=pool, rank=rank, avail_filter=avail_filter,
                              topn=topn, topn_max=topn_max, combo_cap=combo_cap)
        for f in r['failed']:
            rec = dict(room=r['room'], slot=f['slot'], reason=f['reason'],
                       tried=f['tried'], sample=f.get('sample') or [])
            fails.append(rec)
            pending.append(dict(room=room, inst=inst, slot=slot, product=product,
                                level=level, need=need, info=rec))
    # 诊断补人**放到最后**：中途补进去的人会占床位，把后面房间挤死（本轮实测）
    if force_on_fail:
        for p in pending:
            team = [o for o in pool if o not in st.working(p['slot'])][:p['need']]
            for op in team:
                st.place(p['room'], p['inst'], p['slot'], op, p['product'], p['level'], check=False)
            forced.append(dict(room=f"{p['room']}#{p['inst'] + 1}", slot=p['slot'], team=team))
    SCH.pack_dorms(st, ds, leads=list(leads or []))
    return st, fails, forced


def work_hist(st):
    c = collections.Counter()
    for op in st.roster():
        p = st.project(op)
        c[round(sum(st.win[i][2] for i in p['work']), 1)] += 1
    return dict(sorted(c.items()))


def run(name, policy, hours, ds, pool, leads, force_on_fail=False, rest_slots=None):
    t = time.time()
    st, fails, forced = build_day(policy, hours, ds, pool, force_on_fail=force_on_fail, leads=leads,
                                  rest_slots=rest_slots)
    res = SCH.verify(st, ds)
    print()
    print('=' * 100)
    print(SCH.fmt_report(st, res, f'场景 {name}'))
    print(f'  用时 {time.time() - t:.1f}s   工作时长分布(小时→人数): {work_hist(st)}')
    if fails:
        print(f'  ⚠ 排不动的 (房间,区间) {len(fails)} 处：')
        for f in fails[:6]:
            print(f"     {f['room']} 第{f['slot'] + 1}班：{f['reason']}（试了 {f['tried']} 组）")
            for s in f['sample'][:2]:
                print(f"        例：队伍 {s['team']} 卡在 {s['stop_at']} → {s['reasons']}")
    if forced:
        print(f"  （诊断用）强制补人的 (房间,区间) {len(forced)} 处："
              + '、'.join(f"{f['room']}第{f['slot'] + 1}班" for f in forced))
    if res['bed_overflow']:
        print(f"  ⚠ 床位溢出区间：{res['bed_overflow']}（这些区间的排班没排满，不在岗人数真的超过 20）")
    prod = [i for i in range(st.n_slots) if i not in st.rest_slots]
    last = max(prod)
    print(f"  床位瓶颈：最后一班(第{last + 1}班)在岗 {len(st.working(last))} 人 ⇒ 他们必须在下班后拿到床位"
          f"才能回满；而末段不在岗 {len(st.roster() - st.working(last))} 人只有 {st.beds} 张床")
    if res['failures']:
        print(f"  终检器失败人数 {len(res['failures'])}/{len(res['end'])}；未回满最差 5 人："
              + '、'.join(f'{k} {v:+.2f}' for k, v in
                          sorted(res['failures'].items(), key=lambda kv: kv[1])[:5]))
    return st, res, fails


def main():
    ds = Dataset()
    box = load_box()
    ds.set_box(box)
    pool = sorted(n for n, v in box.items() if v.get('own', True))
    leads = recovery_leads(ds, pool)
    lead_names = [op for _, op in leads]
    print('=' * 100)
    print('window 调度器验收 —— 用户给的 6,6,12 三班用例')
    print(f"干员池：{len(pool)} 人（Arknights_OperBox_Export.json）；"
          f"常驻宿舍（真实恢复技持有者）：{[(o, b) for b, o in leads]}")
    onduty = sum(n for _, _, _, n in SPEC)
    print(f'布局 252：{len(SPEC)} 间房，每区间在岗 {onduty} 人；床位 {SCH.BED_CAP}'
          f'（4 间 × 5）⇒ 唯一干员上限 {onduty + SCH.BED_CAP - len(leads)}（去掉常驻宿舍 {len(leads)} 人）')

    run('A1: 6,6,12 @ literal（字面判据·不强行补人）', 'literal', [6, 6, 12], ds, pool, lead_names)
    run('A2: 6,6,12 @ literal + 强行补满尾班（诊断：硬要 24h 全覆盖会怎样）', 'literal',
        [6, 6, 12], ds, pool, lead_names, force_on_fail=True)
    run('B: 6,6,12 @ steady（长期稳态口径：迭代到不动点）', 'steady', [6, 6, 12], ds, pool, lead_names)
    run('C: 6,6,6,6 @ literal（第 4 班设为**纯休息班**，00:00 前留 6h 恢复）', 'literal',
        [6, 6, 6, 6], ds, pool, lead_names, rest_slots=[3])

    print()
    print('=' * 100)
    print('边界公式：要在 00:00 回满 ⇔ 从「最后一次满心情」到 00:00，'
          '最后一段**连续工作**的消耗 ≤ 其后的休息恢复')
    for h in (2, 4, 6, 12):
        need = SCH.min_rest_tail(h, DEV, REST)
        print(f'  尾班单独 {h:>2}h（3 人房，消耗 {DEV}/h，恢复 {REST}/h）→ 需休息 {need:.2f}h → '
              f'最晚结束 {SCH.latest_end(h, DEV, REST):.2f} 时')
    print('  ⇒ 6,6,12 的第三段 [12,24) 结束于 24.00 时 ⇒ **字面判据下无解**（任何人都回不满，见场景 A1/A2）')
    print(f'  ⇒ 6,6,6,4（末段 22:00 收工）也不够：连续工作 10h 消耗 9.00 > 2h 恢复 '
          f'{2 * (REST + 0.25):.2f}')
    print('  ⇒ 6,6,6,6 把第 4 班整段设为**纯休息班**：时间上够了，但**床位**卡住（见场景 C 的 −4.50）')
    print('     根因：末段只有 20 张床，而"工作过最后一班的人"有 32 个 ⇒ 拿不到床的人 00:00 回不满')
    print('  ⇒ 因此字面判据在本规模（每班 32 人 / 20 床）下不可达；要可达必须二选一：')
    print('     ① 最后一班在岗人数 ≤ 20（等于牺牲产能）；② 允许区间内轮床（把床位当共享资源，按时长折算）')


if __name__ == '__main__':
    main()
