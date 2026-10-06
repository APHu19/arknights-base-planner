# -*- coding: utf-8 -*-
"""schedule.py —— 干员级窗口排班：**可行性判定核** + **单房间排班**（本轮只做这两块）

策略（为什么这样设计）
  1. 班次表就是**真实时间区间**（6,6,12 → [0,6) [6,12) [12,24)），不引入"轮换组数 G"这种抽象；
     所谓 ABC／AB／6 组只是某些可行解的**表现形式**，不是输入。
  2. 心情检查**内嵌在枚举期**：每个候选落位前当场投影当事人当天时间线
     （工作 −rate·h ／ 休息 +恢复·h），不合格立刻换人；不存在"排完再回头检查"。
  3. **不允许常驻**：某人加上本区间后若全天每个区间都在岗（无休息窗口）→ 直接判死。
  4. 床位 = 4 间 × 5 = **20** 是**每个区间**"不在岗人数"的上限，超了就不能再排人。
  5. `core/daycheck.py` 是**唯一终检器**；本模块不复制、不修改它的判据，只做"排人时的事前预测"。

两个口径（**判据 = A(steady) 已由用户裁定为正式验收口径**；literal 降级为诊断列）
  · 'steady'（默认，判据 A）—— **长期稳态**：把当天时间线反复迭代到不动点（第 1 天从 24 起算，
                     之后每天拿当天末值接着走），要求**稳态那一天**
                     ① 任何工作窗口都不被打穿（心情不归零）② 全天最低心情 ≥ STEADY_FLOOR。
                     语义 = "两次上班之间的休息足以撑过下一段工作"，且**允许上下班连排**（连排＝一段长班）。
  · 'literal'（诊断）—— 字面口径：次日 00:00 必须回满。实测在正常规模下**结构性不可达**，原因见文件尾。
  `core/daycheck.py` 仍是唯一终检器，且它的默认判据已经同步为 A（两个口径都会打印，**不偷偷放宽**）。
用法
    from solve import schedule as SCH
    st = SCH.DayState([6, 6, 12], ds=ds, policy='literal')
    SCH.schedule_room(st, '制造站', product='Pure Gold', level=3, need=3, slots=[0], pool=pool)
    SCH.pack_dorms(st, ds)
    print(SCH.verify(st, ds)['report'])          # → core/daycheck.py 的真实判定

本轮 `probe_sched.py` 用 6,6,12 实测出的两个**结构性障碍**（都是判据本身与基建规模的冲突，不是排班技巧问题）：
  ① **时间**：任何在跨越/贴近 00:00 的区间在岗的人，00:00 必然 < 24（消耗恒 > 0）⇒ 24h 全覆盖表在 literal 下必 ✘；
  ② **床位**：末段（00:00 前那段）只有 20 张床，而最后一班在岗 ~32 人 ⇒ 工作过末班的人在 00:00 前拿不到床位，
     照样回不满（实测恰好 −4.50/人）。要过 literal，必须让"最后一班在岗人数 ≤ 20"或允许区间内轮床。
  ③ **用户裁定（2024 会话）**：正式验收口径改为 **A = steady**（迭代到不动点、绝不见底）——
     6,6,12 在 A 下 **52/52 通过**（最低 7.50、无 24h 常驻、三班各 32 人在岗、床位 20/20），
     `core/daycheck.py` 的默认判据也已同步为 A，且逐人对账误差 0.0；literal 只作为诊断列照实打印。
"""
import itertools

from core.dataset import Dataset
from core.engine import (Ctx, MAX_MORALE, DORM_BASE,
                         drain_of, dorm_rooms_recovery, eval_room)

BEDS_PER_DORM = 5
DORM_COUNT = 4
BED_CAP = BEDS_PER_DORM * DORM_COUNT          # 20
EPS = 0.05
POLICIES = ('steady', 'literal')   # 默认 steady = 判据 A（长期稳态），literal 仅作诊断
STEADY_DAYS = 4          # 稳态迭代天数（第 1 天从 24 起算，之后接着走）
STEADY_FLOOR = 1.0       # 稳态下全天最低心情下限（>0 = 绝不见底/不红脸）

