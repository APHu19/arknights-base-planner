# -*- coding: utf-8 -*-
"""systems.py —— 体系原型库：语义扫描成员 → 收益函数 → 满配/缺人权重 → 替补规则

设计（对应需求原文："用语义理解并翻译为实际收益函数的方式…枚举…权重…替补"）：

1. **原型(ARCHETYPE)** = 一条"机制文法"：`name/room/mech/need/want(扫描规则)/knobs(布局参数)/
   subs(替补规则)/notes`。成员不是写死的名字，而是**按技能原文语义扫描**得到（`find()`），
   所以新干员一进池子就会自动进入对应体系。
2. **收益函数**：贸易=币/时（含订单分布）、制造=件/时或经验/时、发电=架/时、会客=线索/天、
   办公室=联络%、宿舍=恢复/时、中枢=全贸易站+%。全部走本引擎，不抄攻略。
3. **权重**：`norm_value`（同房间归一化满配收益）× `robustness`（**留一法**：缺任意一个必需成员后
   用最佳替补补位，收益/满配收益的最小值）。稳健度低 = 一旦缺人塌方 = 权重低。
4. **替补规则**：按机制区分（归零型 → 必须"不受归零影响"；裁缝型 → 只能换另一个裁缝；
   计数型 → 必须同样提供计数；放大器型 → 必须本身高效率；心情型 → 看恢复量）。
"""
import re
import collections

FAC_KNOBS = ('发电站数量', '贸易站数量', '制造站数量', '宿舍等级')


# ---------------------------------------------------------------- 收益函数
def _ctx(ds, layout=None):
    from core.engine import Ctx
    lay = layout or {'制造站': [(3, 'Pure Gold')] * 3, '贸易站': [(3, 'LMD')] * 3,
                     '发电站': [(3, None)] * 3, '宿舍': [(5, None)] * 4}
    c = Ctx(ds=ds, layout=lay)
    c.dorm_occ = 20
    return c


def revenue(ds, room, team, product=None, by_room=None, hours=1.0, layout=None):
    from core.engine import eval_room, shift_output, power_charge, dorm_rooms_recovery
    from core import orders, meeting
    team = [o for o in (team or []) if o]
    if not team:
        return 0.0, '空', {}
    c = _ctx(ds, layout)
    c.by_room = by_room or {}
    c.staffed = [o for v in (by_room or {}).values() for o in v]
    if room == '贸易站':
        prod = product or 'LMD'
        out, rep = shift_output('贸易站', 3, prod, team, c, hours, ds)
        if prod == 'LMD':
            pr = orders.profile(team, ds, hours)
            return out.get('lmd', 0.0), '币/时', dict(eff=rep.get('eff'), 分布=pr.get('dist'))
        return out.get('orundum', 0.0), '玉/时', dict(eff=rep.get('eff'))
    if room == '制造站':
        prod = product or 'Pure Gold'
        out, rep = shift_output('制造站', 3, prod, team, c, hours, ds)
        if prod == 'Pure Gold':
            return out.get('gold', 0.0), '件/时', dict(eff=rep.get('eff'))
        if prod == 'Battle Record':
            return out.get('exp', 0.0), '经验/时', dict(eff=rep.get('eff'))
        return out.get('shard', 0.0), '片/时', dict(eff=rep.get('eff'))
    if room == '发电站':
        dn, bonus = power_charge([team], hours, ds)
        return dn, '架/时', dict(加成=bonus)
    if room == '会客室':
        sp = meeting.speed(team, ds, box=getattr(ds, '_box', None), hours=hours)
        return sp['clue_per_day'], '线索/天', dict(速度=sp['speed'])
    if room == '人力办公室':
        # 单人岗：每人取自己最好的"联络速度"技能（同名/同族只算一次），再跨人相加
        total = 0.0
        for op in team:
            best = 0.0
            for s in ds.skills_of(op, '人力办公室'):
                m = re.search(r'人脉资源的联络速度\+(\d+)%', s.desc or '')
                if m:
                    best = max(best, float(m.group(1)))
            total += best
        return 5.0 + total, '联络%', {}
    if room == '宿舍':
        return dorm_rooms_recovery([team], ds)[0], '恢复/时', {}
    if room == '控制中枢':
        b = 0.0
        for op in team:
            for s in ds.skills_of(op, '控制中枢'):
                m = re.search(r'所有贸易站订单效率\+(\d+)%', s.desc or '')
                if m:
                    b = max(b, float(m.group(1)))
        return b, '全贸易站+%', {}
    return 0.0, '—', {}


