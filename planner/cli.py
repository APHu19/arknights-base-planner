# -*- coding: utf-8 -*-
"""CLI：terms / room / sim / selftest"""
import sys, os, json, argparse
# 控制台可能是 GBK（Windows 默认），直接 print '✔' 会 UnicodeEncodeError 崩溃 → 强制 UTF-8 且编码失败不中断
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core.dataset import Dataset, load_box
from core.engine import Ctx, eval_room, simulate, drain_of, RATE, power_charge

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def cmd_terms(_):
    ds = Dataset()
    print(f'技能 {len(ds.skills)} 条，干员 {len(ds.op_skills)} 名，全局/术语 {len(ds.globals)} 个\n')
    print('=== 资源与计数类全局变量（引擎实际读写的） ===')
    for k, v in sorted(ds.globals.items()):
        if v['kind'] != '术语':
            print(f"  {k:<8}[{v['kind']:<4}] 基础值: {v['base']}")
            print(f"            {v['note']}")
    print('\n=== 术语（势力/小队/订单类型等，共 %d）===' % len(ds.terms))
    ts = sorted(ds.terms)
    for i in range(0, len(ts), 4):
        print('   ' + '  '.join(f'{t:<14}' for t in ts[i:i + 4]))


def cmd_room(a):
    ds = Dataset()
    ctx = Ctx(ds=ds)
    team = a.ops.split(',')
    prod = a.product
    r = eval_room(a.room, a.level, prod, team, ctx, ds)
    print(f'=== {a.room} Lv{a.level} 产物={prod} 队伍={"+".join(team)} ===')
    for step, payload in r['log']:
        print(f'  [{step}] {json.dumps(payload, ensure_ascii=False)[:300]}')
    print(f"\n  合计效率 {r['eff']:.1f}%  订单上限+{r['cap']}  房间级心情修正 {r['room_morale_mod']:+.2f}/h")
    for op, d in r['detail'].items():
        print(f"    {op:<10} 贡献 {d['contrib']:+.1f}%  自身心情 {d['morale_self']:+.2f}/h  消耗 {r['morale'][op]:.2f}/h")
        for n in d['notes']: print(f'         · {n}')
    print('\n  全局量：', {k: round(v, 2) for k, v in r['resources'].items() if v})


def cmd_sim(a):
    ds = Dataset()
    kpi = simulate(a.path, days=a.days, ds=ds)
    print(f'=== 模拟 {a.days} 天：{os.path.basename(a.path)} ===')
    for k in ('lmd', 'gold', 'gold_cost', 'gold_net', 'shard', 'orundum', 'yu', 'drones', 'shard_cost'):
        if k in kpi: print(f'  {k:<12}{kpi[k]:,.2f} /天')
    lows = kpi['lows']
    print(f"  最低心情 {kpi['min_morale']:.1f}（{kpi['min_who']}）")
    print('  最低 8 名：', [(o, round(lows[o], 1)) for o in sorted(lows, key=lambda o: lows[o])[:8]])


