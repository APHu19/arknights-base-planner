# -*- coding: utf-8 -*-
"""terms_report：术语（种族/势力/小队/技能类）→ 成员 → 使用它的技能（含数值）
用于回答“计算会用到哪些种族/势力”，并作为规则表的依据清单。"""
import sys, os, re, collections
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.dataset import Dataset

ds = Dataset()
COLLECTION = [t for t in ds.globals if ds.members_of(t)]
print(f'集合型术语 {len(COLLECTION)} 个 / 全部术语 {len(ds.globals)} 个\n')

# 按“被技能引用”的术语组织：某术语被哪些技能用到、给什么数值
use = collections.defaultdict(list)
for s in ds.skills:
    for t in COLLECTION:
        if t in (s.name or ''):        # 技能名里含术语（用于“类技能”）
            use[t].append((s.room, s.name, s.desc[:0]))
        if t in (s.desc or ''):
            nums = re.findall(r'[+\-]\d+%?', s.desc)
            use[t].append((s.room, s.name, ' '.join(nums[:3])))
            break

print('=== A. 被技能实际引用的集合型术语（按引用数排序）===')
for t, rows in sorted(use.items(), key=lambda kv: -len(kv[1]))[:22]:
    mem = ds.members_of(t)
    print(f'\n【{t}】成员 {len(mem)} 名：{"、".join(mem[:12])}{"…" if len(mem) > 12 else ""}')
    seen = set()
    for room, name, nums in rows:
        if (room, name) in seen: continue
        seen.add((room, name))
        print(f'    ← [{room}] {name} {nums}')

print('\n\n=== B. 只按“种族”判定的术语 ===')
RACE_HINT = ('族',)
for t in COLLECTION:
    if any(h in t for h in RACE_HINT):
        print(f'  {t}: {ds.members_of(t)}')

print('\n=== C. 反查：关键干员分别属于哪些集合 ===')
for op in ('娜斯提', '缪尔赛思', '多萝西', '蕾缪安', '空弦', '塑心', '摩根', '推进之王',
           '重岳', '黍', '余', '令', '夕', '迷迭香', '真言', '巫恋', '斥罪', '伺夜', '阿罗玛',
           '褐果', '桃金娘', '承曦格雷伊', '菲亚梅塔', '虎狼丸', '史都华德'):
    ts = ds.terms_of_operator(op)
    print(f'  {op:<6} → {ts if ts else "（不属于任何集合型术语）"}')
