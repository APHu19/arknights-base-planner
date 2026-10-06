# -*- coding: utf-8 -*-
"""maa.py —— 写出 MAA 自定义基建计划 + 协议校验 + 人读报告

必须遵守的协议要点（都是本轮踩坑得来）：
  · rooms 只允许 8 种键：trading/manufacture/power/control/meeting/hire/dormitory/processing
    —— **没有 training**；训练室整项不写入（= 不放人）
  · product 只能取 Pure Gold / Originium Shard / LMD / Orundum / Battle Record / Dualchip
  · drones.index 是**标签号，1 基**，范围 [1,5]；room 只能是 trading/manufacture
  · Fiammetta.order 必须 'pre'（否则会把目标干员拉进寝室不放回）
  · 寝室放在 rooms 的**最后**处理；1 号寝室 sort=true 且菲亚梅塔在首位
"""
import json, time, collections

ROOM_ORDER = ['trading', 'manufacture', 'power', 'control', 'meeting', 'hire', 'processing', 'dormitory']
MAA_ROOM = {'贸易站': 'trading', '制造站': 'manufacture', '发电站': 'power', '控制中枢': 'control',
            '会客室': 'meeting', '人力办公室': 'hire', '加工站': 'processing', '宿舍': 'dormitory'}
PROD_OK = {'Pure Gold', 'Originium Shard', 'LMD', 'Orundum', 'Battle Record', 'Dualchip'}
FIA = '菲亚梅塔'
SHIFT_TIME = ['00:00-04:00', '04:00-08:00', '08:00-12:00', '12:00-16:00', '16:00-20:00', '20:00-24:00']


def deck_from_plan(plan, objective, layout_name='333', title=None, author='aphu + DSH'):
    shifts = plan['shifts']
    # 无人机目标：按目标优先级在“制造站/贸易站”里各挑一个实例
    def inst_index(room_name, product_pref):
        for idx, (room, prod, lv, ops) in enumerate(_layout_instances(plan, room_name)):
            if prod == product_pref:
                return idx + 1
        return 1
    mani_pref, trade_pref = _drone_prefs(objective)
    mi = inst_index('制造站', mani_pref)
    ti = inst_index('贸易站', trade_pref)
    plans = []
    for i, s in enumerate(shifts):
        rooms = collections.OrderedDict((k, []) for k in ROOM_ORDER)
        for (room, product, level, team) in s['rooms']:
            key = MAA_ROOM[room]
            inst = {'skip': False}
            if product: inst['product'] = product
            inst.update(operators=list(team), sort=False, autofill=False)
            rooms[key].append(inst)
        for k in range(4):
            ops = list((s['dorm'][k] if k < len(s['dorm']) else []))
            if k == 0 and FIA in ops:                      # 1 号寝室：菲亚梅塔必须在首位
                ops = [FIA] + [o for o in ops if o != FIA]
            rooms['dormitory'].append({'skip': False, 'operators': ops,
                                       'sort': (k == 0), 'autofill': False})
        fia = s.get('fia') or {}
        # 无人机：优先用计划里按目标分配好的目标（solve/drones.py），否则回退到奇偶交替
        dt = s.get('drones')
        if dt:
            drone_room, drone_index = dt['room'], int(dt['index'])
        else:
            drone_room = 'manufacture' if i % 2 == 0 else 'trading'
            drone_index = mi if drone_room == 'manufacture' else ti
        plans.append({
            'name': f'第{i+1:02d}班（{SHIFT_TIME[i]}）',
            'description': f"{objective}｜{'制造站' if i % 2 == 0 else '贸易站'}加速",
            'description_post': '',
            'Fiammetta': {'enable': bool(fia.get('enable') and fia.get('target')),
                          'target': fia.get('target') or '', 'order': 'pre'},
            'drones': {'enable': True, 'room': drone_room,
                       'index': drone_index, 'order': 'pre'},
            'rooms': rooms,
        })
    return {'author': author,
            'id': int(time.time() * 1000),
            'title': title or f'{layout_name} 基建排班（{objective}）',
            'description': f'由 planner 自动枚举生成；目标={objective}；训练室不放人；寝室最后处理；菲亚梅塔 order=pre',
            'planTimes': '6班',
            'scheduleType': {'planTimes': 6, 'trading': 3, 'manufacture': 3, 'power': 3, 'dormitory': 4},
            'plans': plans}


def _layout_instances(plan, room_name):
    """从班次里抽出某类房间的实例顺序（按第一次出现）"""
    seen, out = set(), []
    for s in plan['shifts']:
        for (room, prod, lv, ops) in s['rooms']:
            if room != room_name: continue
            key = tuple(sorted(ops))
            if key in seen: continue
            seen.add(key); out.append((room, prod, lv, ops))
    return out


