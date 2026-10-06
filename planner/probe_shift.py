# -*- coding: utf-8 -*-
"""probe_shift.py —— 自定义班次表回归：模型 / MAA 输出 / GUI 口径

覆盖：
  1. `core.shiftplan.build_table`：用户给的 22:00,10:00,16:00 → 12h/6h/6h，闭环、合计 1440 分钟；
  2. 非法输入必须报错（少于 2 班、重复、格式错、时间越界）；
  3. `emit.maa.deck_from_plan`：自定义表 → 每班写 period/duration、planTimes = '3班'，
     且 `emit.maa.validate` 通过；故意把某班时段改错 → 必须被校验抓出来；
  4. 等价性：6×4h 的表 == 旧的 `--shift-hours 4`（班次数、每班长短一致）。
"""
import os
import sys
import copy

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

from core import shiftplan as SP          # noqa: E402
from emit import maa                      # noqa: E402

ok = fail = 0


def check(tag, cond, extra=''):
    global ok, fail
    if cond:
        ok += 1
        print(f'  ✔ {tag} {extra}')
    else:
        fail += 1
        print(f'  ✘ {tag} {extra}')


def main():
    print('=== 1) 用户用例：--shifts "22:00,10:00,16:00" ===')
    t = SP.build_table(['22:00', '10:00', '16:00'])
    check('班次数 = 3', len(t) == 3)
    check('第1班 22:00→10:00 = 12h', t[0]['start'] == '22:00' and t[0]['end'] == '10:00'
          and abs(t[0]['hours'] - 12) < 1e-9, f"{t[0]['start']}→{t[0]['end']} {t[0]['hours']}h")
    check('第2班 10:00→16:00 = 6h', t[1]['start'] == '10:00' and abs(t[1]['hours'] - 6) < 1e-9)
    check('第3班 16:00→22:00 = 6h', t[2]['start'] == '16:00' and abs(t[2]['hours'] - 6) < 1e-9)
    check('合计 1440 分钟（闭环整天）', SP.total_minutes(t) == 1440)
    check('显示用结束时间 = 下一班开始 − 1 分钟',
          t[1]['display_end'] == '15:59' and t[0]['display_end'] == '09:59')
    print('    ' + SP.summary(t))

    print('=== 2) 非法输入必须报错 ===')
    for bad, why in ((['22:00'], '少于 2 班'), (['10:00', '10:00'], '重复'),
                     (['25:00', '10:00'], '越界'), (['abc', '10:00'], '格式')):
        try:
            SP.build_table(bad)
            check(f'{why} 应报错', False, f'却通过了 {bad}')
        except ValueError as e:
            check(f'{why} 报错', True, str(e)[:40])

    print('=== 3) 6×4h 与旧口径等价 ===')
    t6 = SP.from_hours([4] * 6)
    check('6 班、每班 4h', len(t6) == 6 and all(abs(x['hours'] - 4) < 1e-9 for x in t6))
    check('首班 00:00、末班 20:00→24:00(=00:00)', t6[0]['start'] == '00:00' and t6[5]['end'] == '00:00')

    print('=== 4) MAA 输出：period / duration / planTimes ===')
    plan = {'shifts': [dict(rooms=[('制造站', 'Pure Gold', 3, ['A', 'B', 'C'])],
                            dorm=[['D'], [], [], []], fia={}, hours=x['hours'],
                            name=f"第{x['index']}班（{x['start']}-{x['end']}）",
                            period=[x['start'], x['end']], duration=int(x['minutes']))
                      for x in t]}
    doc = maa.deck_from_plan(plan, 'lmd_test', '333')
    check("planTimes = '3班'", doc['planTimes'] == '3班', doc['planTimes'])
    check('scheduleType.planTimes = 3', doc['scheduleType']['planTimes'] == 3)
    check('每班都写了 period/duration',
          all(p.get('period') and p.get('duration') for p in doc['plans']))
    check('第1班 period = 22:00~10:00 / 720min',
          doc['plans'][0]['period'] == ['22:00', '10:00'] and doc['plans'][0]['duration'] == 720)
    issues = [i for i in maa.validate(doc) if 'Fiammetta' not in i and 'drones' not in i]
    check('协议校验（自定义班次部分）通过', not issues, issues)
    bad = copy.deepcopy(doc)
    bad['plans'][2]['period'] = ['17:00', '22:00']          # 与上一班终点 16:00 不连续
    hit = [i for i in maa.validate(bad) if '不连续' in i or '1440' in i]
    check('时段不连续 / 不到 24h 会被抓出', bool(hit), hit[:1])
    print(f'\n结果：{ok} 通过 / {fail} 失败')
    return 1 if fail else 0


if __name__ == '__main__':
    sys.exit(main())