def cmd_selftest(_):
    ds = Dataset(); ok = fail = 0

    def chk(name, cond, extra=''):
        nonlocal ok, fail
        if cond: ok += 1; print(f'  ✔ {name} {extra}')
        else: fail += 1; print(f'  ✘ {name} {extra}')

    ctx = Ctx(ds=ds)
    print('=== 1) 全局变量：赤金生产线 ===')
    base = ctx.base_resources()
    chk('333 布局下赤金生产线基础值 = 3', base['赤金生产线'] == 3, f"实得 {base['赤金生产线']}")
    chk('外势 = 贸易3+发电3 = 6', base['外势'] == 6, f"实得 {base['外势']}")
    chk('实地 = 制造3', base['实地'] == 3, f"实得 {base['实地']}")
    r = eval_room('贸易站', 3, 'LMD', ['鸿雪', '但书', '古米'], ctx, ds)
    hx = r['detail'].get('鸿雪', {})
    chk('鸿雪·销路宣发 读到赤金生产线 → +15%', any('销路宣发:+15' in n for n in hx.get('notes', [])),
        str(hx.get('notes')))

    print('=== 2) 标准化类技能（类型改写，依次结算） ===')
    std_names = ds.standard_skill_names()
    holders = [s.name for s in ds.skills if ds.is_standardized(s)]
    chk('标准化类技能存在于技能库', bool(holders), f'{std_names} → 命中 {len(holders)} 条：{sorted(set(holders))[:4]}')
    chk('标准化类技能有持有者', any(ds.skills_of(o) and any(ds.is_standardized(s) for s in ds.skills_of(o))
                                    for o in ('香草', '调香师', '史都华德')), '')
    r2 = eval_room('制造站', 3, 'Pure Gold', ['水月', '澄闪', '清流'], ctx, ds)
    log1 = dict(r2['log'])
    chk('P1 normalize_types 已执行', 'P1 normalize_types' in log1, json.dumps(log1.get('P1 normalize_types', {}), ensure_ascii=False)[:120])
    chk('P2 统计出标准化类技能数', '标准化类技能数' in log1['P2 count_globals'],
        f"= {log1['P2 count_globals'].get('标准化类技能数')}")

    print('=== 3) 心情模型：自身 vs 房间级 ===')
    d = drain_of('控制中枢', ['阿米娅', '凯尔希', '令', '重岳', '维什戴尔'], ['阿米娅', '凯尔希', '令', '重岳', '维什戴尔'])
    chk('重岳自身 +0.5/h（不摊给他人）', abs(d['重岳'] - d['阿米娅'] - 0.5) < 1e-6, f"重岳 {d['重岳']:.2f} vs 阿米娅 {d['阿米娅']:.2f}")
    from core.engine import morale_mods
    low = next(s for s in ds.skills_of('巫恋', '贸易站') if '低语' in s.name)
    sm, rm, om = morale_mods(low.desc, '贸易站')
    chk('巫恋·低语 +0.25/h 判定为房间级（全体）', (sm, rm, om) == (0.0, 0.25, 0.0), f'{(sm, rm, om)}')
    d2 = drain_of('贸易站', ['巫恋', '龙舌兰', '柏喙'], [])
    chk('低语对所有在站者生效（他人也 ≥0.25 增量）', d2['龙舌兰'] > 0.05 and d2['巫恋'] > 0.05, f'{d2}')
    r3 = eval_room('贸易站', 3, 'LMD', ['巫恋', '龙舌兰', '柏喙'], ctx, ds)
    notes = ' '.join(n for op in r3['detail'] for n in r3['detail'][op]['notes'])
    chk('低语：他人订单效率归零 + 巫恋按其他人数+45%', '归零' in notes and '×45% = +90%' in notes, notes[:120])

    print('=== 4) 产品适配（贵金属/源石/通用） ===')
    g = eval_room('制造站', 3, 'Pure Gold', ['地灵', '槐琥', '褐果'], ctx, ds)
    s = eval_room('制造站', 3, 'Originium Shard', ['地灵', '槐琥', '褐果'], ctx, ds)
    chk('源石类配方对赤金不生效 / 对碎片生效', g['eff'] < s['eff'], f"赤金 {g['eff']:.0f}% vs 碎片 {s['eff']:.0f}%")

    print('=== 5) 速率标定（含体系资源，使用真实在岗分布）===')
    chk('赤金 100% → 0.833 枚/h', abs(RATE['gold_per_h_per_100'] - 0.8333) < 1e-3)
    simple = eval_room('制造站', 3, 'Pure Gold', ['香草', '调香师', '史都华德'], ctx, ds)['eff']
    chk('简单模式技能（3×标准化·β 175% + 每人 1%×3）= 178%', abs(simple - 178) < 1, f'实得 {simple:.0f}%')
    c2 = Ctx(ds=ds)
    c2.staffed = ['娜斯提', '清流', '阿罗玛', '引星棘刺', '砾', '苍苔', '冬时', '森蚺', '温蒂',
                  '多萝西', '淬羽赫默', '迷迭香', '缪尔赛思', '承曦格雷伊', '雷蛇', '令', '重岳']
    c2.by_room = {'制造站': ['娜斯提', '清流', '阿罗玛', '引星棘刺', '砾', '苍苔', '冬时', '森蚺', '温蒂',
                           '多萝西', '淬羽赫默', '迷迭香'],
                  '控制中枢': ['阿米娅', '凯尔希', '令', '重岳', '维什戴尔'],
                  '发电站': ['缪尔赛思', '承曦格雷伊', '雷蛇'], '人力办公室': ['絮雨'],
                  '宿舍': ['塑心', '车尔尼', '爱丽丝', '菲亚梅塔'], '贸易站': ['巫恋', '龙舌兰', '柏喙']}
    meta = [eval_room('制造站', 3, 'Pure Gold', t, c2, ds, hours=12)['eff'] for t in
            (['娜斯提', '清流', '阿罗玛'], ['引星棘刺', '砾', '苍苔'], ['冬时', '森蚺', '温蒂'], ['多萝西', '淬羽赫默', '迷迭香'])]
    tot = sum(RATE['gold_per_h_per_100'] * e / 100 for e in meta) / 2
    chk('四支赤金队合计产金落在 3.6~4.0 枚/h', 3.6 <= tot <= 4.0, f'{[round(e) for e in meta]}% → {tot:.2f} 枚/h')
    chk('迷迭香吃满思维链环（>200%）', meta[3] > 200, f'{meta[3]:.0f}%')
    hk = eval_room('贸易站', 3, 'LMD', ['黑键', '可露希尔', '吉星'], c2, ds, hours=12)
    chk('黑键·无声共鸣链路生效（无声共鸣>0）', hk['resources'].get('无声共鸣', 0) > 0,
        f"无声共鸣 {hk['resources'].get('无声共鸣')} → eff {hk['eff']:.0f}%")

    print('=== 6) 订单品质模型（对照实测表）===')
    from core.orders import profile, probabilities
    def exp_gold(team, h=12):
        pr = profile(team, ds, h)['probs']
        return 2 * pr[0] + 3 * pr[1] + 4 * pr[2]
    chk('常规期望赤金 = 2.90', abs(exp_gold(['古米', '梓兰', '慕斯']) - 2.9) < 0.02, f'{exp_gold(["古米","梓兰","慕斯"]):.2f}')
    chk('单α 满档 = 3.40', abs(exp_gold(['巫恋', '古米', '梓兰']) - 3.4) < 0.02, f'{exp_gold(["巫恋","古米","梓兰"]):.2f}')
    chk('单β 满档 = 3.80', abs(exp_gold(['柏喙', '古米', '梓兰']) - 3.8) < 0.02, f'{exp_gold(["柏喙","古米","梓兰"]):.2f}')
    chk('α+β 叠加 = 3.80（实测）', abs(exp_gold(['巫恋', '龙舌兰', '柏喙']) - 3.8) < 0.02,
        f'{exp_gold(["巫恋","龙舌兰","柏喙"]):.2f}')
    pr0 = probabilities(['巫恋', '古米', '梓兰'], ds, 0)[0]
    chk('慢热：α 未满档时低于满档', 2 * pr0[0] + 3 * pr0[1] + 4 * pr0[2] < 3.4, 't=0 → 2.90')
    chk('违约索赔·β → 6.64 币/效率点·h（与旧标定一致）',
        abs(profile(['但书', '古米', '梓兰'], ds)['lmd_per_eff_hour'] - 6.64) < 0.02, '')
    chk('币/赤金 恒为 500（品质不改变金条效率）',
        abs(profile(['柏喙', '古米', '梓兰'], ds)['lmd_per_gold'] - 500) < 1, '')

    print(f'\n结果：{ok} 通过 / {fail} 失败')
    return 0 if fail == 0 else 1


