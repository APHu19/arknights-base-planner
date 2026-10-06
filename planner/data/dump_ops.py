# -*- coding: utf-8 -*-
"""dump_ops：导出关键干员的技能原文（供编写 effects.json 规则表对照）"""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from core.dataset import Dataset

OPS = """娜斯提 清流 阿罗玛 引星棘刺 砾 苍苔 冬时 森蚺 温蒂 多萝西 淬羽赫默 铅踝 迷迭香
缪尔赛思 承曦格雷伊 雷蛇 澄闪 格雷伊 阿消 乌有 但书 古米 梓兰 可露希尔 吉星 真言
能天使 新约能天使 空弦 蕾缪安 孑 赫德雷 齐尔查克 地灵 槐琥 褐果 艾雅法拉 谬因 锡兰
巫恋 龙舌兰 柏喙 明椒 卡夫卡 令 夕 重岳 余 望 黍 维什戴尔 阿米娅 凯尔希 摩根 戴菲恩
焰影苇草 跃跃 车尔尼 爱丽丝 塑心 杜林 夜莺 菲亚梅塔 絮雨 斥罪 遥 深律 伊内丝 红
香草 调香师 史都华德 水月 澄闪""".split()

ds = Dataset()
out = []
for op in OPS:
    skl = ds.skills_of(op)
    if not skl:
        continue
    out.append(f'### {op}')
    for s in skl:
        out.append(f'  [{s.room}] {s.name} :: {s.desc}')
    out.append('')
open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'op_skills_dump.txt'), 'w', encoding='utf-8').write('\n'.join(out))
print(f'已导出 {len(OPS)} 名干员技能原文（{len(out)} 行）')

# 只打印制造站 + 贸易站 + 发电站（规则表最需要的）
for op in OPS:
    rows = [s for s in ds.skills_of(op) if s.room in ('制造站', '贸易站', '发电站')]
    if not rows: continue
    print(f'—— {op} ——')
    for s in rows:
        print(f'   [{s.room}] {s.name}: {s.desc[:150]}')
