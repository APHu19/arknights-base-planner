# -*- coding: utf-8 -*-
"""shiftplan.py —— 自定义班次表（一天几班倒 / 每班几点到几点）

用户口径（原文）：
  · 一天**几班倒**由使用者在界面上决定；"新建第 N 班"时输入**开始时间**，
    结束时间 = 下一班的开始时间（界面上显示为"下一班开始 − 1 分钟"）。
  · 第一个班次 = 使用者输入的第一个开始时间（**不强制从 00:00 起**）；
    整张表是**闭环**：最后一班结束后回到第一班开始。
  · 例：['22:00', '10:00', '16:00'] →
        第1班 22:00→10:00（12h）／第2班 10:00→16:00（6h）／第3班 16:00→22:00（6h）

内部约定（与界面显示的唯一差别，必须知道）
  * 计算与 MAA 输出按**整点连续区间**（end = 下一班 start），全天正好 24h。
    理由：MAA 的 `period`/`duration` 需要覆盖整天；而心情模型只关心时长，
    1 分钟缝隙对结果无影响（`display_end` 字段保留"下一班开始 − 1 分钟"给界面用）。
  * **锚点 = 第一班的开始时间**：心情稳态判据（`core/daycheck.py` 判据 A）与
    "从哪切一天"无关（同一条循环旋转后不动点相同），所以锚点取第一班开始最自然。
"""
import re

MIN_SHIFTS = 2
MAX_SHIFTS = 8          # MAA 侧常见 ≤6；模型本身不限，但给个防呆上限
DAY_MINUTES = 1440


def parse_hhmm(s):
    s = str(s).strip().replace('：', ':')
    if not re.match(r'^\d{1,2}:\d{2}$', s):
        raise ValueError(f'时间格式应为 HH:MM（例如 22:00）：{s!r}')
    h, m = s.split(':')
    h, m = int(h), int(m)
    if not (0 <= h < 24 and 0 <= m < 60):
        raise ValueError(f'时间越界（应 00:00~23:59）：{s!r}')
    return h * 60 + m


def fmt_hhmm(mins):
    mins %= DAY_MINUTES
    return f'{mins // 60:02d}:{mins % 60:02d}'


def build_table(starts):
    """['22:00','10:00','16:00']（**用户输入顺序**）→ 班次表 [{index,start,end,minutes,hours,…}]"""
    starts = [s for s in (starts or []) if str(s).strip()]
    ms = [parse_hhmm(s) for s in starts]
    n = len(ms)
    if n < MIN_SHIFTS:
        raise ValueError(f'至少 {MIN_SHIFTS} 班（当前 {n} 班）')
    if n > MAX_SHIFTS:
        raise ValueError(f'最多 {MAX_SHIFTS} 班（当前 {n} 班）')
    if len(set(ms)) != n:
        raise ValueError('班次开始时间重复：' + '、'.join(starts))
    out = []
    for i, m in enumerate(ms):
        nxt = ms[(i + 1) % n]
        dur = (nxt - m) % DAY_MINUTES
        if dur == 0:
            raise ValueError('存在零时长班次（开始时间重复）')
        out.append(dict(index=i + 1, start=fmt_hhmm(m), end=fmt_hhmm(nxt),
                        start_min=m, minutes=dur, hours=dur / 60.0,
                        display_end=fmt_hhmm((nxt - 1) % DAY_MINUTES),
                        wraps=(m + dur) > DAY_MINUTES))
    total = sum(t['minutes'] for t in out)
    if total != DAY_MINUTES:
        raise ValueError(f'班次总时长 {total} 分钟 ≠ 1440（请检查各开始时间）')
    return out


def from_hours(hours_list, start='00:00'):
    """等长/不等长时长表 → 班次表（给 `--shift-hours` 与旧路径复用同一套结构）。"""
    t0 = parse_hhmm(start)
    ms, cur = [], t0
    for h in hours_list:
        ms.append(cur)
        cur = (cur + int(round(float(h) * 60))) % DAY_MINUTES
    return build_table([fmt_hhmm(m) for m in ms])


def hours_list(table):
    return [float(t['hours']) for t in table]


def summary(table):
    return ' / '.join(f"第{t['index']}班 {t['start']}→{t['end']}（{t['hours']:g}h）" for t in table)


def total_minutes(table):
    return sum(int(t['minutes']) for t in table)
