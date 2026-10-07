# -*- coding: utf-8 -*-
"""orders.py —— 订单模型（基础分布 + 品质技能改写 + 但书违约 + 慢热）

【基础贵金属订单表】（3 级贸易站）
    赤金  龙门币   基础耗时       常规概率
     2    1000    2:24(8640s)    30%
     3    1500    3:30(12600s)   50%
     4    2000    4:36(16560s)   20%
    期望 2.9 赤金

【品质技能改写分布】（用户提供的实测表）
    订单需求   常规     α级            β级
      2       30%    15% (−15%)     5% (−25%)
      3       50%    30% (−20%)     10% (−40%)
      4       20%    55% (+35%)     85% (+65%)
    期望      2.9     3.4 (+0.5)     3.8 (+0.9)
  · α 级：进驻累计工作 3 小时达到该值；离开/换工位则清零重算
  · β 级：进驻累计工作 5 小时达到该值
  · α+α 峰值实测 65%/22%/13%，期望 3.46
  · α+β 峰值实测 85%/10%/5%，期望 3.8（与单 β 相同）
  · 叠加模型官方未定 → 按要求**按线性处理**：
      有 β：直接取 β 分布（α 不再额外贡献，与实测一致）
      仅 α：基础分布 + (1 + 0.3×(α数−1)) × (α分布 − 基础分布)
            （α+α 得期望 3.55，实测 3.46，误差 0.09，属线性近似可接受）

【但书违约】（与品质正交，先按品质定档再改写）
    合同法：下笔赤金交付数 < 4 → 违约订单；违约索赔·α/+1、·β/+2 赤金，龙门币同比例放大
    ✅ 校验：违约索赔·β 时 6.64 币/效率点·h、0.01327 赤金/效率点·h
"""
ORDERS = [(2, 1000, 8640), (3, 1500, 12600), (4, 2000, 16560)]
# **订单上限**（全机制.md 贸易站等级表）：Lv1/2/3 = 6/8/10 —— 孑的"差额订单"全靠它
ORDER_CAP = {1: 6, 2: 8, 3: 10}
IN_HAND = 1.0            # 假设：稳态下贸易站手里压着 1 笔订单（自动交付/及时收取）
# 龙舌兰·投资：**按单结算的独立乘区**（不是效率%）
INVEST = {'投资·β': 500.0, '投资·α': 250.0}
BASE_P = (0.30, 0.50, 0.20)
ALPHA_P = (0.15, 0.30, 0.55)
BETA_P = (0.05, 0.10, 0.85)
# α 叠加的**实测分布**（用户提供）：
#   α×1 → (15%,30%,55%)　期望 3.4　；α×2 → (13%,22%,65%)　期望 3.52（原文标注 3.46）
#   存在 β 时 α 不再额外贡献（α+β 实测 = β 分布）
ALPHA2_P = (0.13, 0.22, 0.65)
RAMP_HOURS = {'α': 3.0, 'β': 5.0}
QUALITY_SKILLS = {
    'α': ('裁缝·α', '手工艺品·α', '鉴定师的眼光', '懂行', '千金的眼光'),
    'β': ('裁缝·β', '手工艺品·β', '鉴定师的手段'),
}
BREACH = {'违约索赔·β': 2, '违约索赔·α': 1}


def _quality_skills(team, ds):
    alphas, betas = [], []
    for op in team:
        tiers = set()
        for s in ds.skills_of(op, '贸易站'):
            for tier, names in QUALITY_SKILLS.items():
                if (s.name or '') in names:
                    tiers.add(tier)
        if 'β' in tiers: betas.append(op)
        elif 'α' in tiers: alphas.append(op)
    return alphas, betas


def _extrapolate_alpha(n):
    """α 叠加外推：实测只有 α×1 与 α×2，≥3 个按“一变二的差值”线性外推
       α3 = α2 + (α2 − α1)；αn = α2 + (n−2)×(α2 − α1)，再裁剪归一。"""
    if n <= 1: return ALPHA_P
    if n == 2: return ALPHA2_P
    d = tuple(b - a for a, b in zip(ALPHA_P, ALPHA2_P))
    t = tuple(max(0.01, min(0.99, ALPHA2_P[i] + (n - 2) * d[i])) for i in range(3))
    s = sum(t)
    return tuple(x / s for x in t)


