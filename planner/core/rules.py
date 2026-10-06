# -*- coding: utf-8 -*-
"""rules.py —— 效果规则表（数据驱动，按优先级依次匹配）

设计：
* 每条规则 = 房间 + 正则 + 前置判断 + 通道(chan) + 表达式(expr) + 是否独占(exclusive)
* 同一技能的“效率类”通道按规则顺序**首次命中即定**（更具体的规则写在前面），
  而心情/订单上限/充能/宿舍恢复等**辅助通道**允许多条同时生效。
* 表达式在受限环境内求值，可用变量/函数：
    X  (+Y)  —— 正则捕获组 g1,g2,g3（已转 float）
    n_room / n_other         房间人数 / 其他人数
    fac('贸易站')             设施数量
    group('莱茵生命')         基建内该势力在岗人数（不含副手/活动室）
    room_group('拉特兰')      本房间内该势力人数
    skills_in_room('金属工艺') 本房间内技能名含该关键字的数量
    hours                    连续工作小时（慢热用）
    res('人间烟火')           全局资源
    dorm_occ / dorm_cnt / dorm_lv
    elite_fac                进驻精英干员的设施数
    drone_cap                无人机上限
    gap                      心情落差（24 − 当前心情）
"""
import re

# ---------------------------------------------------------------- 规则表
# chan: prod_any / prod_gold / prod_shard / order / charge
RULES = [
    # ---- 慢热（必须最先，否则会被通用 +X% 抢走）----
    dict(id='ramp', room='制造站', re=r'生产力每小时\+(\d+)%，最终达到\+(\d+)%',
         chan='prod_any', expr='min(g2, g1*hours)'),
    # ---- 按本房间“某类技能”数量加成 ----
    dict(id='per_room_skill', room='制造站',
         re=r'当前制造站内每个(金属工艺|莱茵科技)类技能为自身\+(\d+)%的生产力',
         chan='prod_any', expr='g2*skills_in_room(g1)'),
    # ---- 按势力人数加成（莱茵生命，最多 N 名）----
    dict(id='per_group_gold', room='制造站',
         re=r'每有1名.*?干员（最多(\d+)名），贵金属类配方的生产力\+(\d+)%',
         chan='prod_gold', expr='g2*min(g1, group("莱茵生命"))'),
    # ---- 按设施数量加成（归零时**保留**）----
    dict(id='per_trade_gold', room='制造站', re=r'每个贸易站为当前制造站贵金属类配方的生产力\+(\d+)%',
         chan='prod_gold', expr='g1*fac("贸易站")', facility=True),
    dict(id='per_power_any', room='制造站', re=r'每个发电站为当前制造站\+(\d+)%的生产力',
         chan='prod_any', expr='g1*fac("发电站")', facility=True),
    dict(id='per_member_any', room='制造站', re=r'每个当前制造站内干员为当前制造站\+(\d+)%生产力',
         chan='prod_any', expr='g1*n_room', facility=True),
    # ---- 产品指定 ----
    dict(id='gold_flat', room='制造站', re=r'贵金属类配方的生产力\+(\d+)%',
         chan='prod_gold', expr='g1'),
    dict(id='shard_flat', room='制造站', re=r'源石类配方的生产力\+(\d+)%',
         chan='prod_shard', expr='g1'),
    # ---- 通用生产力（排除已被上面接管的写法）----
    dict(id='prod_any', room='制造站', re=r'生产力\+(\d+)%',
         pre=lambda d: '贵金属类配方' not in d and '源石类配方' not in d
                       and '每小时' not in d and '心情落差' not in d,
         chan='prod_any', expr='g1'),
    # ---- 心情落差（铅踝）----
    dict(id='gap_penalty', room='制造站', re=r'自身每有4点.*?生产力-5%',
         chan='prod_any', expr='-5*int(gap//4)'),
    dict(id='gap_bonus', room='制造站', re=r'当自身.*?心情落差.*?大于12时，生产力\+(\d+)%',
         chan='prod_extra', expr='g1 if gap > 12 else 0', exclusive=False),
    # ---- 贸易站 ----
    dict(id='order_flat', room='贸易站', re=r'订单获取效率\+(\d+)%',
         pre=lambda d: not re.search(r'每有|每名|每间|每级', d),
         chan='order', expr='g1'),
    dict(id='order_per_room_group', room='贸易站',
         re=r'同个贸易站中每有1名.*?干员，当前贸易站订单获取效率\+(\d+)%',
         chan='order', expr='g1*room_group(TERM_GROUP)'),
    dict(id='order_per_other', room='贸易站', re=r'贸易站内除自身以外每名.*?干员\+(\d+)%订单获取效率',
         chan='order', expr='g1*n_other'),
    dict(id='order_per_dorm', room='贸易站', re=r'每间宿舍每级\+(\d+)%获取效率',
         chan='order', expr='g1*dorm_cnt*dorm_lv'),
    dict(id='elite_squad', room='贸易站', re=r'每有一间进驻.*?精英干员的设施，订单获取效率额外\+(\d+)%（最多(\d+)间）',
         chan='order', expr='25 + g1*min(g2, elite_fac)'),
    dict(id='order_per_res', room='贸易站', re=r'每有1点.*?则订单获取效率\+1%',
         chan='order', expr='res("人间烟火")'),
    dict(id='order_per_res2', room='贸易站', re=r'每1点.*?\+1%订单效率',
         chan='order', expr='res("魔物料理")'),
    # ---- 体系（中间产物）消费型 ----
    dict(id='silian_half', room='制造站', re=r'每2点思维链环\+(\d+)%生产力', chan='prod_any', expr='res("思维链环")/2'),
    dict(id='silian_full', room='制造站', re=r'每1点思维链环\+(\d+)%生产力', chan='prod_any', expr='res("思维链环")'),
    dict(id='yanhuo_prod', room='制造站', re=r'每3点人间烟火\+(\d+)%生产力',
         chan='prod_extra', expr='res("人间烟火")/3', exclusive=False),
    dict(id='wushu_prod', room='制造站', re=r'每1点巫术结晶\+(\d+)%生产力',
         chan='prod_extra', expr='res("巫术结晶")*g1', exclusive=False),
    dict(id='paihuai', room='贸易站', re=r'每4点无声共鸣\+(\d+)%订单效率',
         chan='order', expr='res("无声共鸣")/4'),
    dict(id='changwang', room='贸易站', re=r'每2点无声共鸣\+(\d+)%订单效率',
         chan='order', expr='res("无声共鸣")/2'),
    dict(id='mowu', room='贸易站', re=r'每1点魔物料理\+(\d+)%订单效率',
         chan='order', expr='res("魔物料理")*g1'),
    dict(id='hongxue', room='贸易站', re=r'每有1条赤金生产线，则当前贸易站订单获取效率\+(\d+)%',
         chan='order', expr='res("赤金生产线")*g1'),
    # ---- 发电站 ----
    dict(id='charge_flat', room='发电站', re=r'无人机充能速度\+(\d+)%', chan='charge', expr='g1'),
    dict(id='charge_leithan', room='发电站',
         re=r'无人机充能速度\+(\d+)%，.*?每有1名除自身以外的.*?干员（最多(\d+)名），充能速度额外\+(\d+)%',
         chan='charge', expr='g1 + g3*min(g2, group("莱茵生命")-1)'),
    dict(id='charge_cap', room='发电站', re=r'每10架无人机上限\+(\d+)%无人机充能速度（最多\+(\d+)%）',
         chan='charge', expr='min(g2, (drone_cap//10)*g1)'),
]

