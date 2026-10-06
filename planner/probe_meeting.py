# -*- coding: utf-8 -*-
"""probe_meeting：验证会客室线索搜集速度模型（用户提供的数值）"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.dataset import Dataset, load_box
from core.meeting import speed, stars, BASE

ds = Dataset().set_box(load_box()); box = load_box()
st = stars()
print(f'基础效率 {BASE}%｜星级表加载 {len(st)} 名｜干员池阶段：'
      f'{ {o: box[o]["elite"] for o in ("伊内丝","红","虎狼丸","伺夜","余","望","跃跃") if o in box} }')
print('\n队伍                 速度%   技能%   份/天   明细(稀有度档+精英化档+未红脸)')
for team in (['伊内丝', '红'], ['虎狼丸', '伺夜'], ['余', '望'], ['跃跃', '红'],
             ['莱欧斯', '玛露西尔'], ['白雪', '远山']):
    r = speed(team, ds, box=box)
    det = ' / '.join(f"{d['op']}({d['stars']}★E{d['elite']} +{d['rarity']:g}+{d['elite_bonus']:g}+{d['not_red']:g})"
                     for d in r['detail'])
    print(f'  {"+".join(team):<18} {r["speed"]:6.1f}  {r["skill"]:5.1f}  {r["clue_per_day"]:5.2f}   {det}')
print('\n对照：单干员拆解（伊内丝）')
r = speed(['伊内丝'], ds, box=box)
print(f"  126(基础) + {r['detail'][0]['rarity']:g}(5星) + {r['detail'][0]['elite_bonus']:g}(精2) "
      f"+ {r['detail'][0]['not_red']:g}(未红脸) + {r['skill']:g}(聚影 20+2×4h) = {r['speed']:.1f}%")
