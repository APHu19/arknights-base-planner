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
| **单日心情闭环** | ⚠ **检测器已实现**（`core/daycheck.py`，判据=次日 00:00 回满），**当前排班不满足**（实测 −6.4） |
| **干员级窗口排班** | ❌ **未实现 —— 这就是下一块任务** |

## 3. 唯一未完成的大任务：window 调度器

**目标**：排班长期可持续——任意干员两次上班之间的休息足以撑过下一次工作窗口；**验收判据只有一个**：
从 00:00 满心情起算，走完当天班次表，**次日 00:00 必须回满**（`core/daycheck.py` 就是验收器）。

**关键算术（已算清，别再算错）**：每班在岗 ≈30 人 → 每日岗位工时 720 干员·小时；
寝室床位 4×5=**20** ⇒ 每班不在岗 ≤20 ⇒ 唯一干员 **N ≤ 50**；N=50 时每人 **14.4h/天 + 休 9.6h**
（消耗 14.4×0.9≈13 ＜ 恢复 9.6×4.2≈40 ✔ 可行）。**紧约束但可行。**

**已证伪的两条路（不要重走）**：
1. 把同站 A/B 合并成常驻来压人数 → 该站 24h 常驻 → 无休息窗口 → 闭环从 −6.4 恶化到 **−12.6**（`--max-roster` 因此默认 0）
2. 用"设施级轮换组数 G(1/2/3/6)"套模板 → **用户明确否决**：应按**实际时间区间**排（例：6,6,12 三班就是三个真实区间）

**要做的**（详见 `SKILL.md §9`）：
```
按真实区间 W=[(t0,t1)…] 逐个 (房间,区间) 需求排人；
每个候选都要做增量可行性判定（心情检查内嵌在枚举里，不是事后检查）：
   ① 本区间不在岗 ≤20 且此人能拿到床位
   ② 把他放进本区间后重算当天工作/休息窗口 → 任一工作窗口不被消耗光
   ③ 次日 00:00 能回满
   不满足 → 该候选判死，换人；全部排完 → daycheck 终检；失败则记录原因（床位 or 恢复）后重新分组枚举
不允许常驻（无休息窗口的安排直接排除）
```
**落点**：新增 `solve/schedule.py`，替换 `plan.py` 的 `build_shifts/solve_dorms`；
开关 `--sched ab|window`，**默认 ab 保持现状**。

**禁动范围**：`core/rules.py`、`core/engine.py`、`core/orders.py`、`emit/maa.py` 的现有行为不要改；
只允许**新增**文件与**在开关后**改 `plan.py`/`solver.py`。

**验收方式（每个小块都要贴真实输出）**：
```powershell
python planner\cli.py selftest                                        # 必须 25/25
python planner\cli.py solve --main lmd --sched window --fast --rounds 1 --width 6 --topk 3
# 期望：心情闭环检测 = 单日闭环 ✔ ；若失败，把失败原因（床位不足 / 恢复不足）报给用户，不许放宽判据
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
