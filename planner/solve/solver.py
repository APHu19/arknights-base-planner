# -*- coding: utf-8 -*-
"""solver.py —— 顶层流水线：固定房间预设枚举 → 联合求解 → 六班/寝室 → 心情复核 → 打分"""
import itertools, os, json, time, collections
from core.dataset import Dataset, load_box
from core.engine import Ctx
from solve import objectives
from solve.joint import joint_solve, fast_kpi, rebuild_ctx, FIXED_BASE, FIXED_PRESETS
from solve.plan import build_plan
from emit import maa

LAYOUTS = {
    '333': {'制造站': [('Pure Gold', 3)] * 2 + [('Originium Shard', 3)],
            '贸易站': [('LMD', 3)] * 2 + [('Orundum', 3)],
            '发电站': [(None, 3)] * 3},
    '243': {'制造站': [('Pure Gold', 3)] * 3 + [('Originium Shard', 3)],
            '贸易站': [('LMD', 3)] * 2,
            '发电站': [(None, 3)] * 3},
    '153': {'制造站': [('Pure Gold', 3)] * 3 + [('Originium Shard', 3)] + [('Battle Record', 3)],
            '贸易站': [('LMD', 3)],
            '发电站': [(None, 3)] * 3},
    # 252 = 2 发电 / 5 制造 / 2 贸易；发电只有 2 座 → 部分**赤金**站降级
    # （注意：非三级制造站只能产赤金，所以碎片站必须保持 Lv3）
    '252': {'制造站': [('Pure Gold', 2), ('Pure Gold', 2), ('Pure Gold', 2),
                     ('Originium Shard', 3), ('Originium Shard', 3)],
            '贸易站': [('LMD', 3), ('Orundum', 3)],
            '发电站': [(None, 3)] * 2},
    '333经验': {'制造站': [('Pure Gold', 3)] + [('Battle Record', 3)] * 2,
              '贸易站': [('LMD', 3)] * 3,
              '发电站': [(None, 3)] * 3},
}
# 固定房间候选（对应计划书 4d“依次测试填入体系干员与不填入”）
PRESETS = {
    '人力办公室': [['斥罪'], ['絮雨'], ['深律'], ['遥']],
    '会客室': [['伊内丝', '红'], ['余', '望'], ['虎狼丸', '伺夜']],
    '加工站': [['黍'], ['深海色'], []],
}


# 固定房间耗电（《全机制.md》：会客室/加工站/训练室 Lv3 = 60，人力办公室 = 10，**宿舍 = 0**）
FIXED_POWER = {'会客室': 60, '人力办公室': 10, '加工站': 60, '训练室': 60, '宿舍': 0}


def check_power(layout, fixed=None, dorm_power=0, other_consume=None):
    """电力检查：**按每个房间实例的等级**计算。
    发电站 提供电力 Lv1/2/3 = 60/130/270；制造站·贸易站 耗电 Lv1/2/3 = 10/30/60。
    fixed：固定房间耗电（默认按文档 FIXED_POWER = 190）；other_consume 可直接覆盖合计值
    （例如按“4×宿舍65”的老口径 = 450）。"""
    supply = sum({1: 60, 2: 130, 3: 270}.get(lv, 0) for (_, lv) in layout.get('发电站', []))
    consume = 0
    for (_, lv) in layout.get('制造站', []) + layout.get('贸易站', []):
        consume += {1: 10, 2: 30, 3: 60}.get(lv, 0)
    if other_consume is not None:
        consume += other_consume
    else:
        f = dict(FIXED_POWER); f.update(fixed or {})
        f['宿舍'] = dorm_power
        consume += sum(f.values())
    return supply, consume, supply - consume


