# -*- coding: utf-8 -*-
"""probe_systems2.py —— 验证新加规则：设施数量（发电站）修正、工程机器人、赤金生产线

对照项：
  · 温蒂 + 森蚺 + 清流（社区 +115%）—— 分开算 3 电站 vs 加晨曦/森蚺-中枢+Lancet-2 的 4~5 电站
  · 至简 + 机械辅助·β（工程机器人按设施总等级）
  · 图耶（每 2 条赤金生产线 +15%）在 2/3/4 条赤金线下的差异
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

from core.dataset import Dataset, load_box                 # noqa: E402
from core.engine import Ctx, eval_room, shift_output        # noqa: E402


def mk(ds, gold=3, trade=3, power=3, dorm=4):
    lay = {'制造站': [(3, 'Pure Gold')] * gold, '贸易站': [(3, 'LMD')] * trade,
           '发电站': [(3, None)] * power, '宿舍': [(5, None)] * dorm}
    c = Ctx(ds=ds, layout=lay)
    c.dorm_occ = 20
    return c, lay


def ev(ds, lay, room, team, product=None, by_room=None, cur=None):
    c = Ctx(ds=ds, layout=lay)
    c.by_room = by_room or {}
    c.staffed = [o for v in (by_room or {}).values() for o in v]
    c.dorm_occ = 20
    rep = eval_room(room, 3, product, list(team), c, ds)
    out, _ = shift_output(room, 3, product, list(team), c, 1.0, ds) if room in ('制造站', '贸易站') else ({}, None)
    return rep, out


ds = Dataset()
box = load_box()
ds.set_box(box)
c, lay = mk(ds)

print('一、温蒂 + 森蚺 + 清流（制造站赤金）—— 看发电站数量修正是否生效')
for tag, by_room, cur in (
        ('基线 3 电站（无修正）', {'制造站': ['温蒂', '森蚺', '清流'], '发电站': ['澄闪', '深靛', '雷蛇']},
         ['温蒂', '森蚺', '清流']),
        ('+晨曦格雷伊（发电站 +1）',
         {'制造站': ['温蒂', '森蚺', '清流'], '发电站': ['承曦格雷伊', '深靛', '雷蛇']},
         ['温蒂', '森蚺', '清流']),
        ('+森蚺在中枢 & Lancet-2 在发电站（+2）',
         {'制造站': ['温蒂', '森蚺', '清流'], '控制中枢': ['森蚺'], '发电站': ['Lancet-2', '深靛', '雷蛇']},
         ['温蒂', '森蚺', '清流']),
        ('两者叠加（+3 → 6 电站等效）',
         {'制造站': ['温蒂', '森蚺', '清流'], '控制中枢': ['森蚺'],
          '发电站': ['承曦格雷伊', 'Lancet-2', '雷蛇']}, ['温蒂', '森蚺', '清流'])):
    rep, out = ev(ds, lay, '制造站', ['温蒂', '森蚺', '清流'], 'Pure Gold', by_room, cur)
    print(f'  {tag:<34} eff {rep["eff"]:>6.0f}%  件/时 {out.get("gold", 0):.3f}  '
          f'设施数量加成 {getattr(rep.get("resources", {}), "get", lambda *a: None)("发电站") or ""}'
          f' {rep.get("resources", {}).get("工程机器人", "")}')

print('\n二、至简（工程机器人）+ 机械辅助·β')
c2, lay2 = mk(ds)
bots = sum(int(lv) for room, ins in lay2.items() for (lv, _p) in ins)
for team, tag in ((['至简'], '至简（绘图设计）'), (['至简', '刻俄柏'], '至简 + 刻俄柏'),
                  (['至简', '多萝西'], '至简 + 多萝西')):
    rep, out = ev(ds, lay2, '制造站', team, 'Pure Gold', {'制造站': team}, team)
    print(f'  {tag:<18} 设施总等级 {bots} → 机器人 {rep["resources"].get("工程机器人", 0):.0f}'
          f'  eff {rep["eff"]:.0f}%  件/时 {out.get("gold", 0):.3f}')

print('\n三、图耶（每 2 条赤金生产线 +15%）随赤金线数变化')
for g in (2, 3, 4, 5):
    lay3 = {'制造站': [(3, 'Pure Gold')] * g + [(3, 'Originium Shard')] * max(0, 5 - g),
            '贸易站': [(3, 'LMD')] * 2, '发电站': [(3, None)] * 3, '宿舍': [(5, None)] * 4}
    rep, out = ev(ds, lay3, '贸易站', ['图耶'], 'LMD', {'贸易站': ['图耶']}, ['图耶'])
    print(f'  赤金线 {g} 条 → eff {rep["eff"]:.0f}%  币/时 {out.get("lmd", 0):.1f}')

print('\n四、黑键 / 迷迭香 共享感知信息链（宿舍满员 20）')
for tag, by_room, cur, room in (
        ('迷迭香（制造，感知信息→思维链环）', {'制造站': ['迷迭香'], '宿舍': ['爱丽丝', '车尔尼']},
         ['迷迭香'], '制造站'),
        ('黑键（贸易，感知信息→无声共鸣）', {'贸易站': ['黑键'], '宿舍': ['爱丽丝', '车尔尼', '塑心']},
         ['黑键'], '贸易站'),
        ('迷迭香 + 黑键 + 爱丽丝/车尔尼/塑心（全链）',
         {'制造站': ['迷迭香'], '贸易站': ['黑键'], '宿舍': ['爱丽丝', '车尔尼', '塑心']},
         ['迷迭香'], '制造站')):
    rep, out = ev(ds, lay, room, cur, 'Pure Gold' if room == '制造站' else 'LMD', by_room, cur)
    res = rep.get('resources', {})
    print(f'  {tag:<36} eff {rep["eff"]:>6.0f}%  感知信息 {res.get("感知信息", 0):.0f}'
          f' 思维链环 {res.get("思维链环", 0):.0f} 无声共鸣 {res.get("无声共鸣", 0):.0f}')
