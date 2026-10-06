# -*- coding: utf-8 -*-
"""probe_combo_report.py —— 组合枚举 / 收益函数 / 权重与替补 / 单人榜，并生成本地组合表

做四件事（都是"语义→收益函数"的落地，不是抄攻略）：

1. **扫全部技能**，按效果语义打上机制标签（归零独占 / 设施计数 / 阵营计数 / 资源链 /
   分布改造 / 中枢增益 / 心情 / 仓库容量 / 充能 / 线索 / 联络），并从技能原文里抽出
   **合作对象**（"当与X在同一个…"、"如果X进驻在…"、"每有1名…干员"）与**资源术语**，
   用并查集把干员连成"组"。
2. 对每个组用本引擎**算实际收益**（贸易=币/时+分布；制造=件/时或经验/时；发电=架/时；
   会客=线索/天；办公=联络速度%）——这就是"把技能翻译成收益函数"。
3. **满配 vs 缺人（留一法）** → 稳健度 → 权重 → 档位；并按机制给出**替补规则**。
4. 把**所有**已持有干员在每个站的单人次效率全量排名（至简这类"按设施等级"的效果
   一律按最高等级计算，因为本引擎建模的房间就是 Lv3 / 宿舍 Lv5）。

产物：`planner/组合表.md`（人读）+ `planner/data/combos.json`（程序用）
"""
import os
import re
import sys
import json
import itertools
import collections

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

from core.dataset import Dataset, load_box, capacity          # noqa: E402
from core.engine import Ctx, eval_room, shift_output, power_charge, dorm_rooms_recovery  # noqa: E402
from core import orders, meeting                              # noqa: E402

OUT_MD = os.path.join(HERE, '组合表.md')
OUT_JSON = os.path.join(HERE, 'data', 'combos.json')
LAYOUT = {'制造站': [(3, 'Pure Gold')] * 3, '贸易站': [(3, 'LMD')] * 3,
          '发电站': [(3, None)] * 3, '宿舍': [(5, None)] * 4}

# ---------------------------------------------------------------- 语义标签
MECH = [
    ('归零独占', r'其他干员提供的(?:订单获取效率|生产力)全部归零|当前贸易站内干员提供的(?:订单获取效率|生产力)全部归零'),
    ('设施计数', r'每(?:个|座|间|条|有)?\s*\d*\s*(?:发电站|制造站|贸易站|宿舍|赤金生产线)|每级|设施数量'),
    ('阵营计数', r'每有\s*1\s*名[^，。；]{0,14}?(?:干员|[）)]|，)|同阵营|包含所有异格'),
    ('资源链', r'感知信息|思维链环|人间烟火|无声共鸣|巫术结晶|情报储备|热情值|木天蓼|小节|梦境|心情落差'),
    ('分布改造', r'高品质|违约订单|订单上限|特别订单|投资|贵金属订单的出现概率'),
    ('中枢增益', r'所有贸易站|所有制造站|所有干员的心情每小时恢复|控制中枢内'),
    ('心情', r'心情每小时(?:消耗|恢复)|互换心情|心情耗尽'),
    ('仓库容量', r'仓库容量上限|每格仓库容量'),
    ('充能', r'无人机充能速度'),
    ('线索', r'线索'),
    ('联络', r'人脉资源的联络速度|招募位|记忆碎片'),
]
GROUP_TERMS = ['深海猎人', '岁', '莱茵生命', '乌萨斯学生自治团', '企鹅物流', '龙门近卫局',
               '彩虹小队', '格拉斯哥帮', '黑钢国际', '拉特兰', '罗德岛', '企鹅物流',
               '伊比利亚', '卡西米尔', '炎', '维多利亚', '萨尔贡', '哥伦比亚', '谢拉格']
RES_TERMS = ['人间烟火', '感知信息', '思维链环', '无声共鸣', '巫术结晶', '情报储备', '热情值',
             '木天蓼', '小节', '梦境', '心情落差', '赤金生产线']


def ctx_of(ds, extra_rooms=None):
    lay = {k: list(v) for k, v in LAYOUT.items()}
    c = Ctx(ds=ds, layout=lay)
    c.by_room = {k: [] for k in lay}
    c.by_room.update(extra_rooms or {})
    c.staffed = [o for v in (extra_rooms or {}).values() for o in v]
    c.dorm_occ = 20
    return c


