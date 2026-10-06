# -*- coding: utf-8 -*-
"""probe_systems_report.py —— 生成《组合表.md》+ data/systems.json

三层内容：
  一、体系权重总表（语义扫描成员 → 收益函数 → 留一法稳健度 → 权重/档位）
  二、逐体系明细（机制/参数/缺人曲线/替补规则/注释）
  三、附录：① 所有人单人次效率全量榜（按站） ② 文本互指的其它组合（兜底，保证不漏）
"""
import os
import sys
import json
import collections

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

from core.dataset import Dataset, load_box                 # noqa: E402
from solve import systems as SYS                            # noqa: E402
from probe_combo_report import scan_groups              # noqa: E402
from solve.systems import revenue                        # noqa: E402

OUT_MD = os.path.join(HERE, '组合表.md')
OUT_JSON = os.path.join(HERE, 'data', 'systems.json')


def solo_section(ds, box):
    lines = ['| 站（产物） | 前 20 名（数值｜效率%） |', '|---|---|']
    for room, prod in (('贸易站', 'LMD'), ('贸易站', 'Orundum'), ('制造站', 'Pure Gold'),
                       ('制造站', 'Battle Record'), ('制造站', 'Originium Shard'),
                       ('发电站', None), ('会客室', None), ('人力办公室', None), ('宿舍', None)):
        rows = []
        for op in sorted(box):
            if not box[op].get('own'):
                continue
            try:
                v, m, note = revenue(ds, room, [op], ds and prod, by_room={room: [op]}, layout=None)
            except Exception:
                continue
            rows.append((v, m, op, note.get('eff')))
        rows.sort(reverse=True)
        if not rows:
            continue
        top = '、'.join(f"{op} {v:.3g}{'%' if eff else ''}" for v, m, op, eff in rows[:20])
        lines.append(f"| {room}{'（' + prod + '）' if prod else ''} | {top} |")
    return lines


def main():
    ds = Dataset()
    box = load_box()
    ds.set_box(box)
    rows = SYS.evaluate(ds, box)
    groups = scan_groups(ds, box)

    extra = []
    extra.append(('附录A：所有人单人次效率全量榜（每站前 20，已持有）', solo_section(ds, box)))
    txt_groups = collections.defaultdict(list)
    for g in groups:
        txt_groups[g['room']].append(g)
    gl = ['| 房间 | 组员（文本互指 / 同资源） | 原文涉及的技能 |', '|---|---|---|']
    for room, gs in txt_groups.items():
        for g in gs[:40]:
            sk = '、'.join(s['name'] for s in g['skills'][:3])
            gl.append(f"| {room} | {'、'.join(g['members'][:8])} | {sk} |")
    extra.append((f'附录B：文本互指的其它组合（兜底，共 {len(groups)} 组，保证不漏）', gl))

    md = SYS.markdown(rows, extra)
    open(OUT_MD, 'w', encoding='utf-8').write(md)
    json.dump(dict(meta=dict(source='solve/systems.py + probe_systems_report.py',
                             note='weight = 同房间归一化满配收益 × 留一法稳健度'),
                   systems=rows, text_linked_groups=groups),
              open(OUT_JSON, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

    print(f'体系 {len(rows)} 条 → 已写出 {OUT_MD}')
    print(f'JSON → {OUT_JSON}')
    print('档位统计：' + '，'.join(f'{t} {sum(1 for r in rows if r["tier"] == t)}'
                               for t in ('S', 'A', 'B', 'C')))
    for r in rows:
        print(f"  [{r['tier']}] w={r['weight']:.2f} {r['room']:<5} {r['name']:<26} "
              f"{'+'.join(r['team'])[:30]:<32} {r['value']}{r['metric']} 稳健 {r['robustness']:.2f}")


if __name__ == '__main__':
    main()
