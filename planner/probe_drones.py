# -*- coding: utf-8 -*-
"""probe_drones：验证无人机逐目标分配 + 品质叠加精化"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core.dataset import Dataset, load_box
from core.orders import profile, probabilities
from solve import objectives as OBJ
from solve import drones as DR
from solve.joint import joint_solve

ds = Dataset(); box = load_box()

print('=== 1) 品质叠加：精确复现实测分布 ===')
cases = [(['古米', '梓兰', '慕斯'], '常规', (0.30, 0.50, 0.20), 2.90),
         (['巫恋', '古米', '梓兰'], 'α×1', (0.15, 0.30, 0.55), 3.40),
         (['巫恋', '贝娜', '古米'], 'α×2', (0.13, 0.22, 0.65), 3.52),
         (['巫恋', '龙舌兰', '柏喙'], 'α+β', (0.05, 0.10, 0.85), 3.80),
         (['柏喙', '古米', '梓兰'], 'β×1', (0.05, 0.10, 0.85), 3.80)]
for team, label, want, exp in cases:
    p = profile(team, ds, 12)
    got = p['probs']
    eg = 2 * got[0] + 3 * got[1] + 4 * got[2]
    ok = all(abs(a - b) < 0.005 for a, b in zip(got, want))
    print(f'  {label:<6} {"+".join(team):<22} 分布 {tuple(round(x,3) for x in got)} '
          f'期望 {eg:.2f}（标注 {exp}）{"✔" if ok else "✘"}')

print('\n=== 2) 无人机：每架收益排序（按目标）===')
cfg = {'制造站': [('Pure Gold', 3), ('Pure Gold', 3), ('Originium Shard', 3)],
       '贸易站': [('LMD', 3), ('LMD', 3), ('Orundum', 3)],
       '发电站': [(None, 3)] * 3}
for objname in ('yu', 'lmd|consume|none|none'):
    props = OBJ.build(*objname.split('|')) if '|' in objname else OBJ.build(objname)
    r = joint_solve(cfg, props, ds, box, width=8, topk=4, rounds=1, local_search=False, verbose=False)
    print(f'  ---- 目标 {props["name"]} ----')
    rows = DR.rank(r['assign'], r['ctx'], ds, props, r['kpi'], verbose=True)
    targets, detail = DR.allocate(r['assign'], r['ctx'], ds, props, r['kpi'])
    print(f'     影子价 {detail["shadow"]}')
    print(f'     投放：' + ' | '.join(f"{t['label']}({t['maa_room']}#{t['index']})" for t in targets[:6]))
    k2 = DR.apply_to_kpi(r['kpi'], targets, r['assign'], r['ctx'], ds, props)
    print(f'     无人机收益 {k2.get("drone_gain")}')
    print(f'     KPI：玉 {k2.get("yu",0):.0f}  币 {k2.get("lmd",0):,.0f}  赤金净 {k2.get("gold_net",0):+.2f}  '
          f'碎片净 {k2.get("shard_net",0):+.2f}  无人机 {k2.get("drones",0):.0f}/天')
