# -*- coding: utf-8 -*-
"""extract_phases.py —— 从 building_data.json 抽出「干员 × 房间 × 精英化阶段 → 技能」权威映射

输出 data/phases.json：{干员: {房间: [ {name, phase, buffId} ]}}
phase: 0=初始/精0 起可用，1=精1 起，2=精2 起（cond.phase 即“解锁条件”）
同族技能（如 裁缝·α/β）在更高阶段会替换低阶形态；不同族技能共存。
"""
import json, os, sys, re, collections
sys.stdout.reconfigure(encoding='utf-8')
HERE = os.path.dirname(os.path.abspath(__file__))
PLANNER = os.path.dirname(HERE)
ROOT = os.path.dirname(PLANNER)
sys.path.insert(0, PLANNER)
RAW = os.path.join(ROOT, '_raw')
BD = os.path.join(RAW, 'building_data.json')
CT = os.path.join(RAW, 'character_table.json')
OUT = os.path.join(HERE, 'phases.json')
PH = {'PHASE_0': 0, 'PHASE_1': 1, 'PHASE_2': 2, 'PHASE_3': 3, 'PHASE_4': 4, 'PHASE_5': 5, 'PHASE_6': 6}
ROOM = {'CONTROL': '控制中枢', 'TRADING': '贸易站', 'MANUFACTURE': '制造站', 'POWER': '发电站',
        'MEETING': '会客室', 'HIRE': '人力办公室', 'WORKSHOP': '加工站', 'TRAINING': '训练室',
        'DORMITORY': '宿舍'}


def clean(s):
    s = re.sub(r'<@[^>]+>', '', s or '')
    return re.sub(r'\s+', '', s)


def main():
    bd = json.load(open(BD, encoding='utf-8'))
    ct = json.load(open(CT, encoding='utf-8'))
    chars, buffs = bd.get('chars') or {}, bd.get('buffs') or {}
    name2id, id2name = {}, {}
    for cid, c in ct.items():
        if not isinstance(c, dict) or not c.get('name'):
            continue
        id2name[cid] = c['name']
        # 只认真正的干员 id：trap_/token_ 是召唤物/装置，会和干员同名并覆盖真实条目
        if cid.startswith('char_'):
            name2id[c['name']] = cid
        elif c['name'] not in name2id:
            name2id[c['name']] = cid
    # 同名干员的备用 id（有的干员在 building_data 里用 char_xxx，而 character_table 里是 trap_xxx）
    alt = {}
    for cid in chars:
        nm = id2name.get(cid)
        if nm and nm not in name2id:
            alt[nm] = cid
    out, unresolved, no_phase = {}, [], []
    for nm, cid in list(name2id.items()) + list(alt.items()):
        ch = chars.get(cid)
        if not ch:
            continue
        rows = []
        for grp in ch.get('buffChar') or []:
            for b in grp.get('buffData') or []:
                bf = buffs.get(b.get('buffId')) or {}
                room = ROOM.get(bf.get('roomType'))
                if not room:
                    continue
                cond = b.get('cond') or {}
                ph = PH.get(cond.get('phase') if isinstance(cond, dict) else cond, 0)
                rows.append(dict(name=bf.get('buffName') or bf.get('name'), room=room, phase=ph,
                                 buffId=b.get('buffId'), desc=clean(bf.get('description'))))
        if rows:
            d = collections.defaultdict(list)
            for r in rows: d[r['room']].append(r)
            out[nm] = {k: sorted(v, key=lambda x: x['phase']) for k, v in d.items()}
    # 覆盖率：技能库里出现过、但阶段表里没有的干员
    try:
        from core.dataset import Dataset
        ds = Dataset()
        holders = set()
        for s in ds.skills: holders |= set(s.holders)
    except Exception:
        holders = set()
    missing = sorted(h for h in holders if h not in out)
    json.dump({'meta': {'source': 'building_data.json/chars[].buffChar',
                        'operators': len(out), 'holders_total': len(holders),
                        'missing': missing},
               'ops': out}, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f'已写出 {OUT}')
    print(f'  覆盖干员 {len(out)} 名；技能库持有者 {len(holders)} 名')
    print(f'  ⚠ 阶段表缺失（需你手动确认）{len(missing)} 名：')
    for i in range(0, len(missing), 12):
        print('     ' + '、'.join(missing[i:i + 12]))
    for nm in ('明椒', '柏喙', '巫恋', '温蒂', '贝娜', '森蚺', '响石'):
        d = out.get(nm)
        if not d:
            print(f'  {nm}: ⚠ 无阶段数据'); continue
        print(f'  {nm}: ' + '；'.join(
            f"{rm}[" + ' '.join(f'{r["name"]}@E{r["phase"]}' for r in rs) + ']' for rm, rs in d.items()))


if __name__ == '__main__':
    main()
