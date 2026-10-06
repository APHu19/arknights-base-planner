# -*- coding: utf-8 -*-
"""probe_obj2：验证组合式目标 + 逐格电力（含 252）"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gui import state as ST
from solve import objectives as OBJ
from solve.solver import check_power, LAYOUTS

print('=== 1) 组合式目标：任意组合都能表达 ===')
combos = [
    ('lmd', 'no_deficit', 'none', 'none'),
    ('lmd', 'consume', 'none', 'none'),          # 存了很多赤金 → 烧
    ('yu', 'none', 'consume', 'none'),           # 存了很多碎片 → 烧着搓玉
    ('yu', 'none', 'no_deficit', 'none'),        # 边搓边产碎片
    ('balanced', 'produce', 'produce', 'none'),  # 囤金+囤碎片
    ('lmd', 'balance', 'balance', '16'),         # 双平衡 + 心情底线
    ('exp', 'no_deficit', 'none', 'none'),
]
for m, g, s, mo in combos:
    o = OBJ.build(m, g, s, mo)
    w = {k: round(v, 2) for k, v in o['w'].items() if v}
    print(f'  {m}|{g}|{s}|{mo}')
    print(f'      名称：{o["name"]}')
    print(f'      权重：{w}　约束：{o["cons"]}')

print('\n=== 2) 逐格电力（按每个房间实例的等级）===')
for name, cfg in LAYOUTS.items():
    supply, consume, net = check_power(cfg)
    lvs = {r: [lv for _, lv in v] for r, v in cfg.items() if v and v[0][1]}
    print(f'  {name:<8} 供 {supply} / 耗 {consume:.0f} / 净 {net:+.0f}  {"✔" if net >= 0 else "✘ 电力不足"}'
          f'   等级 {lvs}')
grid = ST.LAYOUT_PRESETS['252(部分Lv2)']
print(f'  252(部分Lv2) 走 GUI 口径（固定房间 190）：{ST.power(grid)}')
print(f'  252(部分Lv2) 全 Lv3 会怎样：{ST.power([(r, p, 3) for r, p, lv in grid])}')
print(f'  333 走 GUI 口径：{ST.power(ST.LAYOUT_PRESETS["333"])}')
print(f'  333 用旧口径 450：{ST.power(ST.LAYOUT_PRESETS["333"], 450)}')

print('\n=== 3) 老预设仍可用（兼容）===')
for k in ('lmd_gold_bal', 'yu_ge_trade', 'gold_burn', 'burn_both', 'shard_max'):
    o = OBJ.get(k)
    print(f'  {k:<14} → {o["name"]}　约束 {o["cons"]}')
o = OBJ.get('lmd|consume|consume|none')
print(f'  组合串解析 → {o["name"]}')
