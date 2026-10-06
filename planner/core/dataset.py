# -*- coding: utf-8 -*-
"""dataset.py —— 技能库 / 干员池 / 术语（全局变量）的载入与索引

设计要点：
* 技能主键用 icon（bskill_xxx），因为**技能名会重名**（标准化·β、金属工艺·α 等被多人共用）。
* 术语表（terms）就是全局变量注册表：赤金生产线、人间烟火、感知信息… 由 wiki 注释抽取。
"""
import json, os, re
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
PLANNER = os.path.dirname(HERE)
DATA = os.path.join(PLANNER, 'data')
ROOT = os.path.dirname(PLANNER)          # dsh生成333基建表

ROOMS = ['控制中枢', '贸易站', '制造站', '发电站', '会客室', '人力办公室', '加工站', '训练室', '宿舍']
# MAA 房间键（训练室不在协议内！）
MAA_ROOM = {'控制中枢': 'control', '贸易站': 'trading', '制造站': 'manufacture', '发电站': 'power',
            '会客室': 'meeting', '人力办公室': 'hire', '加工站': 'processing', '宿舍': 'dormitory'}


class Skill:
    __slots__ = ('key', 'name', 'room', 'desc', 'holders', 'icon')

    def __init__(self, key, name, room, desc, holders, icon=None):
        self.key, self.name, self.room, self.desc, self.holders = key, name, room, desc, holders
        self.icon = icon

    def __repr__(self):
        return f'<Skill {self.key} {self.name} @{self.room} x{len(self.holders)}>'


