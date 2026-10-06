# -*- coding: utf-8 -*-
"""objectives.py —— 组合式目标系统（主目标 × 赤金收支 × 碎片收支 × 心情底线）

设计：把“想要什么”拆成四个正交维度，任意组合都能表达，覆盖面远大于固定预设：
  主目标 MAIN：玉 / 龙门币 / 经验 / 无人机 / 均衡
  赤金收支 GOLD：不限 / 囤金 / 烧库存 / 平衡 / 不得净亏 / 不得净囤
  碎片收支 SHARD：不限 / 囤碎片 / 烧库存 / 平衡 / 产能≥玉站消化 / 不得净亏 / 不得净囤
  心情底线 MORALE：不限 / 12 / 16 / 20

资源偏好项按“主目标量级的 15%”自动加权（否则 90 枚赤金 对 45,000 龙门币 毫无影响）。
旧的 14 个固定预设保留为快捷方式（`OBJECTIVES`），内部仍走同一套 score()。
"""
MAIN_SCALE = {'yu': 900.0, 'lmd': 45000.0, 'exp': 30000.0, 'drones': 700.0,
              'balanced': 45000.0, 'clue': 4.0}
TYPICAL = {'gold': 90.0, 'gold_cost': 90.0, 'shard': 50.0, 'shard_cost': 50.0,
           'gold_net': 90.0, 'shard_net': 50.0}
RES_SHARE = 0.15          # 资源偏好项占主目标量级的比例

MAINS = {
    'yu': dict(name='合成玉最大化', w={'yu': 1.0},
               order=['Orundum', 'Originium Shard', 'LMD', 'Pure Gold', 'power']),
    'lmd': dict(name='龙门币最大化', w={'lmd': 1.0},
                order=['LMD', 'Pure Gold', 'Orundum', 'Originium Shard', 'power']),
    'exp': dict(name='经验最大化（中级作战记录）', w={'exp': 1.0},
                order=['Battle Record', 'LMD', 'Pure Gold', 'power', 'Orundum']),
    'drones': dict(name='无人机充能最大化', w={'drones': 1.0, 'lmd': 0.0},
                   order=['power', 'LMD', 'Pure Gold', 'Orundum', 'Originium Shard']),
    'balanced': dict(name='均衡（龙门币+玉+经验）', w={'lmd': 1.0, 'yu': 20.0, 'exp': 0.02},
                     order=['Pure Gold', 'LMD', 'Orundum', 'Originium Shard', 'power']),
    # 会客室线索（基础 126% + 干员档 + 后勤技能%；20 小时/份）
    'clue': dict(name='会客室线索速度最大化', w={'clue': 1.0},
                 order=['会客室', 'LMD', 'Pure Gold', 'Orundum', 'Originium Shard', 'power']),
}
GOLD_MODES = {
    'none': dict(name='不限赤金收支', w={}, cons={}),
    'produce': dict(name='尽量多产赤金（囤金）', w={'gold': 1.0, 'gold_net': 1.0}, cons={}),
    'consume': dict(name='尽量多消耗赤金（烧库存）', w={'gold_cost': 1.0}, cons={}),
    'balance': dict(name='赤金收支平衡（净≈0）', w={}, cons={'gold_net': (-1.0, 1.0)}),
    'no_deficit': dict(name='赤金不得净亏（净≥0）', w={}, cons={'gold_net': (0.0, None)}),
    'no_surplus': dict(name='赤金不得净囤（净≤0）', w={}, cons={'gold_net': (None, 0.0)}),
}
SHARD_MODES = {
    'none': dict(name='不限碎片收支', w={}, cons={}),
    'produce': dict(name='尽量多产碎片（囤碎片）', w={'shard': 1.0, 'shard_net': 1.0}, cons={}),
    'consume': dict(name='尽量多消耗碎片（烧库存）', w={'shard_cost': 1.0}, cons={}),
    'balance': dict(name='碎片收支平衡（净≈0）', w={}, cons={'shard_net': (-1.0, 1.0)}),
    'ge_trade': dict(name='碎片产能 ≥ 玉站消化', w={}, cons={'shard_ge_trade': True}),
    'no_deficit': dict(name='碎片不得净亏（净≥0）', w={}, cons={'shard_net': (0.0, None)}),
    'no_surplus': dict(name='碎片不得净囤（净≤0）', w={}, cons={'shard_net': (None, 0.0)}),
}
MORALE_FLOORS = {'none': None, '12': 12.0, '16': 16.0, '20': 20.0}


