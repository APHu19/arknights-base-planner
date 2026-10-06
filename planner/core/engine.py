# -*- coding: utf-8 -*-
"""engine.py —— 结算引擎（按优先级依次操作）

结算流水线（顺序即优先级，每一步都记录到报告里）：
  P0 collect        收集房间内干员与技能
  P1 normalize_types 类型改写：把可被改写的生产技能临时标记为“标准化类”
  P2 count_globals  统计派生全局量：赤金生产线 / 标准化类技能数 / 外势 / 实地 / 势力数 / 配方类型数
  P3 room_nullify   房间级归零：温蒂·森蚺·冬时等使他人生产力归零（仅保留设施数/全局量类加成）
  P4 self_effects   逐干员自身效果（产品适配、通用、条件加成、体系消费）
  P5 room_caps      房间级收口：同种效果取最高、订单上限、效率上限
  P6 resources      全局资源池（人间烟火/感知信息/思维链环/无声共鸣/巫术结晶/情报储备…）

心情模型（已验证）：
  * “自身心情每小时消耗±X”只作用于本人；“所有干员/当前贸易站内…消耗±X”才是房间级
  * 工作消耗 = 1.0/h − 0.05×(人数−1) + 自身修正 − 控制中枢减压
  * 宿舍恢复 = 4.0/h(Lv5满氛围) + 该房间最高的“所有干员心情恢复+X”（按人各算、不摊）
"""
import re, json, os, collections
from .dataset import Dataset, load_box, ROOMS, MAA_ROOM

MAX_MORALE = 24.0
DORM_BASE = 4.0
WORKSHIFT_HOURS = 4.0          # 默认 4h/班，可覆盖

ROOM_OF_MAA = {v: k for k, v in MAA_ROOM.items()}


# ---------------------------------------------------------------- 基础解析
def _num(s):
    m = re.search(r'([\d.]+)', s or '')
    return float(m.group(1)) if m else 0.0


def morale_mods(d, room):
    """返回 (自身修正, 房间全员修正, 房间**其他**干员修正)（每人每小时）"""
    self_m = room_m = others_m = 0.0
    for m in re.finditer(r'心情每小时消耗([+\-])([\d.]+)', d):
        sign = 1 if m.group(1) == '+' else -1
        val = sign * float(m.group(2))
        pre = d[max(0, m.start() - 16):m.start()]
        if '其他' in pre:
            others_m += val
        elif any(k in pre for k in ('所有', '站内', '房间内', '全体')):
            room_m += val
        else:
            self_m += val
    return self_m, room_m, others_m


def room_recovery(d):
    m = re.search(r'所有干员的心情每小时恢复\+([\d.]+)', d)
    return float(m.group(1)) if m else 0.0


class Ctx:
    """全局环境：基建布局 + 资源池"""
    def __init__(self, layout=None, ds=None, box=None):
        self.ds = ds or Dataset()
        self.box = box if box is not None else load_box()
        self.layout = layout or {'制造站': [(3, 'Pure Gold')] * 3, '贸易站': [(3, 'LMD')] * 3,
                                 '发电站': [(3, None)] * 3, '宿舍': [(5, None)] * 4}
        self.res = {}
        self.dorm_occ = 20          # 宿舍满员人数（迷迭香超感/乌有愿者上钩都吃这个）
        self.staffed = []           # 全基建在岗干员（势力/人数类技能读它）
        self.elite_facilities = 1   # 进驻精英干员的设施数（真言·精英小队）
        self.drone_cap = 235        # 无人机上限（承曦格雷伊·巡线框架读它）
        self.by_room = {}           # {房间: [干员]} 全基建在岗分布（跨房间加成读它，如深海猎人）

    # ---- 布局派生：各房间实例 ----
    def rooms(self, room=None):
        return {k: v for k, v in self.layout.items() if room is None or k == room}

    def count(self, room):
        return len(self.layout.get(room, []))

    def gold_lines(self):
        """赤金生产线基础值 = 生产赤金的制造站数量（可被技能增加，故先算基础再迭代）"""
        return sum(1 for lv, prod in self.layout.get('制造站', []) if prod == 'Pure Gold')

    def base_resources(self):
        r = dict(self.res)
        r['赤金生产线'] = self.gold_lines()
        r['外势'] = self.count('贸易站') + self.count('发电站')
        r['实地'] = self.count('制造站')
        r.setdefault('人间烟火', 0.0); r.setdefault('感知信息', 0.0); r.setdefault('无声共鸣', 0.0)
        r.setdefault('思维链环', 0.0); r.setdefault('巫术结晶', 0.0); r.setdefault('情报储备', 0.0)
        r.setdefault('热情值', 0.0); r.setdefault('木天蓼', 0.0); r.setdefault('心情落差', 0.0)
        return r