class Dataset:
    def __init__(self, path=None):
        self.raw = json.load(open(path or os.path.join(DATA, 'skills_raw.json'), encoding='utf-8'))
        self.terms = self.raw['terms']
        self.skills = []                 # 全部技能行
        self.by_key = {}                 # icon -> Skill（同 icon 多处出现时合并 holders）
        self.by_name = defaultdict(list)  # 名称 -> [Skill]
        self.op_skills = defaultdict(list)  # 干员 -> [Skill]
        for room, rows in self.raw['rooms'].items():
            for r in rows:
                # 主键 = (房间, 技能名)。icon 并非唯一（如 bskill_man_spd2 同时是 红松骑士团·β/莱茵科技·β/标准化·β），
                # 名称也非全局唯一，故二者组合才是稳定键。
                key = f"{room}:{r['name']}"
                if key in self.by_key:
                    s = self.by_key[key]
                    for h in r['holders']:
                        if h not in s.holders: s.holders.append(h)
                    continue
                s = Skill(key, r['name'], room, r['desc'], list(r['holders']), r.get('icon'))
                self.skills.append(s); self.by_key[key] = s; self.by_name[s.name].append(s)
                for h in r['holders']:
                    self.op_skills[h].append(s)
        self.globals = self._build_globals()
        self._members_cache = {}
        self._box, self._elite = {}, {}
        # 精英化阶段 → 技能 的权威映射（building_data.json 的 buffChar/cond.phase）
        self.phases = {}
        _ph = os.path.join(DATA, 'phases.json')
        if os.path.exists(_ph):
            try:
                self.phases = json.load(open(_ph, encoding='utf-8')).get('ops') or {}
            except Exception:
                self.phases = {}
        # 载入权威《基建术语》整理结果（干员分类 / 中间产物 / 特殊叠加规则…）
        self.base_terms = {}
        _bt = os.path.join(DATA, 'base_terms.json')
        if os.path.exists(_bt):
            self.base_terms = json.load(open(_bt, encoding='utf-8'))

    # ---------- 全局变量注册表（术语 + 基础值公式 + 提供者） ----------
    RESOURCES = {
        '赤金生产线': dict(base='生产赤金的制造站数量', kind='计数', note='可由绮良/鸿雪等技能增加，被贸易站订单效率与制造站技能读取'),
        '人间烟火': dict(base='0（由岁干员/乌有/令等技能累积）', kind='资源', note='影响订单获取效率、黍的生产力'),
        '感知信息': dict(base='0（宿舍人数/车尔尼/爱丽丝/絮雨等提供）', kind='资源', note='转化为思维链环'),
        '思维链环': dict(base='= 感知信息', kind='资源', note='影响念力/迷迭香生产力'),
        '无声共鸣': dict(base='0（塑心按宿舍人数提供）', kind='资源', note='影响徘徊旋律/怅惘和声'),
        '巫术结晶': dict(base='0（截云等提供）', kind='资源', note='影响相关贸易/制造技能'),
        '情报储备': dict(base='0（灰烬提供）', kind='资源', note='影响相关技能'),
        '热情值': dict(base='0（Ave Mujica 系干员提供）', kind='资源', note='影响丰富工作经验/演技的怪物'),
        '木天蓼': dict(base='0（怪物猎人小队提供）', kind='资源', note='影响可爱的艾露猫'),
        '外势': dict(base='贸易站数 + 发电站数', kind='计数', note='望：外势≥实地 时全体贸易站订单效率+7%'),
        '实地': dict(base='制造站数', kind='计数', note='望：实地>外势 时全体制造站生产力+2%'),
        '小节': dict(base='宿舍等级 × 1/人（车尔尼）', kind='资源', note='转化为感知信息'),
        '梦境': dict(base='宿舍等级 × 1/人（爱丽丝）', kind='资源', note='转化为感知信息'),
        '心情落差': dict(base='心情上限 − 当前心情', kind='派生', note='部分技能按落差加成'),
    }
    # 标准化的“类型改写”关系：哪些技能属于标准化类，以及谁能把别的技能改写成标准化
    TYPE_CONVERT = {'标准化类技能': ['标准化·α', '标准化·β']}

    def _build_globals(self):
        g = {}
        for name, t in self.terms.items():
            g[name] = dict(defs=t.get('defs', []), providers=t.get('providers', []),
                           kind='术语', base=None, note='')
        for name, meta in self.RESOURCES.items():
            g.setdefault(name, dict(defs=[], providers=[], kind='术语', base=None, note=''))
            g[name].update(kind=meta['kind'], base=meta['base'], note=meta['note'])
        return g

    # ---------- 查询 ----------
    def set_box(self, box):
        """登记干员池的精英化阶段，供 skills_of 做阶段过滤。"""
        self._box = box or {}
        self._elite = {n: int((v or {}).get('elite', 0) or 0) for n, v in self._box.items()}
        return self

    def skills_of(self, op, room=None, dedup=True, elite=None):
        """干员的技能。
        · **阶段过滤**：phases.json 里记录每个技能从哪个精英化阶段起解锁（cond.phase），
          只保留“当前阶段已解锁”的（如 明椒 E0 只有 裁缝·α，E2 才有 裁缝·β）。
          干员池里没有的人按“已练满”放宽，避免漏算。
        · **档位归并**：同名同族技能只保留最高档（wiki 表里同一干员会同时出现在 α/β 两行）。
        """
        rows = [s for s in self.op_skills.get(op, []) if room is None or s.room == room]
        if self.phases:
            lv = self._elite.get(op, 3) if elite is None else int(elite)
            pr = self.phases.get(op) or {}
            if room:
                entry = pr.get(room)
                if entry:      # 该干员在这个房间有阶段记录 → 严格按阶段过滤（可能过滤成空）
                    avail = [r['name'] for r in entry if int(r['phase']) <= lv]
                    rows = [s for s in rows if (s.name or '') in avail]
            else:
                kept = []
                for s in rows:
                    entry = pr.get(s.room)
                    if not entry:
                        kept.append(s); continue
                    if (s.name or '') in [r['name'] for r in entry if int(r['phase']) <= lv]:
                        kept.append(s)
                rows = kept
        if not dedup:
            return rows
        best = {}
        for s in rows:
            m = re.search(r'[·・]([αβγ])$', s.name or '')
            fam = re.sub(r'[·・][αβγ]$', '', s.name or '')
            tier = {'α': 1, 'β': 2, 'γ': 3}.get(m.group(1), 9) if m else 9
            if fam not in best or tier > best[fam][0]:
                best[fam] = (tier, s)
        return [s for _, s in best.values()]

    def term_def(self, name):
        return ' | '.join(self.globals.get(name, {}).get('defs', []) or [])[:200]

    def members_of(self, term):
        """解析“集合型术语”的成员名单（干员/技能/设施）。
        术语定义形如：
          包含以下干员赫默、伊芙利特、…、娜斯提
          包含以下技能标准化·α、标准化·β
          包含以下设施发电站、制造站、贸易站…
          由以下干员提供望每有一间贸易站、发电站，外势+1     ← 需截断效果文本
        """
        if term in self._members_cache:
            return self._members_cache[term]
        # 优先使用权威整理结果里的“干员分类”（技能判定用的就是这一套）
        official = (self.base_terms.get('干员分类') or {}).get(term)
        if isinstance(official, list):
            self._members_cache[term] = official
            return official
        txt = ' '.join(self.globals.get(term, {}).get('defs', []))
        if not re.match(r'^(包含以下干员|包含以下技能|包含以下设施|由以下干员的基建技能提供|'
                        r'由以下干员提供|拥有该基建技能的干员|包含所有)', txt):
            self._members_cache[term] = []      # 资源/派生类术语（可影响…/每当…）没有成员名单
            return []
        txt = re.sub(r'^(包含以下干员|包含以下技能|包含以下设施|由以下干员的基建技能提供|由以下干员提供|'
                     r'拥有该基建技能的干员|包含所有异格干员.*?|包含所有)', '', txt).strip()
        bad = ('每', '提供', '影响', '包含', '则', '时', '+', '%', '点', '间', '名', '个')
        out = []
        for tok in re.split(r'[、,，。；;：:\s]+', txt):
            tok = tok.strip()
            if not tok or len(tok) > 14 or any(b in tok for b in bad):
                tok = re.split(r'(?=每|提供|影响|则|时)', tok)[0].strip()
                if not tok or len(tok) > 14 or any(b in tok for b in bad):
                    continue
            out.append(tok)
        self._members_cache[term] = out
        return out

    def terms_of_operator(self, op):
        """该干员出现在哪些集合型术语里（种族/势力/小队/技能类…）"""
        return [t for t in self.globals if op in self.members_of(t)]

    def is_standardized(self, skill):
        """是否属于“标准化类技能”（名称含“标准化”，对间隔号字符差异免疫；含类型改写后的临时标记）"""
        return '标准化' in (skill.name or '') or getattr(skill, 'forced_standard', False)

    def standard_skill_names(self):
        """从术语注释里解析标准化类技能的准确名称，失败则回退"""
        d = ' '.join(self.terms.get('标准化类技能', {}).get('defs', []))
        names = re.findall(r'标准化[·・\.][αβγa-zA-Z]+', d)
        return names or ['标准化·α', '标准化·β']


