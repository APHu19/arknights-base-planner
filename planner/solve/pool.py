# -*- coding: utf-8 -*-
"""pool.py —— 候选池与单房间打分

按计划书 4c 的优先级**生成顺序**（不是硬分层）：
    体系干员 > 拥有本房间技能的干员 > 仅拥有宿舍技能的干员 > 其余
其中“体系干员”= 能产生/消费中间产物（人间烟火/感知信息/无声共鸣/思维链环/巫术结晶/魔物料理…）的干员。
真正的取舍交给束搜索按**房间收益**打分，不做硬性分层（硬分层会亏效率，已实测过）。
"""
from core.engine import eval_room, shift_output, RATE
from core.dataset import Dataset

SYSTEM_OPS = {
    # 产生者
    '迷迭香', '黑键', '塑心', '深律', '絮雨', '车尔尼', '爱丽丝', '夕', '令', '黍', '桑葚',
    '截云', '森西', '灰烬', '战车', '至简', '红云', '槐琥', '雪雉', '异客', '维什戴尔', '魔王',
    '菲亚梅塔', '歌蕾蒂娅', '斯卡蒂', '幽灵鲨', '安哲拉', '乌尔比安', '泰拉大陆调查团',
    '火龙S黑角', '麒麟R夜刀', '丰川祥子', '若叶睦',
    # 消费者
    '乌有', '但书', '可露希尔', '佩佩', '鸿雪', '绮良', '齐尔查克', '玛恩纳',
}
DORM_ONLY_ROOMS = ('宿舍',)


def relevant_ops(ds, room):
    """拥有该房间技能的干员（含档位归并后的判断）"""
    out = set()
    for s in ds.skills:
        if s.room == room:
            out.update(s.holders)
    return out


def eligible_pool(ds, box, room, exclude=(), products=None):
    """按优先级排序的候选池。exclude：已被其他房间占用的干员。"""
    owned = {o for o, v in box.items() if v.get('own')}
    rel = relevant_ops(ds, room)
    dorm_rel = relevant_ops(ds, '宿舍')
    pri = []
    for op in sorted(owned):
        if op in exclude or op in DORM_ONLY_ROOMS:
            continue
        if op in SYSTEM_OPS and (op in rel or op in dorm_rel):
            pri.append((0, op))
        elif op in rel:
            pri.append((1, op))
        elif op in dorm_rel:
            pri.append((2, op))
        elif op in SYSTEM_OPS:
            pri.append((0, op))
    pri.sort()
    return [op for _, op in pri]


def score_team(room, level, product, team, ctx, ds, hours=12.0):
    """返回 (主指标, 明细报告, 产出字典)"""
    out, r = shift_output(room, level, product, team, ctx, hours, ds)
    if room == '发电站':
        return r['charge'], r, out
    if 'lmd' in out:
        return out['lmd'], r, out
    if 'gold' in out:
        return out['gold'], r, out
    if 'shard' in out:
        return out['shard'], r, out
    if 'orundum' in out:
        return out['orundum'], r, out
    if 'exp' in out:
        return out['exp'], r, out
    return 0.0, r, out


def room_products(room, cfg):
    """cfg: {'贸易站': [('LMD',3),('Orundum',3)], '制造站': [('Pure Gold',3)], ...}"""
    return cfg.get(room, [])
