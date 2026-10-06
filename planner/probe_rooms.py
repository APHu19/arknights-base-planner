# -*- coding: utf-8 -*-
"""probe_rooms.py —— 核对 skills_raw.json 的房间分布（抽取器修好后必须含人力办公室）"""
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

d = json.load(open(os.path.join(HERE, 'data', 'skills_raw.json'), encoding='utf-8'))
rooms = d['rooms']
print('meta.rooms =', d['meta']['rooms'])
print(f'技能总数 = {d["meta"].get("skill_count")}（实际 {sum(len(v) for v in rooms.values())}）')
for r, rows in rooms.items():
    print(f'  {r:<8} {len(rows):>4} 条  例：' + '、'.join(x['name'] for x in rows[:4]))
hr = rooms.get('人力办公室') or []
print(f'\n人力办公室条目 = {len(hr)}；示例：')
for x in hr[:6]:
    print(f"   {x['name']:<12} {'/'.join(x['holders'])[:24]:<26} {x['desc'][:64]}")
