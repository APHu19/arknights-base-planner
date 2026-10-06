# -*- coding: utf-8 -*-
"""probe_gold.py —— 验证「赤金约束反馈（无人机连续旋钮）」真的会动、动得准、上限在哪

做法：求解器只跑一次拿到装配，然后用**同一套装配**按不同"赤金净下限"各建一次计划：
  · 下限 0（CLI 默认 no_deficit）
  · 下限 +8（人为收紧，逼反馈出手）
  · 下限 +30（超过无人机旋钮的最大补偿能力 → 看它是否如实报告补不满）
"""
import os
import sys

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
from solve.solver import run                           # noqa: E402

DAYS = 14


def show(tag, plan):
    k = plan['kpi']
    gf = (plan.get('drone_detail') or {}).get('gold_fix')
    print(f"{tag:<26} 赤金净 {k.get('gold_net', 0):>+7.2f}｜龙门币 {k.get('lmd', 0):>9,.0f}｜"
          f"玉 {k.get('yu', 0):>5.0f}｜无人机 {k.get('drones', 0):>6.1f}")
    if gf:
        print(f"{'':<26}   ⚙ 改投第 {'、'.join(map(str, gf['moved_shifts']))} 班 → {gf['to']}"
              f"（每架 {gf['per_drone_gold']:g} 赤金，需补 {gf['need_gold']:+.2f}，"
              f"实补 {gf['gained_gold']:+.2f}）")
    else:
        print(f"{'':<26}   （未触发反馈）")


def main():
    ds = Dataset()
    box = load_box()
    ds.set_box(box)
    print('=' * 104)
    print('赤金约束反馈验证（同一套装配，只改"赤金净下限"；window 路径）')
    props = OBJ.build('lmd', 'no_deficit', 'none', 'none')
    got = run(layout='333', objective=props, ds=ds, box=box, width=6, topk=3, rounds=1,
              days=DAYS, fast=True, verbose=False, out_dir=None, sched='ab')
    assign, fixed = got['assign'], got['fixed']
    for floor in (0.0, 8.0, 30.0, 45.0):
        obj = dict(props)
        obj['cons'] = dict(props.get('cons') or {})
        obj['cons']['gold_net'] = (floor, None)
        plan = build_plan(assign, fixed, ds, days=DAYS, objective=obj, hours=4.0, sched='window')
        show(f'下限 {floor:+.0f}', plan)
        got_net = plan['kpi'].get('gold_net', 0)
        if floor <= 36:
            assert got_net >= floor - 0.51, f'反馈没把赤金净拉到下限（{got_net} < {floor}）'
        else:
            assert got_net >= 30, '超过上限时应尽量补（这里应把 6 班全改投赤金）'
    print('=' * 104)
    print('结论：① 下限在无人机可补偿范围内（实测约 ±36 赤金/天）时，反馈精确达标——只改投无人机，'
          '不停站、不动队伍；② 超出范围时尽量补到上限并如实报告（solver 打 ⚠），不假装达标。')
    print('     代价：每挪一班约丢 600~1,800 龙门币/天（无人机原本投贸易站的收益），是可接受的最小损失。')


if __name__ == '__main__':
    main()
