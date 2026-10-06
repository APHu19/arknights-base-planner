# -*- coding: utf-8 -*-
"""probe_solve：验证候选池与单房间束搜索（贸易站/制造站/发电站）"""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core.dataset import Dataset, load_box
from core.engine import Ctx
from solve.pool import eligible_pool, score_team
from solve.beam import beam_search

ds = Dataset(); box = load_box()
print(f'干员池 {sum(1 for v in box.values() if v.get("own"))} 名（已持有）')
for room in ('贸易站', '制造站', '发电站'):
    pool = eligible_pool(ds, box, room)
    print(f'  {room} 候选池 {len(pool)} 名（前 12：{pool[:12]}）')

ctx = Ctx(ds=ds, box=box)
# 先用一个粗略背景（体系资源会随结果迭代）
ctx.staffed = ['迷迭香', '塑心', '车尔尼', '爱丽丝', '絮雨', '深律', '令', '重岳', '夕']
ctx.by_room = {'制造站': ['迷迭香'], '宿舍': ['塑心', '车尔尼', '爱丽丝', '菲亚梅塔'],
               '人力办公室': ['絮雨'], '控制中枢': ['令', '重岳', '阿米娅', '凯尔希', '维什戴尔']}

for room, product, level in (('贸易站', 'LMD', 3), ('贸易站', 'Orundum', 3),
                             ('制造站', 'Pure Gold', 3), ('制造站', 'Originium Shard', 3),
                             ('发电站', None, 3)):
    pool = eligible_pool(ds, box, room)
    t0 = time.time()
    res = beam_search(room, level, product, pool, ctx, ds, width=25, topk=5)
    dt = time.time() - t0
    print(f'\n=== {room} {product or ""} （{dt:.1f}s，池 {len(pool)}）===')
    for sc, team, rep in res:
        extra = ''
        if room == '发电站': extra = f'充能 +{rep["charge"]:.0f}%'
        elif 'lmd' in (rep.get('detail') and {}) or True:
            from core.engine import shift_output
            out, _ = shift_output(room, level, product, team, ctx, 12, ds)
            extra = ' '.join(f'{k} {v:.2f}/班' for k, v in out.items())
        print(f'  {"+".join(team):<28} 效率 {rep["eff"]:6.1f}%  {extra}')