def load_box(path=None):
    """读取干员池（MAA 导出）。返回 {名字: {own, elite, potential}}

    **重名去重（重要，踩过）**：MAA 导出里"阿米娅"有三条 ——
    `char_002_amiya`（持有、精2）与 `char_1001_amiya2` / `char_1037_amiya3`（阿米娅近卫/术师，未持有）。
    朴素的 `out[o['name']] = …` 会让**后面的未持有条目覆盖真正持有的那条**，
    于是 阿米娅 被当成"未持有/精0"：GUI 显示未持有、MAA 校验报 `未持有干员 ['阿米娅']`、
    求解器候选池也跟着少人。合并规则：**持有优先 → 精英化高优先 → char_ 前缀优先**。
    """
    p = path or os.path.join(ROOT, 'Arknights_OperBox_Export.json')
    box = json.load(open(p, encoding='utf-8-sig'))
    if isinstance(box, dict):
        for v in box.values():
            if isinstance(v, list):
                box = v
                break
    best = {}
    for o in box:
        if not isinstance(o, dict) or not o.get('name'):
            continue
        name = o['name']
        rec = dict(own=bool(o.get('own', 1)), elite=int(o.get('elite', 0) or 0),
                   potential=int(o.get('potential', 0) or 0))
        oid = str(o.get('id') or '')
        key = (rec['own'], rec['elite'], oid.startswith('char_'), oid)
        if name not in best or key > best[name][0]:
            best[name] = (key, rec)
    return {n: rec for n, (_k, rec) in best.items()}


if __name__ == '__main__':
    ds = Dataset()
    print('技能', len(ds.skills), '| 干员', len(ds.op_skills), '| 术语', len(ds.terms))
    print('\n资源/计数类全局变量：')
    for k, v in ds.globals.items():
        if v['kind'] != '术语':
            print(f"  {k:<8}[{v['kind']}] 基础值={v['base']}  {v['note'][:40]}")
    print('\n术语中名含“生产线/值/势/地/共鸣/链环/信息/烟火/结晶/储备”的：')
    for k in ds.globals:
        if re.search(r'生产线|热情值|外势|实地|共鸣|链环|感知|烟火|结晶|情报储备|心情落差', k):
            print(f'  {k}: {ds.term_def(k)[:80]}')
