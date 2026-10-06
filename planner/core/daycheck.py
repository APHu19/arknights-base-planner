# -*- coding: utf-8 -*-
"""daycheck.py —— 单日心情闭环检测（用户口径）

规则（唯一验收标准）：
  · 从 **00:00 满心情(24)** 开始，按当天班次表把 24 小时走完；
  · 次日 00:00 若该干员**仍为满心情**（允许 ε=0.05 误差）→ 判定"入能敷出"；
  · 对任意一次「下班 → 下次上班」，下班后的休息时长必须让他在**下一个工作窗口内不被消耗光**。
本模块支持**异形班次**（各班长短不一），班次由 (start, end) 或 hours 给出。

用法：
    from core.daycheck import morale_day
    res = morale_day(shifts, ds)          # shifts: [dict(hours=…, rooms=[…], dorm=[[…]])]
    res['ok'], res['failures'], res['windows']
"""
from core.engine import Ctx, drain_of, dorm_rooms_recovery, _resolve_resources, MAX_MORALE


def _hours_of(s):
    if s.get('hours') is not None:
        return float(s['hours'])
    try:
        return float(s['end']) - float(s['start'])
    except Exception:
        return 4.0


def morale_day(shifts, ds, box=None, eps=0.05):
    """单日闭环检测。返回 dict(ok, start, end, lows, failures, windows, log)"""
    roster = set()
    for s in shifts:
        for _, _, _, ops in s['rooms']: roster |= set(ops)
        for d in s['dorm']: roster |= set(d)
    mor = {o: MAX_MORALE for o in roster}
    start = dict(mor)
    lows = {o: MAX_MORALE for o in roster}
    # 每人每班的净变化（+恢复 / −消耗），用于窗口诊断
    per_op_windows = {o: [] for o in roster}
    log = []
    for idx, s in enumerate(shifts, 1):
        h = _hours_of(s)
        ctrl = next((ops for r, p, lv, ops in s['rooms'] if r == '控制中枢'), [])
        c0 = Ctx(ds=ds); c0.by_room = {}
        for r, p, lv, ops in s['rooms']:
            c0.by_room.setdefault(r, []).extend(ops)
        c0.staffed = [o for r, p, lv, ops in s['rooms'] for o in ops]
        res = _resolve_resources(c0, c0.staffed, c0.base_resources(), ds)
        yh = res.get('人间烟火', 0.0)
        working = {}
        for r, p, lv, ops in s['rooms']:
            for o, v in drain_of(r, ops, ctrl, yh, ds).items():
                working[o] = (r, v)
        dormant = {}
        for d in s['dorm']:
            if not d: continue
            rr = dorm_rooms_recovery([d], ds)[0]
            for o in d: dormant[o] = rr
        for o in roster:
            before = mor[o]
            if o in working:
                r, v = working[o]
                mor[o] = max(0.0, mor[o] - v * h)
                per_op_windows[o].append(dict(shift=idx, kind='work', room=r,
                                              hours=h, rate=round(v, 3),
                                              before=round(before, 2), after=round(mor[o], 2)))
            elif o in dormant:
                rr = dormant[o]
                mor[o] = min(MAX_MORALE, mor[o] + rr * h)
                per_op_windows[o].append(dict(shift=idx, kind='dorm', hours=h,
                                              rate=round(rr, 3),
                                              before=round(before, 2), after=round(mor[o], 2)))
            else:
                per_op_windows[o].append(dict(shift=idx, kind='idle', hours=h,
                                              before=round(before, 2), after=round(mor[o], 2)))
            lows[o] = min(lows[o], mor[o])
        log.append(dict(shift=idx, hours=h, min_morale=round(min(mor.values()), 2)))
    end = dict(mor)
    failures = {o: round(mor[o] - MAX_MORALE, 3) for o in roster if mor[o] < MAX_MORALE - eps}
    # 窗口级诊断：任一工作窗口内是否会被消耗光
    starved = {}
    for o, ws in per_op_windows.items():
        for w in ws:
            if w['kind'] == 'work' and w['before'] - w.get('rate', 0) * w['hours'] < -1e-9:
                starved[o] = w
    return dict(ok=(not failures), start=start, end=end, lows=lows, failures=failures,
                starved=starved, windows=per_op_windows, log=log,
                report=_fmt(failures, starved, lows))


def _fmt(failures, starved, lows):
    if not failures and not starved:
        return f'单日闭环 ✔ 次日 00:00 全部回到满心情（最低 {min(lows.values()):.1f}）'
    parts = []
    if failures:
        worst = sorted(failures.items(), key=lambda kv: kv[1])[:6]
        parts.append('次日 00:00 未回满：' + '、'.join(f'{o} {v:+.2f}' for o, v in worst))
    if starved:
        parts.append('工作窗口内被消耗光：' + '、'.join(
            f"{o}(第{w['shift']}班 {w['before']}−{w['rate']}×{w['hours']}h)" for o, w in list(starved.items())[:4]))
    return '单日闭环 ✘ ' + '；'.join(parts)