# 房间**物理**容量（含宿舍 5 床）；排人时不得超
CAP = {'控制中枢': 5, '贸易站': 3, '制造站': 3, '发电站': 3, '会客室': 2,
       '人力办公室': 1, '加工站': 1, '训练室': 1, '宿舍': BEDS_PER_DORM}


# ---------------------------------------------------------------- 时间轴
def windows(hours_list, start=0.0):
    """把班次时长表折成**真实时间区间** [(t0, t1, h), …]；
    例：[6,6,12] → [(0,6,6), (6,12,6), (12,24,12)]。可不等长。"""
    out, t = [], float(start)
    for h in hours_list:
        h = float(h)
        out.append((t, t + h, h))
        t += h
    return out


def min_rest_tail(hours, drain, rest):
    """尾班（时长 hours、消耗率 drain）结束后，要在 00:00 前回满所需的**最小休息时长**：
        drain·hours ≤ rest·t  →  t ≥ drain·hours / rest"""
    if drain <= 0 or rest <= 0:
        return 0.0
    return float(hours) * float(drain) / float(rest)


def latest_end(hours, drain, rest, day_end=24.0):
    """字面判据下，该尾班**最晚**能结束的时刻（结束得更晚 → 00:00 必回不满）。"""
    return float(day_end) - min_rest_tail(hours, drain, rest)