# 同站条件加成（干员, 需要的同伴, 加成%）
PARTNER_BONUS = [
    ('摩根', '推进之王', 35),        # 帮派指南针：与推进之王同站 +35%
    ('蕾缪安', '能天使', 25),        # 相伴：与能天使同站 +25%
    ('德克萨斯', '拉普兰德', 65),    # 恩怨：与拉普兰德同站 +65%（代价：心情 +0.3/h）
    ('赫德雷', '伊内丝', 5),         # 白手起家·β：伊内丝在工作场所 +5%
    ('赫德雷', 'W', 5),
]

# 归零者：使房间内**他人**生产力归零，但“根据设施数量提供加成的生产力”保留
ZERO_RE = r'当前制造站内其他干员提供的生产力全部归零（不包含根据设施数量提供加成的生产力）'
# 特殊叠加规则（wiki《基建术语》原文）：
#   · 回收利用 / 配合意识：无法叠加，且优先生效
#   · 自动化·α / 自动化·β / 仿生海龙：无法互相叠加，且**清零效果优先生效**
# 实现：同一干员在同族里只保留效果最高的一条。
FAMILY = {
    '回收利用': 'recycle', '配合意识': 'recycle',
    '自动化·α': 'zero_power', '自动化·β': 'zero_power', '仿生海龙': 'zero_power',
    '流程优化': 'zero_power', '科学改造': 'zero_power',
}
# 巫恋·低语：他人订单效率归零，本人按其他人数 ×45%
LOWWHISPER = dict(re=r'当前贸易站内其他干员提供的订单获取效率全部归零，且每人为自身\+(\d+)%订单获取效率',
                  expr='g1')

