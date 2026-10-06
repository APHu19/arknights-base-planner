# -*- coding: utf-8 -*-
"""faction_queries.py —— 生成《势力/种族查询清单.md》
格式严格按用户给定：
    =国家=
    ==拉特兰==
    {{#ask:[[分类:干员]][[国家::拉特兰]]}}
值取自技能库中**真实被基建技能引用**的集合型术语；并附我方抽取的成员名单做交叉核验。
"""
import sys, os, re
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.dataset import Dataset

ds = Dataset()
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '势力种族查询清单.md')

# 属性归类（依据 PRTS 的语义属性；不确定的同时给出候选属性，贴上去哪个有结果就用哪个）
NATION = {'拉特兰', '叙拉古', '维多利亚', '乌萨斯', '炎', '龙门', '哥伦比亚', '萨尔贡', '谢拉格',
          '卡西米尔', '玻利瓦尔', '阿戈尔', '萨米', '伊比利亚', '莱塔尼亚', '雷姆必拓', '米诺斯',
          '汐斯塔', '东', '高卢', '杜林'}
RACE = {'杜林族'}
SKILLCLASS = {'标准化类技能', '金属工艺类技能', '莱茵科技类技能', '莱茵科技类', '金属工艺类'}
FACILITY = {'其他设施', '工作场所'}

# 被技能引用到的术语
used = {}
for s in ds.skills:
    for t in ds.globals:
        if t in (s.desc or '') or t in (s.name or ''):
            used.setdefault(t, []).append((s.room, s.name, s.desc[:0]))
collections = {t: ds.members_of(t) for t in used if ds.members_of(t)}
skillclasses = {t: [] for t in used if t in SKILLCLASS}

L = []
L.append('# 势力 / 种族 / 小队 查询清单（用于核对基建技能判定对象）')
L.append('')
L.append('> 说明：值取自《后勤技能一览带注释.md》中**真实被基建技能引用**的术语，共 '
         f'{len(collections) + len(skillclasses)} 个。')
L.append('> 每块下方 `<!-- 我方抽取 -->` 是本地从技能表解析出的成员名单，可与你查询结果对照；')
L.append('> 若某块查不到，说明该属性名不是 PRTS 的属性名（见文末“属性名自检”）。')
L.append('')

def section(title, items, prop_candidates):
    L.append(f'={title}=')
    L.append('')
    for term in sorted(items):
        props = prop_candidates(term)
        L.append(f'=={term}==')
        for p in props:
            L.append(f'{{{{#ask:[[分类:干员]][[{p}::{term}]]}}}}')
        mem = items[term]
        users = sorted({f'{r}/{n}' for r, n, _ in used.get(term, [])})
        if mem:
            L.append(f'<!-- 我方抽取：{"、".join(mem)}（共 {len(mem)}） -->')
        L.append(f'<!-- 引用它的技能：{"、".join(users[:12])} -->')
        L.append('')

nat = {t: m for t, m in collections.items() if t in NATION}
rac = {t: m for t, m in collections.items() if t in RACE}
fac = {t: m for t, m in collections.items() if t in FACILITY}
squad = {t: m for t, m in collections.items() if t not in NATION | RACE | FACILITY}

section('国家', nat, lambda t: ['国家', '势力'])
section('种族', rac, lambda t: ['种族', '国家'])
section('势力 / 组织 / 小队', squad, lambda t: ['势力', '团队', '国家'])
section('设施集合', fac, lambda t: ['设施', '势力'])

L.append('=技能类集合=')
L.append('')
L.append('> 这类不是干员集合，而是**按技能名计数**的类型（你的“水月/标准化”问题属于此类）。')
L.append('')
for term in sorted(skillclasses):
    L.append(f'=={term}==')
    L.append(f'{{{{#ask:[[分类:技能]][[所属技能类::{term}]]}}}}')
    names = ds.standard_skill_names() if '标准化' in term else []
    if names:
        L.append(f'<!-- 我方抽取的技能名：{"、".join(names)} -->')
    L.append('')

L.append('=属性名自检=')
L.append('')
L.append('> 若上面某块没有结果，用下面三行分别探测“属性是否存在 / 取值写法”。')
L.append('')
for p in ('国家', '势力', '团队', '种族', '出身地'):
    L.append(f'=={p}==')
    L.append(f'探测（列出所有取值）：{{{{#ask:[[分类:干员]][[{p}::+]]|limit=50|link=none|format=list}}}}')
    L.append('')

open(OUT, 'w', encoding='utf-8').write('\n'.join(L))
print(f'已写出 {OUT}')
print(f'集合型术语 {len(collections)} 个（国家 {len(nat)} / 种族 {len(rac)} / 势力小队 {len(squad)} / 设施 {len(fac)}）；技能类 {len(skillclasses)} 个')
print('\n---- 文件开头示例 ----')
print('\n'.join(L[:34]))
