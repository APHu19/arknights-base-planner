# -*- coding: utf-8 -*-
"""daycheck.py —— 心情可持续性检测（**判据 = A：长期稳态**，2024 会话由用户裁定）

判据 A · 'steady'（默认，正式验收口径）
    把当天班次表**反复迭代到不动点**（第 1 天从满心情 24 起算，之后每天拿当天末值接着走），
    要求**稳态那一天**：
      ① 任何工作窗口都不被打穿（心情不归零）
      ② 全天最低心情 ≥ floor（默认 1.0）
    语义 = 「两次上班之间的休息足以撑过下一段工作」，且**允许上下班连排**（连排＝一段长班）。
    不要求 00:00 必须满——那在物理上做不到（见下）。

判据 B · 'literal'（**仅作诊断保留**，不再作为验收口径）
    00:00 满心情起算，走完一天，次日 00:00 必须回满。实测在正常规模下**结构性不可达**：
      · **时间**：任何在跨越/贴近 00:00 的区间在岗的人，00:00 必然 < 24（消耗率恒 ≥0.05/h > 0）；
      · **床位**：末段只有 20 张床，而"最后一班"在岗约 32 人 ⇒ 拿不到床的人回不满
        （实测恰好 −4.50/人，中枢 5 人房 0.75/h × 6h）。
    例：6,6,12 三班表在 B 下必 ✘；同一张表在 A 下 52/52 通过。

用法：
    from core.daycheck import morale_day
    res = morale_day(shifts, ds)                    # 默认判据 A
    res = morale_day(shifts, ds, criterion='literal')
    res['ok'], res['report'], res['steady_lows'], res['literal_failures']
"""
from core.engine import Ctx, drain_of, dorm_rooms_recovery, _resolve_resources, MAX_MORALE

DEFAULT_DAYS = 4          # 稳态迭代天数（第 1 天从 24 起算，之后接着走）
DEFAULT_FLOOR = 1.0       # 稳态全天最低心情下限（>0 = 绝不见底/不红脸）


def _hours_of(s):
    if s.get('hours') is not None:
        return float(s['hours'])
    try:
        return float(s['end']) - float(s['start'])
    except Exception:
        return 4.0


def _timeline(shifts, ds):
    """把班次表折算成「每人 × 每班」的时间线 (kind, hours, rate)，只算一次、可反复播放。"""
    roster = set()
    for s in shifts:
        for _, _, _, ops in s['rooms']:
            roster |= set(ops)
        for d in s['dorm']:
            roster |= set(d)
    tl = {o: [] for o in roster}
    shift_info = []
    for idx, s in enumerate(shifts, 1):
        h = _hours_of(s)
        ctrl = next((ops for r, p, lv, ops in s['rooms'] if r == '控制中枢'), [])
        c0 = Ctx(ds=ds)
        c0.by_room = {}
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
            if not d:
                continue
            rr = dorm_rooms_recovery([d], ds)[0]
            for o in d:
                dormant[o] = rr
        for o in roster:
            if o in working:
                r, v = working[o]
                tl[o].append(dict(shift=idx, kind='work', room=r, hours=h, rate=v))
            elif o in dormant:
                tl[o].append(dict(shift=idx, kind='dorm', hours=h, rate=dormant[o]))
            else:
                tl[o].append(dict(shift=idx, kind='idle', hours=h, rate=0.0))
        shift_info.append(dict(shift=idx, hours=h, onduty=len(working), dorm=len(dormant)))
    return roster, tl, shift_info


def _play_day(tl, roster, mor0):
    """按时间线走完一天。返回 (末值, 全天最低, 被打穿的班次, 逐人逐班明细)。"""
    end, lows, dips, windows = {}, {}, {}, {}
    for o in roster:
        mor = mor0[o]
        low = mor
        ws = []
        for seg in tl[o]:
            before = mor
            if seg['kind'] == 'work':
                if before - seg['rate'] * seg['hours'] < -1e-9:
                    dips.setdefault(o, []).append(seg['shift'])
                mor = max(0.0, mor - seg['rate'] * seg['hours'])
            else:
                mor = min(MAX_MORALE, mor + seg['rate'] * seg['hours'])
            low = min(low, mor)
            ws.append(dict(shift=seg['shift'], kind=seg['kind'], room=seg.get('room'),
                           hours=seg['hours'], rate=round(seg['rate'], 3),
                           before=round(before, 2), after=round(mor, 2)))
        end[o], lows[o], windows[o] = mor, low, ws
    return end, lows, dips, windows


def _log_of(windows, shifts):
    """逐班最低心情（用于报告）。"""
    out = []
    for i, s in enumerate(shifts, 1):
        vals = [ws[i - 1]['after'] for ws in windows.values() if len(ws) >= i]
        out.append(dict(shift=i, hours=_hours_of(s),
                        min_morale=round(min(vals), 2) if vals else None))
    return out