# ---------------------------------------------------------------- 收益函数
def plan_contact(team, ds):
    """人力办公室：联络速度% = 基础 5% + 各干员技能（同名效果取最高）。"""
    base = 5.0
    best = {}
    for op in team:
        for s in ds.skills_of(op, '人力办公室'):
            m = re.search(r'人脉资源的联络速度\+(\d+)%', s.desc or '')
            if m:
                best[s.name] = max(best.get(s.name, 0.0), float(m.group(1)))
    return base + sum(best.values())


def revenue(room, team, ds, product=None, hours=1.0):
    """把"谁在哪个房间"翻译成**收益函数**。返回 (主指标名, 数值, 备注dict)"""
    team = [o for o in team if o]
    if not team:
        return ('空', 0.0, {})
    c = ctx_of(ds)
    if room == '贸易站':
        prod = product or 'LMD'
        out, rep = shift_output('贸易站', 3, prod, team, c, hours, ds)
        eff = float(rep.get('eff') or 0)
        if prod == 'LMD':
            pr = orders.profile(team, ds, hours)
            return ('币/时', out.get('lmd', 0.0), dict(eff=eff, 耗金=out.get('gold_cost', 0.0),
                                                   分布=pr.get('dist')))
        return ('玉/时', out.get('orundum', 0.0), dict(eff=eff, 耗片=out.get('shard_cost', 0.0)))
    if room == '制造站':
        prod = product or 'Pure Gold'
        out, rep = shift_output('制造站', 3, prod, team, c, hours, ds)
        eff = float(rep.get('eff') or 0)
        if prod == 'Pure Gold':
            return ('件/时', out.get('gold', 0.0), dict(eff=eff))
        if prod == 'Battle Record':
            return ('经验/时', out.get('exp', 0.0), dict(eff=eff))
        return ('片/时', out.get('shard', 0.0), dict(eff=eff))
    if room == '发电站':
        dn, bonus = power_charge([team], hours, ds)
        return ('架/时', dn, dict(加成=bonus))
    if room == '会客室':
        sp = meeting.speed(team, ds, box=getattr(ds, '_box', None), hours=hours)
        return ('线索/天', sp['clue_per_day'], dict(速度=sp['speed']))
    if room == '人力办公室':
        return ('联络%', plan_contact(team, ds), {})
    if room == '宿舍':
        rr = dorm_rooms_recovery([team], ds)[0]
        return ('恢复/时', rr, {})
    if room == '控制中枢':
        # 中枢的收益体现在"别人"身上：贸易站 +7%（取最高）与减压
        bonus = 0.0
        for op in team:
            for s in ds.skills_of(op, '控制中枢'):
                m = re.search(r'所有贸易站订单效率\+(\d+)%', s.desc or '')
                if m:
                    bonus = max(bonus, float(m.group(1)))
        return ('全贸易站+%', bonus, {})
    return ('—', 0.0, {})