# 术语 → 势力名映射（正则里用 TERM_GROUP 占位，此处按技能出现顺序解析）
GROUP_HINTS = ['莱茵生命', '拉特兰', '格拉斯哥帮', '叙拉古', '深海猎人', '岁',
               'A1小队', 'S.E.E.S.', '彩虹小队', '乌萨斯学生自治团', '作业平台', '怪物猎人小队', '泡影国狩猎小队']


def _groups_in(desc):
    return [g for g in GROUP_HINTS if g in desc]


_SAFE_BUILTINS = {'min': min, 'max': max, 'int': int, 'abs': abs, 'round': round, 'float': float}


def _eval(expr, env):
    try:
        return float(eval(expr, {'__builtins__': _SAFE_BUILTINS}, env))
    except Exception:
        return 0.0


def _captures(m):
    out = {}
    for i, g in enumerate(m.groups(), start=1):
        out[f'g{i}'] = float(g) if g is not None and re.fullmatch(r'-?\d+(\.\d+)?', str(g)) else g
    return out


def evaluate_room(room, level, product, team, ctx, ds, hours=4.0, morale=None):
    """返回 dict(eff, detail, morale, cap, charge, zeroed, log, resources)"""
    from .engine import morale_mods, room_recovery, MAX_MORALE
    log = []
    n_room, n_other = len(team), max(0, len(team) - 1)
    staffed = list(ctx.staffed) or list(team)   # 全基建在岗者（势力/人数类技能读它）
    resg = dict(ctx.base_resources())
    # 全局资源（人间烟火/感知信息/思维链环）——与 engine._resolve_resources 对齐
    from .engine import _resolve_resources
    resg = _resolve_resources(ctx, staffed, resg, ds, cur_room=room, cur_team=team)
    env_base = dict(
        n_room=n_room, n_other=n_other, hours=hours,
        fac=lambda r: ctx.count(r),
        group=lambda name: sum(1 for o in ctx.staffed if o in _members_of(ds, name)),
        room_group=lambda name: sum(1 for o in team if o in _members_of(ds, name)),
        skills_in_room=lambda kw: sum(1 for op in team for s in ds.skills_of(op, room) if kw in (s.name or '')),
        res=lambda k: resg.get(k, 0.0),
        dorm_occ=ctx.dorm_occ, dorm_cnt=ctx.count('宿舍'), dorm_lv=5,
        elite_fac=ctx.elite_facilities, drone_cap=ctx.drone_cap, gap=0.0,
    )
    zeroed = any(re.search(ZERO_RE, s.desc) for op in team for s in ds.skills_of(op, room))
    # --- 流水线日志（P0~P6，供 CLI 与报告展示）---
    log.append(('P0 collect', {op: [s.name for s in ds.skills_of(op, room)] for op in team}))
    forced = [op for op in team if any('标准化类技能' in s.desc and
              any(k in s.desc for k in ('改为', '视为', '变成')) for s in ds.skills_of(op, room))]
    std_count = sum(1 for op in team for s in ds.skills_of(op, room) if ds.is_standardized(s)) + len(forced)
    log.append(('P1 normalize_types', {'改写者': forced}))
    log.append(('P2 count_globals', {'标准化类技能数': std_count, '赤金生产线': resg.get('赤金生产线'),
                                     '外势': resg.get('外势'), '实地': resg.get('实地')}))
    log.append(('P3 room_nullify', {'触发': zeroed}))
    log.append(('P6 resources', {k: round(v, 2) for k, v in resg.items() if v}))
    detail = {}
    for op in team:
        env = dict(env_base); env['gap'] = MAX_MORALE - (morale or {}).get(op, MAX_MORALE)
        contrib, notes, facility_part = 0.0, [], 0.0
        vals = {}
        for s in ds.skills_of(op, room):
            d = s.desc
            # 产品适配
            if '贵金属类配方' in d and product != 'Pure Gold': notes.append(f'{s.name}:产品不适用'); continue
            if '源石类配方' in d and product != 'Originium Shard': notes.append(f'{s.name}:产品不适用'); continue
            for rule in RULES:
                if rule['room'] != room: continue
                m = re.search(rule['re'], d)
                if not m: continue
                if rule.get('pre') and not rule['pre'](d): continue
                env2 = dict(env); env2.update(_captures(m))
                if 'TERM_GROUP' in rule['expr']:
                    gs = _groups_in(d)
                    env2['TERM_GROUP'] = gs[0] if gs else ''
                v = _eval(rule['expr'], env2)
                if rule['chan'] == 'charge':
                    contrib += v; vals[s.name] = vals.get(s.name, 0.0) + v; notes.append(f"{s.name}:充能+{v:g}%")
                else:                    # 产品映射
                    ch = rule['chan']
                    if ch == 'prod_gold' and product != 'Pure Gold': notes.append(f'{s.name}:不适用(非赤金)'); break
                    if ch == 'prod_shard' and product != 'Originium Shard': notes.append(f'{s.name}:不适用(非碎片)'); break
                    contrib += v; vals[s.name] = vals.get(s.name, 0.0) + v; notes.append(f'{s.name}:+{v:g}%')
                    if rule.get('facility'): facility_part += v
                if rule.get('exclusive', True) and rule['chan'] != 'prod_extra':
                    break
        # —— 特殊叠加规则：同族技能不叠加（自动化·α/·β/仿生海龙、回收利用/配合意识…）——
        fam = {}
        for nm, v in vals.items():
            f = FAMILY.get(nm)
            if f: fam.setdefault(f, []).append((nm, v))
        for f, items in fam.items():
            if len(items) > 1:
                items.sort(key=lambda x: -abs(x[1]))
                for nm, v in items[1:]:
                    contrib -= v; notes.append(f'（叠加规则：{nm} 与 {items[0][0]} 同族，不叠加→不计）')
        detail[op] = dict(contrib=contrib, notes=notes, facility_part=facility_part)
    # 归零者结算（保留 facility_part）
    if zeroed:
        for op, v in detail.items():
            if re.search(ZERO_RE, ' '.join(s.desc for s in ds.skills_of(op, room))):
                v['notes'].append('（归零者：本人加成保留）'); continue
            keep = v['facility_part']
            if v['contrib'] != keep:
                v['notes'].append(f'（归零者：生产力归零，保留设施类 {keep:g}%）')
            v['contrib'] = keep
    # 巫恋·低语
    lw = [(op, s) for op in team for s in ds.skills_of(op, room) if re.search(LOWWHISPER['re'], s.desc)]
    if lw:
        src = lw[0][0]
        for op in team:
            if op == src: continue
            detail[op]['notes'].append('（低语：他人订单效率归零）'); detail[op]['contrib'] = 0.0
        m = re.search(LOWWHISPER['re'], lw[0][1].desc)
        bonus = float(m.group(1)) * n_other
        detail[src]['contrib'] += bonus
        detail[src]['notes'].append(f'（低语：{n_other} 名其他干员 ×{m.group(1)}% = +{bonus:g}%）')
        log.append(('P4.5 lowwhisper', {'归零': n_other, '本人加成': bonus}))
    # —— 同站条件加成（数据来自技能原文）——
    for op, partner, val in PARTNER_BONUS:
        if op in team and partner in team and op in detail:
            detail[op]['contrib'] += val
            detail[op]['notes'].append(f'（同站条件：与 {partner} 同站 +{val}%）')
    base = sum(v['contrib'] for v in detail.values())
    cap = 0
    for op in team:
        for s in ds.skills_of(op, room):
            for pat, mul in ((r'订单上限\+(\d+)', 1), (r'当前贸易站每级\+(\d+)个订单上限', level),
                             (r'当前贸易站每级\+(\d+)', level)):
                mm = re.search(pat, s.desc)
                if mm: cap += int(mm.group(1)) * mul
    charge = sum(v['contrib'] for v in detail.values()) if room == '发电站' else 0.0
    # —— 房间效率通道：跨房间/中枢影响，作用于**房间本身**，不归属任何干员 ——
    room_bonus, room_notes = 0.0, []
    if room == '制造站':
        by_room = getattr(ctx, 'by_room', {}) or {}
        hunt = [o for o in by_room.get('制造站', []) if o in _members_of(ds, '深海猎人')]
        if hunt and '歌蕾蒂娅' in (by_room.get('控制中枢') or []):
            elite = (ctx.box.get('歌蕾蒂娅') or {}).get('elite', 0)
            per = 10 if elite >= 2 else 5          # 精2 = 10%/人（上限 90%），精0 = 5%/人（上限 45%）
            cap = 90 if elite >= 2 else 45
            if any(o in hunt for o in team):        # 本制造站内有深海猎人（同站多人只算一次）
                room_bonus = min(cap, per * len(hunt))
                room_notes.append(f'深海猎人特殊加成（歌蕾蒂娅 精{elite}）：{len(hunt)} 人 × {per}% = +{room_bonus:g}%（房间效率）')
    # —— P5 房间效率收口 ——
    # 效率 = 1 + X + Y：X = 每个正常工作的干员 +1%（贸易站/制造站）；Y = 技能（含外部效果，见 GLOBAL）
    per_worker = 1.0 * n_room if room in ('贸易站', '制造站') else 0.0
    ext = _external_eff(room, ctx, ds, product, resg)
    eff = 100.0 + per_worker + base + ext + room_bonus + (charge if room == '发电站' else 0.0)
    # 心情
    per_mod = {}
    for op in team:
        sm = rm = om = 0.0
        for s in ds.skills_of(op, room):
            a, b, c = morale_mods(s.desc, room); sm += a; rm += b; om += c
        per_mod[op] = (sm, rm, om)
    room_m = sum(v[1] for v in per_mod.values()); tot_others = sum(v[2] for v in per_mod.values())
    wb = max(0.05, 1.0 - 0.05 * (n_room - 1))
    mor = {op: max(0.05, wb + per_mod[op][0] + room_m + tot_others - per_mod[op][2]) for op in team}
    return dict(room=room, level=level, product=product, team=list(team), eff=eff, base=base,
                cap=cap, charge=charge, detail=detail, morale=mor, zeroed=zeroed,
                room_bonus=room_bonus, room_notes=room_notes, resources=resg, log=log)


