# -*- coding: utf-8 -*-
"""app.py —— Tkinter 可视化界面（四页）

① 干员池：导入 MAA JSON / 粘贴文本 / 搜索点选（无·精0·精1·精2）+ 导出
② 基建配置：九宫格（制造=橙黄 / 贸易=淡蓝 / 发电=荧光绿，罗马数字等级，产物选择）+ 电力条 + 布局预设
③ 班次与目标：班次增删（开始时间自动、结束时间自动生成）+ 目标选择 + 寝室模式 + 菲亚梅塔开关
④ 求解与结果：后台求解（不卡界面）+ 进度日志 + KPI 与六班表 + 导出 MAA

运行：python planner\\gui\\app.py            （--selftest 仅建界面后退出，用于自检）
"""
import os, sys, json, queue, threading, time, traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from gui import state as ST

PLANNER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ELITE_CN = {0: '无', 1: '精0', 2: '精1', 3: '精2'}


class ToolTip:
    """鼠标悬停显示说明（用于每个选项旁的 ? 号）"""

    def __init__(self, widget, text, delay=350):
        self.widget, self.text, self.delay = widget, text, delay
        self.tip = None
        self.job = None
        widget.bind('<Enter>', self._enter, add='+')
        widget.bind('<Leave>', self._leave, add='+')
        widget.bind('<ButtonPress>', self._leave, add='+')

    def _enter(self, _ev=None):
        self._cancel()
        self.job = self.widget.after(self.delay, self._show)

    def _leave(self, _ev=None):
        self._cancel()
        if self.tip:
            self.tip.destroy(); self.tip = None

    def _cancel(self):
        if self.job:
            try: self.widget.after_cancel(self.job)
            except Exception: pass
            self.job = None

    def _show(self):
        if self.tip or not self.text:
            return
        try:
            x = self.widget.winfo_rootx() + 18
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        except Exception:
            return
        self.tip = tk.Toplevel(self.widget)
        self.tip.wm_overrideredirect(True)
        self.tip.wm_geometry(f'+{x}+{y}')
        tk.Label(self.tip, text=self.text, justify='left', background='#ffffe0',
                 relief='solid', borderwidth=1, wraplength=340,
                 font=('Microsoft YaHei', 9)).pack(ipadx=4, ipady=2)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('基建排班自主枚举器 · planner')
        self.geometry('1180x760')
        self.st = ST.initial_state()
        self.grid_cells = list(self.st['grid'])
        self.log_q = queue.Queue()
        self.result = None
        self.nb = ttk.Notebook(self)
        self.nb.pack(fill='both', expand=True)
        self._tab_box()
        self._tab_layout()
        self._tab_shift()
        self._tab_run()
        self.protocol('WM_DELETE_WINDOW', self.on_close)
        self.after(200, self._drain_log)

    # ================================================== ① 干员池
    def _tab_box(self):
        f = ttk.Frame(self.nb); self.nb.add(f, text='① 干员池')
        top = ttk.Frame(f); top.pack(fill='x', padx=8, pady=6)
        ttk.Button(top, text='导入 MAA JSON…', command=self.import_json).pack(side='left')
        ttk.Button(top, text='按本机 MAA 导出修正', command=self.resync_box).pack(side='left', padx=6)
        ttk.Button(top, text='把剪贴板/文本框内容解析', command=self.parse_text).pack(side='left', padx=6)
        ttk.Button(top, text='导出干员池…', command=self.export_box).pack(side='left')
        ttk.Label(top, text='搜索：').pack(side='left', padx=(16, 2))
        self.q_var = tk.StringVar()
        e = ttk.Entry(top, textvariable=self.q_var, width=16); e.pack(side='left')
        e.bind('<KeyRelease>', lambda ev: self.refresh_ops())
        self.show_unowned = tk.BooleanVar(value=False)
        ttk.Checkbutton(top, text='显示未持有', variable=self.show_unowned,
                        command=self.refresh_ops).pack(side='left', padx=8)

        bar = ttk.Frame(f); bar.pack(fill='x', padx=8)
        ttk.Button(bar, text='切换持有（选中行）', command=self.toggle_own).pack(side='left')
        ttk.Button(bar, text='精英化 +1（选中行）', command=self.cycle_elite).pack(side='left', padx=4)
        ttk.Button(bar, text='精英化 精0', command=lambda: self.set_elite(0)).pack(side='left')
        ttk.Button(bar, text='精1', command=lambda: self.set_elite(1)).pack(side='left', padx=2)
        ttk.Button(bar, text='精2', command=lambda: self.set_elite(2)).pack(side='left')
        ttk.Label(bar, text='　单击=切换持有　双击=精英化+1（作用于**点到的那一行**）').pack(side='left')

        mid = ttk.Panedwindow(f, orient='horizontal'); mid.pack(fill='both', expand=True, padx=8, pady=4)
        left = ttk.Frame(mid); right = ttk.Frame(mid)
        mid.add(left, weight=3); mid.add(right, weight=2)

        self.tree = ttk.Treeview(left, columns=('state',), show='tree headings', height=20)
        self.tree.heading('#0', text='干员'); self.tree.heading('state', text='持有 / 精英化')
        self.tree.column('#0', width=200); self.tree.column('state', width=120, anchor='center')
        self.tree.pack(fill='both', expand=True, side='left')
        sb = ttk.Scrollbar(left, orient='vertical', command=self.tree.yview); sb.pack(side='right', fill='y')
        self.tree.configure(yscrollcommand=sb.set)
        # 用**点到的那一行**（identify_row）而不是刷新后的 selection —— 之前刷新会丢选中，
        # 于是"点 A 行改到了 B 行"，把 阿米娅 之类误改成未持有（实测踩过）
        self.tree.bind('<Button-1>', self._on_click, add='+')
        self.tree.bind('<Double-1>', self._on_double, add='+')
        self.tree.bind('<space>', lambda ev: self.toggle_own())

        ttk.Label(right, text='导入区：可直接粘贴 ① MAA 导出的 JSON 文件**路径**'
                              '（如 C:\\...\\Arknights_OperBox_Export.json）；'
                              '② MAA JSON 内容；③ 本程序导出的干员池 JSON；④ 每行一个名字（可带 精0/精1/精2）'
                  , wraplength=380, justify='left').pack(anchor='w')
        self.paste = tk.Text(right, height=18)
        self.paste.pack(fill='both', expand=True, pady=4)
        self.box_stat = ttk.Label(f, text='')
        self.box_stat.pack(anchor='w', padx=8, pady=(0, 6))
        self.refresh_ops()

    def _row_name(self, ev):
        """事件坐标 → 行名（点到哪行就是哪行；空白处返回 None）"""
        iid = self.tree.identify_row(ev.y)
        return self.tree.item(iid, 'text') if iid else None

    def _on_click(self, ev):
        n = self._row_name(ev)
        if n:
            self._keep = n
        return None                      # 不 return 'break'：让 Treeview 自己处理选中

    def _on_double(self, ev):
        n = self._row_name(ev)
        if n:
            self.cycle_elite(n)
        return 'break'

    def refresh_ops(self):
        box = self.st['box']
        q = self.q_var.get().strip()
        keep = getattr(self, '_keep', None)
        self.tree.delete(*self.tree.get_children())
        iid_keep = None
        for name in sorted(box):
            v = box[name]
            if not self.show_unowned.get() and not v.get('own'):
                continue
            if q and q not in name:
                continue
            state = ('✔ ' + ST.ELITE_CN.get(int(v.get('elite', 0)), '精0')) if v.get('own') else '✘ 未持有'
            iid = self.tree.insert('', 'end', text=name, values=(state,))
            if name == keep:
                iid_keep = iid
        if iid_keep:                     # **保住选中**：刷新前后同一行仍是选中态
            self.tree.selection_set(iid_keep)
            self.tree.focus(iid_keep)
        n_own = len(ST.owned_list(box))
        n_ref = 0
        try:
            ref = ST.import_maa_json(ST.maa_export_path())
            n_ref = sum(1 for n, v in ref.items()
                        if n in box and (bool(box[n].get('own')) != bool(v['own'])
                                         or int(box[n].get('elite', 0)) != v['elite']))
        except Exception:
            pass
        extra = (f'　⚠ 与 MAA 导出有 {n_ref} 处不一致 → 点"按本机 MAA 导出修正"'
                 if n_ref else '　（与 MAA 导出一致）')
        self.box_stat.config(text=f'共 {len(box)} 名；持有 {n_own} 名{extra}')

    def _sel_name(self):
        sel = self.tree.selection()
        if sel:
            return self.tree.item(sel[0], 'text')
        return getattr(self, '_keep', None)

    def set_elite(self, lv):
        n = self._sel_name()
        if not n:
            return
        self.st['box'][n] = ST._entry(n, True, lv)
        self._keep = n
        self.refresh_ops()

    def cycle_elite(self, name=None):
        n = name or self._sel_name()
        if not n: return
        v = self.st['box'].setdefault(n, ST._entry(n))
        v['own'] = True
        v['elite'] = (int(v.get('elite', 0)) + 1) % (ST.MAX_ELITE + 1)
        self._keep = n
        self.refresh_ops()

    def toggle_own(self, name=None):
        n = name or self._sel_name()
        if not n: return
        v = self.st['box'].setdefault(n, ST._entry(n, own=False))
        v['own'] = not v.get('own')
        self._keep = n
        self.refresh_ops()

    def resync_box(self):
        try:
            box, changed, p = ST.sync_box_from_maa(self.st['box'])
        except Exception as e:
            messagebox.showerror('修正失败', str(e))
            return
        self.st['box'] = box
        self.refresh_ops()
        messagebox.showinfo('已按 MAA 导出修正',
                            f'来源：{p}\n修正/补齐 {changed} 名干员的持有与精英化')

    def import_json(self):
        p = filedialog.askopenfilename(filetypes=[('JSON', '*.json'), ('全部', '*.*')])
        if not p: return
        try:
            box = ST.import_maa_json(p)
            self.st['box'].update(box)
            self.refresh_ops()
            messagebox.showinfo('导入成功', f'导入 {len(box)} 名干员（来源：{p}）')
        except Exception as e:
            messagebox.showerror('导入失败', str(e))

    def parse_text(self):
        txt = self.paste.get('1.0', 'end')
        before = dict(self.st['box'])
        box = ST.parse_box_text(txt, self.st['box'])
        self.st['box'] = box
        self.refresh_ops()
        if box == before:
            messagebox.showwarning('没有变化',
                                   '这段内容没有带来任何改动。\n'
                                   '提示：可以直接粘贴 MAA 导出的 JSON **文件路径**，'
                                   '或点上面的"按本机 MAA 导出修正"。')
        else:
            messagebox.showinfo('解析完成', f'当前干员池共 {len(box)} 名；'
                                          f'持有 {len(ST.owned_list(box))} 名')

    def export_box(self):
        p = filedialog.asksaveasfilename(defaultextension='.json', initialfile='planner_box.json')
        if not p: return
        json.dump(self.st['box'], open(p, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        messagebox.showinfo('已导出', p)

    # ================================================== ② 基建配置
    def _tab_layout(self):
        f = ttk.Frame(self.nb); self.nb.add(f, text='② 基建配置')
        top = ttk.Frame(f); top.pack(fill='x', padx=8, pady=6)
        ttk.Label(top, text='布局预设：').pack(side='left')
        for name in ST.LAYOUT_PRESETS:                    # 不固定宽度：中文名不再被截断
            ttk.Button(top, text=name, command=lambda n=name: self.apply_preset(n)).pack(
                side='left', padx=3)
        ttk.Label(top, text='　（点房间格 = 换房间类型；右侧两个下拉 = 该格等级 / 产物）'
                  ).pack(side='left', padx=6)

        wrap = ttk.Frame(f); wrap.pack(fill='both', expand=True, padx=8, pady=6)
        g = ttk.Frame(wrap); g.pack(anchor='w')
        self.cells, self.lv_boxes, self.prod_boxes = [], [], []
        for i in range(9):
            r, c = i // 3, i % 3
            cell = ttk.Frame(g); cell.grid(row=r, column=c * 2, padx=(0, 2), pady=6)
            b = tk.Button(cell, width=14, height=5, relief='ridge', font=('Microsoft YaHei', 10),
                          command=lambda i=i: self.click_cell(i))
            b.pack()
            ctrl = ttk.Frame(g); ctrl.grid(row=r, column=c * 2 + 1, padx=(0, 12), pady=6, sticky='n')
            lv = ttk.Combobox(ctrl, width=4, state='readonly', values=['Ⅰ', 'Ⅱ', 'Ⅲ'])
            lv.pack(pady=(6, 2)); lv.bind('<<ComboboxSelected>>', lambda ev, i=i: self._set_level(i))
            pd = ttk.Combobox(ctrl, width=13, state='readonly')
            pd.pack(); pd.bind('<<ComboboxSelected>>', lambda ev, i=i: self._set_product(i))
            self.cells.append(b); self.lv_boxes.append(lv); self.prod_boxes.append(pd)

        bottom = ttk.Frame(f); bottom.pack(fill='x', padx=8, pady=8)
        self.power_lbl = ttk.Label(bottom, text='', font=('Microsoft YaHei', 11, 'bold'))
        self.power_lbl.pack(anchor='w')
        rowp = ttk.Frame(bottom); rowp.pack(anchor='w', pady=3)
        ttk.Label(rowp, text='固定房间合计耗电：').pack(side='left')
        self.other_var = tk.StringVar(value=str(self.st.get('other_power', 450)))
        ttk.Combobox(rowp, textvariable=self.other_var, width=22, state='readonly',
                     values=['450', '190']).pack(side='left')
        ttk.Label(bottom, text='电力规则：发电站 Ⅰ/Ⅱ/Ⅲ = 60/130/270；制造·贸易 Ⅰ/Ⅱ/Ⅲ = 10/30/60；'
                               '450 = 含 4 间宿舍（界面口径）／190 = 文档口径（宿舍不计，求解按这个算）；'
                               '非三级制造站只能产赤金（选碎片/经验会自动回到赤金）').pack(anchor='w', pady=4)
        self.render_grid()

    def apply_preset(self, name):
        self.grid_cells = [tuple(c) for c in ST.LAYOUT_PRESETS[name]]
        self.render_grid()

    def click_cell(self, i):
        """点房间格 = **只换房间类型**（等级/产物在右侧下拉里，不再一次点击做两件事）。"""
        room, prod, lv = self.grid_cells[i]
        nxt = {'制造站': '贸易站', '贸易站': '发电站', '发电站': '空', '空': '制造站'}[room]
        if nxt == '空':
            prod2 = None
        elif nxt == '发电站':
            prod2 = None
        else:
            prod2 = ST.PRODUCT_CHOICES[nxt][0][1]        # 新房间的默认产物
        self.grid_cells[i] = (nxt, prod2, int(lv or 3) if nxt != '空' else 3)
        self.render_grid()

    def _set_level(self, i):
        room, prod, _lv = self.grid_cells[i]
        lv = {'Ⅰ': 1, 'Ⅱ': 2, 'Ⅲ': 3}.get(self.lv_boxes[i].get(), 3)
        if room == '制造站' and lv < 3 and prod != 'Pure Gold':
            prod = 'Pure Gold'                           # 游戏规则：非三级制造站只能产赤金
        self.grid_cells[i] = (room, prod, lv)
        self.render_grid()

    def _set_product(self, i):
        room, _prod, lv = self.grid_cells[i]
        cn = self.prod_boxes[i].get()
        prod = ST.PRODUCT_BY_CN.get(room, {}).get(cn, None)
        if room == '制造站' and prod is not None and prod != 'Pure Gold' and int(lv) < 3:
            lv = 3                                       # 选碎片/经验 → 自动拉到三级
        self.grid_cells[i] = (room, prod, int(lv))
        self.render_grid()

    def render_grid(self):
        for i, cell in enumerate(self.grid_cells):
            room, prod, lv = cell[0], cell[1], (int(cell[2]) if len(cell) > 2 else 3)
            txt = room
            if room != '空':
                txt += f'\n{ST.ROMAN[lv]}'
                if prod: txt += f'\n{ST.PRODUCT_CN.get(prod, prod)}'
            self.cells[i].config(text=txt, bg=ST.ROOM_COLORS.get(room, '#DDDDDD'))
            # 右侧两个下拉：空/发电站 → 产物标灰不可选
            self.lv_boxes[i].set(ST.ROMAN.get(lv, 'Ⅲ'))
            self.lv_boxes[i].config(state='disabled' if room == '空' else 'readonly')
            opts = ST.PRODUCT_CHOICES.get(room, [])
            self.prod_boxes[i].config(values=[cn for cn, _ in opts])
            if opts:
                self.prod_boxes[i].config(state='readonly')
                self.prod_boxes[i].set(ST.PRODUCT_TO_CN.get(prod, opts[0][0]))
            else:
                self.prod_boxes[i].config(state='disabled')
                self.prod_boxes[i].set('—' if room != '空' else '')
        supply, consume, net = ST.power(self.grid_cells, float(self.other_var.get()))
        ok = net >= 0
        doc_net = net + (float(self.other_var.get()) - 190.0)   # 求解器按文档口径 190 计
        hint = ('' if ok else f'　（游戏内无法运转；求解仍按文档口径 190 → 净 {doc_net:+.0f}，'
                              f'可点"开始求解"确认后继续）')
        self.power_lbl.config(text=f'电力：供 {supply} ／ 耗 {consume:.0f} ／ 净 {net:+.0f}　'
                                   f'{"✔ 可正常运行" if ok else "✘ 电力不足"}{hint}',
                              foreground='#1a7f37' if ok else '#c0392b')

    # ================================================== ③ 班次与目标
    def _tab_shift(self):
        f = ttk.Frame(self.nb); self.nb.add(f, text='③ 班次与目标')
        left = ttk.Frame(f); left.pack(side='left', fill='both', expand=True, padx=8, pady=8)
        ttk.Label(left, text='班次表（由开始时间定义；结束时间 = 下一班开始 − 1 分钟，自动生成）',
                  font=('Microsoft YaHei', 10, 'bold')).pack(anchor='w')
        self.shift_lb = tk.Listbox(left, height=12, font=('Consolas', 10))
        self.shift_lb.pack(fill='both', expand=True, pady=4)
        row = ttk.Frame(left); row.pack(fill='x')
        ttk.Label(row, text='开始时间 HH:MM：').pack(side='left')
        self.new_start_var = tk.StringVar()
        ttk.Entry(row, textvariable=self.new_start_var, width=8).pack(side='left', padx=3)
        self.add_btn = ttk.Button(row, text='新建第 3 班', command=self.add_shift)
        self.add_btn.pack(side='left', padx=4)
        row2 = ttk.Frame(left); row2.pack(fill='x', pady=3)
        ttk.Button(row2, text='删除选中', command=self.del_shift).pack(side='left')
        ttk.Button(row2, text='把选中班改为上面的开始时间',
                   command=self.edit_shift).pack(side='left', padx=6)
        ttk.Button(row2, text='恢复默认 6×4h', command=self.reset_shifts).pack(side='left')
        self.shift_info = ttk.Label(left, text='', wraplength=340, foreground='#444', justify='left')
        self.shift_info.pack(anchor='w', pady=(6, 0))

        right = ttk.Frame(f); right.pack(side='left', fill='both', expand=True, padx=8, pady=8)
        ttk.Label(right, text='本次要求（四个维度任意组合）').pack(anchor='w')
        from solve import objectives as OBJ
        self.OBJ = OBJ

        def combo(label, var, table, default):
            r = ttk.Frame(right); r.pack(fill='x', pady=2)
            ttk.Label(r, text=label, width=9).pack(side='left')
            cb = ttk.Combobox(r, textvariable=var, state='readonly', width=42,
                              values=[f'{k}｜{v["name"]}' for k, v in table.items()])
            cb.pack(side='left')
            var.set(next((f'{k}｜{v["name"]}' for k, v in table.items() if k == default), ''))
            cb.bind('<<ComboboxSelected>>', lambda e: self.update_obj_desc())
            return cb

        self.main_var = tk.StringVar(); self.gold_var = tk.StringVar()
        self.shard_var = tk.StringVar(); self.mor_var = tk.StringVar()
        combo('主目标', self.main_var, OBJ.MAINS, self.st.get('main', 'lmd'))
        combo('赤金收支', self.gold_var, OBJ.GOLD_MODES, self.st.get('gold', 'no_deficit'))
        combo('碎片收支', self.shard_var, OBJ.SHARD_MODES, self.st.get('shard', 'none'))
        combo('心情底线', self.mor_var, {k: {'name': v} for k, v in
                                        (('none', '不限'), ('12', '≥12'), ('16', '≥16'), ('20', '≥20'))},
              self.st.get('morale', 'none'))
        self.trust_var = tk.BooleanVar(value=bool(self.st.get('trust', False)))
        ttk.Checkbutton(right, text='重视信赖：让更多不同干员轮到班（轮换更广，小权重）',
                        variable=self.trust_var, command=self.update_obj_desc).pack(anchor='w', pady=(6, 0))
        me = dict(self.st.get('min_eff') or {})
        row_e = ttk.Frame(right); row_e.pack(fill='x', pady=3)
        ttk.Label(row_e, text='会客室最低线索速度：').pack(side='left')
        self.meet_eff_var = tk.StringVar(value=str(me.get('会客室', 0) or 0))
        ttk.Entry(row_e, textvariable=self.meet_eff_var, width=6).pack(side='left')
        ttk.Label(row_e, text='（0 = 不限；例：230 会强制用「伊内丝+红」这类高速队）').pack(side='left')
        row_h = ttk.Frame(right); row_h.pack(fill='x', pady=3)
        ttk.Label(row_h, text='人力办公室最低效率：').pack(side='left')
        self.hire_eff_var = tk.StringVar(value=str(me.get('人力办公室', 0) or 0))
        ttk.Entry(row_h, textvariable=self.hire_eff_var, width=6).pack(side='left')
        ttk.Label(row_h, text='（0 = 不限；达不到会退回全局最优并告警，不会假装达标）').pack(side='left')
        self.obj_desc = ttk.Label(right, text='', wraplength=440, foreground='#444', justify='left')
        self.obj_desc.pack(anchor='w', pady=4)
        ttk.Separator(right).pack(fill='x', pady=8)
        ttk.Label(right, text='寝室安排').pack(anchor='w')
        self.dorm_var = tk.StringVar(value=self.st.get('dorm_mode', 'precise'))
        ttk.Radiobutton(right, text='MAA自动设置', value='auto',
                        variable=self.dorm_var).pack(anchor='w')
        ttk.Radiobutton(right, text='MAA精准设置（心情紧张时推荐；固定顺序 + 菲亚梅塔首位）',
                        value='precise', variable=self.dorm_var).pack(anchor='w')
        self.fia_var = tk.BooleanVar(value=bool(self.st.get('fiammetta', True)))
        ttk.Checkbutton(right, text='持有菲亚梅塔 → 启用恢复交换（写文件时 order=pre）',
                        variable=self.fia_var).pack(anchor='w', pady=6)
        self.update_obj_desc()
        self.render_shifts()

    # ---- 目标组合 ----
    @staticmethod
    def _key(s):
        return (s or '').split('｜')[0] or 'none'

    def current_objective(self):
        return self.OBJ.build(self._key(self.main_var.get()), self._key(self.gold_var.get()),
                              self._key(self.shard_var.get()), self._key(self.mor_var.get()),
                              trust=bool(getattr(self, 'trust_var', None)
                                         and self.trust_var.get()))

    def current_min_eff(self):
        """会客室/人力办公室最低效率要求（0 = 不限）"""
        out = {}
        for key, var in (('会客室', getattr(self, 'meet_eff_var', None)),
                         ('人力办公室', getattr(self, 'hire_eff_var', None))):
            try:
                v = float((var.get() if var else '0') or 0)
            except Exception:
                v = 0.0
            if v > 0:
                out[key] = v
        return out

    def update_obj_desc(self):
        try:
            o = self.current_objective()
            me = self.current_min_eff()
            extra = ('　最低效率：' + '、'.join(f'{k} ≥ {v:g}' for k, v in me.items())) if me else ''
            self.obj_desc.config(text='当前组合：' + o['name'] +
                                      (f"　约束：{o['cons']}" if o['cons'] else '　（无硬约束）') + extra)
        except Exception as e:
            self.obj_desc.config(text=f'组合无效：{e}')

    # ---- 班次表：由「开始时间」定义，结束时间 = 下一班开始 − 1 分钟（闭环） ----
    @staticmethod
    def _add_minutes(hhmm, minutes):
        h, m = map(int, str(hhmm).split(':'))
        t = (h * 60 + m + int(minutes)) % (24 * 60)
        return f'{t // 60:02d}:{t % 60:02d}'

    @staticmethod
    def _mins(hhmm):
        h, m = map(int, str(hhmm).split(':'))
        return h * 60 + m

    def _recalc_shifts(self):
        """结束时间 = 下一班开始 − 1 分钟；最后一班回到第一班（闭环）。"""
        sh = self.st['shifts']
        n = len(sh)
        for i, s in enumerate(sh):
            if n >= 2:
                s['end'] = self._add_minutes(sh[(i + 1) % n]['start'], -1)
            else:
                s['end'] = self._add_minutes(s['start'], 240)

    def _table(self):
        """→ (core.shiftplan 班次表 | None, 错误信息)"""
        from core import shiftplan as SP
        starts = [s['start'] for s in self.st['shifts']]
        try:
            return SP.build_table(starts), ''
        except Exception as e:
            return None, str(e)

    def render_shifts(self):
        self._recalc_shifts()
        self.shift_lb.delete(0, 'end')
        tbl, err = self._table()
        for i, s in enumerate(self.st['shifts'], 1):
            dur = (self._mins(self._add_minutes(s['end'], 1)) - self._mins(s['start'])) % 1440
            self.shift_lb.insert('end', f'第{i}班   {s["start"]} - {s["end"]}   {dur / 60:g}h')
        if hasattr(self, 'add_btn'):
            self.add_btn.config(text=f'新建第 {len(self.st["shifts"]) + 1} 班')
        if hasattr(self, 'new_start_var'):
            self.new_start_var.set(self._suggest_start())
        if hasattr(self, 'shift_info'):
            from core import shiftplan as SP
            if err:
                self.shift_info.config(text=f'⚠ {err}（求解会拒绝，请先改好）', foreground='#a00')
            else:
                self.shift_info.config(
                    text=f'{SP.summary(tbl)}\n合计 {SP.total_minutes(tbl)} 分钟（= 整天）；'
                         f'界面上结束时间按"下一班开始 − 1 分钟"显示，计算与 MAA 输出按整点连续区间。',
                    foreground='#444')

    def _suggest_start(self):
        """新建班的建议开始时间：把**最长的那一班**对半切开（最自然）。"""
        sh = sorted(self.st['shifts'], key=lambda s: self._mins(s['start']))
        if len(sh) < 2:
            return '00:00'
        best, span = None, -1
        for i, s in enumerate(sh):
            nxt = sh[(i + 1) % len(sh)]['start']
            d = (self._mins(nxt) - self._mins(s['start'])) % 1440
            if d > span:
                best, span = s['start'], d
        return self._add_minutes(best, span // 2)

    def _sort_cycle(self):
        """保持"第一班"不动，其余按顺时针顺序排（保证 MAA 的 period 连续）。"""
        sh = self.st['shifts']
        if len(sh) < 2:
            return
        anchor = self._mins(sh[0]['start'])
        rest = sorted(sh[1:], key=lambda s: (self._mins(s['start']) - anchor) % 1440)
        self.st['shifts'] = [sh[0]] + rest

    def add_shift(self):
        from core import shiftplan as SP
        txt = (self.new_start_var.get() or '').strip()
        try:
            SP.parse_hhmm(txt)
        except Exception as e:
            messagebox.showwarning('开始时间不合法', str(e))
            return
        if any(s['start'] == txt for s in self.st['shifts']):
            messagebox.showwarning('重复', f'{txt} 已经有一班了')
            return
        if len(self.st['shifts']) >= 8:
            messagebox.showwarning('班次过多', '最多 8 班')
            return
        self.st['shifts'].append({'start': txt, 'end': txt})
        self._sort_cycle()
        self.render_shifts()

    def edit_shift(self):
        from core import shiftplan as SP
        sel = self.shift_lb.curselection()
        if not sel:
            messagebox.showinfo('提示', '先在列表里选中要改的那一班')
            return
        txt = (self.new_start_var.get() or '').strip()
        try:
            SP.parse_hhmm(txt)
        except Exception as e:
            messagebox.showwarning('开始时间不合法', str(e))
            return
        i = int(sel[0])
        if any(j != i and s['start'] == txt for j, s in enumerate(self.st['shifts'])):
            messagebox.showwarning('重复', f'{txt} 已经有一班了')
            return
        self.st['shifts'][i]['start'] = txt
        if i != 0:
            self._sort_cycle()
        self.render_shifts()

    def del_shift(self):
        sel = self.shift_lb.curselection()
        if not sel:
            return
        if len(self.st['shifts']) <= 2:
            messagebox.showwarning('至少两班', '一天至少要有 2 班')
            return
        self.st['shifts'].pop(int(sel[0]))
        self.render_shifts()

    def reset_shifts(self):
        from gui.state import DEFAULT_SHIFTS
        import copy
        self.st['shifts'] = copy.deepcopy(DEFAULT_SHIFTS)
        self.render_shifts()

    # ================================================== ④ 求解与结果
    def _tab_run(self):
        f = ttk.Frame(self.nb); self.nb.add(f, text='④ 求解与结果')
        left = ttk.Frame(f); left.pack(side='left', fill='y', padx=(8, 4), pady=8)
        right = ttk.Frame(f); right.pack(side='left', fill='both', expand=True, padx=(4, 8), pady=8)
        ttk.Label(left, text='求解选项', font=('Microsoft YaHei', 11, 'bold')).pack(anchor='w')
        tips = {
            '束宽': '束搜索每层保留的候选方案数。越大越可能找到好方案，但耗时线性增加。',
            '每槽候选': '每个岗位槽位考察的候选班组数（top-k）。越大越稳，越慢。',
            '迭代轮数': '固定房间与装配交替优化的轮数。1 轮最快；2~3 轮更接近最优。',
            '复核天数': '算完之后模拟多少天来复核心情/产出（14 天是常用口径）。',
            '快速': '勾选 = 关闭 2-opt 局部搜索，速度快很多，方案略差。',
            '班次时长': '**仅在没填自定义班次时生效**：等长班次的时长（4h → 6 班）。'
                    '③ 页填了开始时间就以那张表为准。',
            '排班路径': 'window = 干员级窗口排班（判据 A：长期稳态，推荐）；'
                    'ab = 旧的"同站 A/B 整段轮换 + 恢复债寝室"（会红脸）。',
            '爆仓策略': '制造站仓储溢出时：warn 只告警 / clip 自动降效并把损失从产出里扣掉 / off 不检查。',
        }
        self.w_var = tk.StringVar(value='14')
        self.k_var = tk.StringVar(value='6')
        self.r_var = tk.StringVar(value='1')
        self.d_var = tk.StringVar(value='14')
        self.fast_var = tk.BooleanVar(value=True)
        self.hours_var = tk.StringVar(value=str(self.st.get('shift_hours', 4)))
        self.sched_var = tk.StringVar(
            value=('ab｜同站A/B整段轮换（旧）' if self.st.get('sched') == 'ab'
                   else 'window｜窗口排班（判据A，推荐）'))
        self.storage_var = tk.StringVar(
            value={'off': 'off｜不检查', 'clip': 'clip｜自动降效（剪掉超出）'}
            .get(self.st.get('storage'), 'warn｜只告警（默认）'))

        def row(label, widget_fn, tipkey, tip_extra=''):
            r = ttk.Frame(left); r.pack(fill='x', pady=3)
            ttk.Label(r, text=label, width=10, anchor='w').pack(side='left')
            w = widget_fn(r); w.pack(side='left', padx=2)
            q = ttk.Label(r, text='?', foreground='#0b6', font=('Microsoft YaHei', 10, 'bold'))
            q.pack(side='left', padx=3)
            ToolTip(q, tips.get(tipkey, '') + tip_extra)
            return w

        row('束宽', lambda p: ttk.Combobox(p, textvariable=self.w_var, width=6, state='readonly',
                                          values=['8', '10', '14', '18', '24']), '束宽')
        row('每槽候选', lambda p: ttk.Combobox(p, textvariable=self.k_var, width=6, state='readonly',
                                            values=['4', '6', '8', '10']), '每槽候选')
        row('迭代轮数', lambda p: ttk.Combobox(p, textvariable=self.r_var, width=6, state='readonly',
                                            values=['1', '2', '3']), '迭代轮数')
        row('复核天数', lambda p: ttk.Combobox(p, textvariable=self.d_var, width=6, state='readonly',
                                            values=['7', '14', '21']), '复核天数')
        row('快速', lambda p: ttk.Checkbutton(p, text='关闭局部搜索（更快）',
                                             variable=self.fast_var), '快速')
        row('班次时长', lambda p: ttk.Combobox(p, textvariable=self.hours_var, width=6, state='readonly',
                                             values=['2', '3', '4', '6', '8', '12']), '班次时长')
        row('排班路径', lambda p: ttk.Combobox(p, textvariable=self.sched_var, width=26, state='readonly',
                                             values=['window｜窗口排班（判据A，推荐）',
                                                     'ab｜同站A/B整段轮换（旧）']), '排班路径')
        row('爆仓策略', lambda p: ttk.Combobox(p, textvariable=self.storage_var, width=22, state='readonly',
                                             values=['warn｜只告警（默认）', 'clip｜自动降效（剪掉超出）',
                                                     'off｜不检查']), '爆仓策略')
        btns = ttk.Frame(left); btns.pack(fill='x', pady=(10, 4))
        self.run_btn = ttk.Button(btns, text='开始求解', command=self.start_solve, width=14)
        self.run_btn.pack(side='left')
        ttk.Button(btns, text='导出 MAA 计划…', command=self.export_maa).pack(side='left', padx=4)
        self.pbar = ttk.Progressbar(left, mode='determinate', maximum=100, length=240)
        self.pbar.pack(fill='x', pady=(6, 2))
        self.pbar_lbl = ttk.Label(left, text='就绪（未开始）', foreground='#444')
        self.pbar_lbl.pack(anchor='w')

        # —— 右侧：两个白框各自有名称与注释 ——
        ttk.Label(right, text='运行日志（求解过程 / 排班路径 / 心情判据 / 赤金反馈 / 排班缺口）',
                  font=('Microsoft YaHei', 10, 'bold')).pack(anchor='w')
        self.log = tk.Text(right, height=11, state='disabled', wrap='word')
        self.log.pack(fill='both', expand=False, pady=(2, 8))
        ttk.Label(right, text='结果概览（KPI：玉 / 龙门币 / 赤金与碎片收支 / 线索 / 心情）',
                  font=('Microsoft YaHei', 10, 'bold')).pack(anchor='w')
        self.kpi_lbl = ttk.Label(right, text='', font=('Microsoft YaHei', 11, 'bold'), justify='left')
        self.kpi_lbl.pack(anchor='w', padx=4, pady=(2, 8))
        ttk.Label(right, text='逐班安排明细（每个班次下按房间列出进驻干员）',
                  font=('Microsoft YaHei', 10, 'bold')).pack(anchor='w')
        self.res_tree = ttk.Treeview(right, columns=('detail',), show='tree headings', height=12)
        self.res_tree.heading('#0', text='房间/班次'); self.res_tree.heading('detail', text='安排')
        self.res_tree.column('#0', width=150); self.res_tree.column('detail', width=820)
        self.res_tree.pack(fill='both', expand=True, pady=(2, 4))

    def logln(self, s):
        self.log_q.put(s)

    def _drain_log(self):
        while True:
            try: s = self.log_q.get_nowait()
            except queue.Empty: break
            self.log.config(state='normal'); self.log.insert('end', s + '\n')
            self.log.see('end'); self.log.config(state='disabled')
            if s.startswith('[进度]'):
                try:
                    pct = int(s.split()[1].rstrip('%'))
                    self.pbar.config(value=max(0, min(100, pct)))
                    self.pbar_lbl.config(text=s[4:].strip())
                except Exception:
                    pass
        self.after(200, self._drain_log)

    def start_solve(self):
        cfg = ST.grid_to_cfg(self.grid_cells)
        supply, consume, net = ST.power(self.grid_cells, float(self.other_var.get()))
        if net < 0:
            doc_net = net + (float(self.other_var.get()) - 190.0)
            if not messagebox.askyesno(
                    '电力不足（界面口径）',
                    f'按界面口径：供 {supply} / 耗 {consume:.0f} / 净 {net:+.0f} ✘\n\n'
                    f'求解器按**文档口径**（固定房间 190）算，净 {doc_net:+.0f}。\n'
                    f'要按文档口径继续求解吗？（想按界面口径就必须加发电站或给制造/贸易站降级）'):
                return
            self.logln(f'[电力] 界面口径(固定房间 {self.other_var.get()}) 净 {net:+.0f}；'
                       f'求解按文档口径 190 计，净 {doc_net:+.0f}')
        self.run_btn.config(state='disabled')
        self.pbar.config(value=3); self.pbar_lbl.config(text='[进度] 3% 启动中…')
        self.result = None
        t = threading.Thread(target=self._solve_worker, args=(cfg,), daemon=True)
        t.start()

    def _solve_worker(self, cfg):
        try:
            from solve.solver import run
            o = self.current_objective()
            self._obj = o
            tbl, err = self._table()
            if err:
                self.logln('[错误] 班次表：' + err)
                self.after(10, lambda: messagebox.showwarning('班次表有误', err))
                return
            from core import shiftplan as SP
            me = self.current_min_eff()
            self.logln('[进度] 10% 开始求解（装配 → 固定房间 → 排班 → 复核）')
            self.logln(f'[求解] 布局 {sum(len(v) for v in cfg.values())} 间，目标 {o["name"]}，'
                       f'束宽 {self.w_var.get()}，快速={self.fast_var.get()}')
            self.logln(f'[班次] {SP.summary(tbl)}')
            if me:
                self.logln('[约束] 最低效率：' + '、'.join(f'{k} ≥ {v:g}' for k, v in me.items()))
            self.logln('[进度] 30% 正在枚举装配与固定房间…')
            r = run(layout=cfg, objective=o, ds=None, box=self.st['box'],
                    width=int(self.w_var.get()), topk=int(self.k_var.get()),
                    rounds=int(self.r_var.get()), days=int(self.d_var.get()),
                    fast=self.fast_var.get(), refine=False, verbose=False,
                    storage=(self.storage_var.get() or 'warn').split('｜')[0],
                    shift_hours=float(self.hours_var.get() or 4),
                    sched=(self.sched_var.get() or 'ab').split('｜')[0], table=tbl,
                    min_eff=me)
            self.result = r
            self.logln('[进度] 100% 完成')
            self.after(10, lambda: self.show_result(r))
        except Exception:
            self.logln('[错误] ' + traceback.format_exc().splitlines()[-1])
            self.after(10, lambda: messagebox.showerror('求解失败', traceback.format_exc()[-800:]))
        finally:
            self.after(10, lambda: self.run_btn.config(state='normal'))

    def show_result(self, r):
        k = r['kpi']
        self.kpi_lbl.config(text=(
            f"合成玉 {k.get('yu',0):,.0f}/天　龙门币 {k.get('lmd',0):,.0f}/天　经验 {k.get('exp',0):,.0f}/天\n"
            f"赤金 产 {k.get('gold',0):.2f} / 耗 {k.get('gold_cost',0):.2f} / 净 {k.get('gold_net',0):+.2f}　"
            f"碎片 产 {k.get('shard',0):.1f} / 耗 {k.get('shard_cost',0):.1f}\n"
            f"14 天最低心情 {k.get('min_morale',0):.1f}（{k.get('min_who','')}）　"
            f"低于10 {sum(1 for v in (k.get('lows') or {}).values() if v<10)} 人　"
            f"MAA 协议：{'通过 ✔' if not r['issues'] else r['issues']}"))
        self.res_tree.delete(*self.res_tree.get_children())
        for i, p in enumerate(r['plan']['shifts']):
            node = self.res_tree.insert('', 'end', text=f'第{i+1}班', values=('',))
            for (room, prod, lv, ops) in p['rooms']:
                tag = f'{room}{"·" + ST.PRODUCT_CN.get(prod, prod) if prod else ""}'
                self.res_tree.insert(node, 'end', text=tag, values=('/'.join(ops),))
            self.res_tree.insert(node, 'end', text='寝室', values=(' ｜ '.join('/'.join(d) for d in p['dorm']),))
            fia = p.get('fia') or {}
            if fia.get('enable'):
                self.res_tree.insert(node, 'end', text='菲亚梅塔', values=(f'交换 → {fia.get("target")}',))

    def export_maa(self):
        if not self.result:
            messagebox.showinfo('提示', '请先求解'); return
        p = filedialog.asksaveasfilename(defaultextension='.json',
                                         initialfile=f'{self._obj.get("main","plan")}_基建.json')
        if not p: return
        json.dump(self.result['doc'], open(p, 'w', encoding='utf-8'), ensure_ascii=False, indent=4)
        from emit import maa
        rpt = maa.report(self.result['plan'], self.result['doc'], self.result['kpi'],
                         self._obj.get('name', ''), '自定义')
        open(os.path.splitext(p)[0] + '.txt', 'w', encoding='utf-8').write(rpt)
        messagebox.showinfo('已导出', p + '\n（同目录还有同名 .txt 报告）')

    # ==================================================
    def on_close(self):
        self.st['grid'] = self.grid_cells
        self.st['main'] = self._key(self.main_var.get())
        self.st['gold'] = self._key(self.gold_var.get())
        self.st['shard'] = self._key(self.shard_var.get())
        self.st['morale'] = self._key(self.mor_var.get())
        self.st['dorm_mode'] = self.dorm_var.get()
        self.st['fiammetta'] = bool(self.fia_var.get())
        self.st['trust'] = bool(self.trust_var.get())
        self.st['min_eff'] = self.current_min_eff()
        self.st['sched'] = (self.sched_var.get() or 'window').split('｜')[0]
        self.st['storage'] = (self.storage_var.get() or 'warn').split('｜')[0]
        try:
            self.st['other_power'] = float(self.other_var.get())
        except Exception:
            pass
        try:
            ST.save_config(self.st)
        except Exception:
            pass
        self.destroy()


def main():
    app = App()
    if '--selftest' in sys.argv:
        app.update()
        print('GUI selftest OK：四个页签均已构建')
        app.destroy(); return 0
    app.mainloop()
    return 0


if __name__ == '__main__':
    sys.exit(main())
