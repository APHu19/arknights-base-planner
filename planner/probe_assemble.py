# -*- coding: utf-8 -*-
"""probe_assemble：验证联合装配（333 布局：3 制造 / 3 贸易 / 3 发电）"""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core.dataset import Dataset, load_box
from solve.assemble import assemble_simple, summarize

ds = Dataset(); box = load_box()
cfg = {
    '制造站': [('Pure Gold', 3), ('Pure Gold', 3), ('Originium Shard', 3)],
    '贸易站': [('LMD', 3), ('LMD', 3), ('Orundum', 3)],
    '发电站': [(None, 3), (None, 3), (None, 3)],
}
t0 = time.time()
assign, report, ctx, fixed = assemble_simple(cfg, ds, box, width=18, hours=12)
k, lines = summarize(assign, report, ctx, ds, fixed, hours=12)
print(f'装配耗时 {time.time()-t0:.1f}s\n')
print('=== 装配结果（每实例 A/B 两队）===')
for room, d in sorted(assign.items()):
    for (i, grp), (product, level, team) in sorted(d.items()):
        rep = report[(room, i, grp)]
        print(f'  {room}#{i+1}-{grp} {str(product or ""):<16} {"+".join(team):<30} eff {rep["eff"]:6.1f}%')
print('\n=== 每班产出汇总（A/B 折半）===')
for kk, vv in sorted(k.items()):
    print(f'  {kk:<12}{vv:,.2f} /班（12h）  ≈ {vv*2:,.0f} /天')
print('\n=== 体系资源（不动点后）===')
for kk in ('感知信息', '思维链环', '无声共鸣', '人间烟火', '赤金生产线', '外势', '实地'):
    print(f'  {kk}: {ctx.base_resources().get(kk)}')
