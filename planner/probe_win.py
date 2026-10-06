# -*- coding: utf-8 -*-
"""probe_win.py —— window vs ab 苹果对苹果对比（**同一套装配**，只换排班路径）

为什么要这么比：`--sched window` 会改变"谁在哪个区间上班"，KPI 必然与 ab 不同；
但如果直接重跑求解器，变量太多（装配本身可能变）→ 分不清差异来自"排班"还是"装配"。
本探针只求解一次，然后用同一份 assign/fixed 分别 `build_plan(sched='ab')` 与 `(sched='window')`，
逐项打印 KPI、无人机投放、以及每间贸易站的产物与逐班队伍。
"""
import os
import sys
import collections

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

from core.dataset import Dataset, load_box            # noqa: E402
from solve import objectives as OBJ                    # noqa: E402
from solve.plan import build_plan                      # noqa: E402
from solve.solver import run, LAYOUTS                  # noqa: E402

DAYS = 14


def kpi_line(tag, kpi):
    return (f"{tag:<8} 玉 {kpi.get('yu', 0):>7.0f}｜币 {kpi.get('lmd', 0):>9,.0f}｜"
            f"赤金净 {kpi.get('gold_net', 0):>+6.2f}｜碎片净 {kpi.get('shard_net', 0):>+6.2f}｜"
            f"线索 {kpi.get('clue', 0):.2f}｜最低心情 {kpi.get('min_morale', 0):>5.1f}"
            f"（{kpi.get('min_who', '')}）｜{DAYS} 天内 <10 人数 "
            f"{sum(1 for v in kpi['lows'].values() if v < 10)}")


def instances(shifts, room):
    """(产物, 等级) → 逐班队伍"""
    seq = []
    for s in shifts:
        for (r, p, lv, ops) in s['rooms']:
            if r == room:
                seq.append((p, lv, tuple(ops)))
    return seq


def main():
    ds = Dataset()
    box = load_box()
    ds.set_box(box)
    props = OBJ.build('lmd', 'no_deficit', 'none', 'none')
    print('=' * 118)
    print('window vs ab —— 同一套装配，只换排班路径（求解器只跑一次）')
    got = run(layout='333', objective=props, ds=ds, box=box, width=6, topk=3, rounds=1,
              days=DAYS, fast=True, verbose=False, out_dir=None, sched='ab')
    assign, fixed = got['assign'], got['fixed']
    print(kpi_line('ab', got['kpi']))
    print('        ab 心情：', got['plan']['daycheck'] is None and '—' or '（daycheck 见 run 输出）')
    print('        ab 无人机：', {i + 1: (s.get('drones') or {}).get('index') for i, s in
                                enumerate(got['plan']['shifts'])})
    for tag in ('ab', 'window'):
        print('-' * 118)
        plan = build_plan(assign, fixed, ds, days=DAYS, objective=props, hours=4.0, sched=tag)
        print(kpi_line(tag, plan['kpi']))
        print(f"        无人机逐班标签：{[(s.get('drones') or {}).get('index') for s in plan['shifts']]}")
        print(f"        无人机投放明细：{plan.get('drone_detail')}")
        if plan.get('daycheck'):
            dc = plan['daycheck']
            print(f"        判据A：{'✔' if dc['steady_ok'] else '✘'} 稳态最低 "
                  f"{min(dc['steady_lows'].values()):.2f}｜排班无缺口：{plan['window_result'].get('ok')}"
                  f"（在岗 {plan['window_result'].get('onduty')} 人/班，在册 {plan['window_result'].get('roster')} 人）")
        for room in ('贸易站', '制造站'):
            seq = instances(plan['shifts'], room)
            print(f"        {room} 逐班：")
            for k, (p, lv, ops) in enumerate(seq, 1):
                print(f"          第{k}班 [{p}] {'+'.join(ops)}")
        # 每间贸易站累计产出（按班次汇总，判断是不是"产物混用"）
        cnt = collections.Counter()
        for s in plan['shifts']:
            for (r, p, lv, ops) in s['rooms']:
                if r == '贸易站':
                    cnt[p] += 1
        print(f"        贸易站产物计数（按班）：{dict(cnt)}")
    print('=' * 118)


if __name__ == '__main__':
    main()
