# -*- coding: utf-8 -*-
"""dump_trade：导出贸易站相关干员原文，用于补齐规则表缺口"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.dataset import Dataset
OPS = ['空弦', '新约能天使', '能天使', '蕾缪安', '孑', '赫德雷', '齐尔查克', '但书', '古米', '梓兰',
       '可露希尔', '吉星', '真言', '推进之王', '摩根', '德克萨斯', '拉普兰德', '能天使', '巫恋',
       '龙舌兰', '柏喙', '慕斯', '缠丸', '乌有', '可露希尔', '渡桥', '明椒', '卡夫卡']
ds = Dataset()
seen = set()
for op in OPS:
    if op in seen: continue
    seen.add(op)
    rows = ds.skills_of(op, '贸易站')
    print(f'—— {op} ——')
    for s in rows:
        print(f'   {s.name}: {s.desc[:150]}')
    if not rows: print('   （无贸易站技能）')