# ---------------------------------------------------------------- 语义扫描
def zero_survivors(ds, box, room):
    """**能在归零房里活下来的人**：技能效果不是"订单获取效率+X%"/"生产力+X%"，
    而是分布(裁缝/卡夫卡)、按单加钱(龙舌兰·投资)、订单上限、特别订单(可露希尔)、
    违约(但书)、按设施/资源/仓库容量给加成的人 —— 他们才配进巫恋/温蒂/森蚺的房间。"""
    KEEP = (r'高品质|裁缝|手工艺品|鉴定师|投资|订单上限|特别订单|违约索赔|合同法|'
            r'每格仓库容量|仓库容量上限|工程机器人|每个发电站|每个贸易站|每条赤金生产线|'
            r'每间宿舍每级|思维链环|感知信息|无声共鸣|人间烟火|协同|配合')
    out = []
    for s in ds.skills:
        if s.room != room:
            continue
        if re.search(KEEP, s.desc or ''):
            for h in s.holders:
                if box.get(h, {}).get('own') and h not in out:
                    out.append(h)
    return out


def find(ds, box, pattern, room=None, owned_only=True):
    """技能原文匹配 pattern 的干员（可限定房间）；owned_only=只看已持有"""
    out = []
    for s in ds.skills:
        if room and s.room != room:
            continue
        if not re.search(pattern, s.desc or ''):
            continue
        for h in s.holders:
            if owned_only and not box.get(h, {}).get('own'):
                continue
            if h not in out:
                out.append(h)
    return out


def term_members(ds, term):
    try:
        return list(ds.members_of(term))
    except Exception:
        return []


