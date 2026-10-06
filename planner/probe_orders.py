# -*- coding: utf-8 -*-
"""probe_orders：验证订单模型（品质分布 / 慢热 / 违约 / 与实测期望对照）"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core.dataset import Dataset
from core.orders import profile, probabilities
from core.engine import Ctx, shift_output

ds = Dataset()
print('=== 0) 品质技能持有者 ===')
from core.orders import QUALITY_SKILLS
for tier, names in QUALITY_SKILLS.items():
    for nm in names:
        holders = [s.holders for s in ds.skills if s.name == nm and s.room == '贸易站']
        print(f'  [{tier}] {nm}: {holders[0] if holders else "（库中无）"}')

print('\n=== 1) 概率分布与期望赤金（对照用户实测表）===')
cases = [
    (['古米', '梓兰', '慕斯'], '常规 → 2.9', 2.9),
    (['巫恋', '古米', '梓兰'], '单α → 3.4', 3.4),
    (['柏喙', '古米', '梓兰'], '单β → 3.8', 3.8),
    (['巫恋', '龙舌兰', '柏喙'], 'α+β → 实测 3.8', 3.8),
]
for team, label, want in cases:
    p = profile(team, ds, hours=12)
    exp = sum(g * pr for (g, l, s), pr in zip([(2, 0, 0), (3, 0, 0), (4, 0, 0)], p['probs']))
    print(f'  {"+".join(team):<22} {label:<18} 分布 {tuple(round(x,3) for x in p["probs"])} '
          f'期望赤金 {exp:.2f}（目标 {want}）  品质档={p["quality"]}')

print('\n=== 2) 慢热（α 3h / β 5h 线性）===')
for h in (0, 1, 2, 3, 5):
    pr, tag, note = probabilities(['巫恋', '古米', '梓兰'], ds, hours=h)
    exp = 2 * pr[0] + 3 * pr[1] + 4 * pr[2]
    print(f'  单α 工作{h}h：期望赤金 {exp:.2f}  ({note})')

print('\n=== 3) 速率（每 1 点效率）===')
for team, note in ((['古米', '梓兰', '慕斯'], '常规'),
                   (['巫恋', '古米', '梓兰'], '单α满档'),
                   (['柏喙', '古米', '梓兰'], '单β满档'),
                   (['但书', '古米', '梓兰'], '但书违约β'),
                   (['乌有', '但书', '能天使'], '乌有+但书')):
    p = profile(team, ds, hours=12)
    print(f'  {note:<12} {p["lmd_per_eff_hour"]:.2f} 币/效率点·h | {p["gold_cost_per_eff_hour"]:.5f} 赤金/效率点·h | '
          f'{p["lmd_per_gold"]:.0f} 币/赤金 | 每单 {p["gold_per_order"]:.2f}赤金/{p["lmd_per_order"]:.0f}币/{p["hours_per_order"]:.2f}h')

ctx = Ctx(ds=ds)
ctx.staffed = ['令', '重岳', '迷迭香', '车尔尼', '爱丽丝', '絮雨', '塑心', '巫恋', '龙舌兰', '柏喙']
ctx.by_room = {'控制中枢': ['令', '重岳', '阿米娅', '凯尔希', '维什戴尔'], '制造站': ['迷迭香'],
               '宿舍': ['塑心', '车尔尼', '爱丽丝', '菲亚梅塔'], '人力办公室': ['絮雨'],
               '贸易站': ['巫恋', '龙舌兰', '柏喙']}
print('\n=== 4) 实际站点（含效率）===')
for t in (['巫恋', '龙舌兰', '柏喙'], ['乌有', '但书', '能天使'], ['黑键', '可露希尔', '吉星']):
    out, r = shift_output('贸易站', 3, 'LMD', t, ctx, 12, ds)
    print(f'  {"+".join(t):<24} eff {r["eff"]:5.1f}% → {out["lmd"]/12:6.0f} 币/h  耗金 {out["gold_cost"]/12:.2f}/h')