# ---------------------------------------------------------------- 一天的状态
class DayState:
    """一天的时间线状态：谁在哪个区间、在哪个房间、消耗多少、休息多少。

    assign: {(房间, 区间序号): dict(product=, level=, team=[干员…])}
    rate:   {(区间, 干员): 消耗/h}
    rest:   {(区间, 干员): 恢复/h}   —— pack_dorms 后填；之前用 rest_rate 保守估计
    """

    def __init__(self, hours, ds=None, yanhuo=0.0, beds=BED_CAP,
                 policy='steady', rest_rate=None, parked=None, targets=None, rest_slots=None):
        assert policy in POLICIES, f'policy 只能是 {POLICIES}'
        self.ds = ds or Dataset()
        self.hours = [float(h) for h in hours]
        self.win = windows(self.hours)
        self.yanhuo = float(yanhuo)
        self.beds = int(beds)
        self.policy = policy
        self.rest_rate = float(rest_rate) if rest_rate else DORM_BASE
        self.parked = list(parked or [])   # 常驻宿舍的干员（只吃床位/算恢复，不参与生产排班）
        # 每个区间**计划**在岗人数（床位约束要用"计划值"而不是"当前填了多少"，
        # 否则排前几个房间时后面区间还是空的，会把所有人误判成"不在岗"）
        self.slot_target = {int(k): int(v) for k, v in (targets or {}).items()}
        # **纯休息区间**（不排生产，如"6,6,6,6"的第 4 班）：不参与床位硬约束；
        # 枚举期对它的恢复按 0 保守估计（20 床要 52 人分，不能假设人人有床），
        # 最终以 pack_dorms 实算的寝室名单为准（daycheck 也用同一份名单）。
        self.rest_slots = {int(x) for x in (rest_slots or [])}
        self.assign = {}
        self.rate = {}
        self.rest = {}
        self.dorm = {}
        self.rejects = []          # 候选被拒样本日志（验收证据）
        self.reject_counts = {}    # 拒绝理由归类计数
        self.reject_total = 0
        self.notes = []

    # ---------- 基本查询 ----------
    @property
    def n_slots(self):
        return len(self.win)

    def roster(self):
        s = set(self.parked)
        for v in self.assign.values():
            s |= set(v['team'])
        return s

    def working(self, slot):
        return {o for (r, k, i), v in self.assign.items() if i == slot for o in v['team']}

    def instances(self, slot):
        """本区间已排的房间格（(房间, 实例序号)），用于计数"几间房有人"。"""
        return sorted((r, k) for (r, k, i), v in self.assign.items() if i == slot and v['team'])

    def rest_rate_of(self, slot, op):
        """该区间该干员的恢复速率：有寝室名单就按实算，否则给估计值
        （纯休息区间保守取 0；生产区间按宿舍基础 4.0/h——那 20 张床由不在岗者轮换）。"""
        if (slot, op) in self.rest:
            return self.rest[(slot, op)]
        return 0.0 if slot in self.rest_slots else self.rest_rate

    def target(self, slot):
        """该区间**计划**在岗人数；未给计划值时退回"当前实际在岗"（保守：会立刻卡住新面孔）。"""
        if slot in self.slot_target:
            return self.slot_target[slot]
        return len(self.working(slot))

    def bed_limits(self):
        """每区间"不在岗人数"上限 = 床位 + 该区间计划在岗人数。"""
        return {j: self.beds + self.target(j) for j in range(self.n_slots)}

    # ---------- 结算上下文的近似（只用于给队伍打分，不参与心情判定） ----------
    def ctx_of(self, slot, layout=None):
        ctx = Ctx(ds=self.ds)
        by = {}
        for (r, k, i), v in self.assign.items():
            if i == slot:
                by.setdefault(r, []).extend(v['team'])
        ctx.by_room = by
        ctx.staffed = [o for ops in by.values() for o in ops]
        if layout:
            ctx.layout = layout
        return ctx

    def refresh_all(self):
        """按当前 assign 重算所有 (区间, 干员) 的消耗率。中枢班变动会连带影响全基建（cc_relief）。"""
        self.rate = {}
        for i in range(self.n_slots):
            ctrl = list(self.assign.get(('控制中枢', 0, i), {}).get('team') or [])
            for (r, k, s), v in self.assign.items():
                if s != i or not v['team']:
                    continue
                cc = v['team'] if r == '控制中枢' else ctrl
                rates = _drain(r, list(v['team']), cc, self.yanhuo, self.ds)
                for m in v['team']:
                    self.rate[(i, m)] = rates[m]

    # ---------- 快照 / 回滚（候选试排用） ----------
    def snapshot(self):
        assign = {k: dict(product=v['product'], level=v['level'], team=list(v['team']))
                  for k, v in self.assign.items()}
        return (assign, dict(self.rate), dict(self.rest),
                {k: [list(r) for r in v] for k, v in self.dorm.items()})

    def restore(self, snap):
        assign, rate, rest, dorm = snap
        self.assign = {k: dict(product=v['product'], level=v['level'], team=list(v['team']))
                       for k, v in assign.items()}
        self.rate = dict(rate)
        self.rest = dict(rest)
        self.dorm = {k: [list(r) for r in v] for k, v in dorm.items()}

    # ---------- 时间线投影（可行性判定的核心） ----------
    def _walk(self, op, mor, override=None):
        """从给定心情走完**一天**，返回当天轨迹摘要（工作区间/最低/被打穿/上班时是否满）。"""
        low = mor
        dip, late, work = [], [], []
        for i, (_t0, _t1, h) in enumerate(self.win):
            r = (override or {}).get(i)
            if r is None:
                r = self.rate.get((i, op))
            if r:
                work.append(i)
                before = mor
                if before < MAX_MORALE - EPS:
                    late.append(i)
                if before - r * h < -1e-9:
                    dip.append(i)
                mor = max(0.0, mor - r * h)
            else:
                mor = min(MAX_MORALE, mor + self.rest_rate_of(i, op) * h)
            low = min(low, mor)
        return dict(end=mor, low=low, dip=dip, late=late, work=work)

    def project(self, op, override=None, days=None):
        """投影当事人的时间线。`days=1`（literal）从 00:00 满心情起算；
        `days>1`（steady）反复迭代到不动点，只报**最后一天**的轨迹。

        返回 dict(work=工作区间, end=当天末心情, low=当天最低, dip=被打穿的区间,
                  late=上班时未满的区间, full=00:00是否回满, next_window=, steady=)
        """
        if days is None:
            days = STEADY_DAYS if self.policy == 'steady' else 1
        days = max(1, int(days))
        mor, rec = MAX_MORALE, None
        for _ in range(days):
            rec = self._walk(op, mor, override)
            mor = rec['end']
        out = dict(rec)
        out['op'] = op
        out['days'] = days
        out['end'] = round(out['end'], 3)
        out['low'] = round(out['low'], 3)
        out['full'] = out['end'] >= MAX_MORALE - EPS
        out['next_window'] = (not out['late'] and not out['dip'])
        out['steady'] = (not out['dip']) and out['low'] >= STEADY_FLOOR
        return out

    def verdict(self, op, override=None):
        """(可否, 拒绝理由列表, 投影) —— 按 self.policy 的口径判定。"""
        p = self.project(op, override)
        reasons = []
        if p['dip']:
            reasons.append('工作窗口内被打穿(第%s班)' % '/'.join(str(i + 1) for i in p['dip']))
        if self.policy == 'literal':
            if not p['full']:
                reasons.append('次日00:00未回满(%.2f/24)' % p['end'])
        else:                                   # steady：长期可持续
            if p['low'] < STEADY_FLOOR:
                reasons.append('稳态下心情见底(%.2f)' % p['low'])
        return (not reasons), reasons, p

    # ---------- 增量可行性判定 ----------
    def can_place(self, room, inst, slot, op, product=None, level=None):
        """把 op 放进 (房间, 第几间, 区间) 是否可行。**当场**判：容量 / 区间冲突 / 常驻 / 床位 / 心情闭环。
        返回 (ok, reasons, info)；本方法不改动状态（内部快照-试排-回滚）。
        注：键必须带**实例序号**——5 间制造站是 5 个独立房间，不能按房间名合并。"""
        cur = self.assign.get((room, inst, slot))
        if cur and op in cur['team']:
            return True, [], dict(already=True)
        if op in self.working(slot):
            return False, ['区间冲突：本区间已在其他房间在岗'], {}
        cap = CAP.get(room, 3)
        if cur and len(cur['team']) >= cap:
            return False, [f'{room} 容量已满({cap} 人)'], {}
        busy = [i for i in range(self.n_slots) if op in self.working(i)]
        if len(busy) >= self.n_slots - 1:
            return False, ['常驻：加上本区间后全天无休息窗口'], {}
        # 床位：**每个区间**的"不在岗人数"都要 ≤ 20 床。
        # 排到一半时还没排满的区间要**按计划在岗人数算**（否则前面房间刚排人就会被误判床位不足）。
        # ⇒ 等价约束：总人数 N ≤ 20 + 该区间计划在岗人数。
        N = len(self.roster() | {op})
        for j in range(self.n_slots):
            if j in self.rest_slots:        # 纯休息区间：20 床由大家轮换，不构成"排不下"的硬约束
                continue
            occ = len(self.working(j) | ({op} if j == slot else set()))
            occ = max(occ, self.target(j))
            if N - occ > self.beds:
                return False, [f'床位不足：第{j + 1}班不在岗 {N - occ} 人 > {self.beds} 床'
                               f'（总人数 {N}，该班在岗 {occ}）'], {}
        snap = self.snapshot()
        try:
            v = self.assign.setdefault((room, inst, slot), dict(product=product, level=level, team=[]))
            if product is not None:
                v['product'] = product
            if level is not None:
                v['level'] = level
            v['team'].append(op)
            self.refresh_all()
            affected = sorted(self.roster()) if room == '控制中枢' else list(v['team'])
            bad = []
            for m in affected:
                ok, rs, p = self.verdict(m)
                if not ok:
                    bad.append((m, rs, p))
        finally:
            self.restore(snap)
        if bad:
            head = '；'.join(f'{m} ' + '，'.join(rs) for m, rs, _ in bad[:3])
            return False, [f'心情不可行：{head}'], dict(detail=bad)
        return True, [], {}

    def place(self, room, inst, slot, op, product=None, level=None, check=True):
        """真正落位。check=False 为**强制排人**（仅用于诊断：明知不可行也要让终检器给出真实数字）。"""
        if check:
            ok, reasons, info = self.can_place(room, inst, slot, op, product, level)
            if not ok:
                self.reject_total += 1
                for why in reasons:
                    k = why.split('：')[0].split('(')[0][:22]
                    self.reject_counts[k] = self.reject_counts.get(k, 0) + 1
                if len(self.rejects) < 200:
                    self.rejects.append(dict(room=f'{room}#{inst + 1}', slot=slot, op=op,
                                             reasons=list(reasons)))
                return False, list(reasons)
        v = self.assign.setdefault((room, inst, slot), dict(product=product, level=level, team=[]))
        if product is not None:
            v['product'] = product
        if level is not None:
            v['level'] = level
        if op not in v['team']:
            v['team'].append(op)
        self.refresh_all()
        return True, []