# ---------------------------------------------------------------- 房间结算
ZEROERS = {'温蒂', '森蚺', '冬时'}          # 使房间内其他干员生产力归零
ZERO_KEEP = ('设施', '每有', '赤金生产线', '配方', '势力', '标准化')   # 归零时仍生效的加成类型


def _product_ok(skill, product):
    """产品适配：贵金属类配方 → 只对赤金；源石类配方 → 只对源石碎片；其余为通用，两边都吃"""
    d = skill.desc
    if '贵金属类配方' in d:
        return product == 'Pure Gold'
    if '源石类配方' in d:
        return product == 'Originium Shard'
    return True


def eval_room(room, level, product, team, ctx, ds=None, log=None):
    """结算一个房间。返回详细报告（含逐干员效率、心情、消耗、参与的全局量）"""
    ds = ds or ctx.ds
    log = log if log is not None else []
    n = len(team)
    # ---- P0 collect ----
    members = {op: ds.skills_of(op, room) for op in team}
    log.append(('P0 collect', {op: [s.name for s in v] for op, v in members.items()}))

    # ---- P1 normalize_types：类型改写（标准化类） ----
    forced = set()
    for op, skl in members.items():
        for s in skl:
            if '标准化类技能' in s.desc and ('改为' in s.desc or '视为' in s.desc or '变成' in s.desc):
                forced.add(op)
    changed = []
    if forced:
        for op, skl in members.items():
            if op in forced: continue
            for s in skl:
                if '生产力' in s.desc or '订单获取效率' in s.desc:
                    changed.append((op, s.name))
    log.append(('P1 normalize_types', {'改写者': sorted(forced), '被改写': changed}))

    # ---- P2 count_globals ----
    std_count = 0
    for op, skl in members.items():
        for s in skl:
            if ds.is_standardized(s) or (op in forced):
                std_count += 1
    res = dict(ctx.base_resources())
    res['标准化类技能数'] = std_count
    log.append(('P2 count_globals', {'标准化类技能数': std_count, '赤金生产线': res['赤金生产线'],
                                     '外势': res['外势'], '实地': res['实地']}))
    res_p = _resolve_resources(ctx, team, res, ds)          # P6 资源池（先算好供 P4 读）
    log.append(('P6 resources', res_p))

    # ---- P3 room_nullify ----
    zeroed = any(op in ZEROERS for op in team)
    log.append(('P3 room_nullify', {'触发': zeroed, '来源': [o for o in team if o in ZEROERS]}))

    # ---- P4 self_effects ----
    detail, base = {}, 0.0
    for op in team:
        add, notes = 0.0, []
        for s in members[op]:
            d = s.desc
            if not _product_ok(s, product):
                notes.append(f'{s.name}:产品不适用'); continue
            m = re.search(r'生产力\+(\d+)%', d)
            if m:
                v = float(m.group(1)); add += v; notes.append(f'{s.name}:生产力+{v:g}%')
            m = re.search(r'订单获取效率\+(\d+)%', d)
            if m:
                v = float(m.group(1)); add += v if room == '贸易站' else 0
                notes.append(f'{s.name}:订单效率+{v:g}%')
            # 体系消费型
            if s.name == '意识实体':                       # 迷迭香：思维链环→生产力
                v = res_p.get('思维链环', 0.0); add += v; notes.append(f'{s.name}:思维链环{v:g}%')
            if s.name == '稻禾厚，顺秋收':                  # 黍：每3点人间烟火+1%生产力
                v = res_p.get('人间烟火', 0.0) / 3; add += v; notes.append(f'{s.name}:人间烟火/3={v:g}%')
            if s.name == '“愿者上钩”':                     # 乌有：宿舍人数→人间烟火→订单效率
                v = res_p.get('人间烟火', 0.0); add += v if room == '贸易站' else 0
                notes.append(f'{s.name}:人间烟火{v:g}%')
            if s.name == '销路宣发':                        # 鸿雪：赤金生产线→订单效率
                v = 5 * res_p.get('赤金生产线', 0.0); add += v if room == '贸易站' else 0
                notes.append(f'{s.name}:赤金生产线×5={v:g}%')
            if '外势' in d and room == '贸易站' and res_p['外势'] >= res_p['实地']:
                add += 7; notes.append(f'{s.name}:外势≥实地 +7%')
            if '实地' in d and room == '制造站' and res_p['实地'] > res_p['外势']:
                add += 2; notes.append(f'{s.name}:实地>外势 +2%')
        if zeroed and op not in ZEROERS:
            if any('设施' in x or '每有' in x or '生产线' in x or '配方' in x for x in notes):
                notes.append('（归零者：仅保留计数/设施类）')
                add = sum(float(re.search(r'\+([\d.]+)', x).group(1)) for x in notes if '设施' in x or '生产线' in x)
            else:
                notes.append('（归零者：生产力归零）'); add = 0.0
        detail[op] = dict(contrib=add, notes=notes)

    # ---- P4.5 优先级改写类（“先归零他人，再按他人数量给自己加成”）----
    if room == '贸易站' and any('低语' in s.name for s in members.get('巫恋', [])):
        for op in team:
            if op == '巫恋': continue
            detail[op]['notes'].append('（巫恋·低语：他人订单效率归零）')
            detail[op]['contrib'] = 0.0
        bonus = 45.0 * (n - 1)
        detail['巫恋']['contrib'] += bonus
        detail['巫恋']['notes'].append(f'（低语：{n-1} 名其他干员 ×45% = +{bonus:g}%）')
        log.append(('P4.5 lowwhisper', {'归零人数': n - 1, '巫恋额外': bonus}))
    base = sum(v['contrib'] for v in detail.values())
    log.append(('P4 self_effects', {op: v['notes'] for op, v in detail.items()}))

    # ---- P5 room_caps ----
    eff = 100.0 + base
    cap = 0
    for op in team:
        for s in members[op]:
            for pat, mul in ((r'订单上限\+(\d+)', 1), (r'当前贸易站每级\+(\d+)个订单上限', level),
                             (r'当前贸易站每级\+(\d+)', level)):
                m = re.search(pat, s.desc)
                if m: cap += int(m.group(1)) * mul
    log.append(('P5 room_caps', {'订单上限+': cap, '合计效率': eff}))

    # ---- 心情 ----
    self_m = room_m = 0.0
    per_mod = {}
    for op in team:
        sm = rm = om = 0.0
        for s in members[op]:
            a, b, c = morale_mods(s.desc, room); sm += a; rm += b; om += c
        per_mod[op] = (sm, rm, om)
    room_m = sum(v[1] for v in per_mod.values())
    total_others = sum(v[2] for v in per_mod.values())
    work_base = max(0.05, 1.0 - 0.05 * (n - 1))
    morale = {op: max(0.05, work_base + per_mod[op][0] + room_m + total_others - per_mod[op][2])
              for op in team}
    for op in team: detail[op]['morale_self'] = per_mod[op][0]
    return dict(room=room, level=level, product=product, team=list(team), eff=eff, cap=cap,
                detail=detail, morale=morale, room_morale_mod=room_m,
                zeroed=zeroed, resources=res_p, log=log)