# 外部补强：**其他房间的人对本配队的加成**（要塞进该体系的账面，否则会低估）
SUPPORTS = {
    '归零制造（温蒂/森蚺）': {'控制中枢': ['森蚺', '阿米娅'], '发电站': ['Lancet-2', '承曦格雷伊'],
                          'note': '发电站数量修正直接乘在"每个发电站+X%"上：晨曦 +1、森蚺(中枢)+Lancet-2 +2；'
                                  '此时其他发电站不能放作业平台，否则晨曦失效'},
    '归零贸易（巫恋高品质）': {'控制中枢': ['阿米娅', '明椒'],
                          'note': '中枢"所有贸易站订单效率 +7%"（取最高）'},
    '感知信息链（迷迭香+黑键）': {'宿舍': ['爱丽丝', '车尔尼', '塑心'], '人力办公室': ['絮雨'],
                              '控制中枢': ['夕'],
                              'note': '宿舍满员 20 人 + 感知信息提供者（爱丽丝/车尔尼/塑心/絮雨/夕）'},
    '人间烟火（乌有）': {'控制中枢': ['夕', '令'], 'note': '夕心情<12 给烟火 15 点；宿舍满员'},
    '孑差额订单': {'控制中枢': ['灵知'],
                 'note': '灵知：每个进驻贸易站的谢拉格干员 → 订单上限 +6、订单效率 −15%'
                         '（上限进孑的差额乘区，效率是代价）'},
    '但书违约 / 可露希尔特别订单': {'控制中枢': ['阿米娅', '明椒'], 'note': '中枢 +7% 贸易效率'},
    '中枢贸易增益（阿米娅/诗怀雅/明椒）': {'贸易站': ['德克萨斯', '能天使', '拉普兰德'],
                                   'note': '中枢加成的价值 = 加成% × 前三贸易站币/时（见折算口径）'},
    '仓库体系（红云/泡泡）': {'note': '容量同时给"生产力"与"防爆仓余量"（见 爆仓余量 列）'},
    '至简工程机器人': {'note': '机器人 = 全基建设施总等级（本模型 47），与房间等级无关'},
    '发电充能（澄闪/深靛/伊芙利特…）': {'控制中枢': ['逻各斯'], 'note': 'PhonoR-0 需逻各斯在中枢再 +5%'},
}
def archetypes():
    """每条 = 一个体系原型（成员按语义扫描，不写死）"""
    A = []
    A.append(dict(
        name='归零制造（温蒂/森蚺）', room='制造站', product='Pure Gold', mech='归零独占+设施计数',
        need=3, knobs=('发电站数量', '晨曦+1', '森蚺中枢Lancet-2+2'),
        want=lambda ds, box: (find(ds, box, r'其他干员提供的生产力全部归零', '制造站')
                              + zero_survivors(ds, box, '制造站')
                              + ['承曦格雷伊', 'Lancet-2', '清流']),
        core=lambda ds, box: [o for o in ('温蒂', '森蚺', '清流') if box.get(o, {}).get('own')],
        subs='替补必须是"不受归零影响"的：按设施数量(清流/温蒂自身)/资源/仓库容量给加成的干员；'
             '绝不能用普通效率干员（会被归零）',
        notes='发电站数量是收益倍增器：晨曦+1、森蚺在中枢且 Lancet-2 在发电站再+2（且此时不能用作业平台，'
              '否则晨曦失效）；承曦格雷伊除外'))
    A.append(dict(
        name='归零贸易（巫恋高品质）', room='贸易站', product='LMD', mech='归零独占+分布改造',
        need=3, knobs=(),
        want=lambda ds, box: (['巫恋'] + find(ds, box, r'高品质贵金属订单的出现概率', '贸易站')
                              + find(ds, box, r'龙门币收益\+\d+', '贸易站')),
        core=lambda ds, box: [o for o in ('巫恋',) if box.get(o, {}).get('own')],
        subs='两个位置各有独立逻辑：裁缝位只能换另一个裁缝（明椒/柏喙/卡夫卡，改分布）；'
             '第三位优先龙舌兰（投资·β 把高品质订单变钱），其次普通高效率（但效率会被低语归零→基本无用）',
        notes='低语把队友效率归零 ⇒ 队友价值 100% 来自"订单分布"与"投资"，不是效率'))
    A.append(dict(
        name='感知信息链（迷迭香+黑键）', room='制造站', product='Pure Gold', mech='资源链',
        need=3, knobs=('宿舍满员', '宿舍等级'),
        want=lambda ds, box: (['迷迭香', '黑键', '爱丽丝', '车尔尼', '絮雨', '夕', '塑心', '深律']
                              + find(ds, box, r'感知信息\+|小节|梦境|记忆碎片')),
        core=lambda ds, box: [o for o in ('迷迭香',) if box.get(o, {}).get('own')],
        subs='提供者按"单位产出换算"排序：记忆碎片(办公室,每招募位10)＞宿舍人数＞小节/梦境(每级+1)；'
             '消费者(迷迭香/黑键)无替补',
        notes='迷迭香把感知信息转思维链环（制造），黑键转无声共鸣（贸易）——同一池资源喂两个房间，'
              '宿舍满员 20 人是最大来源'))
    A.append(dict(
        name='人间烟火（乌有）', room='贸易站', product='LMD', mech='资源链',
        need=1, knobs=('宿舍满员', '夕心情<12'),
        want=lambda ds, box: ['乌有', '夕', '令', '黍', '余', '望'],
        core=lambda ds, box: [o for o in ('乌有',) if box.get(o, {}).get('own')],
        subs='乌有自身就是消费者，无替补；夕/令/黍是烟火提供者，可互相替换（取最高）',
        notes='需要夕在中枢且心情<12 → 与"夕当感知信息提供者(心情>12)"互斥，同一人两种用法'))
    A.append(dict(
        name='仓库体系（红云/泡泡）', room='制造站', product='Battle Record', mech='仓库容量',
        need=3, knobs=(),
        want=lambda ds, box: (['红云', '泡泡'] + find(ds, box, r'仓库容量上限\+\d+', '制造站')
                              + find(ds, box, r'每格仓库容量提供\d+%', '制造站')),
        core=lambda ds, box: [],   # 红云/泡泡是两套替代方案
        subs='红云体系看"每格 2%"，泡泡体系看"≤16格1%/格、>16格3%/格" ⇒ 替补要挑"容量/生产力比"高的'
             '（稀音 12 格 + 经验专精、刻俄柏、石棉、火神、卡达、豆苗）',
        notes='经验书用红云+稀音；赤金用泡泡+刻俄柏。两套不可混（回收利用/配合意识不叠加、优先生效）'))
    A.append(dict(
        name='企鹅物流（德克萨斯/能天使/拉普兰德）', room='贸易站', product='LMD', mech='搭档点名',
        need=3, knobs=(),
        want=lambda ds, box: ['德克萨斯', '能天使', '拉普兰德', '蕾缪安', '摩根', '推进之王',
                              '贝洛内', '伺夜', '雪雉', '空弦'],
        core=lambda ds, box: [o for o in ('德克萨斯', '能天使', '拉普兰德')
                              if box.get(o, {}).get('own')],
        subs='恩怨(德克萨斯×拉普兰德,+65%)与默契是**成对**生效 ⇒ 替补要么整对替换，要么换成"纯效率型"'
             '（雪雉/空弦/月见夜/古米/空爆 +30~40% 档）',
        notes='拉普兰德本身不加效率，她给的是订单上限+4（服务孑/但书）与德克萨斯的+65%'))
    A.append(dict(
        name='孑差额订单', room='贸易站', product='LMD', mech='订单上限联动',
        need=3, knobs=(),
        want=lambda ds, box: (['孑'] + find(ds, box, r'订单上限\+\d+', '贸易站')
                              + ['灵知', '银灰', '初雪', '拉普兰德', '崖心', '角峰', '可颂', '拜松']),
        core=lambda ds, box: [o for o in ('孑',) if box.get(o, {}).get('own')],
        subs='孑 E0（摊贩经济：每差 1 笔 +4%，靠上限拉开差额）与孑 E1+（市井之道：每笔订单 +4%，'
             '但每 10% 队友效率扣 1 上限）是**两套完全不同**的配队 ⇒ 替补池也不同',
        notes='谢拉格包：灵知在中枢给"每个贸易站谢拉格干员 订单上限+6/效率-15%" ⇒ 银灰(+4/15%)/初雪(宿舍)'
              '配合，把上限堆高服务孑'))
    A.append(dict(
        name='雪雉放大器', room='贸易站', product='LMD', mech='放大器',
        need=3, knobs=(),
        want=lambda ds, box: ['雪雉', '能天使', '德克萨斯', '空弦', '月见夜', '古米', '空爆'],
        core=lambda ds, box: [o for o in ('雪雉',) if box.get(o, {}).get('own')],
        subs='雪雉把"队友效率"再放大一次 ⇒ 替补必须本身高效率（能天使/德克萨斯/空弦），不能用低效工具人',
        notes='每个 5% 队友订单效率 → 额外 5%，上限 35%：队友越强她越强（正反馈）'))
    A.append(dict(
        name='设施计数贸易（空弦/图耶/鸿雪）', room='贸易站', product='LMD', mech='设施计数',
        need=3, knobs=('宿舍等级×4', '赤金生产线数量'),
        want=lambda ds, box: (find(ds, box, r'每间宿舍每级|每有\d+条赤金生产线', '贸易站')
                              + ['清流', '奇异'] ),
        core=lambda ds, box: [],   # 布局型：按当前布局取最优
        subs='这类人的收益是**布局的函数**：空弦看宿舍等级（4×Lv5→+40%），图耶/鸿雪看赤金生产线数；'
             '替补只能是"同等布局收益"或干脆换成固定效率型',
        notes='想把图耶/鸿雪拉满就得增加赤金生产线（制造站产赤金的数量），会挤掉碎片/经验产能'))
    A.append(dict(
        name='但书违约 / 可露希尔特别订单', room='贸易站', product='LMD', mech='分布改造',
        need=3, knobs=(),
        want=lambda ds, box: (['但书', '可露希尔'] + find(ds, box, r'订单上限\+\d+', '贸易站')),
        core=lambda ds, box: [o for o in ('但书', '可露希尔') if box.get(o, {}).get('own')],
        subs='但书看"违约订单"（下笔<4 赤金）→ 要靠订单上限/分布把违约比例压低或提高交割量；'
             '可露希尔产"特别订单"（不计违约）⇒ 两者机制不同，不能互替',
        notes='这对是"赤金收支"的调节阀：违约订单吃更多赤金、给更多币，和 --gold 约束强耦合'))
    A.append(dict(
        name='中枢贸易增益（阿米娅/诗怀雅/明椒）', room='控制中枢', product=None, mech='中枢增益',
        need=1, knobs=('贸易站数量',),
        want=lambda ds, box: ['阿米娅', '诗怀雅', '明椒', '重岳', '维什戴尔', '夕', '电弧', '凯尔希'],
        core=lambda ds, box: [o for o in ('阿米娅', '诗怀雅', '明椒') if box.get(o, {}).get('own')],
        subs='三种"所有贸易站+7%"取最高 ⇒ 只需一个在场；替补优先级 明椒(还能顺手提供朝气蓬勃)'
             '≈阿米娅≈诗怀雅',
        notes='中枢还有减压职责：重岳/维什戴尔/电弧/彩虹小队决定别人能不能长班'))
    A.append(dict(
        name='彩虹小队（中枢减压）', room='控制中枢', product=None, mech='心情',
        need=3, knobs=(),
        want=lambda ds, box: term_members(ds, '彩虹小队') + ['战车', '灰烬', '霜华', '闪击'],
        core=lambda ds, box: [o for o in term_members(ds, '彩虹小队') if box.get(o, {}).get('own')],
        subs='需要 3 名同时在中枢才触发全员减压 ⇒ 替补只能同为彩虹小队成员',
        notes='价值不在产出而在"让夕/但书/巫恋这类长班干员不下岗"（配合菲亚梅塔）'))
    A.append(dict(
        name='发电充能（澄闪/深靛/伊芙利特…）', room='发电站', product=None, mech='充能',
        need=3, knobs=('无人机上限', '发电站数量'),
        want=lambda ds, box: (find(ds, box, r'无人机充能速度\+\d+%', '发电站') + ['逻各斯', '森蚺', 'Lancet-2']),
        core=lambda ds, box: [],   # 排序型：按充能%取前 3（互相可替换，无强制核心）
        subs='纯单人岗（发电站上限 1 人/站 ×3）：按充能%降序取前 3。'
             '注意 PhonoR-0 需逻各斯在中枢、承曦格雷伊怕"其他电站有作业平台"',
        notes='无人机是"可搬运的产能"：核算成赤金/龙门币/玉的边际收益再决定投向'))
    A.append(dict(
        name='会客线索', room='会客室', product=None, mech='线索',
        need=2, knobs=('宿舍氛围', '会客室等级'),
        want=lambda ds, box: (['伊内丝', '红', '陈', '伺夜', '梅', '提丰', '凛视', '泰拉大陆调查团']
                              + find(ds, box, r'线索搜集速度', '会客室')),
        core=lambda ds, box: [],   # 排序型：按单人线索速度取前 2
        subs='按"单人线索速度加成"排序（伊内丝+54/红+50/莫斯提马/安洁莉娜/塞雷娅+46…）；'
             '搭档型(提丰×凛视)要么整对要么换纯加成',
        notes='线索速度基础 126% 已含满氛围；星级/精英化也给加成'))
    A.append(dict(
        name='办公室人脉（斥罪/水灯心…）', room='人力办公室', product=None, mech='联络',
        need=1, knobs=('招募位数量', '记忆碎片'),
        want=lambda ds, box: find(ds, box, r'人脉资源的联络速度', '人力办公室'),
        core=lambda ds, box: [],   # 单人岗：谁联络最高用谁
        subs='单人岗（上限 1）：按联络速度%排序，斥罪+50 最高；絮雨例外——她会把记忆碎片转感知信息，'
             '是"感知信息体系"的一环，按体系价值而非纯速度选',
        notes='基础联络速度 5%，1 次刷新需 12h；增招募位/记忆碎片系技能服务于感知信息'))
    A.append(dict(
        name='宿舍恢复/007 保障', room='宿舍', product=None, mech='心情',
        need=4, knobs=('宿舍等级',),
        want=lambda ds, box: (['菲亚梅塔', '杜林', '车尔尼', '爱丽丝', '古米', '初雪']
                              + find(ds, box, r'心情每小时恢复', '宿舍')),
        core=lambda ds, box: [o for o in ('菲亚梅塔',) if box.get(o, {}).get('own')],
        subs='全体恢复(取最高)与单体恢复分工：全体型保整队，单体型(古米/初雪)专门喂 007 关键人',
        notes='菲亚梅塔的患难之交=把满心情换给宿舍前一位 ⇒ 决定"谁可以不下班"'))
    A.append(dict(
        name='阵营计数（岁/深海猎人/莱茵）', room='制造站', product='Pure Gold', mech='阵营计数',
        need=3, knobs=(),
        want=lambda ds, box: (term_members(ds, '岁') + term_members(ds, '深海猎人')
                              + term_members(ds, '莱茵生命')
                              + find(ds, box, r'每有1名.*?干员（最多\d+名）', '制造站')),
        core=lambda ds, box: [],   # 计数型：同阵营可互相替换
        subs='计数型：替补必须同样贡献计数（同阵营/同小队），或者换成纯生产力型',
        notes='同站多人只算一次；歌蕾蒂娅精0/精2 决定 45%/90% 两档'))
    A.append(dict(
        name='至简工程机器人', room='制造站', product='Pure Gold', mech='设施计数',
        need=1, knobs=('全基建设施总等级（上限 64）',),
        want=lambda ds, box: ['至简'] + find(ds, box, r'工程机器人', '制造站'),
        core=lambda ds, box: [o for o in ('至简',) if box.get(o, {}).get('own')],
        subs='单人；替补就是普通高效率制造干员（至简只在"设施等级堆很高"时划算）',
        notes='机器人 = 基建内每间设施每级 +1（满级 333+4宿舍 ≈ 47~59）⇒ 每 8 个 +5%'))
    return A


