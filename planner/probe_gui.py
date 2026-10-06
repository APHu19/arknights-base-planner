# -*- coding: utf-8 -*-
"""probe_gui：无交互验证 GUI 的三条入口与求解链路"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:                                    # GBK 控制台会把 ↔ / ✔ 之类字符打崩
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

from gui import state as ST

print('=== 1) 干员池三条入口 ===')
box = ST.default_box()
print(f'  默认（MAA 导出）：{len(box)} 名，持有 {len(ST.owned_list(box))} 名')
box2 = ST.parse_box_text('能天使 精2\n德克萨斯,1\n黑键\n', base={})
print(f'  文本粘贴解析：{box2}')
j = json.dumps([{'name': '水月', 'own': 1, 'elite': 2}])
box3 = ST.parse_box_text(j, base={})
print(f'  JSON 片段解析：{box3}')

print('\n=== 2) 九宫格 ↔ cfg 与电力 ===')
for name, grid in ST.LAYOUT_PRESETS.items():
    cfg = ST.grid_to_cfg(grid)
    s, c, n = ST.power(grid)
    print(f'  {name:<12} 房间 {dict((k, len(v)) for k, v in cfg.items())} → 电力 供 {s}/耗 {c:.0f}/净 {n:+.0f}')
grid = ST.LAYOUT_PRESETS['333']
print(f'  往返一致：{ST.cfg_to_grid(ST.grid_to_cfg(grid, 3)) == [tuple(x) for x in grid]}')

print('\n=== 3) GUI 求解链路（直接调用 worker，不开线程）===')
import tkinter as tk
from gui.app import App
app = App()
app.update()
app.main_var.set('yu'); app.gold_var.set('none'); app.shard_var.set('ge_trade')
app.mor_var.set('none'); app.ge_var.set(False)
app.update_obj_desc()
print('  当前组合：', app.current_objective()['name'])
app.w_var.set('8'); app.k_var.set('4'); app.r_var.set('1'); app.d_var.set('14')
app.fast_var.set(True)
cfg = ST.grid_to_cfg(app.grid_cells, 3)
print(f'  当前界面布局 → {dict((k, len(v)) for k, v in cfg.items())}')
app._solve_worker(cfg)
app.update()
r = app.result
print(f'  求解结果：玉 {r["kpi"].get("yu",0):.0f}/天 龙门币 {r["kpi"].get("lmd",0):,.0f}/天 '
      f'最低心情 {r["kpi"]["min_morale"]:.1f} 协议 {r["issues"] or "通过 ✔"}')
rows = app.res_tree.get_children()
print(f'  结果表渲染：{len(rows)} 个班次节点，示例 = '
      f'{app.res_tree.item(rows[0], "text")} / {app.res_tree.item(app.res_tree.get_children(rows[0])[0], "text")}')
app.destroy()
print('\nGUI 全链路 OK')
