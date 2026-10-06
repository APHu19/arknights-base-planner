# -*- coding: utf-8 -*-
"""probe_audit.py —— 把"本质"量出来：容量 / 电力 / 阵容质量 / 体系干员是否被用到

起因：用户实测反馈 ①发电站塞了 3 个劣质干员 ②人力办公室塞 2 个 ③效率低得离谱。
本探针先核对权威数值（全机制.md），再用修正后的容量跑一次 333纯钱，把关键事实打出来。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

from core.dataset import Dataset, load_box, capacity, ROOM_CAPACITY   # noqa: E402
from core.engine import power_charge, eval_room                        # noqa: E402
from gui import state as ST                                            # noqa: E402
from solve import objectives as OBJ                                    # noqa: E402
from solve.solver import run, check_power                              # noqa: E402


def main():
    print('=' * 108)
    print('一、房间进驻上限（权威：全机制.md 各设施等级表）')
    for room in ('控制中枢', '制造站', '贸易站', '发电站', '会客室', '人力办公室', '加工站', '训练室', '宿舍'):
        c = ROOM_CAPACITY[room]
        s = '、'.join(f'Lv{k}={v}' for k, v in c.items()) if isinstance(c, dict) else f'各级都 {c}'
        print(f'  {room:<7} {s}')
    print('  ⇒ 之前 assemble.py 把生产房间**一律按 3 人**排 —— 发电站（上限 1）因此被塞了 3 人 ×3 站。')

    print('\n二、电力（供/耗/净）—— 固定房间两种口径')
    for name, grid in ST.LAYOUT_PRESETS.items():
        for other in (450.0, 190.0):
            s, c, n = ST.power(grid, other)
            flag = '✔' if n >= 0 else '✘'
            print(f'  {name:<12} 固定 {other:>3.0f}：供 {s:>4} ／ 耗 {c:>4.0f} ／ 净 {n:>+5.0f} {flag}')
    print('  权威依据：宿舍 Lv1..5 = 10/20/30/45/65 电力（全机制.md 宿舍等级表）→ 4×Lv5 = 260，'
          '加 190 = 450。\n  注：252 只有 2 座发电站（540），在 450 口径下**电力不够**，'
          '必须降宿舍等级或再降制造站等级。')

    print('\n三、发电站阵容质量（修正容量后：每站 1 人）')
    ds = Dataset()
    box = load_box()
    ds.set_box(box)
    owned = [n for n, v in box.items() if v.get('own')]
    score = []
    for op in owned:
        try:
            rep = eval_room('发电站', 3, None, [op], _ctx(ds), ds)
            charge = float(rep.get('eff') or 100) - 100.0
        except Exception:
            charge = 0.0
        if charge > 0:
            score.append((charge, op))
    score.sort(reverse=True)
    print('  单人有充能加成的干员 Top10：' + '、'.join(f'{o}(+{c:.0f}%)' for c, o in score[:10]))
    print(f'  （池里共 {len(score)} 人有充能技能；机器人示例：'
          + '、'.join(o for _c, o in score if o in ('Lancet-2', 'THRM-EX', 'Castle-3')) + '）')

    print('\n四、容量修正 + 333纯钱 跑一次（同一目标，只是不再往发电站塞 3 人）')
    props = OBJ.build('lmd', 'no_deficit', 'none', 'none')
    got = run(layout=ST.grid_to_cfg(ST.LAYOUT_PRESETS['333纯钱']), objective=props, ds=ds, box=box,
              width=6, topk=3, rounds=1, days=14, fast=True, verbose=False, out_dir=None,
              sched='window', other_consume=450.0)
    k = got['kpi']
    print(f"  结果：龙门币 {k.get('lmd', 0):,.0f}/天｜玉 {k.get('yu', 0):.0f}｜"
          f"赤金净 {k.get('gold_net', 0):+.2f}｜线索 {k.get('clue', 0):.2f}｜"
          f"最低心情 {k.get('min_morale', 0):.1f}（{k.get('min_who', '')}）")
    print(f"  对比：修正前（发电站 3 人）同目标约 38,756 龙门币/天；"
          f"你的 v13-A 参考值 84,361/天")
    used = {o for s in got['plan']['shifts'] for (_r, _p, _l, ops) in s['rooms'] for o in ops}
    watch = ['但书', '巫恋', '龙舌兰', '明椒', '柏喙', '可露希尔', '菲亚梅塔', '承曦格雷伊',
             '温蒂', '森蚺', '迷迭香', '多萝西']
    print('  体系/关键干员是否上场：' + '、'.join(f'{w}{"✔" if w in used else "✘"}' for w in watch))
    if got['plan'].get('daycheck'):
        print('  ' + str(got['plan']['daycheck'].get('report'))[:110])

    print('\n五、发电站三站实际人选与充能')
    for s in got['plan']['shifts']:
        for (r, p, lv, ops) in s['rooms']:
            if r == '发电站':
                dn, b = power_charge([list(ops)], 4.0, ds)
                print(f'  {ops} → 充能 {dn:.2f} 架/4h（加成 {b:+.0f}%）')
                break
        break
    print('=' * 108)


def _ctx(ds):
    from core.engine import Ctx
    c = Ctx(ds=ds)
    c.by_room = {'发电站': []}
    c.staffed = []
    return c


if __name__ == '__main__':
    main()