def try_presets(cfg, objective, ds, box, base_assign, ctx, hours=12.0):
    """在给定装配上试各种固定房间组合，用**快照目标**选最优，返回 (fixed, score)"""
    props = objectives.get(objective) if isinstance(objective, str) else objective
    best = None
    for office in PRESETS['人力办公室']:
        for meet in PRESETS['会客室']:
            for work in PRESETS['加工站']:
                fixed = dict(FIXED_BASE)
                fixed['人力办公室'] = office; fixed['会客室'] = meet; fixed['加工站'] = work
                c2 = Ctx(ds=ds, box=box)
                rebuild_ctx(c2, fixed, base_assign)
                k = fast_kpi(base_assign, fixed, c2, ds, hours)
                v = objectives.score(k, props)
                if best is None or v > best[0]:
                    best = (v, fixed, k)
    return best[1], best[2]


def _compact_roster(assign, fixed, target=50):
    """把轮换人数压到 ≤ target：合并同一房间实例的 A/B 两组（改成 24h 常驻同队）。
    目的：每班在岗 30 人，要让**不在岗人数 ≤ 寝室床位 20**，轮换总人数就必须 ≤50，
    否则必然有人在自己休息窗口里拿不到床位 → 单日闭环（次日 00:00 回满）无法成立。"""
    fixed_ops = {o for ops in fixed.values() for o in ops}

    def uniq(a):
        return len({o for k, (p, l, t) in a.items() for o in t} | fixed_ops)

    merges = []
    for (room, i, grp) in list(assign):
        if grp != 'B':
            continue
        a_key = (room, i, 'A')
        if a_key not in assign:
            continue
        trial = dict(assign)
        prod, lv, team = assign[a_key]
        trial[(room, i, 'B')] = (prod, lv, list(team))
        merges.append([uniq(trial), trial, (room, i)])
    log = []
    while merges and uniq(assign) > target:
        merges.sort(key=lambda x: x[0])
        n, trial, key = merges.pop(0)
        if n < uniq(assign):
            assign = trial
            log.append(key)
    return assign, log