def _resolve_resources(ctx, team, res, ds, cur_room=None, cur_team=None):
    """全局资源池（中间产物）。按**在岗分布** ctx.by_room 结算——因为同一资源常由“别处”的干员提供：
    塑心在宿舍提供无声共鸣、深律在办公室提供无声共鸣、絮雨在办公室提供感知信息、桑葚在办公室提供人间烟火…
    cur_room：正在结算的房间；该房间队伍里的干员当然算“在该房间”。"""
    r = dict(res)
    by_room = getattr(ctx, 'by_room', None) or {}
    staffed = list(ctx.staffed) or list(team)
    OFFICE_EXTRA = 2                      # 人力办公室 Lv3：3 个招募位 − 初始位 = 2

    cur = list(cur_team or [])

    def where(op, *rooms):
        if by_room:
            if any(op in (by_room.get(rm) or []) for rm in rooms):
                return True
            return bool(cur_room and cur_room in rooms and op in cur)
        return op in team or op in cur     # 退化：全基建名单 + 当前房间队伍

    dorm_occ = ctx.dorm_occ
    # 感知信息
    siwei = 0.0
    if where('迷迭香', '制造站'): siwei += dorm_occ          # 超感
    if where('黑键', '贸易站'): siwei += dorm_occ            # 乐感
    if where('车尔尼', '宿舍'): siwei += 5                   # 小节→感知信息（Lv5）
    if where('爱丽丝', '宿舍'): siwei += 5                   # 梦境→感知信息
    if where('絮雨', '人力办公室'): siwei += OFFICE_EXTRA * 10   # 记忆碎片→感知信息
    if where('夕', '控制中枢'): siwei += 10                  # 心情>12
    # 思维链环（由迷迭香把感知信息转过来）
    silian = siwei if where('迷迭香', '制造站') else 0.0
    # 无声共鸣
    wusheng = 0.0
    if where('塑心', '宿舍'): wusheng += dorm_occ
    if where('深律', '人力办公室'): wusheng += OFFICE_EXTRA * 15
    if where('黑键', '贸易站'): wusheng += siwei             # 乐感：感知信息→无声共鸣
    # 人间烟火（重岳计数：非宿舍设施内的岁干员）
    nonsui_rooms = [o for rm, ops in by_room.items() if rm != '宿舍' for o in ops]
    sui = sum(1 for o in (nonsui_rooms or staffed) if o in ('年', '夕', '令', '重岳', '黍', '余', '望'))
    yanhuo = 0.0
    if where('乌有', '贸易站'): yanhuo += dorm_occ           # 愿者上钩：宿舍人数
    if where('令', '控制中枢'): yanhuo += 15                 # 山河远阔（心情>12）
    if where('桑葚', '人力办公室'): yanhuo += OFFICE_EXTRA * 10   # 灾后普查
    yanhuo += 5 * min(5, sui)
    r.update(感知信息=siwei, 思维链环=silian, 无声共鸣=wusheng, 人间烟火=yanhuo,
             巫术结晶=(int(yanhuo // 5) if where('截云', '制造站') else 0),
             魔物料理=(5.0 if where('森西', '宿舍') else 0.0))
    return r


# ---------------------------------------------------------------- 心情 / 宿舍 / 模拟
def cc_relief(ctrl, yanhuo=0.0, ds=None, box=None):
    """控制中枢给其他设施的心情恢复。
    特殊比较规则：公事公办 / 孤光共照 / 巴别塔之帜 **取最高生效**（不是相加），
    控制中枢自身每名干员 +0.05 是独立的基础部分。"""
    base = 0.05 * len(ctrl)
    group_best = 0.0
    if '重岳' in ctrl:                      # 孤光共照：+0.05，每 20 点人间烟火再 +0.05
        group_best = max(group_best, 0.05 + 0.05 * (yanhuo // 20))
    if '维什戴尔' in ctrl:                  # 巴别塔之帜：+0.1，魔王在中枢再 +0.1
        group_best = max(group_best, 0.10 + (0.10 if '魔王' in ctrl else 0.0))
    if '玛恩纳' in ctrl:                    # 公事公办（数值待确认，先按 +0.05 计）
        group_best = max(group_best, 0.05)
    if '电弧' in ctrl:                      # 点滴关照：控制中枢内干员恢复 +0.05
        base += 0.05
    return base + group_best


def drain_of(room, team, ctrl, yanhuo=0.0, ds=None):
    """逐干员心情消耗（/h）。1 + X + Y：
    X = 房间人数项（1人0 / 2人−0.05 / 3人−0.1 …），**控制中枢例外**：
        中枢内的被动是“每有 1 名中枢干员，中枢内外均 −0.05/h”，故中枢内 = 1 − 0.05×中枢人数。
    Y = 自身修正 + 房间全员修正 + 房间“其他干员”修正 − 其他来源的心智减压。"""
    ds = ds or Dataset(); n = len(team)
    if room == '控制中枢':
        base = max(0.05, 1.0 - 0.05 * len(ctrl or team))     # 中枢被动（内外同减）
        relief = 0.0
    else:
        base = max(0.05, 1.0 - 0.05 * (n - 1))
        relief = cc_relief(ctrl, yanhuo, ds)
    per = {}
    for op in team:
        sm = rm = om = 0.0
        for s in ds.skills_of(op, room):
            a, b, c = morale_mods(s.desc, room); sm += a; rm += b; om += c
        per[op] = (sm, rm, om)
    room_m = sum(v[1] for v in per.values())
    total_others = sum(v[2] for v in per.values())
    return {op: max(0.05, base + per[op][0] + room_m + total_others - per[op][2] - relief) for op in team}


def dorm_rooms_recovery(rooms, ds=None):
    ds = ds or Dataset()
    out = []
    for r in rooms:
        buff = 0.0
        for op in r:
            for s in ds.skills_of(op, '宿舍'):
                buff = max(buff, room_recovery(s.desc))
        out.append(DORM_BASE + buff)
    return out


# ---------------------------------------------------------------- 速率（均为实测标定值）
RATE = dict(
    gold_per_h_per_100=0.8333,        # 赤金 基础 4320s/枚 → 100% 时 0.833 枚/h
    shard_per_h_per_100=1.0,          # 源石碎片 基础 3600s/片 → 100% 时 1 片/h
    exp_per_h_per_100=1000 / 3.0,     # 中级作战记录 1000 经验 / 3h → 100% 时 333 经验/h
    lmd_per_h_per_eff=6.64,           # 兼容旧口径（现由 core/orders.py 按订单结构计算）
    gold_cost_per_h_per_eff=0.01326,
    orundum_per_h_per_eff=0.1,        # 合成玉：7200s 给 20 玉 → eff100 时 10 玉/h
    shard_eat_per_h_per_eff=0.01,     # 玉站吃碎片：eff100 时 1 片/h
    drone_base_minutes=3.0,           # 1 架无人机 = 3 分钟基础耗时
    drone_charge_minutes=6.0,         # 充电 6 分钟/架
)


def shift_output(room, level, product, team, ctx, hours, ds):
    r = eval_room(room, level, product, team, ctx, ds)
    eff = r['eff']
    if room == '制造站':
        if product == 'Pure Gold':
            return {'gold': RATE['gold_per_h_per_100'] * eff / 100 * hours}, r
        if product == 'Originium Shard':
            return {'shard': RATE['shard_per_h_per_100'] * eff / 100 * hours}, r
        if product == 'Battle Record':
            # 中级作战记录：1000 经验 / 3:00:00 基础（全机制.md）
            return {'exp': RATE['exp_per_h_per_100'] * eff / 100 * hours}, r
    if room == '贸易站':
        if product == 'LMD':
            from .orders import profile
            pr = profile(team, ds, hours)
            return {'lmd': pr['lmd_per_eff_hour'] * eff * hours,
                    'gold_cost': pr['gold_cost_per_eff_hour'] * eff * hours}, r
        if product == 'Orundum':
            return {'orundum': RATE['orundum_per_h_per_eff'] * eff * hours,
                    'shard_cost': RATE['shard_eat_per_h_per_eff'] * eff * hours}, r
    return {}, r


def power_charge(power_teams, hours, ds, base_per_station=10.0 / 3.0):
    """发电站充能 → 无人机架数。
    按用户口径：**每座发电站**效率 = +X+Y（有正常工作干员 +5%，技能计入 Y），
    **总无人机效率 = 三站相加**。每站基础 10/3 架·h（三站合计 10 架/h，与实测 240 架/天一致）。"""
    total, bonus_sum = 0.0, 0.0
    for team in power_teams:
        bonus = 5.0 if team else 0.0
        for op in team:
            for s in ds.skills_of(op, '发电站'):
                m = re.search(r'恢复速度\+(\d+)%', s.desc) or re.search(r'充能速度\+(\d+)%', s.desc)
                if m: bonus += float(m.group(1))
        total += base_per_station * (1 + bonus / 100)
        bonus_sum += bonus
    return total * hours, bonus_sum


def simulate(deck_path, days=14, hours=4.0, ds=None, verbose=False):
    """从 MAA 计划文件模拟"""
    deck = json.load(open(deck_path, encoding='utf-8'))
    shifts = []
    for p in deck['plans']:
        rooms, dorm = [], []
        for rk, insts in p['rooms'].items():
            for inst in insts:
                ops = list(inst.get('operators', []))
                if rk == 'dormitory': dorm.append(ops)
                else: rooms.append((ROOM_OF_MAA.get(rk, rk), inst.get('product'), 3, ops))
        shifts.append(dict(rooms=rooms, dorm=dorm, fia=p.get('Fiammetta', {})))
    return simulate_shifts(shifts, days=days, hours=hours, ds=ds)


def simulate_shifts(shifts, days=14, hours=4.0, ds=None):
    """对“班次结构”做逐班模拟：心情（含菲亚梅塔交换、宿舍恢复）+ 产出/消耗。
    shifts: [dict(rooms=[(房间, 产物, 等级, [干员]), ...], dorm=[[干员], ...], fia={...}), ...]"""
    ds = ds or Dataset()
    roster = set()
    for s in shifts:
        for _, _, _, ops in s['rooms']: roster |= set(ops)
        for d in s['dorm']: roster |= set(d)
    mor = {o: MAX_MORALE for o in roster}
    lows = {o: MAX_MORALE for o in roster}
    per_day = collections.Counter()
    for day in range(days):
        day_kpi = collections.Counter()
        for sh, s in enumerate(shifts):
            ctrl = next((ops for r, p, lv, ops in s['rooms'] if r == '控制中枢'), [])
            staffed = [o for r, p, lv, ops in s['rooms'] for o in ops]
            c0 = Ctx(ds=ds)
            c0.by_room = {}
            for r, p, lv, ops in s['rooms']:
                c0.by_room.setdefault(r, []).extend(ops)
            c0.staffed = staffed
            res = _resolve_resources(c0, staffed, c0.base_resources(), ds)
            yanhuo = res.get('人间烟火', 0.0)
            for r, p, lv, ops in s['rooms']:
                for o, v in drain_of(r, ops, ctrl, yanhuo, ds).items():
                    mor[o] = max(0.0, mor[o] - v * hours)
            for d in s['dorm']:
                if not d: continue
                rr = dorm_rooms_recovery([d], ds)[0]
                for o in d: mor[o] = min(MAX_MORALE, mor[o] + rr * hours)
            fia = s['fia'] or {}
            if fia.get('enable') and mor.get('菲亚梅塔', 0) >= 20.0:
                tgt = fia.get('target')
                if tgt in mor and mor[tgt] < 22.0:
                    mor['菲亚梅塔'], mor[tgt] = mor[tgt], mor['菲亚梅塔']
            for r, p, lv, ops in s['rooms']:
                if not ops: continue
                out, _ = shift_output(r, lv, p, ops, c0, hours, ds)
                for k, v in out.items(): day_kpi[k] += v
            pw = [ops for r, p, lv, ops in s['rooms'] if r == '发电站']
            if pw:
                dn, bonus = power_charge(pw, hours, ds)
                day_kpi['drones'] += dn
            for o in mor: lows[o] = min(lows[o], mor[o])
        per_day.update(day_kpi)
    kpi = {k: v / days for k, v in per_day.items()}
    dr = kpi.get('drones', 0.0)
    kpi['drone_shard'] = dr * (RATE['drone_base_minutes'] / 60.0)
    kpi['drone_orundum'] = dr * (RATE['drone_base_minutes'] / 60.0) / 2.0 * 20
    # 注意：这里**不**把无人机收益加进 yu —— 实际投放由 solve/drones.py 按目标分配后计入，
    # 否则会变成“全部投玉”的乐观假设。
    kpi['yu'] = kpi.get('orundum', 0.0)
    kpi['gold_net'] = kpi.get('gold', 0.0) - kpi.get('gold_cost', 0.0)
    kpi['shard_net'] = kpi.get('shard', 0.0) - kpi.get('shard_cost', 0.0)
    kpi['min_morale'] = min(lows.values()) if lows else 0.0
    kpi['min_who'] = min(lows, key=lambda o: lows[o]) if lows else ''
    kpi['lows'] = lows
    # 会客室线索产出（126% 基础 + 干员稀有度/精英化/未红脸 + 后勤技能%，见 core/meeting.py）
    try:
        from .meeting import clue_per_day as _cpd
        kpi['clue'] = _cpd(shifts, ds, box=getattr(ds, '_box', None), hours=hours)
    except Exception:
        kpi['clue'] = 0.0
    return kpi


def score(kpi, objective):
    """目标 + 约束罚项。objective = dict(main='yu'|'lmd', w_yu=, w_lmd=, min_morale=5, gold_balance=True)"""
    v = objective.get('w_yu', 0) * kpi.get('yu', 0) + objective.get('w_lmd', 0) * kpi.get('lmd', 0)
    pen = 0.0
    floor = objective.get('min_morale', 5.0)
    if kpi['min_morale'] < floor: pen += (floor - kpi['min_morale']) * objective.get('p_morale', 1e4)
    if objective.get('gold_balance') and kpi['gold_net'] < -0.01:
        pen += abs(kpi['gold_net']) * objective.get('p_gold', 1e3)
    return v - pen


# ---------------------------------------------------------------- 规则表驱动结算（权威实现，覆盖上方同名函数）
def eval_room(room, level, product, team, ctx, ds=None, log=None, hours=4.0, morale=None):
    """改为调用 core/rules.py 的数据驱动规则表（更具体规则优先，可处理慢热/计数/归零）"""
    from .rules import evaluate_room
    return evaluate_room(room, level, product, team, ctx, ds or ctx.ds, hours=hours, morale=morale)
