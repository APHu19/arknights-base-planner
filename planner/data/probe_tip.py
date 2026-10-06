# -*- coding: utf-8 -*-
"""probe_tip：看 念力 行的原始 HTML，找出隐藏提示块的真实标记"""
import re
P = r'C:\Users\APHu\dsh生成333基建表\后勤技能一览带注释.md'
html = open(P, encoding='utf-8', errors='replace').read()
trs = re.findall(r'<tr.*?</tr>', html, re.S)
for t in trs:
    if '念力' in t:
        # 只打印描述单元格
        tds = re.findall(r'<td[^>]*>(.*?)</td>', t, re.S)
        desc = tds[2] if len(tds) > 2 else t
        print('---- 描述单元格原样（前 1500 字）----')
        print(desc[:1500])
        print('\n---- 隐藏类标记统计 ----')
        for pat in (r'display\s*:\s*none', r'class="[^"]*tooltip[^"]*"', r'<div', r'<span[^>]*>'):
            print(f'  {pat}: {len(re.findall(pat, desc))}')
        break