# ---------------------------------------------------------------- 队伍打分（只影响"先试谁"，不影响判定）
def _solo_eff(state, room, product, level, op, slot):
    try:
        return float(eval_room(room, level, product, [op], state.ctx_of(slot), state.ds).get('eff') or 0.0)
    except Exception:
        return 0.0


def _team_eff(state, room, product, level, team, slot):
    try:
        return float(eval_room(room, level, product, list(team), state.ctx_of(slot), state.ds).get('eff') or 0.0)
    except Exception:
        return 0.0


def _rank_default(state, room, product, level, op, slot):
    return (-_solo_eff(state, room, product, level, op, slot), op)


# 消耗率记忆化：同一 (房间, 队伍, 中枢班) 的 drain_of 结果完全确定，枚举期会反复问，必须缓存
_DRAIN_CACHE = {}


def _drain(room, team, ctrl, yanhuo, ds):
    key = (id(ds), room, tuple(team), tuple(ctrl or ()), float(yanhuo))
    hit = _DRAIN_CACHE.get(key)
    if hit is None:
        hit = drain_of(room, list(team), list(ctrl or []), yanhuo, ds)
        if len(_DRAIN_CACHE) < 300000:
            _DRAIN_CACHE[key] = hit
    return hit


# ---------------------------------------------------------------- 单房间排班
def schedule_room(state, room, inst=0, product=None, level=3, need=None, slots=None, pool=None,
                  rank=None, team_score=None, topn=8, topn_max=24, combo_cap=600,
                  force_on_fail=False, avail_filter=None, label=''):
    """**单房间**按真实区间排人（本轮的交付主体）。`inst` = 同名房间的第几间（5 间制造站 = 0..4）。

    对 (房间, 区间) 的每个需求：
      候选 = 该房间合格且本区间空闲的干员（可再用 avail_filter 先滤掉"一定排不进"的人，
             例如床位已满时的新面孔——否则枚举会在几百个必然被拒的候选上空转）→
      按 rank 排序取前 topn → 组 need 人队 → 每队逐个干员做 `state.can_place` **增量可行性判定**；
      第一支全队通过的队伍落位；全带失败则沿"候选排名带"往后扩（topn → 2×topn → … → topn_max×4）。
    返回 dict(placed={区间: [干员]}, failed=[…], tried=…, forced=[…])
    """
    need = int(need or CAP.get(room, 3))
    slots = list(range(state.n_slots)) if slots is None else list(slots)
    pool = list(pool or [])
    out = dict(room=f'{room}#{inst + 1}', need=need, placed={}, failed=[], forced=[], tried=0)

    for i in slots:
        have = list((state.assign.get((room, inst, i)) or {}).get('team') or [])
        short = need - len(have)
        if short <= 0:
            out['placed'][i] = have
            continue
        avail = [o for o in pool if o not in state.working(i)
                 and (avail_filter is None or avail_filter(o, i))]
        if len(avail) < short:
            out['failed'].append(dict(slot=i, reason=f'可用干员不足({len(avail)} < {short})', tried=0,
                                      sample=[]))
            continue
        key = rank or (lambda op, s: _rank_default(state, room, product, level, op, s))
        avail.sort(key=lambda op: key(op, i))
        done, tried, sample, dead = False, 0, [], set()
        # 候选**滑动排名带**：先试最靠前的 topn 人，不行再往后退一带（否则前排全被同一条理由拒死后
        # 永远试不到后面的人——这是本轮实测踩到的坑）
        span = max(topn * 2, 12)
        bands, start = [(0, topn), (0, span), (0, topn_max)], topn
        while start < min(len(avail), topn_max * 4):
            bands.append((start, start + span))
            start += span
        for a, b in bands:
            cands = [o for o in avail[a:b] if o not in dead]
            if len(cands) < short:
                continue
            combos = list(itertools.combinations(cands, short))
            if len(combos) > combo_cap:
                # cands 已按 rank 排序 → 直接截断 = "先试最像样的那些组合"（避免为几万组合打分）
                combos = combos[:combo_cap]
            if team_score:
                combos.sort(key=lambda t: -team_score(t, i))
            for t in combos:
                tried += 1
                snap = state.snapshot()
                ok = True
                for k, op in enumerate(t):
                    good, reasons = state.place(room, inst, i, op, product, level)
                    if not good:
                        ok = False
                        # 只把"与队友无关"的拒绝（床位/常驻/容量/冲突）或首位候选的失败记入死名单
                        if all(any(w in x for w in ('床位', '常驻', '容量', '区间冲突')) for x in reasons) \
                                or (k == 0 and not have):
                            dead.add(op)
                        if len(sample) < 3:
                            sample.append(dict(team=list(t), stop_at=op, reasons=reasons))
                        state.restore(snap)
                        break
                if ok:
                    out['placed'][i] = list(t)
                    done = True
                    break
            if done:
                break
        out['tried'] += tried
        if not done:
            out['failed'].append(dict(slot=i, reason='全部候选均不可行', tried=tried, sample=sample))
            if force_on_fail:
                forced = [o for o in avail[:need]]
                for op in forced:
                    state.place(room, inst, i, op, product, level, check=False)
                out['forced'].append(dict(slot=i, team=forced))
    return out


