# -*- coding: utf-8 -*-
"""probe_phase：核对“干员在哪个精英化阶段拥有哪个技能”的信息源
信息源：_raw/building_data.json  → chars[charId].buffChar[].buffData[].{buffId, cond}
        _raw/character_table.json → name → charId
"""
import json, os, sys, re
sys.stdout.reconfigure(encoding='utf-8')
ROOT = r'C:\Users\APHu\dsh生成333基建表'
bd = json.load(open(os.path.join(ROOT, '_raw', 'building_data.json'), encoding='utf-8'))
ct = json.load(open(os.path.join(ROOT, '_raw', 'character_table.json'), encoding='utf-8'))
print('building_data 顶层键：', [k for k in bd][:12])
chars = bd.get('chars') or {}
buffs = bd.get('buffs') or {}
print(f'chars {len(chars)} 名，buffs {len(buffs)} 个')
name2id = {}
for cid, c in ct.items():
    if isinstance(c, dict) and c.get('name'):
        name2id[c['name']] = cid
print('character_table 有名字的干员：', len(name2id))

def show(name):
    cid = name2id.get(name)
    print(f'\n===== {name}（charId={cid}）=====')
    if not cid:
        print('  ⚠ character_table 里找不到'); return
    ch = chars.get(cid)
    if not ch:
        print('  ⚠ building_data.chars 里没有该条'); return
    print('  buffChar 组数 =', len(ch.get('buffChar') or []))
    for grp in ch.get('buffChar') or []:
        for b in grp.get('buffData') or []:
            bid = b.get('buffId'); cond = b.get('cond')
            bf = buffs.get(bid) or {}
            cs = json.dumps(cond, ensure_ascii=False) if not isinstance(cond, str) else cond
            print(f'    cond={cs:<28} buffId={bid:<26} '
                  f'name={bf.get("buffName") or bf.get("name")} room={bf.get("roomType")} '
                  f'desc={(bf.get("description") or "")[:40]}')

for n in ('明椒', '巫恋', '贝娜', '柏喙', '卡夫卡', '森蚺', '温蒂', '响石'):
    show(n)

# 覆盖率：多少持有基建技能的干员能在 building_data 里找到阶段信息
ds_ops = set()
import importlib
sys.path.insert(0, os.path.join(ROOT, 'planner'))
from core.dataset import Dataset
ds = Dataset()
for s in ds.skills:
    ds_ops |= set(s.holders)
missing = [o for o in sorted(ds_ops) if o not in chars and o not in chars.get(name2id.get(o, ''), {})]
noid = [o for o in sorted(ds_ops) if o not in name2id]
nobuffchar = [o for o in sorted(ds_ops) if name2id.get(o) and not (chars.get(name2id[o]) or {}).get('buffChar')]
print(f'\n=== 覆盖率自检（技能库里共 {len(ds_ops)} 名持有者）===')
print(f'  character_table 查不到名字：{len(noid)} 名 {noid[:15]}')
print(f'  有名字但 building_data 无 buffChar：{len(nobuffchar)} 名 {nobuffchar[:15]}')
