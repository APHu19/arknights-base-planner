# -*- coding: utf-8 -*-
"""probe_hunt：验证 深海猎人房间效率加成 + 控制中枢减压取最高"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core.dataset import Dataset, load_box
from core.engine import Ctx, eval_room, cc_relief

ds = Dataset(); box = load_box(); ctx = Ctx(ds=ds, box=box)
MANU = ['娜斯提', '清流', '阿罗玛', '引星棘刺', '砾', '苍苔', '冬时', '森蚺', '温蒂',
        '多萝西', '淬羽赫默', '迷迭香', '斯卡蒂', '幽灵鲨', '安哲拉', '乌尔比安']
ctx.staffed = MANU + ['歌蕾蒂娅', '阿米娅', '凯尔希', '令', '重岳', '维什戴尔'] + ['巫恋', '缪尔赛思']
ctx.by_room = {'制造站': MANU, '控制中枢': ['歌蕾蒂娅', '阿米娅', '凯尔希', '令', '重岳'],
               '贸易站': ['巫恋', '龙舌兰', '柏喙'], '发电站': ['缪尔赛思', '承曦格雷伊', '雷蛇']}
elite = (box.get('歌蕾蒂娅') or {}).get('elite', 0)
print(f'歌蕾蒂娅 精英化 = {elite}（精2 → 10%/人、单站上限 90%）')
print(f'深海猎人在制造站的人数 = {sum(1 for o in MANU if o in ds.members_of("深海猎人"))}'
      f'（斯卡蒂 幽灵鲨 安哲拉 乌尔比安 = 4 人 → 预期 +40%）\n')

for t in (['斯卡蒂', '幽灵鲨', '娜斯提'], ['安哲拉', '乌尔比安', '清流'], ['娜斯提', '清流', '阿罗玛']):
    r = eval_room('制造站', 3, 'Pure Gold', t, ctx, ds, hours=12)
    hunt = [n for d in r['detail'].values() for n in d['notes'] if '深海' in n]
    print(f'  {"+".join(t):<28} eff {r["eff"]:6.1f}%  房间效率加成: {hunt}')

print('\n控制中枢减压（特殊比较规则：取最高）')
print('  重岳+维什戴尔 同在中枢:', cc_relief(['重岳', '维什戴尔'], yanhuo=60), '（应 = max(0.05+0.15, 0.10) + 0.05×2 = 0.30）')
print('  只重岳:', cc_relief(['重岳'], 60), '| 只维什戴尔:', cc_relief(['维什戴尔'], 60), '| 空:', cc_relief([], 60))
