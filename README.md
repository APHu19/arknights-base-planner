# 明日方舟 · 基建排班自主枚举器

> **本项目完全由 DSH（DeepSeek Harness）生成**：全部代码、数据抽取、规则表、求解器、GUI、自检与文档均由 DSH 自动编写与迭代。
> 未使用任何第三方框架（GUI 用 Python 自带 Tkinter）。

**给布局与诉求，自动枚举出六班排班表，并直接输出可导入 MAA 的 JSON。**

## 快速开始

```powershell
python planner\cli.py solve --main lmd --gold no_deficit --out planner\out   # 出表（333 龙门币）
python planner\gui\app.py                                                    # 图形界面
python planner\cli.py selftest                                              # 回归自检（25 条）
```
Windows 用户可直接双击根目录的 **`启动基建排班器.bat`**（图形界面）或 **`快速出表.bat`**（菜单式命令行）。

## 能力

| 维度 | 取值 |
| --- | --- |
| 主目标 `--main` | `yu` 合成玉 / `lmd` 龙门币 / `exp` 经验 / `drones` 无人机 / `clue` 会客室线索 / `balanced` 均衡 |
| 赤金收支 `--gold` | 不限 / 囤金 / **烧库存** / 平衡 / 不得净亏 / 不得净囤 |
| 碎片收支 `--shard` | 同上 + `ge_trade`（碎片产能 ≥ 玉站消化） |
| 心情底线 `--morale` | 不限 / ≥12 / ≥16 / ≥20 |
| 布局 `--layout` | 333 / 243 / 153 / 252（部分制造站降级）/ 333经验 |

配套：干员池三种录入方式（MAA 导入 / 粘贴 / 可视化点选）、逐格等级的九宫格与电力校验、
订单品质分布与违约、体系资源不动点、无人机按目标投放、制造站仓储爆仓检查、MAA 协议校验与报告。

## 文档

| 文件 | 内容 |
| --- | --- |
| [`planner/README.md`](planner/README.md) | 用法、结构、实测结果、关键事实 |
| [`planner/SKILL.md`](planner/SKILL.md) | **维护要点与坑位清单**（铁律、模块地图、已固化数值、心情模型、会客室、未完成清单） |
| [`HANDOFF.md`](HANDOFF.md) | **给下一个会话 AI 的交接单**（当前状态、下一块任务、验收方式） |
| `全机制.md` / `后勤技能一览带注释.md` | 规则与技能原文来源（数据抽取的输入） |

## 状态

引擎自检 **25/25**、GUI 四页签、MAA 协议校验通过、赤金约束成立（333 净产金 +5.32/天）。
**唯一未完成的大任务**：把"单日心情闭环"（次日 00:00 回满）做成**枚举期约束**的干员级窗口排班器——
检测器已实现（`planner/core/daycheck.py`），当前排班尚未通过该判据。详见 `HANDOFF.md §3`。

## 说明

- 游戏数据（`_raw/`）体积大且版权属鹰角网络，**未包含在仓库中**；再生成方式见 `HANDOFF.md §5`。
- `Arknights_OperBox_Export.json` 是**个人干员池**导出，仓库请保持 **Private**。
- 本项目是个人自动化工具，与鹰角网络、MAA 官方均无关联。
