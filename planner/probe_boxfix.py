# -*- coding: utf-8 -*-
"""probe_boxfix.py —— 修正 gui/config.json 里被误点坏的干员池（持有/精英化）

背景：旧版 GUI 的"切换持有/精英化"作用在**刷新后的选中行**上，刷新会丢选中 →
点 A 行可能改到 B 行，把 阿米娅 这类本来持有的干员标成"未持有"，并让 MAA 校验报
`未持有干员 ['阿米娅']`。本工具把"与本地 MAA 导出同名"的条目按导出重设（导出里没有的名字保持不动）。

用法：
    python planner\\probe_boxfix.py            # 只看差异（不改）
    python planner\\probe_boxfix.py --apply    # 实际修复并写回 config.json
"""
import os
import sys
import json

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

from gui import state as ST          # noqa: E402


def main():
    apply = '--apply' in sys.argv
    cfg = ST.load_config()
    box = cfg.get('box') or {}
    if not box:
        print('config.json 里没有干员池（GUI 会直接读 MAA 导出，无需修）')
        return 0
    ref = ST.import_maa_json(ST.maa_export_path())
    if '--debug' in sys.argv:
        print('DEBUG ref 条目', len(ref), '| 阿米娅 =', ref.get('阿米娅'),
              '| config 阿米娅 =', box.get('阿米娅'))
        print('DEBUG ref 前三', list(ref.items())[:3])
        print('DEBUG cfg 前三', list(box.items())[:3])
    diff = []
    for name, v in ref.items():
        cur = box.get(name)
        if (not cur) or bool(cur.get('own')) != bool(v['own']) or int(cur.get('elite', 0)) != v['elite']:
            diff.append((name, cur, v))
    print(f'干员池 {len(box)} 名（本地 MAA 导出 {len(ref)} 名）；与导出不一致 {len(diff)} 处：')
    for name, cur, ref_v in diff[:20]:
        c = f"持有={cur.get('own')} 精{cur.get('elite')}" if cur else '（缺失）'
        print(f'  {name:<12} 当前 {c:<18} → 导出 持有={ref_v["own"]} 精{ref_v["elite"]}')
    if len(diff) > 20:
        print(f'  …另有 {len(diff) - 20} 处')
    if not apply:
        print('\n（未改动；要修复请加 --apply）')
        return 0
    new_box, changed, path = ST.sync_box_from_maa(box)
    cfg['box'] = new_box
    ST.save_config(cfg)
    print(f'\n已按 {path} 修复 {changed} 处，写回 {ST.CONFIG}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
