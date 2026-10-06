# -*- coding: utf-8 -*-
"""probe_joint：验证目标驱动求解（不同目标 → 不同排班），并检查赤金收支"""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core.dataset import Dataset, load_box
from solve.joint import joint_solve
from solve import objectives

ds = Dataset(); box = load_box()
LAYOUTS = {
    '333': {'制造站': [('Pure Gold', 3)] * 2 + [('Originium Shard', 3)],
            '贸易站': [('LMD', 3)] * 2 + [('Orundum', 3)],
            '发电站': [(None, 3)] * 3},
    '243': {'制造站': [('Pure Gold', 3)] * 3 + [('Originium Shard', 3)],
            '贸易站': [('LMD', 3)] * 2,
            '发电站': [(None, 3)] * 2},
    '153': {'制造站': [('Pure Gold', 3)] * 3 + [('Originium Shard', 3)] + [('Battle Record', 3)],
            '贸易站': [('LMD', 3)],
            '发电站': [(None, 3)] * 3},
    '252': {'制造站': [('Pure Gold', 3)] * 4 + [('Originium Shard', 3)],
            '贸易站': [('LMD', 3)] * 2,
            '发电站': [(None, 3)] * 2},
}
print('可选目标：')
for k, v in objectives.OBJECTIVES.items():
    print(f'  {k:<16} {v["name"]}')

for obj in ('lmd_gold_bal', 'gold_burn', 'yu_ge_trade', 'exp_max'):
    t0 = time.time()
    r = joint_solve(LAYOUTS['333'], obj, ds, box, width=12, topk=6, rounds=1, local_search=False)
    k = r['kpi']
    print(f'\n=== 目标 {obj}（{objectives.OBJECTIVES[obj]["name"]}）  {time.time()-t0:.0f}s ===')
    print(f'  每班汇总：龙门币 {k.get("lmd",0):,.0f}  赤金产 {k.get("gold",0):.2f} 耗 {k.get("gold_cost",0):.2f} '
          f'净 {k["gold_net"]:+.2f}  碎片 {k.get("shard",0):.2f} 耗 {k.get("shard_cost",0):.2f}  '
          f'玉 {k.get("yu",0):.0f}  经验 {k.get("exp",0):,.0f}  无人机 {k.get("drones",0):.0f}')
    for key in sorted(r['assign']):
        product, level, team = r['assign'][key]
        print(f'    {key[0]}#{key[1]+1}-{key[2]} {str(product or ""):<16} {"+".join(team)}')
