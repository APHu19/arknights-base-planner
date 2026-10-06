# -*- coding: utf-8 -*-
"""extract_skills.py —— 解析《后勤技能一览带注释.md》（PRTS 页面存档）为结构化技能库

输出：
  data/skills_raw.json : {rooms: {房间: [ {icon, name, desc, holders, terms} ]},
                          terms: {术语: {def, providers}}, meta}
每个技能的稳定标识 = icon（如 bskill_man_spd2），作为静态数据主键（名称仅显示用）。
"""
import re, json, os, html as H

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE)
SRC = os.path.join(os.path.dirname(ROOT), '后勤技能一览带注释.md')
OUT = os.path.join(BASE, 'skills_raw.json')

ROOM_KEYS = ['控制中枢', '贸易站', '制造站', '发电站', '会客室', '人力办公室', '加工站', '训练室', '宿舍']
# 源文档里的别名：wiki 该节标题写作“办公室”
ROOM_ALIAS = {'办公室': '人力办公室', '人力资源办公室': '人力办公室'}

HIDDEN = re.compile(r'<span[^>]*style="[^"]*display\s*:\s*none[^"]*"[^>]*>', re.I)


def strip_hidden_spans(s: str) -> str:
    """精确剥离隐藏的术语提示块。
    注意：隐藏块内部**还嵌有** <span class="term">，非贪婪正则会提前截断，
    因此这里做 span 平衡扫描，删到配对的那个 </span>。"""
    out, i = [], 0
    while True:
        m = HIDDEN.search(s, i)
        if not m:
            out.append(s[i:]); break
        out.append(s[i:m.start()])
        depth, j = 1, m.end()
        end = len(s)
        for t in re.finditer(r'<span\b[^>]*>|</span>', s[m.end():], re.I):
            if t.group(0).lower().startswith('</'):
                depth -= 1
                if depth == 0:
                    end = m.end() + t.end(); break
            else:
                depth += 1
        i = end
    return ''.join(out)


def plain(s: str) -> str:
    # 注意：**不要**整块删除 mc-tooltips —— 那样会把可见的术语名（莱茵生命/金属工艺…）一起删掉，
    # 导致描述里出现“每有1名干员（最多5名）”这类无法匹配的残句。隐藏定义块已在上面单独剥离。
    s = re.sub(r'<[^>]+>', '', s)
    s = H.unescape(s)
    return re.sub(r'\s+', '', s)

def cells(tr: str):
    return re.findall(r'<td[^>]*>(.*?)</td>', tr, re.S)

def table_room(html: str, start: int) -> str:
    """在 <table> 之前 1500 字符内找**最近**的 tabber/标题，找不到返回 '?'。

    踩坑记录：wiki 里这一节的标题是**“办公室”**而不是“人力办公室”，旧实现按 ROOM_KEYS 顺序
    返回"第一个出现过的房间名"，于是把办公室的表错挂到**上一个标题“加工站”**名下 ——
    结果 `skills_raw.json` 里 "加工站" 出现两次、没有任何"人力办公室"技能，
    导致 ①人力办公室无法优化 ②`--min-eff-hire` 假通过 ③感知信息（絮雨）体系无法建模。
    """
    ctx = html[max(0, start - 1500):start]
    best, best_pos = '?', -1
    for k in ROOM_KEYS + list(ROOM_ALIAS):
        for pat in (f'>{k}<', f'title="{k}"', f'id="{k}"'):
            p = ctx.rfind(pat)
            if p > best_pos:
                best, best_pos = ROOM_ALIAS.get(k, k), p
    return best

def main():
    html = open(SRC, encoding='utf-8', errors='replace').read()
    rooms, terms = {}, {}
    order = []
    for m in re.finditer(r'<table.*?</table>', html, re.S):
        tbl = m.group(0)
        room = table_room(html, m.start())
        rows = []
        for tr in re.findall(r'<tr.*?</tr>', tbl, re.S):
            td = cells(tr)
            if len(td) < 4:
                continue
            icon = re.search(r'build_skill_icon/(bskill_[a-z0-9_]+)\.png', td[0])
            name = plain(td[1])
            if not name:
                continue
            desc_html = td[2]
            # 去掉隐藏的术语提示块（<span style="display:none">…</span>），它们会把
            # “每个术语:金属工艺类技能包含以下技能…”这类内联注释插进描述，打断后续正则匹配。
            # 术语本身仍从原始 desc_html 提取（见下方 terms）。
            visible = strip_hidden_spans(desc_html)
            desc = plain(visible)
            # 术语注释：<strong>术语: X</strong> ... 说明 ... ※此外还可由以下干员提供：A、B
            for t in re.findall(r'<strong>术语:\s*(?:<[^>]+>)*([^<]+?)(?:</span>)*\s*</strong>(.*?)</span>', desc_html, re.S):
                term = plain(t[0]); body = t[1]
                prov = re.search(r'还可由以下干员提供：</span>?\s*<?[^>]*>?([^<]+)', t[1])
                provs = [p.strip() for p in re.split(r'[、,，]', plain(prov.group(1))) if p.strip()] if prov else []
                terms.setdefault(term, {'defs': [], 'providers': []})
                d = plain(body)
                if d and d not in terms[term]['defs']:
                    terms[term]['defs'].append(d)
                for p in provs:
                    if p not in terms[term]['providers']:
                        terms[term]['providers'].append(p)
            holders = []
            for h in re.findall(r'<a href="/w/[^"]+" title="([^"]+)"', td[-1]):
                if h not in holders:
                    holders.append(h)
            rows.append({'icon': icon.group(1) if icon else None, 'name': name,
                         'desc': desc, 'holders': holders})
        if room == '?':
            room = ROOM_KEYS[len(order)] if len(order) < len(ROOM_KEYS) else f'table{len(order)}'
        rooms.setdefault(room, []).extend(rows)
        order.append(room)
        print(f'表 {len(order)}: 房间={room} 行数={len(rows)}')

    data = {'meta': {'source': os.path.basename(SRC), 'rooms': order,
                     'skill_count': sum(len(v) for v in rooms.values()),
                     'term_count': len(terms)},
            'rooms': rooms, 'terms': terms}
    json.dump(data, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f'\n技能行合计 {data["meta"]["skill_count"]}，术语 {len(terms)} 个 -> {OUT}')
    print('\n术语清单（前 40）：')
    for i, t in enumerate(sorted(terms)):
        if i >= 40: break
        print(f'  {t}: {(terms[t]["defs"][0] if terms[t]["defs"] else "")[:60]} | 提供者 {terms[t]["providers"][:6]}')

if __name__ == '__main__':
    main()