def cmd_solve(a):
    from solve.solver import run, LAYOUTS, check_power
    from solve import objectives as OBJ
    if a.list:
        print('=== 组合式目标（四个维度任意组合）===')
        print('主目标 --main：')
        for k, v in OBJ.MAINS.items(): print(f'    {k:<9} {v["name"]}')
        print('赤金收支 --gold：')
        for k, v in OBJ.GOLD_MODES.items(): print(f'    {k:<11} {v["name"]}')
        print('碎片收支 --shard：')
        for k, v in OBJ.SHARD_MODES.items(): print(f'    {k:<11} {v["name"]}')
        print('心情底线 --morale：none / 12 / 16 / 20')
        print('\n=== 常用预设（--objective）===')
        for k, v in OBJ.OBJECTIVES.items():
            print(f'  {k:<16} {v["name"]}')
        print('\n=== 可选布局（--layout）===')
        for k, v in LAYOUTS.items():
            s, c, n = check_power(v)
            lvs = {r: [lv for _, lv in vv] for r, vv in v.items() if vv}
            print(f'  {k:<8} 电力 供 {s} / 耗 {c:.0f} / 净 {n:+.0f} {"✔" if n >= 0 else "✘"}   等级 {lvs}')
        return
    obj = a.objective or OBJ.build(a.main, a.gold, a.shard, a.morale)
    got = run(layout=a.layout, objective=obj, width=a.width, topk=a.topk,
              rounds=a.rounds, days=a.days, fast=a.fast, out_dir=a.out,
              storage=a.storage, shift_hours=a.shift_hours, max_roster=a.max_roster)
    k = got['kpi']
    print('\n' + '=' * 60)
    print(f"目标：{got['objective']['name']}")
    print(f"结果：合成玉 {k.get('yu',0):,.0f}/天｜龙门币 {k.get('lmd',0):,.0f}/天｜经验 {k.get('exp',0):,.0f}/天")
    print(f"      赤金 产 {k.get('gold',0):.2f} 耗 {k.get('gold_cost',0):.2f} 净 {k.get('gold_net',0):+.2f}／天"
          f"｜碎片 产 {k.get('shard',0):.2f} 耗 {k.get('shard_cost',0):.2f} 净 {k.get('shard_net',0):+.2f}／天")
    print(f"      会客室线索 {k.get('clue',0):.2f} 份/天"
          + (f"（信用折算开关：{a.clue_weight}，仅显示不影响排班）" if a.clue_weight else "（信用未折算，见 --clue-weight）"))
    print(f"      14 天最低心情 {k.get('min_morale',0):.1f}（{k.get('min_who','')}）"
          f"｜低于10 {sum(1 for v in k['lows'].values() if v<10)} 人")
    print(f"      MAA 协议校验：{'通过 ✔' if not got['issues'] else got['issues']}")
    print('=' * 60)