# ---------------------------------------------------------------- 寝室打包（4 间 × 5 床）
def pack_dorms(state, ds=None, leads=None, per_dorm=BEDS_PER_DORM):
    """按"当天最低心情"优先占床，4 间寝室各 ≤5 人；恢复速率由 `dorm_rooms_recovery` 实算。
    **没抢到床位的人按"闲着"处理（恢复 0）**——否则事前预测会比终检器乐观（历史 bug）。
    返回 (溢出列表, 每区间的寝室列表)"""
    ds = ds or state.ds
    leads = [o for o in (leads or [])]
    state.dorm = {}
    overflow = []
    for i in range(state.n_slots):
        off = sorted(state.roster() - state.working(i), key=lambda o: state.project(o)['low'])
        rooms = [[] for _ in range(DORM_COUNT)]
        for ld in leads:                       # 恢复技干员先铺进不同寝室（各算各的，不摊分）
            if ld in off:
                for r in rooms:
                    if len(r) < per_dorm:
                        r.append(ld)
                        off.remove(ld)
                        break
        for o in off:
            for r in rooms:
                if len(r) < per_dorm:
                    r.append(o)
                    break
            else:
                overflow.append((i, o))
                state.rest[(i, o)] = 0.0       # 没床 = 没恢复（与终检器的 'idle' 口径一致）
        state.dorm[i] = [r for r in rooms if r]
        rr = dorm_rooms_recovery(state.dorm[i], ds)
        for idx, r in enumerate(state.dorm[i]):
            for o in r:
                state.rest[(i, o)] = rr[idx]
    return overflow, state.dorm


