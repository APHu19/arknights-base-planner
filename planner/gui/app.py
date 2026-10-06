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
        ttk.Button(top, text='把剪贴板/文本框内容解析', command=self.parse_text).pack(side='left', padx=6)
        ttk.Button(top, text='导出干员池…', command=self.export_box).pack(side='left')
        ttk.Label(top, text='搜索：').pack(side='left', padx=(16, 2))
        self.q_var = tk.StringVar()
        e = ttk.Entry(top, textvariable=self.q_var, width=16); e.pack(side='left')
        e.bind('<KeyRelease>', lambda ev: self.refresh_ops())
        self.show_unowned = tk.BooleanVar(value=False)
        ttk.Checkbutton(top, text='显示未持有', variable=self.show_unowned,
                        command=self.refresh_ops).pack(side='left', padx=8)
        ttk.Label(top, text='双击行 = 切换精英化（无→精0→精1→精2）；空格 = 切换持有').pack(side='left', padx=8)

        mid = ttk.Panedwindow(f, orient='horizontal'); mid.pack(fill='both', expand=True, padx=8, pady=4)
        left = ttk.Frame(mid); right = ttk.Frame(mid)
        mid.add(left, weight=3); mid.add(right, weight=2)

        self.tree = ttk.Treeview(left, columns=('own', 'elite'), show='tree headings', height=20)
        self.tree.heading('#0', text='干员'); self.tree.heading('own', text='持有'); self.tree.heading('elite', text='精英化')
        self.tree.column('#0', width=170); self.tree.column('own', width=60, anchor='center')
        self.tree.column('elite', width=80, anchor='center')
        self.tree.pack(fill='both', expand=True, side='left')
        sb = ttk.Scrollbar(left, orient='vertical', command=self.tree.yview); sb.pack(side='right', fill='y')
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.bind('<Double-1>', self.cycle_elite)
        self.tree.bind('<space>', self.toggle_own)

        ttk.Label(right, text='粘贴区（MAA 导出的文本或 JSON 片段，每行一个干员，可带 精0/精1/精2）').pack(anchor='w')
        self.paste = tk.Text(right, height=18)
        self.paste.pack(fill='both', expand=True, pady=4)
        self.box_stat = ttk.Label(f, text='')
        self.box_stat.pack(anchor='w', padx=8, pady=(0, 6))
        self.refresh_ops()

    def refresh_ops(self):
        box = self.st['box']
        q = self.q_var.get().strip()
        self.tree.delete(*self.tree.get_children())
        for name in sorted(box):
            v = box[name]
            if not self.show_unowned.get() and not v.get('own'): continue
            if q and q not in name: continue
            self.tree.insert('', 'end', text=name, values=('✔' if v.get('own') else '', ELITE_CN.get(v.get('elite', 0), '无')))
        n_own = len(ST.owned_list(box))
        self.box_stat.config(text=f'共 {len(box)} 名；持有 {n_own} 名')

    def _sel_name(self):
        sel = self.tree.selection()
        return self.tree.item(sel[0], 'text') if sel else None

    def cycle_elite(self, _ev=None):
        n = self._sel_name()
        if not n: return
        v = self.st['box'].setdefault(n, {'own': True, 'elite': 0})
        v['own'] = True
        v['elite'] = (int(v.get('elite', 0)) + 1) % 4
        self.refresh_ops()

    def toggle_own(self, _ev=None):
        n = self._sel_name()
        if not n: return
        v = self.st['box'].setdefault(n, {'own': False, 'elite': 0})
        v['own'] = not v.get('own')
        self.refresh_ops()

    def import_json(self):
        p = filedialog.askopenfilename(filetypes=[('JSON', '*.json'), ('全部', '*.*')])
        if not p: return
        try:
            box = ST.import_maa_json(p)
            self.st['box'].update(box)
            self.refresh_ops()
            messagebox.showinfo('导入成功', f'导入 {len(box)} 名干员')
        except Exception as e:
            messagebox.showerror('导入失败', str(e))

    def parse_text(self):
        txt = self.paste.get('1.0', 'end')
        box = ST.parse_box_text(txt, self.st['box'])
        self.st['box'] = box
        self.refresh_ops()
        messagebox.showinfo('解析完成', f'当前干员池共 {len(box)} 名')

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
        for name in ST.LAYOUT_PRESETS:
            ttk.Button(top, text=name, width=8,
                       command=lambda n=name: self.apply_preset(n)).pack(side='left', padx=2)
        ttk.Label(top, text='　当前格：').pack(side='left')
        self.cur_prod = tk.StringVar(value='Pure Gold')
        self.prod_box = ttk.Combobox(top, textvariable=self.cur_prod, width=14,
                                     values=ST.MANU_PRODUCTS + ST.TRADE_PRODUCTS, state='readonly')
        self.prod_box.pack(side='left')
        ttk.Label(top, text='（左键切房间类型，右键切等级，选中上方产物后左键点制造/贸易格即改产物）').pack(side='left', padx=6)

        self.cells = []
        g = ttk.Frame(f); g.pack(padx=8, pady=6)
        for i in range(9):
            b = tk.Button(g, width=16, height=5, relief='ridge', font=('Microsoft YaHei', 10),
                          command=lambda i=i: self.click_cell(i))
            b.grid(row=i // 3, column=i % 3, padx=6, pady=6)
            b.bind('<Button-3>', lambda ev, i=i: self.right_cell(i))
            self.cells.append(b)
        bottom = ttk.Frame(f); bottom.pack(fill='x', padx=8, pady=8)
        self.power_lbl = ttk.Label(bottom, text='', font=('Microsoft YaHei', 11, 'bold'))
        self.power_lbl.pack(anchor='w')
        rowp = ttk.Frame(bottom); rowp.pack(anchor='w', pady=3)
        ttk.Label(rowp, text='固定房间合计耗电：').pack(side='left')
        self.other_var = tk.StringVar(value='190')
        ttk.Combobox(rowp, textvariable=self.other_var, width=6, state='readonly',
                     values=['190', '450']).pack(side='left')
        ttk.Label(rowp, text='（190 = 文档口径：会客60+办公10+加工60+训练60+宿舍0；'
                             '450 = 旧口径：把 4×宿舍按 65 计入）').pack(side='left')
        ttk.Label(bottom, text='电力规则：发电站 Ⅰ/Ⅱ/Ⅲ = 60/130/270；制造·贸易 Ⅰ/Ⅱ/Ⅲ = 10/30/60；'
                               '右键格子 = 逐格降级/升级（252 这类布局必须给部分制造站降到 Ⅱ）').pack(anchor='w', pady=4)
        self.render_grid()

    def apply_preset(self, name):
        self.grid_cells = list(ST.LAYOUT_PRESETS[name])
        self.render_grid()

    def click_cell(self, i):
        room, prod, lv = self.grid_cells[i]
        if room in ('制造站', '贸易站') and self.cur_prod.get() in (
                ST.MANU_PRODUCTS if room == '制造站' else ST.TRADE_PRODUCTS):
            self.grid_cells[i] = (room, self.cur_prod.get(), lv)
        else:
            nxt = {'制造站': '贸易站', '贸易站': '发电站', '发电站': '空', '空': '制造站'}[room]
            prod2 = None if nxt in ('发电站', '空') else ('Pure Gold' if nxt == '制造站' else 'LMD')
            self.grid_cells[i] = (nxt, prod2, lv if lv else 3)
        self.render_grid()

    def right_cell(self, i):
        """右键：把**该格**等级在 Ⅰ→Ⅱ→Ⅲ 间循环（252 这类布局需要逐格降级）"""
        room, prod, lv = self.grid_cells[i]
        if room == '空': return
        self.grid_cells[i] = (room, prod, (int(lv or 3) % 3) + 1)
        self.render_grid()

    def render_grid(self):
        for i, cell in enumerate(self.grid_cells):
            room, prod, lv = cell[0], cell[1], (int(cell[2]) if len(cell) > 2 else 3)
            txt = room
            if room != '空':
                txt += f'\n{ST.ROMAN[lv]}'
                if prod: txt += f'\n{ST.PRODUCT_CN.get(prod, prod)}'
            self.cells[i].config(text=txt, bg=ST.ROOM_COLORS.get(room, '#DDDDDD'))
        supply, consume, net = ST.power(self.grid_cells, float(self.other_var.get()))
        ok = net >= 0
        self.power_lbl.config(text=f'电力：供 {supply} ／ 耗 {consume:.0f} ／ 净 {net:+.0f}　'
                                   f'{"✔ 可正常运行" if ok else "✘ 电力不足，无法运行（可右键给制造/贸易站降级）"}',
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
        self.ge_var = tk.BooleanVar(value=bool(self.st.get('shard_ge_trade', False)))
        ttk.Checkbutton(right, text='附加约束：碎片产能 ≥ 玉站消化（搓玉稳健）',
                        variable=self.ge_var, command=self.update_obj_desc).pack(anchor='w', pady=4)
        self.obj_desc = ttk.Label(right, text='', wraplength=430, foreground='#444')
        self.obj_desc.pack(anchor='w', pady=4)
        ttk.Separator(right).pack(fill='x', pady=8)
        ttk.Label(right, text='寝室安排').pack(anchor='w')
        self.dorm_var = tk.StringVar(value=self.st.get('dorm_mode', 'precise'))
        ttk.Radiobutton(right, text='游戏自动填入', value='auto', variable=self.dorm_var).pack(anchor='w')
        ttk.Radiobutton(right, text='MAA 精准设置（心情紧张时推荐；固定顺序 + 菲亚梅塔首位）',
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
                              self._key(self.shard_var.get()), self._key(self.mor_var.get()))

    def update_obj_desc(self):
        try:
            o = self.current_objective()
            if self.ge_var.get():
                o['cons'] = dict(o.get('cons') or {}); o['cons']['shard_ge_trade'] = True
            self.obj_desc.config(text='当前组合：' + o['name'] +
                                      (f"　约束：{o['cons']}" if o['cons'] else '　（无硬约束）'))
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
        top = ttk.Frame(f); top.pack(fill='x', padx=8, pady=6)
        ttk.Label(top, text='束宽').pack(side='left'); self.w_var = tk.StringVar(value='14')
        ttk.Combobox(top, textvariable=self.w_var, values=['8', '10', '14', '18', '24'], width=5,
                     state='readonly').pack(side='left', padx=3)
        ttk.Label(top, text='每槽候选').pack(side='left'); self.k_var = tk.StringVar(value='6')
        ttk.Combobox(top, textvariable=self.k_var, values=['4', '6', '8', '10'], width=5,
                     state='readonly').pack(side='left', padx=3)
        ttk.Label(top, text='迭代轮数').pack(side='left'); self.r_var = tk.StringVar(value='1')
        ttk.Combobox(top, textvariable=self.r_var, values=['1', '2', '3'], width=5,
                     state='readonly').pack(side='left', padx=3)
        ttk.Label(top, text='复核天数').pack(side='left'); self.d_var = tk.StringVar(value='14')
        ttk.Combobox(top, textvariable=self.d_var, values=['7', '14', '21'], width=5,
                     state='readonly').pack(side='left', padx=3)
        self.fast_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(top, text='快速（关局部搜索）', variable=self.fast_var).pack(side='left', padx=8)
        ttk.Label(top, text='班次时长(h)').pack(side='left')
        self.hours_var = tk.StringVar(value=str(self.st.get('shift_hours', 4)))
        ttk.Combobox(top, textvariable=self.hours_var, width=5, state='readonly',
                     values=['2', '3', '4', '6', '8', '12']).pack(side='left', padx=3)
        ttk.Label(top, text='排班路径').pack(side='left')
        self.sched_var = tk.StringVar(value='window｜窗口排班（判据A，推荐）')
        ttk.Combobox(top, textvariable=self.sched_var, width=30, state='readonly',
                     values=['window｜窗口排班（判据A，推荐）', 'ab｜同站A/B整段轮换（旧）']).pack(
            side='left', padx=3)
        ttk.Label(top, text='爆仓策略').pack(side='left')
        self.storage_var = tk.StringVar(value=self.st.get('storage', 'warn'))
        ttk.Combobox(top, textvariable=self.storage_var, width=18, state='readonly',                     values=['warn｜只告警（默认）', 'clip｜自动降效（剪掉超出）', 'off｜不检查']).pack(side='left', padx=3)
        self.run_btn = ttk.Button(top, text='开始求解', command=self.start_solve)
        self.run_btn.pack(side='left', padx=8)
        ttk.Button(top, text='导出 MAA 计划…', command=self.export_maa).pack(side='left')

        self.log = tk.Text(f, height=12, state='disabled')
        self.log.pack(fill='both', expand=False, padx=8)
        self.kpi_lbl = ttk.Label(f, text='', font=('Microsoft YaHei', 11, 'bold'), justify='left')
        self.kpi_lbl.pack(anchor='w', padx=8, pady=6)
        self.res_tree = ttk.Treeview(f, columns=('detail',), show='tree headings', height=10)
        self.res_tree.heading('#0', text='房间/班次'); self.res_tree.heading('detail', text='安排')
        self.res_tree.column('#0', width=140); self.res_tree.column('detail', width=900)
        self.res_tree.pack(fill='both', expand=True, padx=8, pady=4)

    def logln(self, s):
        self.log_q.put(s)

    def _drain_log(self):
        while True:
            try: s = self.log_q.get_nowait()
            except queue.Empty: break
            self.log.config(state='normal'); self.log.insert('end', s + '\n')
            self.log.see('end'); self.log.config(state='disabled')
        self.after(200, self._drain_log)

    def start_solve(self):
        cfg = ST.grid_to_cfg(self.grid_cells)
        supply, consume, net = ST.power(self.grid_cells, float(self.other_var.get()))
        if net < 0:
            messagebox.showerror('电力不足', f'供 {supply} / 耗 {consume:.0f} / 净 {net:+.0f}，请先调整九宫格。')
            return
        self.run_btn.config(state='disabled')
        self.result = None
        t = threading.Thread(target=self._solve_worker, args=(cfg,), daemon=True)
        t.start()

    def _solve_worker(self, cfg):
        try:
            from solve.solver import run
            o = self.current_objective()
            if self.ge_var.get():
                o['cons'] = dict(o.get('cons') or {}); o['cons']['shard_ge_trade'] = True
            self._obj = o
            tbl, err = self._table()
            if err:
                messagebox.showwarning('班次表有误', err)
                self.logln('[错误] 班次表：' + err)
                return
            from core import shiftplan as SP
            self.logln(f'[求解] 布局 {sum(len(v) for v in cfg.values())} 间，'
                       f'目标 {o["name"]}，束宽 {self.w_var.get()}')
            self.logln(f'[班次] {SP.summary(tbl)}')
            r = run(layout=cfg, objective=o, ds=None, box=self.st['box'],
                    width=int(self.w_var.get()), topk=int(self.k_var.get()),
                    rounds=int(self.r_var.get()), days=int(self.d_var.get()),
                    fast=self.fast_var.get(), refine=False, verbose=False,
                    storage=(self.storage_var.get() or 'warn').split('｜')[0],
                    shift_hours=float(self.hours_var.get() or 4),
                    sched=(self.sched_var.get() or 'ab').split('｜')[0], table=tbl)
            self.result = r
            self.logln('[完成] 求解与复核结束')
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
        self.st['shard_ge_trade'] = bool(self.ge_var.get())
        self.st['dorm_mode'] = self.dorm_var.get()
        self.st['fiammetta'] = bool(self.fia_var.get())
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