def _external_eff(room, ctx, ds, product, res):
    """**外部效果**（控制中枢等）：效率 = 1 + X + Y 里的 Y 还包含别处干员带来的全局加成。
    例：阿米娅（控制中枢）「所有贸易站订单效率+7%」、凯尔希「所有制造站生产力+2%」、
    望「外势≥实地 → 所有贸易站+7% / 实地>外势 → 所有制造站+2%」。
    结果按 (by_room 指纹, 房间, 产物) 缓存，避免每次结算都全表扫描。"""
    if room not in ('贸易站', '制造站'):
        return 0.0
    by_room = getattr(ctx, 'by_room', None) or {}
    staffed = tuple(sorted((k, tuple(sorted(v or []))) for k, v in by_room.items()))
    key = (staffed, room, product)
    cache = getattr(ctx, '_ext_cache', None)
    if cache is None:
        cache = ctx._ext_cache = {}
    if key in cache:
        return cache[key]
    ext = 0.0
    for rname, ops in by_room.items():
        for op in (ops or []):
            for s in ds.skills_of(op):          # 不限房间：技能写在哪个房间都可能给全局加成
                d = s.desc or ''
                for m in re.finditer(r'所有贸易站订单效率\+(\d+)%', d):
                    if room == '贸易站': ext += float(m.group(1))
                for m in re.finditer(r'所有制造站生产力\+(\d+)%', d):
                    if room == '制造站': ext += float(m.group(1))
                if '外势' in d and room == '贸易站' and res.get('外势', 0) >= res.get('实地', 0):
                    ext += 7.0
                if '实地' in d and room == '制造站' and res.get('实地', 0) > res.get('外势', 0):
                    ext += 2.0
    cache[key] = ext
    return ext


def _members_of(ds, group_name):
    """术语“包含以下干员…”→ 成员集合（交给 dataset 的正确解析器）"""
    return set(ds.members_of(group_name))
