# -*- coding: utf-8 -*-
"""meeting.py —— 会客室线索搜集速度（用户提供数值 + 全机制.md 规则）

规则（《全机制.md》§线索搜集速度 + 用户补充的数值）：
  · **每份线索基础生成时间 20 小时**
  · 基础效率默认 **126%**
  · 每名进驻干员提供：稀有度档（4星+2% / 5星+4% / 6星+5%）
                      + 精英化档（精1 +8% / 精2 +16%）
                      + **未红脸 +5%**（心情 > 0）
  · 会客室后勤技能的百分数**加算**（伊内丝·聚影为慢热：20%→+2%/h→上限 30%；
    无辜笑脸仅**线索交流**期间生效）
  · 各类单项取最高值；宿舍总氛围档尚未确证，默认按 0 计（可用 ambience 传入）

产出：`clue_per_day = 24 / (20 / (1 + speed/100))`（份/天）
"""
import json, os, re, functools

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
CT = os.path.join(ROOT, '_raw', 'character_table.json')

BASE = 126.0
RARITY_BONUS = {4: 2.0, 5: 4.0, 6: 5.0}
ELITE_BONUS = {0: 0.0, 1: 8.0, 2: 16.0}
NOT_RED = 5.0
CLUE_HOURS = 20.0


@functools.lru_cache(maxsize=1)
def stars():
    """干员 → 星级（1~6）。容错多种字段名与结构；失败则回退到干员池导出。"""
    out = {}
    def take(rec):
        nm = rec.get('name') or rec.get('cnName') or rec.get('nameCn')
        r = rec.get('rarity', rec.get('star', rec.get('stars', rec.get('rarityId'))))
        if not nm or r is None:
            return
        try:
            if isinstance(r, str):                       # 本 dump 用 'TIER_5' 这类字符串
                m = re.search(r'(\d+)', r)
                n = int(m.group(1)) if m else None
            else:
                n = int(r)
                if n <= 5: n += 1                        # 数字形式是 0~5
            if n and 1 <= n <= 6:
                out.setdefault(str(nm), n)
        except Exception:
            pass
    try:
        ct = json.load(open(CT, encoding='utf-8'))
        rows = ct.values() if isinstance(ct, dict) else ct
        # 只认真正的干员 id：trap_/token_ 召唤物/装置会与干员同名并抢占条目
        for cid, c in (ct.items() if isinstance(ct, dict) else [(None, x) for x in ct]):
            if not isinstance(c, dict):
                continue
            nm = c.get('name')
            if not nm:
                continue
            r = c.get('rarity', c.get('star', c.get('stars', c.get('rarityId'))))
            if r is None:
                continue
            try:
                if isinstance(r, str):
                    m = re.search(r'(\d+)', r)
                    n = int(m.group(1)) if m else None
                else:
                    n = int(r)
                    if n <= 5: n += 1
            except Exception:
                continue
            if not n or not (1 <= n <= 6):
                continue
            if cid and str(cid).startswith('char_'):
                out[str(nm)] = n            # 真干员：强制覆盖
            else:
                out.setdefault(str(nm), n)  # 其它前缀（trap_/token_/召唤物）：仅在缺位时补
    except Exception:
        pass
    if not out:
        try:                                    # 回退：MAA 干员池导出
            p = os.path.join(ROOT, 'Arknights_OperBox_Export.json')
            raw = json.load(open(p, encoding='utf-8-sig'))
            if isinstance(raw, dict):
                for v in raw.values():
                    if isinstance(v, list): raw = v; break
            for rec in raw:
                if isinstance(rec, dict): take(rec)
        except Exception:
            pass
    return out


def _rarity_bonus(st):
    return max([v for k, v in RARITY_BONUS.items() if st >= k] or [0.0])


def skill_bonus(op, ds, hours=4.0, exchanging=False):
    """该干员在会客室的后勤技能加成%"""
    tot = 0.0
    for s in ds.skills_of(op, '会客室'):
        d = s.desc or ''
        m = re.search(r'线索搜集速度提升(\d+)%', d)
        v = float(m.group(1)) if m else 0.0
        m2 = re.search(r'每小时提升(\d+)%，最终达到(\d+)%', d)   # 伊内丝·聚影（慢热）
        if m2:
            v = min(float(m2.group(2)), v + float(m2.group(1)) * hours)
        if '线索交流' in d and not exchanging:                    # 无辜笑脸：仅交流期间
            v = 0.0
        tot += v
    return tot


def speed(team, ds, box=None, morale=None, ambience=0.0, exchanging=False, hours=4.0,
          include_skill=True):
    """返回 dict(speed%, skill%, detail, clue_per_day)"""
    st_map = stars()
    box = box or {}
    total = BASE + ambience
    detail = []
    for op in team:
        st = st_map.get(op, 0)
        el = int((box.get(op) or {}).get('elite', 0) or 0)
        rb = _rarity_bonus(st)
        eb = ELITE_BONUS.get(2 if el >= 2 else el, 0.0)
        nb = NOT_RED if (morale is None or morale.get(op, 24.0) > 0) else 0.0
        total += rb + eb + nb
        detail.append(dict(op=op, stars=st, elite=el, rarity=rb, elite_bonus=eb, not_red=nb))
    sk = sum(skill_bonus(op, ds, hours, exchanging) for op in team) if include_skill else 0.0
    total += sk
    return dict(speed=total, skill=sk, detail=detail,
                clue_per_day=24.0 / (CLUE_HOURS / (1.0 + total / 100.0)))


def clue_per_day(plan_shifts, ds, box=None, morale=None, hours=4.0):
    """按班次表算会客室线索产出（**按班次时长加权平均**；等长表结果与旧口径完全一致）。
    为什么不直接取算术平均：自定义班次表可以不等长（例：22:00→10:00 是 12h），
    算术平均会让 6h 的班和 12h 的班等价，产物被高估/低估。"""
    vals, wts = [], []
    for s in plan_shifts:
        team = next((ops for (room, prod, lv, ops) in s['rooms'] if room == '会客室'), None)
        if not team: continue
        h = float(s.get('hours') or hours)
        vals.append(speed(team, ds, box, morale, hours=h)['clue_per_day'])
        wts.append(h)
    return (sum(v * w for v, w in zip(vals, wts)) / sum(wts)) if wts else 0.0
