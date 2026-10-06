# -*- coding: utf-8 -*-
"""dump_sys：导出体系（中间产物）相关干员的全部技能原文"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.dataset import Dataset

OPS = ['迷迭香', '黑键', '塑心', '深律', '絮雨', '车尔尼', '爱丽丝', '夕', '令', '黍', '桑葚',
       '截云', '森西', '灰烬', '战车', '至简', '红云', '槐琥', '雪雉', '异客', '玛恩纳', '魔王',
       '维什戴尔', '承曦格雷伊', '歌蕾蒂娅', '斯卡蒂', '幽灵鲨', '安哲拉', '乌尔比安',
       '丰川祥子', '若叶睦', '八幡海铃', '三角初华', '祐天寺若麦', '泰拉大陆调查团',
       '火龙S黑角', '麒麟R夜刀', '佩佩', '可露希尔', '绮良', '鸿雪']
ds = Dataset()
for op in OPS:
    skl = ds.skills_of(op)
    if not skl:
        print(f'—— {op} ——（技能库中无此人）'); continue
    print(f'—— {op} ——')
    for s in skl:
        print(f'   [{s.room}] {s.name}: {s.desc[:170]}')
