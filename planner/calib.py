# -*- coding: utf-8 -*-
"""calib.py —— 规则表标定：用规则引擎复算 v7 表的四支赤金队 / 钱2 / 玉站 / 发电站"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core.dataset import Dataset
from core.engine import Ctx, eval_room, RATE

ds = Dataset(); ctx = Ctx(ds=ds)
# 全基建在岗者（势力计数用）：v7 的典型在岗名单
ctx.staffed = ['娜斯提', '清流', '阿罗玛', '引星棘刺', '砾', '苍苔', '冬时', '森蚺', '温蒂',
               '多萝西', '淬羽赫默', '迷迭香', '缪尔赛思', '承曦格雷伊', '雷蛇',
               '巫恋', '龙舌兰', '柏喙', '乌有', '但书', '吉星', '真言', '可露希尔', '能天使',
               '新约能天使', '空弦', '蕾缪安', '孑', '赫德雷', '齐尔查克',
               '地灵', '槐琥', '褐果', '艾雅法拉', '谬因', '锡兰', '絮雨', '斥罪',
               '阿米娅', '凯尔希', '令', '重岳', '维什戴尔', '黍', '余', '望']
ctx.elite_facilities = 2
# 在岗分布（跨房间加成/体系资源读它）
ctx.by_room = {
    '制造站': ['娜斯提', '清流', '阿罗玛', '引星棘刺', '砾', '苍苔', '冬时', '森蚺', '温蒂',
             '多萝西', '淬羽赫默', '迷迭香'],
    '贸易站': ['巫恋', '龙舌兰', '柏喙', '乌有', '但书', '能天使', '黑键'],
    '控制中枢': ['阿米娅', '凯尔希', '令', '重岳', '维什戴尔'],
    '发电站': ['缪尔赛思', '承曦格雷伊', '雷蛇'],
    '人力办公室': ['絮雨'],
    '宿舍': ['塑心', '车尔尼', '爱丽丝', '菲亚梅塔'],
}

GOLD = [('娜斯提', '清流', '阿罗玛', 250), ('引星棘刺', '砾', '苍苔', 224),
        ('冬时', '森蚺', '温蒂', 210), ('多萝西', '淬羽赫默', '迷迭香', 230)]
print('=== 赤金队（旧模型值 → 规则表值；hours=4 与 12）===')
tot4 = tot12 = 0.0
for a, b, c, old in GOLD:
    e4 = eval_room('制造站', 3, 'Pure Gold', [a, b, c], ctx, ds, hours=4)['eff']
    e12 = eval_room('制造站', 3, 'Pure Gold', [a, b, c], ctx, ds, hours=12)['eff']
    tot4 += RATE['gold_per_h_per_100'] * e4 / 100
    tot12 += RATE['gold_per_h_per_100'] * e12 / 100
    print(f'  {"+".join((a,b,c)):<28} 旧 {old}%  规则表 hours=4: {e4:6.1f}%  hours=12: {e12:6.1f}%')
print(f'  四队合计（A/B 各半）：hours=4 → {tot4/2:.2f} 枚/h ；hours=12 → {tot12/2:.2f} 枚/h（旧模型 3.81）')

print('\n=== 贸易站 ===')
for team, prod, old in ((['巫恋', '龙舌兰', '柏喙'], 'LMD', 1024),
                        (['乌有', '但书', '能天使'], 'LMD', 1261),
                        (['但书', '吉星', '真言'], 'LMD', 1153),
                        (['可露希尔', '吉星', '真言'], 'LMD', None)):
    r = eval_room('贸易站', 3, prod, team, ctx, ds, hours=12)
    lmd = RATE['lmd_per_h_per_eff'] * r['eff']
    print(f'  {"+".join(team):<26} eff {r["eff"]:6.1f}%  → {lmd:6.0f} 币/h（旧 {old}）')
    for op, d in r['detail'].items():
        if d['notes']: print(f'        {op}: {d["notes"]}')

print('\n=== 体系链路：无声共鸣 → 订单效率（黑键）===')
r = eval_room('贸易站', 3, 'LMD', ['黑键', '可露希尔', '吉星'], ctx, ds, hours=12)
print(f"  黑键+可露希尔+吉星 eff {r['eff']:.1f}% -> {RATE['lmd_per_h_per_eff']*r['eff']:.0f} 币/h")
print(f"    资源池：感知信息 {r['resources'].get('感知信息')}｜思维链环 {r['resources'].get('思维链环')}｜无声共鸣 {r['resources'].get('无声共鸣')}")
for op, d in r['detail'].items():
    if d['notes']: print(f'    {op}: {d["notes"]}')
print('\n=== 迷迭香分项（校准 270% 的来源）===')
r = eval_room('制造站', 3, 'Pure Gold', ['多萝西', '淬羽赫默', '迷迭香'], ctx, ds, hours=12)
print(f"  eff {r['eff']:.1f}%｜思维链环 {r['resources'].get('思维链环')}｜感知信息 {r['resources'].get('感知信息')}")
for op, d in r['detail'].items():
    print(f'    {op}: {d["notes"]}')

print('\n=== 玉站 / 碎片站 ===')
for team, prod in ((['新约能天使', '空弦', '蕾缪安'], 'Orundum'), (['地灵', '槐琥', '褐果'], 'Originium Shard')):
    r = eval_room('贸易站' if prod == 'Orundum' else '制造站', 3, prod, team, ctx, ds, hours=12)
    print(f'  {"+".join(team):<26} {prod:<16} eff {r["eff"]:.1f}%')

print('\n=== 发电站充能 ===')
for team in (['缪尔赛思', '承曦格雷伊', '雷蛇'], ['澄闪', '格雷伊', '阿消']):
    r = eval_room('发电站', 3, None, team, ctx, ds, hours=12)
    print(f'  {"+".join(team):<28} 充能 +{r["charge"]:.0f}%')
