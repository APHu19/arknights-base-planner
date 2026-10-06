# HANDOFF —— 给下一个会话的 AI（先读这份，再读 SKILL.md）

> 本项目**完全由 DSH（DeepSeek Harness）生成**。前一个会话的上下文已用尽，本文件是你的交接单。

## 1. 三十秒了解项目

给《明日方舟》基建排班的自主枚举器：**输入布局与诉求 → 自动枚举六班排班 → 输出可导入 MAA 的 JSON**。
代码在 `planner/`，入口是 `planner/cli.py` 与 `planner/gui/app.py`，根目录两个 `.bat` 负责一键启动。

## 2. 当前状态（务必如实沿用，不要吹）

| 项 | 状态 |
| --- | --- |
| 引擎 / 规则 / 数据抽取 | ✅ 自检 `python planner\cli.py selftest` **25/25** |
| GUI 四页签 | ✅ `python planner\gui\app.py --selftest` 通过 |
| MAA 输出协议校验 | ✅ `emit.maa.validate` 通过（导出的 json 可直接被 MAA 读） |
| 一键启动 | ✅ `启动基建排班器.bat`（GUI）、`快速出表.bat`（菜单式 CLI） |
| 会客室线索模型 | ✅ 已实现（126% 基础含满氛围 + 星级/精英化/未红脸 + 后勤技能，加算） |
| 无人机分配 | ✅ 按"每架目标口径收益"投放；**不做余量封顶**，净消耗由模拟如实显示 |
| 制造站仓储/爆仓 | ✅ 已实现；**所有制造站检测，仅班次 ≥6h 执行**；`--storage warn/clip/off` |
| **单日心情闭环** | ✅ **判据已由用户裁定为 A（长期稳态）**：`core/daycheck.py` 默认 `criterion='steady'`（迭代到不动点、不被打穿、最低 ≥1），**字面口径降级为诊断列**照实打印（它在正常规模下结构性不可达：贴 00:00 在岗必回不满 + 末段 20 床 vs 最后一班 32 人 = −4.50/人）。默认路径实测：`判据A(长期稳态) ✔ 稳态最低心情 12.00`，KPI 无变化。详见 `planner/SKILL.md §10` |
| **干员级窗口排班** | ✅ **已接线**：`--sched window`（默认 `ab` 完全不变）。`solve/schedule.py`（判定核+组合层）+ `plan.build_window_shifts` + `solver.run(sched=)` + `cli --sched`。333/@4h 实测：判据 A ✔、排班无缺口、MAA 协议通过、龙门币 41,539（ab 38,756）、赤金净 +1.25、玉 660。**限制**：只支持 4h×6 班（`emit/maa.py` 写死 6 班标签）。**遗留**：窗口路径连续上班→订单品质满档→产量高于 ab，赤金预算闸门仍是按 ab 算的（可能被推到约束边缘，solver 会打 ⚠）→ 下一步"贸易站节流/按窗口产量重算预算"。见 `planner/SKILL.md §10.1`、`probe_win.py` |

## 3. 唯一未完成的大任务：window 调度器

**目标**：排班长期可持续——任意干员两次上班之间的休息足以撑过下一次工作窗口。**验收判据 = A（长期稳态，
已由用户裁定）**：把当天时间线**迭代到不动点**，要求稳态那天①任何工作窗口不被打穿 ②全天最低心情 ≥ 1.0。
`core/daycheck.py` 默认就是这个口径；字面口径（次日 00:00 回满）**只作诊断**，实测在本规模下结构性不可达。

**关键算术（已算清，别再算错）**：每班在岗 **32** 人（252 布局 13 间房）→ 每日岗位工时 768 干员·小时；
寝室床位 4×5=**20** ⇒ 每班不在岗 ≤20 ⇒ 唯一干员 **N ≤ 20+32 = 52**（扣掉常驻宿舍 4 人后 **48** 人排班）；
48 人 × 2 班 = 96 岗位 = 3 班 × 32 ✔（实测就是"每人 2 段 6h/18h + 6~12h 休息"的结构）。

**已证伪的两条路（不要重走）**：
1. 把同站 A/B 合并成常驻来压人数 → 该站 24h 常驻 → 无休息窗口 → 判据 A 也会 ✘（实测 8/72 人最低 0.00）
2. 用"设施级轮换组数 G(1/2/3/6)"套模板 → **用户明确否决**：应按**实际时间区间**排（例：6,6,12 三班就是三个真实区间）

