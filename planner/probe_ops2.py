# -*- coding: utf-8 -*-
"""probe_ops2.py —— 打印指定干员的全部后勤技能（房间/技能名/原文），用于写"体系原型" """
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

from core.dataset import Dataset, load_box          # noqa: E402

WANT = sys.argv[1].split(',') if len(sys.argv) > 1 else [
    '黑键', '灵知', '银灰', '初雪', '至简', '承曦格雷伊', '迷迭香', '夕', '爱丽丝', '絮雨',
    '车尔尼', '塑心', '凛视', '提丰', '伺夜', '贝洛内', '摩根', '蕾缪安', '温蒂', '森蚺',
    '清流', '红云', '泡泡', '稀音', '刻俄柏', '槐琥', '泡普卡', '雪雉', '空弦', '图耶',
    '孑', '但书', '可露希尔', '龙舌兰', '巫恋', '柏喙', '明椒', '菲亚梅塔', '澄闪', '深靛',
    '札拉克', '玫兰莎', '月见夜', '古米', '空爆', '夜烟', '砾', '斑点', '断罪者', '食铁兽']

ds = Dataset()
box = load_box()
ds.set_box(box)
for op in WANT:
    sk = ds.skills_of(op)
    if not sk:
        print(f'{op:<8} —（无记录）')
        continue
    print(f'{op:<8} 精英化{box.get(op, {}).get("elite", "?")}')
    for s in sk:
        print(f'    @{s.room:<5} {s.name:<12} {s.desc}')