def morale_day(shifts, ds, box=None, eps=0.05, criterion='steady',
               days=DEFAULT_DAYS, floor=DEFAULT_FLOOR):
    """心情可持续性检测。默认判据 A（长期稳态）；criterion='literal' 走字面口径（诊断用）。

    返回 dict(ok, criterion, report, …) 以及两个口径的完整结果：
      · 稳态(A)：steady_ok / steady_failures / steady_lows / steady_end / steady_starved
      · 字面(B)：literal_ok / literal_failures / literal_lows / literal_end
    为兼容旧调用保留的键：start / end / lows / failures / starved / windows / log
    （旧键 = 当前生效口径的结果；criterion='literal' 时与历史行为完全一致）。
    """
    roster, tl, shift_info = _timeline(shifts, ds)
    mor0 = {o: MAX_MORALE for o in roster}

    # —— 口径 B：字面（单日，00:00 起满 → 次日 00:00 必须满）——
    lit_end, lit_lows, lit_dips, lit_windows = _play_day(tl, roster, mor0)
    lit_fail = {o: round(lit_end[o] - MAX_MORALE, 3) for o in roster
                if lit_end[o] < MAX_MORALE - eps}

    # —— 口径 A：长期稳态（迭代到不动点，看最后一天）——
    mor = dict(mor0)
    st_end, st_lows, st_dips, st_windows = {}, {}, {}, {}
    for _ in range(max(1, int(days))):
        st_end, st_lows, st_dips, st_windows = _play_day(tl, roster, mor)
        mor = dict(st_end)
    st_fail = {o: round(st_lows[o] - floor, 3) for o in roster
               if st_lows[o] < floor or o in st_dips}

    steady_ok = not st_fail
    literal_ok = (not lit_fail) and (not lit_dips)
    ok = steady_ok if criterion == 'steady' else literal_ok

    res = dict(
        ok=ok, criterion=criterion, days=days, floor=floor,
        shifts_n=len(shifts), shift_info=shift_info,
        # 当前生效口径（兼容旧键）
        start=dict(mor0),
        end=dict(st_end if criterion == 'steady' else lit_end),
        lows=dict(st_lows if criterion == 'steady' else lit_lows),
        failures=dict(st_fail if criterion == 'steady' else lit_fail),
        starved=dict(st_dips if criterion == 'steady' else lit_dips),
        windows=st_windows if criterion == 'steady' else lit_windows,
        # 稳态（判据 A）
        steady_ok=steady_ok, steady_failures=st_fail, steady_lows=st_lows,
        steady_end=st_end, steady_starved=st_dips, steady_windows=st_windows,
        # 字面（判据 B，诊断）
        literal_ok=literal_ok, literal_failures=lit_fail, literal_lows=lit_lows,
        literal_end=lit_end, literal_starved=lit_dips,
    )
    res['log'] = _log_of(res['windows'], shifts)
    res['report'] = _fmt(res)
    return res


def _fmt(res):
    st_fail, st_lows, st_dip = res['steady_failures'], res['steady_lows'], res['steady_starved']
    lit_fail = res['literal_failures']
    n = len(res['steady_lows']) or 1
    if res['criterion'] == 'steady':
        head = '判据A(长期稳态) ' + ('✔' if res['steady_ok'] else '✘')
        if res['steady_ok']:
            body = (f'{res["days"]} 天迭代后无人被打穿，稳态最低心情 '
                    f'{min(st_lows.values()):.2f}（≥ {res["floor"]:g}）')
        else:
            worst = sorted(st_fail.items(), key=lambda kv: kv[1])[:5]
            body = '稳态不可持续：' + '、'.join(f'{o} 最低 {st_lows[o]:.2f}' for o, _ in worst)
            if st_dip:
                body += '；工作窗口内被打穿：' + '、'.join(
                    f'{o}(第{"/".join(map(str, sh))}班)' for o, sh in list(st_dip.items())[:3])
        diag = (f'［诊断·字面口径：{len(lit_fail)}/{n} 人在次日 00:00 未回满'
                f'（该口径在本规模下结构性不可达，见 daycheck 文档头）］')
        return head + ' ' + body + ' ' + diag
    # 字面口径（仅诊断）
    if res['literal_ok']:
        body = (f'判据B(字面·诊断) ✔ 次日 00:00 全部回到满心情'
                f'（最低 {min(res["literal_lows"].values()):.1f}）')
    else:
        parts = []
        if lit_fail:
            worst = sorted(lit_fail.items(), key=lambda kv: kv[1])[:6]
            parts.append('次日 00:00 未回满：' + '、'.join(f'{o} {v:+.2f}' for o, v in worst))
        if res['literal_starved']:
            parts.append('工作窗口内被消耗光：' + '、'.join(
                f'{o}(第{"/".join(map(str, sh))}班)'
                for o, sh in list(res['literal_starved'].items())[:4]))
        body = '判据B(字面·诊断) ✘ ' + '；'.join(parts)
    diag = (f'［判据A(长期稳态)：{"✔" if res["steady_ok"] else "✘"} '
            f'{res["days"]} 天迭代后最低心情 {min(st_lows.values()):.2f}，'
            f'未达标 {len(st_fail)}/{n} 人］')
    return body + ' ' + diag
