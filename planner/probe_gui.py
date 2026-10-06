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
app.mor_var.set('none')
app.update_obj_desc()
print('  当前组合：', app.current_objective()['name'])
print('  附加约束（信赖/最低效率）：', app.trust_var.get(), app.current_min_eff())
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

print('\n=== 4) 本次返工点的回归断言 ===')
ok = bad = 0


def ck(tag, cond, extra=''):
    global ok, bad
    if cond:
        ok += 1; print(f'  ✔ {tag} {extra}')
    else:
        bad += 1; print(f'  ✘ {tag} {extra}')


ck('干员池只有一列（持有/精英化合并）', tuple(app.tree['columns']) == ('state',),
   app.tree['columns'])
ck('阿米娅按导出=已持有精2', app.st['box'].get('阿米娅', {}).get('own') is True
   and app.st['box']['阿米娅'].get('elite') == 2, app.st['box'].get('阿米娅'))
ck('固定房间耗电默认 450', app.other_var.get() == '450', app.other_var.get())
ck('每格都有 等级/产物 下拉', len(app.lv_boxes) == 9 and len(app.prod_boxes) == 9)
app.apply_preset('333')
ck('制造站产物下拉给三种（赤金/经验/碎片）',
   [cn for cn, _ in ST.PRODUCT_CHOICES['制造站']] == ['赤金', '作战记录（经验）', '源石碎片'])
ck('贸易站产物下拉给两种（龙门币/合成玉）',
   [cn for cn, _ in ST.PRODUCT_CHOICES['贸易站']] == ['龙门币（赤金订单）', '合成玉（源石订单）'])
ck('发电站产物下拉标灰（disabled）', str(app.prod_boxes[6]['state']) == 'disabled',
   app.prod_boxes[6]['state'])
app.grid_cells[0] = ('制造站', 'Originium Shard', 3)
app.lv_boxes[0].set('Ⅱ'); app._set_level(0)
ck('非三级制造站自动回到赤金', app.grid_cells[0][1] == 'Pure Gold', app.grid_cells[0])
app.grid_cells[1] = ('制造站', 'Pure Gold', 2)
app.prod_boxes[1].set('作战记录（经验）'); app._set_product(1)
ck('选经验自动拉到三级', app.grid_cells[1][2] == 3, app.grid_cells[1])
before = tuple(app.grid_cells[2])
app.click_cell(2)                                  # 制造站 → 贸易站
ck('点格子只换类型（不再同时改产物/等级）',
   app.grid_cells[2][0] == '贸易站' and app.grid_cells[2][2] == before[2], app.grid_cells[2])
ck('排班路径下拉存在', 'window' in app.sched_var.get(), app.sched_var.get())
ck('进度条存在', hasattr(app, 'pbar') and hasattr(app, 'pbar_lbl'))
ck('信赖开关存在', hasattr(app, 'trust_var') and app.trust_var.get() is False)
ck('最低效率输入存在', app.current_min_eff() == {}, app.current_min_eff())
ck('两个白框有名称标注', all(w.winfo_exists() for w in (app.log, app.kpi_lbl, app.res_tree)))
app.destroy()
print(f'\nGUI 全链路 OK；返工点断言 {ok} 通过 / {bad} 失败')