**要做的**（详见 `SKILL.md §9/§10`）：
```
按真实区间 W=[(t0,t1)…] 逐个 (房间,区间) 需求排人；
每个候选都要做增量可行性判定（心情检查内嵌在枚举里，不是事后检查）：
   ① 每个区间不在岗 ≤20（N ≤ 20 + 该区间计划在岗人数）
   ② 把他放进本区间后重算当天工作/休息窗口 → 任一工作窗口不被消耗光
   ③ 稳态不动点：最低心情 ≥ 1.0（判据 A）
   不满足 → 该候选判死，换人；全部排完 → daycheck 终检；失败则记录原因（床位 or 恢复）后重新分组枚举
不允许常驻（无休息窗口的安排直接排除）
```
**落点**：`solve/schedule.py` **已就位并接线**（`--sched window`；默认 `ab` 不变，见 `SKILL.md §10.1`）。
**自定义班次表已可用**：`--shifts "22:00,10:00,16:00"`（开始时间定义、闭环、可不等长；GUI ③ 页签可点"新建第 N 班"），
MAA 输出带 `period/duration`、`planTimes='n班'`，见 `SKILL.md §10.2` 与 `probe_shift.py`。
**剩下的活**：① 12h 长班的稳态余量很薄（最低心情 1.5 vs 下限 1）→ 可调 `STEADY_FLOOR` 或限制最长班；
② 赤金反馈只在无人机旋钮范围内（±36 赤金/天）有效，超出仍会告警。

**禁动范围**：`core/rules.py`、`core/engine.py`、`core/orders.py`、`emit/maa.py` 的现有行为不要改；
只允许**新增**文件与**在开关后**改 `plan.py`/`solver.py`。
（`core/daycheck.py` 已按用户裁定改成判据 A，属已授权改动。）

**验收方式（每个小块都要贴真实输出）**：
```powershell
python planner\cli.py selftest                                        # 必须 25/25
python planner\probe_sched.py                                         # 场景 B 必须「判据A(长期稳态) ✔」
python planner\cli.py solve --main lmd --sched window --fast --rounds 1 --width 6 --topk 3
# 期望：心情闭环检测 = 判据A(长期稳态) ✔ ；若失败，把原因（床位不足 / 恢复不足 / 常驻）报给用户，不许放宽判据
```

## 4. 怎么跑（三条命令就够）

```powershell
cd C:\Users\APHu\dsh生成333基建表
python planner\cli.py solve --main lmd --gold no_deficit --out planner\out   # 出表
python planner\gui\app.py                                                    # 图形界面
python planner\cli.py selftest                                               # 回归自检
```
四维目标：`--main {yu,lmd,exp,drones,clue,balanced}` × `--gold {none,produce,consume,balance,no_deficit,no_surplus}`
× `--shard {同上+ge_trade}` × `--morale {none,12,16,20}`。

## 5. 数据来源与再生成（`_raw/` 未进仓库）

| 文件 | 作用 | 来源 |
| --- | --- | --- |
| `planner/data/skills_raw.json` | 后勤技能库（561 条） | 由 `后勤技能一览带注释.md` 抽取（该 md 已在仓库） |
| `planner/data/phases.json` | 干员×房间×精英化阶段→技能（429/429） | 由 `_raw/building_data.json` 抽取 → `data/extract_phases.py` |
| `planner/data/base_terms.json` | 权威术语/分类/特殊叠加规则 | 用户提供 |
| `Arknights_OperBox_Export.json` | 干员池（GUI 默认读它） | 游戏导出/MAA 导出 |

`_raw/building_data.json`、`_raw/character_table.json` 体积大（≈20MB）且属游戏方数据，**被 .gitignore 排除**；
需要重新抽取阶段表时把它们放回 `_raw/` 再跑 `python planner\data\extract_phases.py`。

## 6. 绝对不要做的事（前一个会话踩过）

1. 不要凭记忆改数值；改了必须说明"哪条规则变了、哪条自检预期值随之变"（例：效率 +1%/人 使 175%→178%）
2. 不要动默认路径（`--sched ab`、`--max-roster 0`、`--storage warn`）；新功能一律放开关后面
3. 不要用 `python -c "…"` 内联验证（本机引号必炸）→ 写 `probe_*.py`
4. `.bat` 内容只能 ASCII（UTF-8 中文会被 cmd 按 GBK 解析成命令）
5. **上下文将尽时不要开始大改造**；宁可交接，不要半截截断
6. 不要放宽验收判据来"让它通过"——做不到就如实报失败原因
7. 写入只能落在项目目录内；不要 pip 安装（GUI 用 Tkinter 就是为此）