def build(main='lmd', gold='none', shard='none', morale='none',
          order_override=None, name=None):
    """组合式构造目标。返回可直接喂给 score()/joint_solve() 的 props"""
    if main not in MAINS: raise KeyError(f'未知主目标 {main}：{list(MAINS)}')
    if gold not in GOLD_MODES: raise KeyError(f'未知赤金条件 {gold}：{list(GOLD_MODES)}')
    if shard not in SHARD_MODES: raise KeyError(f'未知碎片条件 {shard}：{list(SHARD_MODES)}')
    scale = MAIN_SCALE.get(main, 45000.0)
    w = dict(MAINS[main]['w'])
    cons = {}
    for table, key in ((GOLD_MODES, gold), (SHARD_MODES, shard)):
        m = table[key]
        for k, v in m['w'].items():
            w[k] = w.get(k, 0.0) + v * (RES_SHARE * scale / max(1.0, TYPICAL.get(k, 1.0)))
        cons.update(m['cons'])
    fl = MORALE_FLOORS.get(str(morale))
    if fl is not None:
        cons['min_morale'] = (fl, None)
    parts = [MAINS[main]['name'], GOLD_MODES[gold]['name'], SHARD_MODES[shard]['name']]
    if fl is not None: parts.append(f'心情底线 {fl:g}')
    # 含碎片约束时，必须**先排碎片站再排玉站**：否则玉站先把强干员挑走、碎片不够，
    # 预算修复只能把玉站降级成弱队（实测会从 ~600 玉掉到 240）。
    order = list(order_override or MAINS[main]['order'])
    if shard in ('ge_trade', 'no_deficit', 'balance') and 'Originium Shard' in order:
        order.remove('Originium Shard')
        order.insert(0, 'Originium Shard')
    return dict(key=f'{main}|{gold}|{shard}|{morale}',
                name=name or ' · '.join(parts), w=w, cons=cons,
                order=order, main=main, gold=gold, shard=shard, morale=str(morale))


# ---------------- 旧固定预设（快捷方式，供 CLI/GUI 直接选） ----------------
_PRESET_SPECS = {
    'lmd_max': ('lmd', 'none', 'none', 'none'),
    'lmd_gold_bal': ('lmd', 'no_deficit', 'none', 'none'),
    'lmd_morale_safe': ('lmd', 'no_deficit', 'none', '16'),
    'gold_burn': ('lmd', 'consume', 'none', 'none'),
    'gold_balance': ('lmd', 'balance', 'none', 'none'),
    'gold_hoard': ('balanced', 'produce', 'none', 'none'),
    'yu_max': ('yu', 'none', 'none', 'none'),
    'yu_ge_trade': ('yu', 'none', 'ge_trade', 'none'),
    'yu_then_lmd': ('yu', 'none', 'ge_trade', 'none'),
    'shard_max': ('balanced', 'none', 'produce', 'none'),
    'exp_max': ('exp', 'no_deficit', 'none', 'none'),
    'exp_lmd_mix': ('exp', 'no_deficit', 'none', 'none'),
    'drone_max': ('drones', 'none', 'none', 'none'),
    'balanced': ('balanced', 'no_deficit', 'none', 'none'),
    # 新增：库存消耗/囤积向
    'burn_both': ('lmd', 'consume', 'consume', 'none'),
    'burn_shard': ('yu', 'none', 'consume', 'none'),
    'hoard_both': ('balanced', 'produce', 'produce', 'none'),
}
OBJECTIVES = {}
for _k, (_m, _g, _s, _mo) in _PRESET_SPECS.items():
    o = build(_m, _g, _s, _mo)
    o['key'] = _k
    OBJECTIVES[_k] = dict(name=o['name'], desc=f'主目标={MAINS[_m]["name"]}；赤金={GOLD_MODES[_g]["name"]}；'
                                              f'碎片={SHARD_MODES[_s]["name"]}',
                          w=o['w'], cons=o['cons'], order=o['order'], key=_k,
                          main=_m, gold=_g, shard=_s, morale=_mo)

PENALTY = {'gold_net': 1e4, 'shard_net': 1e4, 'min_morale': 5e3, 'shard_ge_trade': 2e3}


def get(name):
    """取目标：既支持旧预设名，也支持 'main|gold|shard|morale' 组合串"""
    if name in OBJECTIVES:
        o = dict(OBJECTIVES[name]); o['key'] = name; return o
    if '|' in str(name):
        m, g, s, mo = (str(name).split('|') + ['none'] * 4)[:4]
        return build(m, g, s, mo)
    raise KeyError(f'未知目标 {name}；可选：{list(OBJECTIVES)}，或组合串 main|gold|shard|morale')


def score(kpi, objective, price=None):
    """目标值 − 约束罚项 − 影子价格成本"""
    v = 0.0
    for k, w in objective['w'].items():
        v += w * float(kpi.get(k, 0.0))
    if price:
        v -= price.get('gold', 0.0) * float(kpi.get('gold_cost', 0.0))
        v -= price.get('shard', 0.0) * float(kpi.get('shard_cost', 0.0))
    pen = 0.0
    cons = objective.get('cons') or {}
    for key in ('gold_net', 'shard_net'):
        rng = cons.get(key)
        if not rng: continue
        lo, hi = rng
        val = kpi.get(key, 0.0)
        if lo is not None and val < lo: pen += (lo - val) * PENALTY[key]
        if hi is not None and val > hi: pen += (val - hi) * PENALTY[key]
    mm = cons.get('min_morale')
    if mm:
        lo = mm[0]
        if kpi.get('min_morale', 99) < lo:
            pen += (lo - kpi['min_morale']) * PENALTY['min_morale']
    if cons.get('shard_ge_trade'):
        need = kpi.get('shard_cost', 0.0)
        have = kpi.get('shard', 0.0)
        if have < need:
            pen += (need - have) * PENALTY['shard_ge_trade']
    return v - pen


def slot_priority(objective, product, room):
    key = product or room
    order = objective.get('order') or []
    return order.index(key) if key in order else len(order)