def main():
    ap = argparse.ArgumentParser(prog='planner')
    sub = ap.add_subparsers(dest='cmd', required=True)
    sub.add_parser('terms').set_defaults(f=cmd_terms)
    p = sub.add_parser('room'); p.add_argument('--room', required=True); p.add_argument('--ops', required=True)
    p.add_argument('--product', default=None); p.add_argument('--level', type=int, default=3); p.set_defaults(f=cmd_room)
    p = sub.add_parser('sim'); p.add_argument('path'); p.add_argument('--days', type=int, default=14); p.set_defaults(f=cmd_sim)
    sub.add_parser('selftest').set_defaults(f=cmd_selftest)
    p = sub.add_parser('solve', help='按目标自动枚举排班并写出 MAA 计划')
    p.add_argument('--objective', default=None, help='预设名（见 --list）或组合串 main|gold|shard|morale')
    p.add_argument('--main', default='lmd', choices=['yu', 'lmd', 'exp', 'drones', 'balanced', 'clue'],
                   help='主目标')
    p.add_argument('--gold', default='no_deficit',
                   choices=['none', 'produce', 'consume', 'balance', 'no_deficit', 'no_surplus'],
                   help='赤金收支：produce=囤金 / consume=烧库存 / balance=净≈0 / no_deficit=不得净亏')
    p.add_argument('--shard', default='none',
                   choices=['none', 'produce', 'consume', 'balance', 'ge_trade', 'no_deficit', 'no_surplus'],
                   help='碎片收支：同上；ge_trade=产能≥玉站消化')
    p.add_argument('--morale', default='none', choices=['none', '12', '16', '20'], help='心情底线')
    p.add_argument('--layout', default='333')
    p.add_argument('--out', default=None, help='输出目录（不填则只打印不写文件）')
    p.add_argument('--days', type=int, default=14)
    p.add_argument('--width', type=int, default=16); p.add_argument('--topk', type=int, default=8)
    p.add_argument('--rounds', type=int, default=2)
    p.add_argument('--fast', action='store_true', help='关闭局部搜索，跑得快')
    p.add_argument('--clue-weight', type=float, default=0.0,
                   help='信用/线索折算权重（默认 0 = 不影响排班，只在结果里显示线索份/天）')
    p.add_argument('--storage', default='warn', choices=['off', 'warn', 'clip'],
                   help='制造站爆仓策略：off=不检查 / warn=只告警（默认）/ clip=自动降效（剪掉超容量产出）')
    p.add_argument('--shift-hours', type=float, default=4.0, choices=[2.0, 3.0, 4.0, 6.0, 8.0, 12.0],
                   help='每班时长（小时）。仓储检测只在 ≥6h 的班次执行')
    p.add_argument('--max-roster', type=int, default=0,
                   help='轮换人数上限（**默认 0 = 不压缩**）。⚠ 实测：靠“合并同站 A/B 两组”来压人数会把'
                        '该站变成 24h 常驻 → 干员没有休息窗口 → 单日闭环直接崩（伤到 -12.6）。'
                        '真正满足闭环需要“逐干员不等长工作窗口”的排班器，见 SKILL.md §7')
    p.add_argument('--list', action='store_true', help='只列出可用目标与布局')
    p.set_defaults(f=cmd_solve)
    a = ap.parse_args()
    sys.exit(a.f(a) or 0)


if __name__ == '__main__':
    main()