def probabilities(team, ds, hours=12.0):
    """返回 (概率元组, 档位说明, 慢热说明)。
    分布取**实测值**（不再用线性近似）：
      有 β            → β 分布（α+β 实测等于 β）
      仅 1 个 α       → α 分布
      仅 ≥2 个 α      → α×2 实测分布；≥3 个按“一变二的差值”外推
    慢热：α 3h、β 5h 线性爬升（原文只给了峰值与时长，中间过程按线性处理）。"""
    alphas, betas = _quality_skills(team, ds)
    if betas:
        target, ramp, tag = BETA_P, RAMP_HOURS['β'], f'β×{len(betas)}'
    elif len(alphas) >= 2:
        target, ramp, tag = _extrapolate_alpha(len(alphas)), RAMP_HOURS['α'], f'α×{len(alphas)}'
    elif len(alphas) == 1:
        target, ramp, tag = ALPHA_P, RAMP_HOURS['α'], 'α×1'
    else:
        return BASE_P, '常规', '无品质技能'
    w = 1.0 if ramp <= 0 else min(1.0, hours / ramp)
    probs = tuple(max(0.0, b + w * (t - b)) for b, t in zip(BASE_P, target))
    s = sum(probs)
    probs = tuple(p / s for p in probs) if s else BASE_P
    return probs, tag, f'{tag}，慢热 {w*100:.0f}%（{ramp:g}h 满档）'


def profile(team, ds, hours=12.0, cap=None, level=3):
    """把一支贸易站队伍翻译成**订单的每单分解 + 每天/每小时的收益**。

    返回里现在显式拆开三个乘区（这是用户要求的口径）：
      · **订单速率**：`hours_per_order` 来自"品质分布 × 基础耗时"，受效率影响（eff 用 lmd_per_eff_hour 体现）
      · **每单币/赤金**：`lmd_per_order / gold_per_order`（含**违约索赔**改写、**龙舌兰·投资**加钱）
      · **订单上限**：`cap`（Lv3 基础 10 + 技能；孑的差额、银灰/拉普兰德/灵知都作用在这里）
    """
    probs, tag, ramp_note = probabilities(team, ds, hours)
    breach = None
    invest = 0.0
    for op in team:
        for s in ds.skills_of(op, '贸易站'):
            for name, extra in BREACH.items():
                if (s.name or '') == name and (extra > BREACH.get(breach or '', 0)):
                    breach = name
            for name, money in INVEST.items():
                if (s.name or '') == name:
                    invest = max(invest, money)
    extra = BREACH.get(breach, 0)
    rows = []
    for (gold, lmd, secs), p in zip(ORDERS, probs):
        g, l = gold, lmd
        if extra and gold < 4:                    # 但书·违约索赔：赤金交付 +N，龙门币同比例
            g = gold + extra
            l = lmd * g / gold
        if invest and gold > 3:                   # 龙舌兰·投资：该笔订单 >3 赤金 → 直接加钱
            l = l + invest
        rows.append((g, l, secs, p))
    gold_exp = sum(g * p for g, l, s, p in rows)
    lmd_exp = sum(l * p for g, l, s, p in rows)
    sec_exp = sum(s * p for g, l, s, p in rows)
    hours_exp = sec_exp / 3600.0
    cap = float(ORDER_CAP.get(int(level or 3), 10) if cap is None else cap)
    return dict(
        lmd_per_eff_hour=lmd_exp / hours_exp / 100.0,
        gold_cost_per_eff_hour=gold_exp / hours_exp / 100.0,
        gold_per_order=gold_exp, lmd_per_order=lmd_exp, hours_per_order=hours_exp,
        lmd_per_gold=(lmd_exp / gold_exp if gold_exp else 0.0),
        probs=probs, quality=tag, ramp=ramp_note, breach=breach, invest=(invest or 0.0),
        cap=cap, in_hand=IN_HAND, gap=(cap - IN_HAND),
        per_order=[dict(gold=g, lmd=l, secs=s, p=p) for g, l, s, p in rows],
        quality_skills=_quality_skills(team, ds))