# ---------------------------------------------------------------- 输出 & 终检
def to_shifts(state):
    """转成 `core/daycheck.py` 认识的班次表（含 hours/start/end，支持异形区间）。"""
    out = []
    for i, (t0, t1, h) in enumerate(state.win):
        rooms = []
        for (r, k, s), v in sorted(state.assign.items()):
            if s != i or not v['team']:
                continue
            rooms.append((r, v['product'], v['level'], list(v['team'])))
        out.append(dict(rooms=rooms, dorm=[list(d) for d in (state.dorm.get(i) or [])],
                        fia={}, hours=h, start=t0, end=t1))
    return out


def bed_report(state):
    """终检口径的床位占用：实际不在岗 vs 20 床（某区间没排满时，不在岗会真的超过床位）。"""
    rows = []
    for i in range(state.n_slots):
        w = state.working(i)
        rows.append(dict(slot=i + 1, onduty=len(w), offduty=len(state.roster() - w), beds=state.beds,
                         over=max(0, len(state.roster() - w) - state.beds)))
    return rows


def verify(state, ds=None, criterion=None):
    """**唯一终检器**：core/daycheck.py（默认判据 A = 长期稳态；criterion='literal' 可切到字面诊断）。
    返回它的原始结果，另挂 'kernel'/'beds'/'bed_overflow' 供对照。"""
    from core.daycheck import morale_day
    res = morale_day(to_shifts(state), ds or state.ds, criterion=criterion or state.policy)
    res['kernel'] = kernel_rows(state)
    res['beds'] = bed_report(state)
    res['bed_overflow'] = [r['slot'] for r in res['beds'] if r['over']]
    return res