def _drone_prefs(objective):
    if objective.startswith('yu') or objective == 'shard_max':
        return 'Originium Shard', 'Orundum'
    if objective.startswith('exp'):
        return 'Battle Record', 'LMD'
    return 'Pure Gold', 'LMD'


def validate(doc, owned=None):
    """协议校验：返回问题列表（空 = 通过）"""
    issues = []
    if doc.get('planTimes') != '6班': issues.append('planTimes 应为 6班')
    for i, p in enumerate(doc.get('plans', [])):
        tag = f'第{i+1}班'
        for k in p:
            if k not in ('name', 'description', 'description_post', 'Fiammetta', 'drones', 'rooms',
                         'period', 'duration', 'groups'):
                issues.append(f'{tag} 未知字段 {k}')
        rooms = p.get('rooms') or {}
        if list(rooms)[-1] != 'dormitory':
            issues.append(f'{tag} 寝室必须放在 rooms 最后（当前最后是 {list(rooms)[-1]}）')
        for rk in rooms:
            if rk not in ROOM_ORDER:
                issues.append(f'{tag} 非法房间键 {rk}（training 不属于协议！）')
        cnt = collections.Counter()
        for rk, insts in rooms.items():
            for inst in insts:
                if inst.get('product') and inst['product'] not in PROD_OK:
                    issues.append(f'{tag} 非法产品 {inst["product"]}')
                for nm in inst.get('operators', []):
                    cnt[nm] += 1
        dup = [k for k, v in cnt.items() if v > 1]
        if dup: issues.append(f'{tag} 同一班次重复用工 {dup}')
        if owned is not None:
            miss = [k for k in cnt if k not in owned]
            if miss: issues.append(f'{tag} 未持有干员 {miss}')
        fia = p.get('Fiammetta') or {}
        if fia.get('order') != 'pre':
            issues.append(f'{tag} Fiammetta.order 必须为 pre')
        d = p.get('drones') or {}
        if d.get('room') not in ('trading', 'manufacture'):
            issues.append(f'{tag} drones.room 非法 {d.get("room")}')
        if not (1 <= int(d.get('index', 0)) <= 5):
            issues.append(f'{tag} drones.index 必须在 [1,5]')
        dorm = rooms.get('dormitory') or []
        if dorm:
            if not dorm[0].get('sort'):
                issues.append(f'{tag} 1 号寝室必须 sort=true')
            ops0 = dorm[0].get('operators') or []
            if FIA in ops0 and ops0[0] != FIA:
                issues.append(f'{tag} 菲亚梅塔必须在 1 号寝室首位')
    return issues


def report(plan, doc, kpi, objective, layout_name, extra_lines=()):
    L = []
    L.append('=' * 92)
    L.append(f'{layout_name} 基建排班 · 目标：{objective}')
    L.append('=' * 92)
    L.append(f"合成玉 {kpi.get('yu',0):,.0f}/天｜龙门币 {kpi.get('lmd',0):,.0f}/天｜经验 {kpi.get('exp',0):,.0f}/天")
    L.append(f"赤金 产 {kpi.get('gold',0):.2f} / 耗 {kpi.get('gold_cost',0):.2f} / 净 {kpi.get('gold_net',0):+.2f}"
             f"｜碎片 产 {kpi.get('shard',0):.2f} / 耗 {kpi.get('shard_cost',0):.2f}"
             f"｜无人机 {kpi.get('drones',0):.0f}/天")
    L.append(f"14 天最低心情 {kpi.get('min_morale',0):.1f}（{kpi.get('min_who','')}）"
             f"｜低于10的人数 {sum(1 for v in (kpi.get('lows') or {}).values() if v < 10)}")
    L += list(extra_lines)
    L.append('')
    L.append('—— 六班安排 ——')
    for i, p in enumerate(doc['plans']):
        r = p['rooms']
        L.append(f"[{p['name']}]")
        for rk, cn in (('trading', '贸易'), ('manufacture', '制造'), ('power', '发电'),
                       ('control', '控制'), ('meeting', '会客'), ('hire', '办公'), ('processing', '加工')):
            if r.get(rk):
                L.append(f"   {cn}: " + ' | '.join(
                    f"{inst.get('product','')}{'/'.join(inst['operators'])}" for inst in r[rk]))
        L.append(f"   寝室: " + ' || '.join('/'.join(inst['operators']) for inst in r['dormitory']))
        L.append(f"   菲亚梅塔={p['Fiammetta']}  无人机→{p['drones']['room']}#{p['drones']['index']}")
    return '\n'.join(L)
