# -*- coding: utf-8 -*-
"""state.py —— GUI 状态与持久化

· 干员池：导入 MAA JSON / 粘贴文本 / 可视化点选 三条入口 → 统一为 {名字: {'own':bool,'elite':int}}
· 记忆上次选择：写入 gui/config.json，下次启动自动恢复
· 九宫格与班次结构：与 solver 的 cfg 互相转换
"""
import json, os, re, copy

HERE = os.path.dirname(os.path.abspath(__file__))
PLANNER = os.path.dirname(HERE)
ROOT = os.path.dirname(PLANNER)
CONFIG = os.path.join(HERE, 'config.json')

ROOM_COLORS = {'制造站': '#E8A33D', '贸易站': '#7FB3D5', '发电站': '#7CFC00', '空': '#DDDDDD'}
ROOM_ORDER9 = ['制造站', '贸易站', '发电站', '空']
ROMAN = {1: 'Ⅰ', 2: 'Ⅱ', 3: 'Ⅲ'}
MANU_PRODUCTS = ['Pure Gold', 'Originium Shard', 'Battle Record']
TRADE_PRODUCTS = ['LMD', 'Orundum']
PRODUCT_CN = {'Pure Gold': '赤金', 'Originium Shard': '源石碎片', 'Battle Record': '作战记录',
              'LMD': '龙门币', 'Orundum': '源石订单'}

LAYOUT_PRESETS = {
    # 每格 = (房间, 产物, 等级)
    '333': [('制造站', 'Pure Gold', 3), ('制造站', 'Pure Gold', 3), ('制造站', 'Originium Shard', 3),
            ('贸易站', 'LMD', 3), ('贸易站', 'LMD', 3), ('贸易站', 'Orundum', 3),
            ('发电站', None, 3), ('发电站', None, 3), ('发电站', None, 3)],
    '333经验': [('制造站', 'Pure Gold', 3), ('制造站', 'Battle Record', 3), ('制造站', 'Battle Record', 3),
              ('贸易站', 'LMD', 3), ('贸易站', 'LMD', 3), ('贸易站', 'LMD', 3),
              ('发电站', None, 3), ('发电站', None, 3), ('发电站', None, 3)],
    '243': [('制造站', 'Pure Gold', 3), ('制造站', 'Pure Gold', 3), ('制造站', 'Pure Gold', 3),
            ('制造站', 'Originium Shard', 3), ('贸易站', 'LMD', 3), ('贸易站', 'Orundum', 3),
            ('发电站', None, 3), ('发电站', None, 3), ('发电站', None, 3)],
    '153': [('制造站', 'Pure Gold', 3), ('制造站', 'Pure Gold', 3), ('制造站', 'Pure Gold', 3),
            ('制造站', 'Originium Shard', 3), ('制造站', 'Battle Record', 3), ('贸易站', 'LMD', 3),
            ('发电站', None, 3), ('发电站', None, 3), ('发电站', None, 3)],
    # 252 = 2 发电 / 5 制造 / 2 贸易：发电只有两座 → 部分**赤金**站降级
    # （非三级制造站只能产赤金，碎片站必须 Lv3）
    '252(部分Lv2)': [('制造站', 'Pure Gold', 2), ('制造站', 'Pure Gold', 2), ('制造站', 'Pure Gold', 2),
                    ('制造站', 'Originium Shard', 3), ('制造站', 'Originium Shard', 3),
                    ('贸易站', 'LMD', 3), ('贸易站', 'Orundum', 3),
                    ('发电站', None, 3), ('发电站', None, 3)],
}

DEFAULT_SHIFTS = [{'start': '00:00', 'end': '04:00'}, {'start': '04:00', 'end': '08:00'},
                  {'start': '08:00', 'end': '12:00'}, {'start': '12:00', 'end': '16:00'},
                  {'start': '16:00', 'end': '20:00'}, {'start': '20:00', 'end': '24:00'}]


# ---------------------------------------------------------------- 干员池
def default_box():
    """默认用本地 MAA 导出（若存在）"""
    p = os.path.join(ROOT, 'Arknights_OperBox_Export.json')
    if os.path.exists(p):
        return import_maa_json(p)
    return {}