# ---------------------------------------------------------------- 组枚举
def scan_groups(ds, box):
    """语义扫描 → 组（并查集连边：同一技能的合作对象 / 同一资源术语 / 同一机制同房间）"""
    names = set(ds.op_skills.keys())
    parent = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    edges, tags_of = [], collections.defaultdict(set)
    for s in ds.skills:
        desc = s.desc or ''
        tags = [t for t, pat in MECH if re.search(pat, desc)]
        holders = [h for h in s.holders if h in names]
        partners = sorted({n for n in names if n in desc and n not in holders})
        terms = sorted({t for t in RES_TERMS if t in desc})
        facs = re.findall(r'每(?:个|座|间|条)?\s*\d*\s*(发电站|制造站|贸易站|宿舍|赤金生产线)', desc)
        groups = sorted({g for g in GROUP_TERMS if g in desc})
        for h in holders:
            for t in tags:
                tags_of[h].add(t)
            find(h)
        for a, b in itertools.combinations(holders, 2):
            union(a, b)
            edges.append((a, b, s.name, '同技能'))
        for h in holders:
            for p in partners:
                union(h, p)
                edges.append((h, p, s.name, '原文点名'))
        for h in holders:
            for t in terms:
                tags_of[h].add('资源链')
    # 资源提供者→消费者 连边
    for term, meta in (ds.terms or {}).items():
        provs = [p for p in (meta.get('providers') or []) if p in names]
        users = [h for h in names for s in ds.skills_of(h) if term in (s.desc or '')]
        for p in provs:
            for u in users:
                if p != u:
                    union(p, u)
                    edges.append((p, u, term, '资源链'))
    groups = collections.defaultdict(list)
    for n in list(parent):
        groups[find(n)].append(n)
    out = []
    for root, members in groups.items():
        if len(members) < 2:
            continue
        rooms = collections.Counter()
        for m in members:
            for s in ds.skills_of(m):
                rooms[s.room] += 1
        room = rooms.most_common(1)[0][0] if rooms else '控制中枢'
        tags = collections.Counter()
        for m in members:
            for t in tags_of.get(m, ()):
                tags[t] += 1
        # 相关技能原文（只留与该房间有关的）
        rows = []
        for s in ds.skills:
            if s.room != room:
                continue
            if any(h in members for h in s.holders):
                rows.append(dict(name=s.name, desc=s.desc, holders=[h for h in s.holders if h in members]))
        out.append(dict(members=sorted(members), room=room,
                        tags=[t for t, _ in tags.most_common(3)] or ['其他'],
                        skills=rows, size=len(members)))
    out.sort(key=lambda d: (-d['size'], d['room']))
    return out


