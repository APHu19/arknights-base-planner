# -*- coding: utf-8 -*-
"""probe_trade.py —— 打印贸易站/制造站关键干员的技能原文（用于核对组合加成）"""
import os
import sys
import json

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

WANT = ('德克萨斯', '能天使', '拉普兰德', '雪雉', '空弦', '孑', '但书', '可露希尔', '龙舌兰',
        '图耶', '柏喙', '明椒', '巫恋', '菲亚梅塔', '空爆', '月见夜', '古米')
d = json.load(open(os.path.join(HERE, 'data', 'skills_raw.json'), encoding='utf-8'))
for room in ('贸易站', '制造站', '控制中枢', '宿舍', '发电站'):
    rows = d['rooms'].get(room) or []
    hit = [r for r in rows if any(h in r['holders'] for h in WANT)]
    if not hit:
        continue
    print(f'—— {room}（{len(rows)} 条技能，命中关键干员 {len(hit)} 条）——')
    for r in hit:
        who = '/'.join(h for h in r['holders'] if h in WANT) or '/'.join(r['holders'])[:30]
        print(f"  {who:<14} {r['name']:<12} {r['desc'][:96]}")
