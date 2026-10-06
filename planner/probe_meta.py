# -*- coding: utf-8 -*-
"""probe_meta.py —— 单走等效效率表 + 社区体系复算 + 关键干员技能原文

用途：把"社区共识编队"与"本引擎实算"对账，产出可参考的体系/单走清单。
数据来源分两层：
  · 机制与数值 = 本项目 `data/skills_raw.json` + `全机制.md`（权威）
  · 社区编队 = 网络攻略（PRTS 底稿的基建指南 / NGA 讨论帖），只作对照
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

from core.dataset import Dataset, load_box                     # noqa: E402
from core.engine import Ctx, eval_room, shift_output           # noqa: E402
from core import orders, meeting                                # noqa: E402

LAYOUT = {'制造站': [(3, 'Pure Gold')] * 3, '贸易站': [(3, 'LMD')] * 3,
          '发电站': [(3, None)] * 3, '宿舍': [(5, None)] * 4}


def ctx_of(ds):
    c = Ctx(ds=ds, layout=dict(LAYOUT))
    c.by_room = {k: [] for k in LAYOUT}
    c.staffed = []
    c.dorm_occ = 20
    return c


def solo_table(ds, box, room, product=None):
    ctx = ctx_of(ds)
    rows = []
    for op in box:
        if not box[op].get('own'):
            continue
        try:
            r = eval_room(room, 3, product, [op], ctx, ds)
        except Exception:
            continue
        eff = float(r.get('eff') or 0.0)
        rows.append((eff, op))
    rows.sort(reverse=True)
    return rows


def combo(ds, box, room, team, product=None, hours=1.0):
    ctx = ctx_of(ds)
    r = eval_room(room, 3, product, list(team), ctx, ds)
    out, _ = shift_output(room, 3, product, list(team), ctx, hours, ds)
    return r, out


def main():
    ds = Dataset()
    box = load_box()
    ds.set_box(box)
    print('=' * 112)
    print(f'干员池：{len(box)} 名（持有 {sum(1 for v in box.values() if v.get("own"))} 名）；'
          f'技能 {len(ds.skills)} 条')

    print('\n【一】单走等效效率（1 人独进驻，本引擎实算；ctx=333+R 4×Lv5 宿舍满员）')
    for room, prod, tag in (('贸易站', 'LMD', '贸易站 龙门币 订单效率%'),
                            ('制造站', 'Pure Gold', '制造站 赤金 生产力%'),
                            ('制造站', 'Battle Record', '制造站 经验 生产力%'),
                            ('发电站', None, '发电站 充能%（eff−100）')):
        rows = solo_table(ds, box, room, prod)
        if room == '发电站':
            rows = [(e - 100.0, o) for e, o in rows if e > 100.0]
            rows.sort(reverse=True)
        print(f'  {tag}：' + '、'.join(f'{o} {e:.0f}%' for e, o in rows[:12]))

    # 会客室要按**线索速度**口径（rules 里没有会客室 → eval_room 恒为 100，必须用 core/meeting）
    rows = []
    for op in box:
        if not box[op].get('own'):
            continue
        try:
            sp = meeting.speed([op], ds, box=box)['speed'] - meeting.BASE
        except Exception:
            sp = 0.0
        rows.append((sp, op))
    rows.sort(reverse=True)
    print('  会客室 单人线索速度加成%（基础 126 之外的部分）：'
          + '、'.join(f'{o} {e:.0f}%' for e, o in rows[:12]))

    # 人力办公室：**本引擎还没建规则**（eval_room 恒 100）→ 只列技能原文，别给假数字
    hire = []
    for op in box:
        if not box[op].get('own'):
            continue
        for s in ds.skills_of(op, '人力办公室'):
            hire.append((op, s.name, (s.desc or '')[:60]))
    print(f'  人力办公室：本引擎**尚未建模**（rules 无该房间，eff 恒 100）→ 目前只有 {len(hire)} 条技能可查：')
    for op, nm, d in hire[:10]:
        print(f'      {op:<8} {nm:<10} {d}')

    print('\n【二】社区共识编队 → 本引擎复算（对照社区数字）')
    cases = [
        ('贸易站', 'LMD', ['能天使', '德克萨斯', '拉普兰德'], '企鹅相簿', '+100%（+中枢107%）'),
        ('贸易站', 'LMD', ['雪雉', '空弦', '空爆'], '空弦高效组', '+105%'),
        ('贸易站', 'LMD', ['孑', '德克萨斯', '拉普兰德'], '差额订单(孑无精)', '最高121%'),
        ('贸易站', 'LMD', ['巫恋', '柏喙', '桃金娘'], '巫恋高品质订单', '+90%&4赤金率90%'),
        ('贸易站', 'LMD', ['巫恋', '明椒', '龙舌兰'], '本项推荐(裁缝β)', 'v13: 1024币/时'),
        ('制造站', 'Pure Gold', ['清流', '温蒂', '森蚺'], '归零+清流', '115%'),
        ('制造站', 'Battle Record', ['红云', '刻俄柏', '稀音'], '红云仓库体系(经验)', '106%'),
        ('制造站', 'Pure Gold', ['泡泡', '火神', '刻俄柏'], '泡泡仓库体系(赤金)', '95%'),
        ('制造站', 'Pure Gold', ['迷迭香', '槐琥', '泡普卡'], '槐琥+泡普卡顶班', '40%+抵消副作用'),
        ('发电站', None, ['澄闪'], '澄闪(充能第一)', '+60%'),
        ('发电站', None, ['PhonoR-0'], 'PhonoR-0(逻各斯在中枢再+5%)', '+10%/+15%'),
    ]
    for room, prod, team, name, ref in cases:
        miss = [o for o in team if o not in box]
        if miss:
            print(f'  {name:<22} 缺干员 {miss} → 跳过')
            continue
        r, out = combo(ds, box, room, team, prod, hours=1.0)
        eff = float(r.get('eff') or 0.0)
        extra = ''
        if room == '贸易站':
            pr = orders.profile(list(team), ds, 1.0)
            extra = (f"｜币/时 {out.get('lmd', 0):.0f}｜耗金/时 {out.get('gold_cost', 0):.2f}"
                     f"｜分布 {pr.get('dist')}")
            if prod == 'Orundum':
                extra = f"｜玉/时 {out.get('orundum', 0):.1f}"
        elif room == '制造站':
            extra = (f"｜件/时 {out.get('gold', out.get('exp', 0) / 1000 * 3 / 3):.2f}"
                     if prod == 'Pure Gold' else f"｜经验/时 {out.get('exp', 0):.0f}")
        print(f'  {name:<22} {"+".join(team):<26} eff {eff:>5.0f}%（社区参考 {ref}）{extra}')

    print('\n【三】关键干员技能原文（本机数据，权威；只取前 90 字）')
    keys = ['巫恋', '温蒂', '森蚺', '清流', '红云', '泡泡', '稀音', '刻俄柏', '迷迭香', '槐琥',
            '泡普卡', '空弦', '雪雉', '孑', '柏喙', '明椒', '龙舌兰', '但书', '可露希尔',
            '菲亚梅塔', '承曦格雷伊', '澄闪', '乌有', '夕', '絮雨', '爱丽丝', '斥罪', '遥', '图耶']
    for op in keys:
        if op not in box:
            continue
        sk = ds.skills_of(op)
        if not sk:
            print(f'  {op:<6}（本机数据里没有后勤技能记录）')
            continue
        for s in sk:
            print(f'  {op:<6}@{s.room:<5} {s.name:<12} {(s.desc or "")[:90]}')
    print('=' * 112)


if __name__ == '__main__':
    main()