# ---------------------------------------------------------------- 评估
def best_team(ds, box, room, cands, need, product=None, layout=None, cap=16):
    """从候选池里**枚举组合**取收益最高的一队（组合型体系的本质："三人合起来才强"）。

    逐人贪心会选错：红云/泡泡/雪雉/拉普兰德本人的单人收益很低，他们的价值来自**组合**。
    池子先按单人收益预筛到 cap 个，再穷举 C(cap, need)。"""
    import itertools
    pool = [o for o in dict.fromkeys(cands) if box.get(o, {}).get('own')]
    need = int(need)
    if need <= 0 or not pool:
        return []
    if len(pool) > cap:
        scored = sorted(((revenue(ds, room, [o], product, by_room={room: [o]}, layout=layout)[0], o)
                         for o in pool), reverse=True)
        pool = [o for _v, o in scored[:cap]]
    if len(pool) <= need:
        return pool
    best, bestv = list(pool[:need]), -1.0
    for combo in itertools.combinations(pool, need):
        v, _m, _n = revenue(ds, room, list(combo), product,
                            by_room={room: list(combo)}, layout=layout)
        if v > bestv:
            best, bestv = list(combo), v
    return best


def evaluate(ds, box, layout=None):
    """对每条原型：满配收益 / 留一法稳健度 / 权重 / 档位 / 替补规则

    满配编队的构造规则（重要）：
      ① **核心成员优先**（`core`：机制上必需的人，如 巫恋/温蒂/雪雉/孑/拉普兰德——他们本人的
         单人收益可能是 0，但体系没他们就塌）→ 先占位；
      ② 剩余位置再从候选池按**本房间单人收益**贪心补满。
    缺人曲线：逐个移除**核心成员**，用候选池里最好的人补位，再看收益掉多少
    （`need==1` 的单人岗：如果池里还有别人就是"可换"，否则 0）。"""
    rows = []
    for A in archetypes():
        cands = [o for o in dict.fromkeys(A['want'](ds, box)) if box.get(o, {}).get('own')]
        core = [o for o in A['core'](ds, box) if o and box.get(o, {}).get('own')]
        need = int(A['need'])
        team = list(dict.fromkeys(core))[:need]
        rest_pool = [o for o in cands if o not in team]
        if len(team) < need:
            team += best_team(ds, box, A['room'], rest_pool, need - len(team), A['product'], layout)
        if not team:
            continue
        val, metric, note = revenue(ds, A['room'], team, A['product'],
                                    by_room={A['room']: team}, layout=layout)
        # —— 外部补强：把本体系假设的"其他房间的人"算进账面，并给出补强增益 ——
        sup = SUPPORTS.get(A['name'], {})
        by_with = {A['room']: team}
        for rm, ops in sup.items():
            if rm == 'note':
                continue
            by_with[rm] = [o for o in ops if box.get(o, {}).get('own')]
        v_with, _m2, _n2 = revenue(ds, A['room'], team, A['product'], by_room=by_with, layout=layout)
        support_gain = (v_with / val - 1) if val else 0.0
        val = v_with                       # 满配收益 = **含补强**
        # —— 制造站：红云/稀音这类"容量"同时是生产力与**防爆仓余量** ——
        overflow_h = None
        if A['room'] == '制造站' and val > 0:
            try:
                from core import storage as _ST
                vol = _ST.VOLUME.get(A['product'], 2)
                cap_items = _ST.CAPACITY.get(3, 54) / float(vol)
                overflow_h = round(cap_items / val, 1)      # 不收取时多久会满仓
            except Exception:
                overflow_h = None
        loo, removable = [], [o for o in team if o in core] or list(team)
        for op in removable:
            rest = [o for o in team if o != op]
            pool = [o for o in cands if o not in rest]
            fill = best_team(ds, box, A['room'], pool, need - len(rest), A['product'], layout)
            cand2 = rest + fill
            v2 = 0.0
            if cand2:
                v2, _m, _n = revenue(ds, A['room'], cand2, A['product'],
                                     by_room={A['room']: cand2}, layout=layout)
            loo.append(dict(op=op, rest=round(v2, 3), filled=fill,
                            drop_pct=round((v2 / val - 1) * 100, 1) if val else 0.0))
        robust = min([x['rest'] / val for x in loo], default=1.0) if val else 0.0
        missing = [o for o in (A['core'](ds, box)) if not box.get(o, {}).get('own')]
        rows.append(dict(name=A['name'], room=A['room'], mech=A['mech'], need=need,
                         product=A['product'], team=team, core=[o for o in team if o in core],
                         candidates=cands[:12], missing=missing,
                         value=round(val, 3), metric=metric,
                         note={k: (round(v, 3) if isinstance(v, (int, float)) else v)
                               for k, v in note.items()},
                         leave_one_out=loo, robustness=round(robust, 3),
                         supports={k: v for k, v in sup.items() if k != 'note'},
                         support_gain=round(support_gain, 3), overflow_h=overflow_h,
                         subs=A['subs'], knobs=list(A['knobs']), comments=A['notes']))
    # **支撑型体系**（中枢加成 / 宿舍心情）：它们的价值体现在"别人"身上，
    # 用**显式折算公式**换成等值币/时，才谈得上和产出型一起排权重：
    #   · 中枢贸易增益：加成% × 前三贸易站币/时之和
    #   · 宿舍/彩虹小队等心情支撑：恢复点/时 ÷ 0.9（典型消耗） × 关键岗位币/时 × 受益岗位数
    trade_vals = sorted([r['value'] for r in rows if r['room'] == '贸易站' and r['metric'] == '币/时'],
                        reverse=True)
    top3 = sum(trade_vals[:3]) or 0.0
    key_post = (trade_vals[0] / 24.0) if trade_vals else 0.0
    for r in rows:
        if r['room'] == '控制中枢' and r['metric'] == '全贸易站+%' and r['value']:
            r['value'] = round(top3 * r['value'] / 100.0, 3)
            r['metric'] = '币/时(折算)'
            r['comments'] += '｜折算口径：中枢加成% × 前三贸易站币/时之和'
        elif r['metric'] == '恢复/时':
            mult = 3.0 if '彩虹' in r['name'] else 1.0
            r['value'] = round(r['value'] / 0.9 * key_post * mult, 3)
            r['metric'] = '币/时(折算)'
            r['comments'] += (f'｜折算口径：恢复点/时 ÷ 0.9 × 关键岗位币/时 × 受益岗位数 {mult:g}'
                              f'（关键岗位 = 最优贸易站）')
        elif r['room'] == '控制中枢' and not r['value'] and '彩虹' in r['name']:
            # 彩虹小队：不给贸易加成，价值 = 中枢全员减压 0.75/h（三人在场）→ 折算成岗位价值
            r['value'] = round(0.75 / 0.9 * key_post * 3, 3)
            r['metric'] = '币/时(折算)'
            r['comments'] += '｜折算口径：减压 0.75/h ÷ 0.9 × 关键岗位币/时 × 3 个受益岗位'
    # **按（房间,产物）归一化**：经验/时 与 件/时 不能直接比
    by_key = collections.defaultdict(list)
    for r in rows:
        by_key[(r['room'], r['product'] or '-')].append(r)
    for key, rs in by_key.items():
        top = max([r['value'] for r in rs] or [0.0]) or 1.0
        for r in rs:
            r['norm_value'] = round(r['value'] / top, 3)
            r['weight'] = round(r['norm_value'] * r['robustness'], 3)
    for r in rows:
        w = r['weight']
        r['tier'] = 'S' if w >= 0.75 else 'A' if w >= 0.5 else 'B' if w >= 0.25 else 'C'
    rows.sort(key=lambda r: (-r['weight'], -r['value']))
    return rows