def run(layout='333', objective='lmd_gold_bal', ds=None, box=None, width=16, topk=8,
        rounds=2, days=14, fast=False, refine=True, verbose=True, out_dir=None,
        storage='warn', shift_hours=4.0, max_roster=50, sched='ab', table=None):
    ds = ds or Dataset(); box = box if box is not None else load_box()
    ds.set_box(box)          # 让 skills_of 按精英化阶段过滤（明椒 E0 无 裁缝·β 等）
    if sched == 'window' and not table and abs(float(shift_hours) - 4.0) > 1e-6:
        raise RuntimeError('--sched window 只支持 4h×6 班，或显式给 --shifts 自定义班次表：'
                           'emit/maa.py 的班次时间标签与 planTimes 原本写死 6 班')
    props = objectives.get(objective) if isinstance(objective, str) else objective
    obj_name = props.get('name') or props.get('key') or 'custom'
    cfg = LAYOUTS[layout] if isinstance(layout, str) else layout
    layout_name = layout if isinstance(layout, str) else '自定义'
    t0 = time.time()
    supply, consume, net = check_power(cfg)
    if net < 0:
        raise RuntimeError(f'电力不足：供 {supply} / 耗 {consume}（净 {net}）'
                           f'—— 可给部分制造/贸易站降级，或减少发电站以外的满级房间')
    for i, (prod, lv) in enumerate(cfg.get('制造站') or []):
        if prod and prod != 'Pure Gold' and int(lv) < 3:
            raise RuntimeError(f'制造站#{i+1} 是 Lv{lv}：**非三级制造站只能产赤金**（当前 {prod}），请把它升级或改产赤金')
    if verbose:
        print(f'[1/5] 电力检查：供 {supply} / 耗 {consume} → 净 {net} ✔')
        print(f'      目标：{obj_name}')
        if props.get('cons'): print(f'      约束：{props["cons"]}')
    # 基准装配（用默认固定房间）
    r0 = joint_solve(cfg, props, ds, box, width=width, topk=topk, rounds=rounds,
                     local_search=not fast, verbose=verbose)
    if verbose:
        print(f'[2/5] 基准装配完成（{time.time()-t0:.0f}s）：'
              f"龙门币 {r0['kpi'].get('lmd',0):,.0f} 净产金 {r0['kpi'].get('gold_net',0):+.2f}")
    # 试固定房间组合
    fixed, k_fixed = try_presets(cfg, props, ds, box, r0['assign'], r0['ctx'])
    if verbose:
        print(f"[3/5] 固定房间选定：办公={fixed.get('人力办公室')} 会客={fixed.get('会客室')} "
              f"加工={fixed.get('加工站')}")
    if refine:
        from solve.joint import _solve_once
        r = _solve_once(cfg, props, ds, box, width, topk, rounds, 12.0, not fast, price=None)
        rebuild_ctx(r['ctx'], fixed, r['assign'])
        r['fixed'] = fixed
    else:
        r = r0; r['fixed'] = fixed
    # 六班 + 寝室 + 心情
    # —— 轮换人数压缩到 ≤ max_roster（保证每班不在岗 ≤ 20 床位 → 单日闭环可成立）——
    if max_roster:
        if verbose:
            print('      ⚠ 已启用轮换压缩：会把同站 A/B 合并成 24h 常驻，**破坏单日闭环**（仅实验用）')
        r['assign'], merged = _compact_roster(r['assign'], r['fixed'], target=int(max_roster))
        rebuild_ctx(r['ctx'], r['fixed'], r['assign'])
        n_uniq = len({o for k, (p, l, t) in r['assign'].items() for o in t}
                     | {o for ops in r['fixed'].values() for o in ops})
        if verbose:
            print(f'      轮换压缩：合并 {len(merged)} 组 A/B → 唯一干员 {n_uniq}（上限 {max_roster}）'
                  f'{"✔" if n_uniq <= int(max_roster) else "✘ 仍超上限"}')
    plan = build_plan(r['assign'], r['fixed'], ds, days=days, objective=props, hours=shift_hours,
                      sched=sched, table=table)
    kpi = plan['kpi']
    # —— 仓储/爆仓检查：**所有制造站都检测**，但只有班次 ≥6h 才可能爆仓（贸易站效率低，不检测）——
    from core import storage
    from core.engine import eval_room as _ev
    overflow = []
    if storage != 'off' and shift_hours >= 6.0:
        for i, s in enumerate(plan['shifts'], 1):
            for (room, prod, lv, team) in s['rooms']:
                if room != '制造站' or not prod:
                    continue
                rep = _ev('制造站', lv, prod, list(team), r['ctx'], ds, hours=shift_hours)
                c = storage.check(prod, lv, rep['eff'], shift_hours, list(team), ds)
                if c and not c['fits']:
                    overflow.append(dict(shift=i, product=prod, made=round(c['made'], 2),
                                         capacity=c['capacity'], max_items=round(c['max_items'], 2)))
    if verbose:
        if storage == 'off':
            print('      仓储检查：（已关闭）')
        elif shift_hours < 6.0:
            print(f'      仓储检查：班次 {shift_hours:g}h < 6h，按规则跳过（短班次不会爆仓）')
        else:
            print(f'      仓储检查（班次 {shift_hours:g}h）：'
                  f'{"全部制造站不爆仓 ✔" if not overflow else f"⚠ 爆仓 {len(overflow)} 处 {overflow[:3]}"}')
    # —— 心情可持续性检测（**判据 A：长期稳态**；字面口径作诊断列一起打印）——
    if plan.get('daycheck'):
        day = plan['daycheck']
        if verbose:
            wr = plan.get('window_result') or {}
            print(f'      排班路径：window（干员级窗口排班，判据 A）'
                  f'{"·排班无缺口 ✔" if wr.get("ok", True) else f"·⚠ 有 {len(wr.get("fails") or [])} 处排不出人"}')
            for f in (wr.get('fails') or [])[:8]:
                print(f'         {f["room"]} 第{f["slot"] + 1}班：{f["reason"]}（试了 {f["tried"]} 组）'
                      + (f' 例：{f["sample"][0]["reasons"]}' if f.get('sample') else ''))
            print(f'      心情检测：{day["report"]}')
        if plan.get('window') is not None and (props.get('cons') or {}).get('gold_net'):
            lo = (props['cons']['gold_net'] or (None, None))[0]
            if lo is not None and kpi.get('gold_net', 0.0) < lo - 0.01:
                print(f'      ⚠ 窗口路径实测赤金净 {kpi["gold_net"]:+.2f} < 约束下限 {lo:g}：'
                      f'窗口排班让班组**连续上班**，贸易站订单品质吃满档 → 产量比 ab 高（龙门币约 +10%），'
                      f'而求解器的赤字闸门是按 ab 的产量算的 → 需要"贸易站节流"或按窗口产量重算预算，'
                      f'见 SKILL.md §10')
    else:
        from core.daycheck import morale_day
        day = morale_day(plan['shifts'], ds)
        if verbose:
            print(f'      排班路径：ab（A/B 六班 + 恢复债寝室）')
            print(f'      心情检测：{day["report"]}')
    # 爆仓策略：clip = 把超出容量的产出剪掉（宁可损失也不浪费空间被占死）
    if overflow and storage == 'clip':
        lost = collections.Counter()
        for o in overflow:
            over_items = o['made'] - o['max_items']
            if o['product'] == 'Pure Gold': lost['gold'] += over_items
            elif o['product'] == 'Originium Shard': lost['shard'] += over_items
            elif o['product'] == 'Battle Record': lost['exp'] += over_items * 1000 / 3.0
        for kk, vv in lost.items():
            kpi[kk] = max(0.0, kpi.get(kk, 0.0) - vv)
        kpi['gold_net'] = kpi.get('gold', 0.0) - kpi.get('gold_cost', 0.0)
        kpi['shard_net'] = kpi.get('shard', 0.0) - kpi.get('shard_cost', 0.0)
        if verbose:
            print(f'      已按“自动降效”剪掉超容量产出：{dict(lost)}')
    v = objectives.score(kpi, props)
    if verbose:
        gf = (plan.get('drone_detail') or {}).get('gold_fix')
        if gf:
            print(f"      ⚙ 赤金反馈：把第 {'、'.join(map(str, gf['moved_shifts']))} 班的无人机改投 "
                  f"{gf['to']}（每架 {gf['per_drone_gold']:g} 赤金；需补 {gf['need_gold']:+.2f}，"
                  f"实补 {gf['gained_gold']:+.2f} 赤金/天）")
        print(f"[4/5] 班次/寝室完成（{sched} 路径）：14 天最低心情 {kpi['min_morale']:.1f}（{kpi['min_who']}），"
              f"低于10 {sum(1 for x in kpi['lows'].values() if x < 10)} 人")
    doc = maa.deck_from_plan(plan, obj_name, layout_name)
    issues = maa.validate(doc, owned={o for o, v2 in box.items() if v2.get('own')})
    if verbose:
        print(f"[5/5] MAA 协议校验：{'通过 ✔' if not issues else issues}")
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
        stamp = time.strftime('%y%m%d-%H%M')
        safe = ''.join(c if (c.isalnum() or c in '-_') else '_'
                       for c in str(props.get('key') or 'obj'))[:44]
        name = f'{layout_name}_{safe}_{stamp}'
        path = os.path.join(out_dir, name + '.json')
        json.dump(doc, open(path, 'w', encoding='utf-8'), ensure_ascii=False, indent=4)
        rpt = maa.report(plan, doc, kpi, obj_name, layout_name,
                         extra_lines=[f'电力：供 {supply} / 耗 {consume} / 净 {net}',
                                      f'固定房间：{fixed}',
                                      f'排班路径：{sched}',
                                      f'目标组合：{props.get("key","")}'])
        open(os.path.join(out_dir, name + '.txt'), 'w', encoding='utf-8').write(rpt)
        if verbose: print(f'      已写出 {path}')
    return dict(assign=r['assign'], fixed=r['fixed'], plan=plan, kpi=kpi, doc=doc,
                issues=issues, score=v, objective=props, sched=sched, daycheck=day)
