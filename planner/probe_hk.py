# -*- coding: utf-8 -*-
"""probe_hk：定位 黑键 自站结算时无声共鸣偏低的原因"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core.dataset import Dataset
from core.engine import Ctx, eval_room, _resolve_resources

ds = Dataset(); c = Ctx(ds=ds)
c.staffed = ['迷迭香', '车尔尼', '爱丽丝', '絮雨', '塑心']
c.by_room = {'制造站': ['迷迭香'], '宿舍': ['塑心', '车尔尼', '爱丽丝', '菲亚梅塔'],
             '人力办公室': ['絮雨'], '贸易站': ['巫恋', '龙舌兰', '柏喙']}
team = ['黑键', '可露希尔', '吉星']
print('直接调 _resolve_resources(cur_room=贸易站):')
r = _resolve_resources(c, team, c.base_resources(), ds, cur_room='贸易站')
for k in ('感知信息', '思维链环', '无声共鸣', '人间烟火'):
    print(f'   {k} = {r.get(k)}')
print('\n经 eval_room:')
r2 = eval_room('贸易站', 3, 'LMD', team, c, ds, hours=12)
print('   resources:', {k: r2['resources'].get(k) for k in ('感知信息', '无声共鸣', '人间烟火')})
print('   eff', r2['eff'], '| notes:', [n for d in r2['detail'].values() for n in d['notes']])