def markdown(rows, extra_sections=()):
    L = ['# 基建体系总表（语义 → 收益函数 → 权重 → 替补规则）', '',
         '> 生成：`python planner\\probe_systems_report.py`；成员由**技能原文语义扫描**得到（新干员进池自动入组），',
         '> 收益全部由本引擎实算（333 布局 / 房间 Lv3 / 4×Lv5 宿舍满员 / 宿舍满员 20 人）。',
         '> **权重 = （同房间归一化满配收益）×（留一法稳健度）**；稳健度 = 缺任一必需成员并用机制替补后，',
         '> 收益/满配收益的最小值。档位 S≥0.75 / A≥0.5 / B≥0.25 / C<0.25。', '']
    L += ['## 一、体系权重总表', '',
          '| 档 | 权重 | 房间 | 体系 | 满配编队（含外部补强假设） | 满配收益 | 补强增益 | 防爆仓余量 | 稳健度 | 最痛缺口 |',
          '|---|---|---|---|---|---|---|---|---|---|']
    for r in rows:
        pain = '—'
        if r['leave_one_out']:
            w = min(r['leave_one_out'], key=lambda x: x['rest'])
            pain = f"{w['op']}（{w['drop_pct']:+.0f}%）"
        gain = r.get('support_gain') or 0.0
        gain_s = f'{gain * 100:+.0f}%' if gain else '—'
        ov = r.get('overflow_h')
        ov_s = f'{ov:g}h' if ov else '—'
        L.append('| {} | {:.2f} | {} | {} | {} | {}{} | {} | {} | {:.2f} | {} |'.format(
            r['tier'], r['weight'], r['room'], r['name'], '+'.join(r['team']),
            r['value'], r['metric'], gain_s, ov_s, r['robustness'], pain))
    L += ['', '## 二、逐体系明细（机制 / 参数 / 缺人曲线 / 注释）', '']
    for r in rows:
        L.append('### [{}] {}（{}，需 {} 人，权重 {:.2f}）'.format(
            r['tier'], r['name'], r['room'], r['need'], r['weight']))
        L.append(f"- 机制：{r['mech']}；布局/参数：{'、'.join(r['knobs']) or '无'}")
        L.append(f"- 满配编队：{'+'.join(r['team'])} → {r['value']}{r['metric']}"
                 + (f"（{r['note']}）" if r['note'] else ''))
        if r.get('supports'):
            L.append('- **外部补强（别的房间的人，已计入上面的收益）**：' +
                     '；'.join(f"{rm}→{'+'.join(ops)}" for rm, ops in r['supports'].items()))
            L.append(f"  - 补强增益：{(r.get('support_gain') or 0) * 100:+.0f}%"
                     + (f"；{SUPPORTS.get(r['name'], {}).get('note', '')}"
                        if SUPPORTS.get(r['name'], {}).get('note') else ''))
        if r.get('overflow_h'):
            L.append(f"- **防爆仓余量**：不收取时 {r['overflow_h']:g}h 后满仓（容量 Lv3=54 ÷ 体积）"
                     f"——红云/稀音这类仓库系的价值一半在这里")
        L.append(f"- 候选池（已持有，按单人收益排序）：{'、'.join(r['candidates']) or '—'}")
        if r['missing']:
            L.append(f"- ⚠ 你缺：{'、'.join(r['missing'])}")
        if r['leave_one_out']:
            L.append('- 缺人曲线（留一法 + 机制替补）：' +
                     '；'.join(f"{x['op']}→{x['rest']}{r['metric']}（{x['drop_pct']:+.0f}%）"
                               for x in r['leave_one_out']))
        L.append(f"- 替补规则：{r['subs']}")
        L.append(f"- 注释：{r['comments']}")
        L.append('')
    for title, lines in extra_sections:
        L += [f'## {title}', ''] + list(lines) + ['']
    return '\n'.join(L)