def import_maa_json(path):
    raw = json.load(open(path, encoding='utf-8-sig'))
    if isinstance(raw, dict):
        for v in raw.values():
            if isinstance(v, list): raw = v; break
    out = {}
    for o in raw:
        if not o.get('name'): continue
        out[o['name']] = {'own': bool(o.get('own', 1)), 'elite': int(o.get('elite', 0) or 0)}
    return out


def parse_box_text(text, base=None):
    """解析粘贴文本。支持两种：
       · MAA JSON 片段（含 "name"/"elite"）
       · 纯名单：每行一个名字，可带 精0/精1/精2、0/1/2 或 精英化x
    """
    box = dict(base or {})
    t = (text or '').strip()
    if not t:
        return box
    if t.lstrip().startswith(('{', '[')):
        try:
            raw = json.loads(t)
            if isinstance(raw, dict):
                for v in raw.values():
                    if isinstance(v, list): raw = v; break
            for o in raw:
                if isinstance(o, dict) and o.get('name'):
                    box[o['name']] = {'own': bool(o.get('own', 1)), 'elite': int(o.get('elite', 0) or 0)}
                elif isinstance(o, str):
                    box[o] = {'own': True, 'elite': 0}
            return box
        except Exception:
            pass
    for line in t.splitlines():
        line = line.strip()
        if not line: continue
        m = re.match(r'^(.+?)[\s,，\t]+(?:精)?([0-2])(?:\s|$)', line)
        if m:
            name = m.group(1).strip()
            box[name] = {'own': True, 'elite': int(m.group(2))}
        else:
            box[line] = {'own': True, 'elite': box.get(line, {}).get('elite', 0)}
    return box


def owned_list(box):
    return sorted([n for n, v in box.items() if v.get('own')])


# ---------------------------------------------------------------- 九宫格 ↔ cfg
def grid_to_cfg(grid, level=None):
    """grid: 长度 9 的 [(房间, 产物, 等级)] → solver 的 cfg（按格等级）
    level 参数仅为兼容旧调用：给了就统一用它。"""
    cfg = {}
    for cell in grid:
        room, prod = cell[0], cell[1]
        lv = int(cell[2]) if len(cell) > 2 else (level or 3)
        if level: lv = level
        if room == '空' or not room: continue
        cfg.setdefault(room, []).append((prod, lv))
    return cfg


def cfg_to_grid(cfg):
    out = []
    for room in ('制造站', '贸易站', '发电站'):
        for prod, lv in cfg.get(room, []):
            out.append((room, prod, lv))
    while len(out) < 9: out.append(('空', None, 3))
    return out[:9]


def power(grid, other=190.0):
    """按格等级计算电力。other：固定房间合计耗电
    （文档口径 = 会客60+办公10+加工60+训练60+宿舍0 = 190；旧口径 4×宿舍65 则为 450）"""
    supply, consume = 0, 0
    for cell in grid:
        room, prod = cell[0], cell[1]
        lv = int(cell[2]) if len(cell) > 2 else 3
        if room == '发电站': supply += {1: 60, 2: 130, 3: 270}.get(lv, 0)
        elif room in ('制造站', '贸易站'): consume += {1: 10, 2: 30, 3: 60}.get(lv, 0)
    consume += other
    return supply, consume, supply - consume


# ---------------------------------------------------------------- 持久化
def save_config(state):
    json.dump(state, open(CONFIG, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)


def load_config():
    if os.path.exists(CONFIG):
        try:
            return json.load(open(CONFIG, encoding='utf-8'))
        except Exception:
            pass
    return {}


def initial_state():
    st = load_config()
    st.setdefault('box', default_box())
    st.setdefault('grid', LAYOUT_PRESETS['333'])
    st.setdefault('objective', 'lmd_gold_bal')
    st.setdefault('shifts', copy.deepcopy(DEFAULT_SHIFTS))
    st.setdefault('dorm_mode', 'precise')
    st.setdefault('fiammetta', True)
    st.setdefault('level', 3)
    return st
