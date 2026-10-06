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

ROOM_COLORS = {'制造站': '#FFCC00', '贸易站': '#33CCFF', '发电站': '#CCFF66', '空': '#DDDDDD'}
ROOM_ORDER9 = ['制造站', '贸易站', '发电站', '空']
ROMAN = {1: 'Ⅰ', 2: 'Ⅱ', 3: 'Ⅲ'}
MANU_PRODUCTS = ['Pure Gold', 'Originium Shard', 'Battle Record']
TRADE_PRODUCTS = ['LMD', 'Orundum']
PRODUCT_CN = {'Pure Gold': '赤金', 'Originium Shard': '源石碎片', 'Battle Record': '作战记录',
              'LMD': '龙门币', 'Orundum': '合成玉'}
# 界面下拉用中文标签，值自动映射成 solver 的英文产物名
PRODUCT_CHOICES = {
    '制造站': [('赤金', 'Pure Gold'), ('作战记录（经验）', 'Battle Record'),
             ('源石碎片', 'Originium Shard')],
    '贸易站': [('龙门币（赤金订单）', 'LMD'), ('合成玉（源石订单）', 'Orundum')],
    '发电站': [],
    '空': [],
}
PRODUCT_BY_CN = {room: {cn: en for cn, en in opts} for room, opts in PRODUCT_CHOICES.items()}
PRODUCT_TO_CN = {en: cn for opts in PRODUCT_CHOICES.values() for cn, en in opts}

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
ELITE_CN = {0: '精0', 1: '精1', 2: '精2'}        # elite 就是精英化阶段（0/1/2）；"未持有"另有标志
MAX_ELITE = 2


def maa_export_path():
    return os.path.join(ROOT, 'Arknights_OperBox_Export.json')


def default_box():
    """默认用本地 MAA 导出（若存在）"""
    p = maa_export_path()
    if os.path.exists(p):
        return import_maa_json(p)
    return {}


def _entry(name, own=True, elite=0):
    return {'own': bool(own), 'elite': max(0, min(MAX_ELITE, int(elite or 0)))}


def _load_json(path):
    return json.load(open(path, encoding='utf-8-sig'))


def _rows_of(raw):
    """把各种 JSON 结构归一成 '条目列表'：
       · MAA 导出 = [{'name':…, 'own':…, 'elite':…}, …]
       · 本程序导出 = {'名字': {'own':…, 'elite':…}, …}
       · {'operators': [...]} / 任何含有列表值的字典"""
    if isinstance(raw, dict):
        for k in ('operators', 'ops', 'chars', 'data', 'box'):
            if isinstance(raw.get(k), list):
                return raw[k]
        if raw and all(isinstance(v, dict) for v in raw.values()):
            return [dict(name=k, **(v or {})) for k, v in raw.items()]
        for v in raw.values():
            if isinstance(v, list):
                return v
        return []
    return raw if isinstance(raw, list) else []


def import_maa_json(path):
    """读 MAA 导出 / 本程序导出的干员池 → {名字: {'own':bool,'elite':0..2}}

    MAA 导出走 `core.dataset.load_box`（它做了**重名去重**：阿米娅在导出里有 3 条，
    未持有的"阿米娅近卫/术师"会覆盖掉真正持有的那条 —— 那是"我明明有却显示没有"的根因）。
    """
    from core.dataset import load_box
    return {n: _entry(n, v.get('own', True), v.get('elite', 0)) for n, v in load_box(path).items()}


def sync_box_from_maa(box, path=None):
    """把干员池里"与本地 MAA 导出同名"的条目**按导出重设**持有/精英化（修被误点坏的数据）；
    导出里没有的名字保持原样。返回 (新 box, 改动条数, 导出路径)"""
    p = path or maa_export_path()
    if not os.path.exists(p):
        raise FileNotFoundError(f'找不到 MAA 导出：{p}')
    ref = import_maa_json(p)
    out = dict(box or {})
    changed = 0
    for name, v in ref.items():
        cur = out.get(name)
        if (not cur) or bool(cur.get('own')) != bool(v['own']) or int(cur.get('elite', 0)) != v['elite']:
            changed += 1
        out[name] = dict(v)
    return out, changed, p


def _looks_like_path(t):
    """是否是文件路径（含引号、Windows 盘符、.json 后缀、或当前目录下真实存在的文件）"""
    s = t.strip().strip('"').strip("'")
    if not s or '\n' in s:
        return None
    if s.lower().endswith('.json') or re.match(r'^[A-Za-z]:[\\/]', s) or s.startswith('\\\\'):
        return s if os.path.exists(s) else None
    if os.path.exists(s) and os.path.isfile(s):
        return s
    return None


def parse_box_text(text, base=None):
    """解析"剪贴板/文本框"内容。支持四种（按顺序尝试）：
       ① **文件路径**（如 C:\\...\\Arknights_OperBox_Export.json，可带引号）→ 按 JSON 读入
       ② MAA 导出 JSON 片段：[{'name':…, 'own':…, 'elite':…}, …]
       ③ 本程序导出的 JSON：{'名字': {'own':…, 'elite':…}, …}
       ④ 纯名单：每行一个名字，可带 精0/精1/精2（或 0/1/2）
    """
    box = dict(base or {})
    t = (text or '').strip()
    if not t:
        return box
    p = _looks_like_path(t)
    if p:
        box.update(import_maa_json(p))
        return box
    if t.lstrip().startswith(('{', '[')):
        try:
            raw = json.loads(t)
        except Exception:
            raw = None
        if raw is not None:
            for o in _rows_of(raw):
                if isinstance(o, dict) and o.get('name'):
                    box[o['name']] = _entry(o['name'], o.get('own', 1), o.get('elite', 0))
                elif isinstance(o, str):
                    box[o] = _entry(o)
            return box
    for line in t.splitlines():
        line = line.strip().strip('"').strip("'")
        if not line:
            continue
        m = re.match(r'^(.+?)[\s,，\t]+(?:精)?([0-2])(?:\s|$)', line)
        if m:
            box[m.group(1).strip()] = _entry(m.group(1).strip(), True, int(m.group(2)))
        else:
            cur = box.get(line) or {}
            box[line] = _entry(line, True, cur.get('elite', 0))
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
    st.setdefault('other_power', 450)          # 固定房间合计耗电：默认 450
    st.setdefault('sched', 'window')           # 排班路径：默认窗口排班（判据 A）
    st.setdefault('trust', False)              # 信赖权重：让更多不同干员轮到班
    st.setdefault('min_eff', {'会客室': 0, '人力办公室': 0})
    for k in ('own', 'elite'):                 # 旧版本可能存过别的结构，兜底清掉
        st['box'] = {n: _entry(n, v.get('own', True), v.get('elite', 0))
                     for n, v in (st.get('box') or {}).items() if isinstance(v, dict)}
    st.setdefault('box_warn', '')
    return st