def kernel_rows(state):
    """逐干员的事前预测（供与终检器逐人对账）。"""
    rows = []
    for op in sorted(state.roster()):
        p = state.project(op)
        rows.append(dict(op=op, work=[i + 1 for i in p['work']], end=p['end'], low=p['low'],
                         literal=p['full'], next_window=p['next_window'], steady=p['steady']))
    return rows


def reconcile(state, res):
    """事前预测 vs 终检器的逐人对账（应≈0，用来证明判定核与官方判据一致）。"""
    worst, n = 0.0, 0
    for r in res.get('kernel') or []:
        end2 = (res.get('end') or {}).get(r['op'])
        if end2 is None:
            continue
        n += 1
        worst = max(worst, abs(float(end2) - float(r['end'])))
    return dict(checked=n, max_abs_diff=round(worst, 4))


def coverage(state):
    """每区间的在岗/不在岗/房间数（床位压力 + 人数规模）。"""
    rows = []
    for i, (t0, t1, h) in enumerate(state.win):
        w = state.working(i)
        rows.append(dict(slot=i + 1, span=f'[{t0:g},{t1:g})', hours=h, onduty=len(w),
                         offduty=len(state.roster() - w), beds=state.beds,
                         rooms=len(state.instances(i))))
    return rows


def reject_summary(state, limit=6):
    """候选拒绝理由归类（验收证据：到底卡在哪一条）。"""
    c = dict(state.reject_counts)
    out = sorted(c.items(), key=lambda kv: -kv[1])[:limit]
    return out, state.reject_total


def fmt_report(state, res=None, title=''):
    """人读报告。"""
    L = []
    if title:
        L.append(f'—— {title} ——')
    L.append(f'班次表: {[f"{h:g}h" for h in state.hours]}  区间: '
             + ' '.join(f'[{a:g},{b:g})' for a, b, _ in state.win)
             + f'   口径: {state.policy}   床位: {state.beds}')
    for r in coverage(state):
        L.append(f"  第{r['slot']}班 {r['span']:<10} 在岗 {r['onduty']:>2} / 不在岗 {r['offduty']:>2}"
                 f"  房间 {r['rooms']}  床位占用 {r['offduty']}/{r['beds']}")
    for r in bed_report(state):
        if r['over']:
            L.append(f"  ⚠ 第{r['slot']}班床位溢出 {r['over']} 人（在岗 {r['onduty']}，"
                     f"不在岗 {r['offduty']} > {r['beds']}）→ 这部分人得不到休息，只能按「闲着」算")
    kr = kernel_rows(state)
    if kr:
        lit = sum(1 for r in kr if r['literal'])
        stb = sum(1 for r in kr if r['steady'])
        L.append(f'  干员 {len(kr)} 人：判据A(长期稳态) 达标 {stb}/{len(kr)}〔正式〕，'
                 f'字面口径 达标 {lit}/{len(kr)}〔诊断〕，'
                 f'最低心情 {min(r["low"] for r in kr):.2f}，00:00 最低 {min(r["end"] for r in kr):.2f}')
        bad = [r for r in sorted(kr, key=lambda r: r['end']) if not r['literal']][:5]
        if bad:
            L.append('  00:00 未回满（最差 5 人）：' + '、'.join(
                f"{r['op']} {r['end']:.2f}(第{'/'.join(map(str, r['work']))}班)" for r in bad))
        else:
            L.append('  00:00 全部回满 ✔')
    rs, tot = reject_summary(state)
    if rs:
        L.append(f'  候选被拒 {tot} 次，归类：' + '，'.join(f'{k}×{v}' for k, v in rs))
    if res is not None:
        L.append('  终检器(daycheck)：' + str(res.get('report')))
        L.append('  预测/终检对账：' + str(reconcile(state, res)))
    return '\n'.join(L)