def main():
    ds = Dataset()
    box = load_box()
    ds.set_box(box)
    owned = {n for n, v in box.items() if v.get('own')}
    groups = scan_groups(ds, box)

    # —— 每组：满配 / 留一法 / 权重 ——
    eval_rows = []
    for g in groups:
        members = g['members']
        own_members = [m for m in members if m in owned]
        room = g['room']
        prod = None
        txt = ' '.join(s['desc'] for s in g['skills'])
        if room == '制造站':
            prod = ('Battle Record' if '作战记录' in txt else
                    'Originium Shard' if ('源石' in txt and '贵金属' not in txt) else 'Pure Gold')
        if room == '贸易站':
            prod = 'Orundum' if ('合成玉' in txt or '源石订单' in txt) else 'LMD'
        need = capacity(room, 3)
        team_full = own_members[:need]
        metric, val, note = revenue(room, team_full, ds, prod)
        # 留一法（只对已持有成员），并算"缺一人后最佳剩余队"
        losses = []
        if len(team_full) >= 2:
            for i in range(len(team_full)):
                rest = team_full[:i] + team_full[i + 1:]
                _, v2, _ = revenue(room, rest, ds, prod)
                losses.append((team_full[i], val, v2, (v2 / val - 1) * 100 if val else 0.0))
        worst = min(losses, key=lambda x: x[2]) if losses else None
        robust = (worst[2] / val) if (worst and val) else (1.0 if len(team_full) < 2 else 0.0)
        eval_rows.append(dict(**g, own=[m for m in members if m in owned],
                              missing=[m for m in members if m not in owned],
                              need=need, product=prod, metric=metric,
                              value=round(val, 3), note={k: (round(v, 3) if isinstance(v, float) else v)
                                                         for k, v in note.items()},
                              leave_one_out=[dict(op=a, full=round(b, 3), rest=round(c, 3),
                                                  drop_pct=round(d, 1)) for a, b, c, d in losses],
                              robustness=round(robust, 3)))

    # 同房间内归一化 → 权重（满配收益 × 稳健度）
    by_room = collections.defaultdict(list)
    for r in eval_rows:
        by_room[r['room']].append(r)
    for room, rows in by_room.items():
        top = max([r['value'] for r in rows] or [0.0]) or 1.0
        for r in rows:
            r['norm_value'] = round(r['value'] / top, 3)
            r['weight'] = round(r['norm_value'] * r['robustness'], 3)
    for r in eval_rows:
        w = r.get('weight', 0.0)
        r['tier'] = 'S' if w >= 0.75 else 'A' if w >= 0.5 else 'B' if w >= 0.25 else 'C'
    eval_rows.sort(key=lambda r: (-r.get('weight', 0.0), -r['value']))

    # —— 所有干员的单人次效率（全量，不只 Top）——
    solo = {}
    for room, prod in (('贸易站', 'LMD'), ('贸易站', 'Orundum'), ('制造站', 'Pure Gold'),
                       ('制造站', 'Battle Record'), ('制造站', 'Originium Shard'),
                       ('发电站', None), ('会客室', None), ('人力办公室', None), ('宿舍', None)):
        rows = []
        for op in sorted(owned):
            try:
                m, v, note = revenue(room, [op], ds, prod)
            except Exception:
                continue
            rows.append(dict(op=op, metric=m, value=round(v, 3),
                             eff=round(note.get('eff', 0.0), 1) if 'eff' in note else None))
        rows.sort(key=lambda x: -x['value'])
        key = f'{room}|{prod or "-"}'
        solo[key] = rows

    # —— 生成文件 ——
    data = dict(meta=dict(generated_by='probe_combo_report.py', rooms=list(LAYOUT),
                          note='收益=本引擎实算；weight=同房间归一化收益×留一法稳健度'),
                groups=eval_rows, solo=solo)
    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    json.dump(data, open(OUT_JSON, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

    L = ['# 基建组合总表（语义解析 → 收益函数 → 权重/替补）', '',
         f'> 自动生成：`python planner\\probe_combo_report.py`；数据源 `data/skills_raw.json`（{len(ds.skills)} 条技能）',
         '> 收益全部由本引擎实算（333 布局、房间 Lv3、4×Lv5 宿舍满员）；"至简"这类按设施等级的技能一律按最高等级计。',
         f'> 扫描到 **{len(eval_rows)} 个可成组体系**；权重 = （同房间归一化收益）×（留一法稳健度）。', '']
    L += ['## 一、体系总表（按权重排序）', '',
          '| 档 | 权重 | 房间 | 组名（代表） | 组员 | 机制 | 满配收益 | 稳健度 | 缺一人最痛 | 缺人损失 |',
          '|---|---|---|---|---|---|---|---|---|---|']
    for r in eval_rows[:120]:
        lead = '/'.join(r['own'][:3]) or '/'.join(r['members'][:3])
        pain = ''
        if r['leave_one_out']:
            w = min(r['leave_one_out'], key=lambda x: x['rest'])
            pain = f"{w['op']}"
        L.append(f"| {r['tier']} | {r.get('weight', 0):.2f} | {r['room']} | {lead} | "
                 f"{'/'.join(r['members'][:6])}{'…' if len(r['members']) > 6 else ''} | "
                 f"{'/'.join(r['tags'])} | {r['value']}{r['metric']} | {r['robustness']:.2f} | "
                 f"{pain} | {(min([x['drop_pct'] for x in r['leave_one_out']]) if r['leave_one_out'] else 0):.0f}% |")
    L += ['', '## 二、单人等效效率全量榜（每个站，已持有干员）', '']
    for key, rows in solo.items():
        room, prod = key.split('|')
        L.append(f'### {room}{"（" + prod + "）" if prod != "-" else ""}（{len(rows)} 人）')
        L.append('')
        L.append('| 名次 | 干员 | 数值 | ' + rows[0]['metric'] + ' | 效率% |')
        L.append('|---|---|---|---|---|')
        for i, r in enumerate(rows[:40], 1):
            L.append(f"| {i} | {r['op']} | {r['value']} | {r['metric']} | {r['eff'] if r['eff'] is not None else '—'} |")
        L.append('')
    open(OUT_MD, 'w', encoding='utf-8').write('\n'.join(L))

    print(f'扫描到体系 {len(eval_rows)} 个；单人榜 {sum(len(v) for v in solo.values())} 条')
    print('权重 Top20：')
    for r in eval_rows[:20]:
        print(f"  [{r['tier']}] w={r.get('weight', 0):.2f} {r['room']:<5} "
              f"{'/'.join(r['members'][:4]):<34} {r['value']}{r['metric']:<6} "
              f"稳健 {r['robustness']:.2f} 机制 {'/'.join(r['tags'])}")
    print(f'\n已写出 {OUT_MD}')
    print(f'已写出 {OUT_JSON}')


if __name__ == '__main__':
    main()
