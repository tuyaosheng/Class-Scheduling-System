# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目状态

中小学（初中）排课系统。**M1–M6 已完成**（领域模型/配置/Excel 导入/中文规则解析 → 规则 DSL/约束编译/求解/场地 → 校验器/预检/冲突集 → 软约束优化/多候选方案 → Web 界面全部视图与拖拽 → AI 审核），M7（三年级合排/打包 exe）未开始。2026-08-28 起在此基础上进行「多年级操作流程重构」（年级管理、按年级维护课程/规则、任课表与排课说明分工、界面导航重排、AI 供应商切换到 OpenAI 兼容协议），子项目 1-6（年级管理与作息表导入、课程/学科系按年级维护、单双周配对、任课表导入编辑、排课规则导入、拖拽调整按违规类型着色）已完成，其余 2 个子项目（跨年级统一校验与导出、AI 供应商抽象）待做，详见下方「实施计划」表与「多年级操作流程重构」一节。

实测：初三 32 班 OPTIMAL 0.41 秒，独立校验 0 处违规，预检 3 毫秒零假阳性。

完整设计见 `docs/superpowers/specs/2026-08-21-中小学排课系统-design.md`——动手前必读，本文件只记录其中最容易被违反的约束。

源数据是两份 Excel；`scheduler/` 下是已交付的 M1–M3 实现。

## 系统在做什么

读入**人工编好的**任课表（谁带哪个班）与规则配置，用 OR-Tools CP-SAT 求解每节课的时间位置，输出课表。

**不做任课分配**——谁带哪个班由教务人工决定，是输入不是输出。任何"顺便把任课也排了"的想法都超出范围。

交付形态：本地工具，PyInstaller 打包为单个 exe，内置 FastAPI 服务与 Vue 界面。不是 SaaS，没有账号体系。

## 源数据

| 文件 | 内容 |
|---|---|
| `任课与排课说明.xlsx` | 227 行任课记录。列：姓名/任教年级/学科/任教班/周课时/职务/固定节次/不能排课节次/排课要求/备注 |
| `初三任课安排.xls` | 教务的人工任课安排表，班级 × 学科矩阵，含班主任与备课组长 |

规模：初三 32 班、121 教师、17 门课（16 个学科系）。每班周课时 45（满格）：其中 37 节由系统求解，另 8 格（周一T9班会、周二T8/9体比、周三T8/9校本1、周四T8/9综实2、周五T9体选）教务已固定安排、系统不建模不校验（见「教务固定占位」一节）。三个年级最终统一求解。

## 六条容易踩的坑

### 1. 学科系（family），不是课程名

部分课程是主科的"影子课"，由**同一位教师带同一批班**，在课时分布统计上必须并入主科：

```
综实1 → 物理    校本1 → 英语    综实2 → 数学    体比/体选 → 体育
```

所有"每天至少1节""当天不超1节"类规则**按学科系统计**。

按课程名统计会直接导致无解：物理周课时 4 节却要求"保证每天有1节"（5天需5节），计入综实1 后 4+1=5 才成立。

### 2. 合班课不进求解器，别再建模成"豁免教师冲突"

体比、体选是合班课（一位教师同时面向多个班），但现在统一按「教务固定占位」处理（见坑 6）：`courses.yaml` 标 `external: true`，不生成任务、不进求解器，教师冲突问题自然不存在，不需要求解器/校验器层面单独豁免。

历史决定（2026-08-23）：早期实现过一套 session 模型——`compiler.py`/`verifier.py` 把同教师同一门合班课的多个班折叠成一节课，仍与该教师其他课互斥。这套代码在体比/体选转为占位符后完全没被用上，且已被判定为不必要的复杂度，**已连根拔除**（`Course.multi_class` 字段、`compiler.py` 的 `_split_sessions`/`_occ_var`/`_active_groups`、`verifier.py` 的 `_engagement`、相关测试全部删除）。

**以后再出现合班课，一律走占位符机制，不要重新实现 session 模型。** 如果真的出现一门"合班课需要求解器排时间、但教师不分身约束要豁免"的场景（而不是教务已固定安排），这是全新需求，需要重新设计，不是"把删掉的代码抄回来"。

### 3. 单双周按周次奇偶分别判定教师占用

美术（单周）与心理（双周）合并为"心美"1 课时，占用同一个时间格，但**是两位不同的教师，彼此不冲突**。

按"一个格子一位教师"简化建模会静默丢弃其中一位教师及其全部排课约束。可行性验证脚本就犯过这个错（121 位教师被去重成 119 位）。

**单双周不能整个年级统一同一个方向。** 若一位老师带的所有班全在单周（另一位老师全在双周），该老师就变成单周教 N 个班、双周教 0 个班，负荷忽高忽低。`importer.py` 按班号奇偶各半翻转：奇数班沿用课程目录声明的默认单双周，偶数班翻转，使每位美术/心理老师单周双周各教一半的班，每周课时数一致。编译器/校验器对单双周的判定本来就是逐班独立处理（`_compile_alternate_weeks` 按 class_id 分组配对），不依赖全年级统一同一方向，这处只是 `importer.py` 的分配策略调整，不涉及编译器/校验器改动。

### 4. 约束编译器与校验器必须独立实现

`core/compiler.py`（规则 → CP-SAT 约束）与 `core/verifier.py`（检查解是否合规）**不得共享任何约束逻辑代码**。

复用会让同一个 bug 同时骗过两边，"0 处违规"就失去意义。校验器要从配置重新读规则、独立判定。

### 5. AI 不做算术，不做硬性判定

"有没有撞课""课时数对不对""容量够不够"全部由确定性代码回答，结论**作为既定事实喂给 AI**。

AI 只负责两件事：发现规则未覆盖的隐性不合理；把求解器的冲突集翻译成教务听得懂的话。

### 6. 教务固定占位的课程要整体挖空，不要用 pin_window 硬凑

班会（周一T9）、体比（周二T8/9）、校本1（周三T8/9）、综实2（周四T8/9）、体选（周五T9）共 5 门课、8 格，教务已经自行排定，系统既不排课也不校验，任课信息由教务另外提供（见「任课表模板.xlsx」）。

**别把这类课程当成"有 pin_window 约束的普通任务"来建模。** 之前踩过一次：这 5 门课的周课时曾经比固定窗口短（比如窗口 2 格、周课时写成 1），求解器把任务在窗口内 2 选 1，看起来能求解——但这是假象，教师另一个班的课其实被悄悄挤到了窗口外的某处，跟这门课实际发生的时间对不上。等 Excel 订正为周课时=窗口长度（物理真实值）后，矛盾暴露：校本1、综实2 每一位任课教师都同时带 2 个班，窗口=课时=2 意味着两个班的任务被同时摁死在同一两格，等于该教师分身，直接 INFEASIBLE。

正确处理：这类课程在 `courses.yaml` 标 `external: true`（不生成任务、不生成 pin_window），它们的时段整体进 `plans.yaml` 的 `reserved_slots`（按年级配置的 `[day, period]` 列表），导入器据此自动生成一条年级级、无课程/教师限定的 `forbid_slots` 规则，把这些格位从求解域里整体排除，任何常规课都不能占用。导出 Excel 时这些格位标「（教务固定安排）」占位，不留白也不由系统填内容。

## 规则是数据，不是代码

教务改需求 = 改 YAML，不改代码。每条规则的结构：

```yaml
- type: daily_min                                    # 12 种类型之一
  scope: {grade: 初三, family: [语文, 数学, 英语, 物理]}  # 五维作用域，未指定即通配
  params: {n: 1}
  mode: hard                                          # soft 时额外带 enabled + weight
```

作用域五维：`grade` / `family` / `course` / `teacher` / `class`。同一类规则在不同年级可取不同参数，互不干扰。

新增规则类型时优先考虑能否用现有类型加参数表达；确需新增则同时更新编译器、校验器、预检三处。

## 无解诊断分三层

| 层 | 时机 | 性质 |
|---|---|---|
| L1 预检 | 求解前，总是运行 | 毫秒级、确定性，拦截绝大多数无解 |
| L2 最小冲突集 | 预检通过但无解 | CP-SAT assumption + `SufficientAssumptionsForInfeasibility()` |
| L3 AI | L1/L2 有输出时 | 翻译成人话 + 松绑建议 |

**L1 是重点投入对象。** 实测同一个无解场景，求解器跑 19 秒只吐 `INFEASIBLE`，预检瞬间指出"梁艳红需要48节，可用42格，缺6格"。绝大多数"排不出来"是容量或口径问题，不该劳烦求解器。

L2 只给可放松的规则挂 assumption。教师不分身、班级不重课这类不可放松的约束挂了也没意义。

## 性能基线

可行性验证的实测结果，实现后应大致对齐：

| 场景 | 规模 | 结果 |
|---|---|---|
| 初三 32 班 | 512 任务 / 23,040 变量 | OPTIMAL，0.6 秒 |
| 三年级 96 班 | 1,536 任务 / 69,120 变量 | OPTIMAL，1.9 秒 |

**若实现后明显慢于此，是建模有问题，不是 CP-SAT 不行。** 常见原因：变量粒度过细、用了不必要的整数变量、软约束直接进硬约束。

0.6 秒这个量级决定了产品形态——排课是交互级操作，支持"改一条规则立刻重排""拖动一节课后自动重算"。

上表是最初可行性验证脚本的快照，范围包含全部 17 门课。正式实现引入「教务固定占位」（坑 6）后，5 门课不再进求解器，初三当前实测规模是 384 任务 / 17,280 变量，OPTIMAL 0.41 秒——比表中数字更小，是范围收窄的预期结果，不是异常。

## 中文规则文本解析

Excel 后四列是自然语言，实测 22 种禁排写法。按「周X」正则切段解析，注意：

- `周二下午2、3、4节` → 第 7、8、9 节（下午第 N 节 = 第 5+N 节）
- `周五第4，5节` → 这里的逗号是**数字分隔符**，不是子句分隔符；按逗号切分会解析错

解析结果必须回显给用户确认，不能让歧义静默通过。

## 技术栈

已决定，无需重新讨论：

```
后端  Python 3.10 · FastAPI · uvicorn · OR-Tools CP-SAT · pydantic · openpyxl · PyYAML
AI    anthropic SDK
前端  Vue 3 + Vite · SortableJS · ECharts
打包  PyInstaller --onefile（前端 build 产物内嵌）
```

开发机需 Node.js；交付给教务的仅一个 exe。

## 构建与测试

```bash
pip install -r requirements.txt      # ortools 9.15.6755 / pydantic 2 / openpyxl / PyYAML / pytest

python -m pytest -q                  # 全套测试（当前 340 项，前端另有 80 项 `cd scheduler/web && npm run test`）

# 导入 Excel 并回显中文规则解析结果供教务逐条核对（不落盘）
python -m scheduler.cli import 任课与排课说明.xlsx --grade 初三
# 确认无误后固化成 config/teaching.yaml 与 config/rules.generated.yaml
python -m scheduler.cli import 任课与排课说明.xlsx --grade 初三 --write

# 排课：L1 预检 → 求解 → 独立校验 → 导出 Excel
python -m scheduler.cli solve --out output/初三课表.xlsx
```

`solve` 的退出码：`0` 成功、`1` 无解（已打印 L2 最小冲突集）、`2` 预检未通过（未进求解器）。

Windows 控制台默认 GBK，脚本入口已设 `sys.stdout.reconfigure(encoding='utf-8')`；自己写临时脚本时记得加 `PYTHONIOENCODING=utf-8`。

## 铁律 4 的能力边界

`compiler.py` 与 `verifier.py` 双实现能抓两侧**写法不同**导致的分歧，**抓不住共模建模错误**——两边代码不同却编码了同一个错误的物理模型时，「0 处违规」对它无效。

已发生过一次：合班豁免曾被两侧同时实现成「把合班任务从教师冲突推理里整体删掉」，导致一位教师可被排成同一格既上体育又上体比，编译器 OPTIMAL、校验器 0 违规。正确语义应该是「同教师同一门合班课的多个班折叠成**一节课**，这节课仍要与他的其他课互斥」（session 模型）——这套 session 模型代码后来已整体删除（见坑 2），这里的教训本身仍然成立：双实现测不出两边共同想错的建模错误。

**推论**：涉及物理语义的建模决策，不能只靠双实现互证，要单独回到设计文档核对原意。

## 实施路线

M1 领域模型/配置/Excel导入/规则解析 → M2 规则DSL/编译器/硬约束求解/场地 → M3 校验器/预检/冲突集 → M4 软约束优化 → M5 Web界面/拖拽 → M6 AI审核 → M7 三年级/打包

M1–M3 仅凭现有初三数据即可完成。

**M5/M6 不是空白路线图占位——设计文档里已经有相当具体的方案**（`docs/superpowers/specs/2026-08-21-中小学排课系统-design.md` 第 7.2/9/10 节：拖拽时前端本地算合法/冲突落点、松手后只重解受影响子问题；AI 审核的输入输出结构与职责边界），只是代码完全没写，动手前先读那几节，不用重新设计。M4 实际实现和第 7 节"两阶段 Phase1/Phase2"设计不一样（改成一次求解 + `solve_many` 生成多个带差异度的候选方案），该节已加"现状"标注说明。

### 课程配置扩展一批（2026-08-23 起，M4 之后、M5 之前插入的工作）

不在 M1-M7 的原路线图里，是这次会话新识别出来的一批需求（课程/课程系/课程计划的增删改查，年级日历按年级参数化，跨年级教师防冲突）。三份设计文档：

- `docs/superpowers/specs/2026-08-23-课程配置扩展与跨年级防冲突-design.md`——课程系管理(a)、课程计划增删(b)、年级日历数据模型(c)、空课表模板上传(d)、跨年级防冲突(e)、单双周配对课程改造(f)
- `docs/superpowers/specs/2026-08-23-年级日历参数化-design.md`——`calendar.py` 从全局常量改按年级参数化，是 c/e 能真正生效的地基

**实施计划**（`docs/superpowers/plans/`，随完成情况更新本清单）：

| 计划 | 对应设计项 | 状态 |
|---|---|---|
| `2026-08-23-年级日历参数化.md` | 年级日历参数化 design 全文 + a-f 的 c | **已完成**（`GradeCalendar` + `calendars.yaml`，9 个消费方文件全部迁移完，全套分支审查通过） |
| 课程目录增删改查 (a 的一部分) | 课程配置扩展 design §3.2 | **已完成**（`CourseSettings.vue` + `GET/PUT /api/config/courses`，课程名/学科系/场地/单双周/占位符的增删改） |
| 课程系下拉/重命名 (a 剩余部分) | 课程配置扩展 design §3.2 | 待写计划 |
| 课程计划增删 (b) | 课程配置扩展 design §3.3 | 待写计划——`SettingsPanel.vue` 目前只能编辑已有课程的周课时数字，没有新增/删除课程条目的入口 |
| 单双周配对课程改造 (f) | 课程配置扩展 design §3.7 | 待写计划 |
| 空课表模板上传解析 (d) | 课程配置扩展 design §3.5 | 待写计划 |
| 跨年级防冲突 (e) | 课程配置扩展 design §3.6/4 | 阻塞：「确认排定」交互细节未定 |
| `2026-08-24-求解会话持久化与历史列表-design.md` | 不在原路线图里，本次会话新提出 | **已完成**——`ImportSession`/`SolveJob` 从进程内存字典改成 SQLite（复用 `settings_store.py` 模式），重启不丢；历史列表可查看/选中/单条删除/按类型清空 |
| `2026-08-24-课表拖拽调整与实时冲突检测-design.md` | M5 design §7.2/10 里"最高价值"那部分（拖拽微调 + 实时反馈），范围小于完整 M5 | **已完成**——`ScheduleGrid.vue` 支持同班内拖拽（原生 HTML5 拖拽，非设计文档原定的 SortableJS），本地暂存多处改动，确认时一次性提交 `/adjust` 校验，只退肇事者（复用 `verify()` 当黑盒裁判，不新增独立冲突判断实现）。手动浏览器实测揪出一个单元测试没覆盖到的真实 bug 并已修复：周课时 > 1 的任务在 placements 里有多条记录共用同一 task_id，拖动其中一节曾经会把全部节次一起拖走——现在用 `(task_id, from_slot)` 复合 key 唯一定位 |
| M5 剩余视图（教师课表/场地占用/诊断面板/求解监控/规则配置编辑） | M5 design §10 | **已完成**（2026-08-28）——`CandidateTabs.vue` 加了视图切换（班级课表/教师课表/场地占用/求解监控）；`TeacherScheduleGrid.vue` 纯前端透视已有 placements（`teacher` 字段后端早就有），不需要新后端接口；`VenueOccupancyGrid.vue` 靠新增的 `GET /api/config/venues`（场地容量，之前没对外暴露）+ 已有的 `/api/config/courses`（课程→场地映射）算占用。诊断面板：`SolvePanel.vue` 原来把 L1 预检 issues 和 L2 冲突集文本直接扔了或塞进单行 badge，现在用新组件 `IssueList.vue` 展示完整列表，冲突集多行文本用 `<pre>` 正确换行；每个候选方案的 `verify()` 违规明细也用同一个 `IssueList.vue` 展示（之前只有一个"N 处违规"的计数徽章）。求解监控：`solve()`/`solve_many()`/`ws.py` 的 `_solve_streaming` 现在把 `solver.ObjectiveValue()`（仅当 `compiled.soft_terms` 非空时有意义，纯硬约束模型是 None）和 `solver.ResponseStats()` 一起塞进 `Solution`，`SolveMonitor.vue` 用原生 SVG/CSS 画候选间目标值对比柱状图 + 展示求解器日志原文——**没有引入 ECharts**（设计文档技术栈提到但项目里从没装过），几个候选、几根柱子用不上一个图表库，且这批候选是 `solve_many` 式的"彼此独立、互相有差异度"的解，不是同一个解随时间下降的曲线，柱状图比曲线更诚实。规则配置编辑：新增 `RulesSettings.vue` + `GET/PUT /api/config/rules`，**只读写 `rules.yaml`**（手写的政策级规则，如 M4 那条 `teacher_max_run` 软约束），不碰 `rules.generated.yaml`（导入器从 Excel 批量生成的 121 位教师 `forbid_slots`，走导入确认流程，不该在通用规则编辑器里被当成"一行"来操作）；规则参数（12 种类型形状差异很大）用 JSON 文本框直接编辑，没有为每种类型单独做表单——`rules.yaml` 只是偶尔改的政策级文件，不值得为此做 12 套表单 |
| M6 AI 审核 | 2026-08-21 design §9 | **已完成**（2026-08-28）——新增 `scheduler/ai/reviewer.py`，`review_schedule()` 把课表紧凑文本、生效规则（`describe()`）、独立校验器结论（`verify()` 的 violations，既定事实不重算）、以及三项确定性统计（同班同学科系单日≥2节热点、教师日课时跨度、连堂）一起喂给 prompt，AI 只返回结构化 findings（不做撞课/课时数/容量判定，铁律5）。`POST /api/solve/{job_id}/candidates/{index}/review` 按候选方案缓存结果在 `SolveJob.ai_findings`（SQLite 持久化），避免切换 tab 重复扣费；前端 `AiReviewPanel.vue` 挂在 `CandidateTabs.vue` 里，按钮触发、展示 severity/scope/issue/suggestion。测试沿用 `rule_parser.py` 已有的 FakeClient 注入模式，不打真实网络请求 |

注意 `scheduler/config/calendar.yaml`（单数）是项目最早骨架提交留下的旧文件，`compiler.py` 只在注释里提过一句，代码不读取它——跟年级日历参数化那次新建的 `calendars.yaml`（复数、按年级）是两个不相关的东西，不要混淆或复用。

年级日历参数化那次分支审查还留了三处已知、暂不影响初三的遗留缺口（`scheduler/ai/rule_parser.py` 的 AI 规则解析提示词硬编码 9 节/天；`solver.py` 的 `Placement.day`/`.period` 属性是死代码，同样硬编码；`ScheduleGrid.vue` 曾经硬编码 `PERIODS_PER_DAY=9`，这次拖拽功能顺手把它改成了可选 `days`/`periodsPerDay` props，但调用方还没接入真实日历数据）——这三处只有在真正给七/八年级排课时才会暴露，届时需要专门处理。

### 多年级操作流程重构（2026-08-28 起）

不在 M1-M7 的原路线图里，是这次会话跟用户从头捋了一遍"教务实际应该怎么操作"之后新提出的一批需求，比上面"课程配置扩展一批"更大——把配置的引导流程、界面导航结构、AI 接入方式都重新定过。用户原话里的操作顺序、以及讨论中拍板的几个关键决策：

**关键决策**（改动到相关部分时按这几条来，不用重新问用户）：
- **多年级求解**：各年级独立求解（现有单年级引擎不用改），**导出前**必须跑一次跨年级统一校验，校验不通过不能导出。这一层不是复用 `verify()`——不同年级作息形状不同（见下），"是否撞车"要按**真实钟点区间**判断，不能比较"第几节"。
- **拖拽调整的可视化反馈**：讨论中一度定过"拖起时前端实时算合法/冲突落点"（绿/红预览），后来用户明确改主意——**不做前端实时判断**，沿用现有"确认后交后端 `adjust.py` 算、只退肇事者"机制（已实现），只需要新增"回退提示按违规类型着色"（尚未做）。不要重新捡起前端实时预览这个方向。
- **AI 供应商**：两者并存，**OpenAI 兼容协议为主**（用户自填 base_url + api_key + 模型名），Anthropic 保留为可选项。`ai/rule_parser.py`、`ai/reviewer.py` 两处调用都要走同一层抽象（尚未做）。
- **年级/班级**：年级名称完全自定义，数量不限（不是只支持初一/初二/初三这个固定集合）。
- **课程/学科系**：要按年级分别维护，不是像现在这样全局一份 `courses.yaml`（尚未做——这是子项目 2，改动会牵涉 `compiler.py`/`verifier.py`/`precheck.py`/`exporter.py`/`importer.py`/`routes.py` 全部读 `cfg.courses` 的地方）。
- **任课表 vs 排课说明.xlsx 的分工**：任课表（矩阵）是"谁教谁"的唯一来源；排课说明.xlsx 降级为纯规则文本表（不能排课节次/固定节次/排课要求/备注），按教师姓名匹配，不再提供班级/课程/周课时——那些改由"课程与学科系"步骤里的课程计划提供。现有 `merge_teaching_and_rules` 的"两份 Excel 冲突检测"机制在新流程里会消失（尚未做——子项目 4/5）。
- **规则页面要重做**：现有 `RulesSettings.vue` 直接把 `scheduler/core/rules.py` 的英文 DSL 类型名（`forbid_slots`/`daily_min`……）暴露给用户，教务看不懂，且在新流程里没有清晰的落脚点。计划是把它整体砍掉，能自动生成的规则继续自动生成，少数政策性数值（比如教师半天连堂上限）做成具体场景里的白话输入项。**在此之前它作为「临时视图」保留在第 6 步**，`App.vue` 里有一条 alert 明确标注是临时的。

**新导航结构**：`App.vue` 从原来的四个平铺标签页（课程/规则/排课/设置）重写成左侧栏 9 步流程导航（`AppSidebar.vue`），跟用户描述的操作顺序一一对应：年级与班级 → 作息时间 → 课程与学科系 → 单双周设置 → 任课表 → 排课规则 → 排课与调整 → AI 审核 → 导出课表。年级切换器放在侧边栏顶部（多数步骤按年级分别配置）。视觉方向经用户看过静态 mockup 确认（配色沿用现有 `tokens.css` 的学科系色板和主题色，没有另起炉灶）。还没重做的步骤（4/6/8/9）用 `ComingSoonPanel.vue` 占位或挂载现成组件过渡，不是空白。

**实施计划**（按步骤对应的子项目，随完成情况更新本清单）：

| 子项目 | 内容 | 状态 |
|---|---|---|
| 1. 年级管理 + 作息表批量导入 | 新增 `grades.yaml`（年级名任意、数量不限）；新增 `scheduler/core/calendar_import.py` 解析「作息表模板.xlsx」——一个 sheet 一个年级，从"第N节/时间段"推出 `periods_per_day`/`clock_times`，午休边界用相邻节次起始时间**最大间隔**自动推断；sheet 名不要求跟年级名一致，导入页面手动选映射关系 | **已完成**（2026-08-28）——`GET/PUT /api/config/grades`、`POST /api/config/calendars/parse`（无状态解析，不落盘）、`GET/PUT /api/config/calendars/{grade}`；前端 `GradesSettings.vue`（年级卡片，删除需二次确认）+ `CalendarSettings.vue`（上传→按 sheet 预览→选年级→写入）。解析算法用真实的「作息表模板.xlsx」验证过：七年级 8 节/午休第 4 节后、八/九年级 9 节/午休第 5 节后，跟此前"年级日历参数化"那次手写进 `calendars.yaml` 的七年级/八年级数据完全吻合（那次是手抄的，这次证明批量导入算法算出来的是同一个结果）。已在真实浏览器里跑通"新增年级→上传作息表→选映射→写入→回到年级页看到状态变绿"全流程，多进程/多标签也验证过不会互相踩踏 |
| 2. 课程/学科系按年级维护 + 场地容量 | `courses.yaml` 从全局改按年级分组 | **已完成**（2026-08-28）——`SchedulerConfig.courses` 从 `Dict[str, Course]` 改成 `Dict[str, Dict[str, Course]]`（年级→课程名→Course），新增 `courses_of(grade)` 访问器；`family_of`/`courses_in_family`/`resolve_plan_key` 都加了 `grade` 参数。改动面覆盖 `compiler.py`（`_limit_venue`）、`verifier.py`（`_venue_load`/`_venue_overflow`/`_check_venues` 全部加 `grade` 参数）、`precheck.py`（`_venue_demand`）、`exporter.py`（`_cell_text`）、`importer.py`（`import_excel`/`_build_rules`/`parse_teaching_table`/`merge_teaching_and_rules`，都已有 `grade` 参数，直接换成 `cfg.courses_of(grade)`）、`rules.py`（`_task_dim` 用 `task.grade`）、`ai/reviewer.py`（用 `dataset.grade`）。API 端点 `GET/PUT /api/config/courses` 加了 `grade` 参数（GET 用 query string，未配置的年级返回空列表而不是 404，因为"年级刚建好还没配课程"是正常状态）；新增 `PUT /api/config/venues`（场地容量编辑，拒绝删除仍被课程引用的场地）。前端 `CourseSettings.vue` 加 `grade` prop 并按 grade 变化重新加载，新增"场地容量"区块（场地是物理房间，所有年级共用一份，不按年级分）；`VenueOccupancyGrid.vue`/`CandidateTabs.vue` 一路加 `grade` prop 往下传，因为场地占用视图需要按当前年级取课程→场地映射。**踩了一个真实 bug**：Vue 3 的 `v-model` 绑定 `<input type="number">` 会自动把值转成 number 而不是 string，`saveVenues()` 原来直接调 `r.capacity.trim()` 在真实浏览器里会报 `capacity.trim is not a function`——用 `String(r.capacity).trim()` 统一转再判断。**另踩了一个持久化兼容性 bug**：`SolveJob.cfg` 存在 SQLite 里的历史记录是旧的扁平 `courses` 结构，这次结构调整后 `sessions._data_to_job` 反序列化旧记录会直接 pydantic ValidationError → 500（历史求解任务全部读不出来），加了 `_migrate_flat_courses` 按 job 自己的 grade 包一层来兼容，验证过旧数据能正常读出。已用真实浏览器走通"课程与学科系页面加载/编辑/保存 → 排课与调整页面加载历史任务 → 场地占用视图"全流程 |
| 3. 单双周配对课程可视化配置 | 选哪两门课合并、默认交替规则 | **已完成**（2026-08-28）——用户明确过"具体哪两门课合并由用户在系统里操作决定，之前举的美术/心理例子只是举例，方向不重要"，所以设计上没有做"默认交替方向"的配置项，交替方向（哪个班号奇偶对应哪个方向）继续用 `importer.py` 现有逻辑（按班号奇偶翻转），不暴露给用户。新增 `GET/PUT /api/config/alternate-pairs`：**读**——分别扫 `rules.yaml`（手写，可编辑）和 `rules.generated.yaml`（排课说明导入自动生成，只读展示）里的 `alternate_weeks` 规则，按课程目录里两门课各自的 `alternate` 字段判断谁单周谁双周；**写**——只替换 `rules.yaml` 里这个年级的 `alternate_weeks` 规则，同步把配对的两门课的 `family`/`alternate` 字段写回 `courses.yaml`，`rules.generated.yaml` 不受影响。校验：单双周课程不能是同一门、必须在该年级课程目录里、同一门课不能同时出现在多个配对里。前端新增 `AlternatePairsSettings.vue`，挂在第 4 步，导入生成的配对以只读徽章展示，手写的配对可增删。已用真实浏览器确认：当前初三真实数据的"心美：单周美术/双周心理"（来自 Excel 导入）正确以只读方式展示，下拉框正确列出真实课程目录 |
| 4. 任课表导入 + 可视化编辑 + 重新上传 | 任课表成为"谁教谁"唯一来源，脱离排课说明.xlsx | **已完成**（2026-08-28）——新增 `importer.build_dataset_from_pivot(pivot, cfg, grade, existing_teachers=None)`/`import_teaching_table(path, cfg, grade, existing_teachers=None)`：pivot（班级,课程)->教师）直接构建 Dataset，周课时不再来自 Excel 每行数字或 0.5 课时探测，改由「课程与学科系」步骤的课程计划（`_resolve_course_periods` 把学科系键如"心美"展开成课程名->课时）统一提供；这条路径本身不产生规则（`ImportResult.rules` 恒为 `[]`），任课信息成为唯一来源，排课说明.xlsx 降级为规则文本表是子项目 5 的事。API 新增 `GET /api/config/teaching-table`、`POST /api/config/teaching-table/parse`（无状态预览，不落盘）、`PUT /api/config/teaching-table`（整份提交覆盖式写 `teaching.yaml`，不碰 `rules.generated.yaml`）。前端新增 `TeachingTableSettings.vue`：班级×课程矩阵（班号列固定，横向纵向都可滚动），单元格直接改教师名，"重新上传"整份覆盖预览、"保存"整份提交，挂在第 5 步。**浏览器实测揪出一个真实的数据丢失 bug 并已修复**：`build_dataset_from_pivot` 最初对每个教师名一律 `Teacher(name=name)` 新建空白对象，这条路径本身不产生 `duties`/`forbidden`（那是排课说明.xlsx 的职责），结果编辑任课表任意一个格子并保存，就会把全部教师之前从排课说明.xlsx 导入算出来的班主任职务、禁排节次**整体清空**——用真实 `teaching.yaml`（121 位教师）实测过一次，`git diff --stat` 显示 1786 行插入/3125 行删除而不是预期的单格微调，证实是真实数据损坏，已用 `git checkout` 复原。修复：两个函数加 `existing_teachers: Dict[str, Teacher]` 参数，构建 `teachers` 字典时同名教师直接复用传入的对象（保留 `duties`/`forbidden`），只有真正的新教师才建空白记录；`routes.py` 新增 `_load_existing_teachers(grade)` 读当前 `teaching.yaml`（年级不匹配或文件不存在则返回空字典）在两个写路径调用前先取一次并传入。测试：`test_import_teaching_table.py` 两个新用例（已有教师的 duties/forbidden 原样保留、真正新教师建空白记录）、`test_api_teaching_table.py` 一个新用例（对真实 32 班配置里的李琼——真实数据里她是班主任且有禁排节次——只改别的格子并保存，验证她的 duties/forbidden 原样保留）。浏览器复测：编辑另一位教师（郑艳秀）的格子并保存，文件级校验李琼的 duties/forbidden 确实原样保留，测试完立刻用会话开始前的备份复原了真实 `teaching.yaml`（`git diff --stat` 确认零差异） |
| 5. 年级级排课规则导入 | 排课说明.xlsx 降级为纯规则文本表；正则解析 + AI 复核（两者都跑，不是二选一引擎） | **已完成**（2026-08-28）——跟用户确认过一个关键设计点：新表仍保留「学科」列（去掉的只有任教班/周课时），因为「固定节次」的语义是绑定课程（比如体育要排在指定节次），不是绑定教师，去掉学科列会让这个语义没地方挂。新表列：姓名/任教年级/学科/职务/固定节次/不能排课节次/排课要求/备注，按"姓名+学科"匹配，不再跟任课表做 (班级,课程) 交叉冲突检测——"谁教谁"已经完全由任课表决定，用户明确要求"两个都跑"而不是二选一：`importer.import_rule_text_table(path, cfg, grade, ai_client=None)` 对每一行的四个文本字段永远先跑正则（`ruletext.py`，真正生效的规则来源，符合铁律5），`ai_client` 给定时额外跑 `ai/rule_parser.parse_row_ai` 做复核，结果只用来对比——一致就不打扰用户，不一致就在 `rule_echo` 里标 `mismatch: true` 和 `ai_parsed` 字段，供人工核对；AI 调用失败（未配置/网络错误）只记一条 warning，不影响正则结果，因为 AI 复核本来就是尽力而为。新增 `write_rules_generated_yaml_for_grade`（按年级整体替换 rules.generated.yaml 里的规则，其他年级原样保留）和 `merge_teacher_facts_into_teaching_yaml`（按教师姓名合并职务/禁排进 teaching.yaml，没提到的教师原样保留，复用子项目4那次"存量教师信息不能被覆盖"的教训）。API：`GET /api/config/rules-sheet/template`（下载填写模板，见下）、`POST /api/config/rules-sheet/parse`（无状态预览）、`PUT /api/config/rules-sheet`（确认写盘）。前端新增 `RulesSheetSettings.vue` 挂在第6步最上方，`RulesSettings`（政策性规则）和 `ImportPanel`（两份 Excel 一次性导入）降级为"补充/过渡视图"标注保留在下方。**用户额外提出的要求**："要告诉我这里面的格式应该怎么填写，最好要有模板下载（每一种情况应该怎么写）"——`importer.build_rules_sheet_template()` 生成两个 sheet 的模板：「排课说明」sheet 用真实语料库（`test_ruletext_forbid.py` 里实测的22种不能排课节次写法、`test_ruletext_misc.py` 里的固定节次/排课要求/备注写法）造了12行示例（姓名前缀"示例-"，明确标注导入前需删除替换成真实数据）；「填写说明」sheet 用大段文字逐列讲解语法规则（"周X"锚点、数字间逗号不是分句符、上午/下午第N节的偏移换算、排课要求目前支持的4种固定写法、备注支持的2种写法）。浏览器实测确认过一次真实数据风险并已安全处理：用合成的单教师测试文件点"确认导入"后，`rules.generated.yaml` 的初三规则从132条被整体替换成了2条（`write_rules_generated_yaml_for_grade` 是"按年级整体替换"语义，这是设计如此，不是 bug——用完整数据导入才是正常使用方式），测试完立即用会话开始前的备份复原，`git diff --stat` 确认零差异。测试：`test_import_rule_text_table.py`（12项，含正则规则生成、AI一致/不一致/失败三种场景、按年级替换、教师信息合并保留）、`test_api_rules_sheet.py`（6项，含模板下载、预览不落盘、确认写入、教师信息保留、年级前置校验、课程校验），前端 `RulesSheetSettings.spec.ts`（4项） |
| 6. 求解 + 拖拽调整增强 | 现有机制基本够用，加按违规类型着色 | **已完成**（2026-08-28）——`verifier.py` 的 `Violation` 本来就有 `kind` 字段（教师分身/班级重课/场地超容/违反禁排/越出窗口/每日下限不足/每日上限超出/指定星期节数不符/缺少连堂/单双周未共格/教师半天连堂过长/课时数不符/规则未被校验，共12种），但 `adjust.py` 的 `_violation_details` 之前只取 `.detail`、把 `.kind` 丢了。改成传 `(kind, detail)` 对，`RevertedMove`/`RevertedMoveItem` 新增 `kinds: List[str]` 字段（一次撤销可能同时解决多种违规，所以是列表不是单值）。前端 `ScheduleGrid.vue` 按严重程度把12种 kind 归成4组着色（结构性冲突红/禁排类橙/分布类黄/数据类灰），而不是每种 kind 一个颜色——12种独立色块反而不利于辨认，4组更贴近"这个问题有多严重"的直觉。回退提示每条消息前面加彩色徽章（`kind-badge`），复用现有学科色板的 CSS 写法（`family-N` 那套），但用独立的语义色而非学科色，避免同一页面里颜色语义混淆。测试：`test_adjust.py` 补充3处断言验证 `kinds` 在单条撤销/多条撤销/整体回退三种场景下都正确传递；`ScheduleGrid.spec.ts` 验证徽章渲染文本和 CSS 类。浏览器实测时发现加载真实32班×3候选的完整课表视图会让渲染卡死（现有 `displayedPlacements()`/`cellPlacements()` 对每个格子都整体重新过滤一遍全部 placements，本次改动没有碰这条热路径，是已有性能特征不是新引入的问题）——没有强行反复重试，改用已经通过的单元测试和组件测试作为验证依据 |
| 7. 跨年级统一校验 + 全部导出 | 导出前按真实钟点比对教师跨年级冲突；"导出全部课表" | 待做 |
| 8. AI 供应商抽象 | OpenAI 兼容为主 + Anthropic 并存 | 待做 |

## 待确认事项

动到相关部分时需先向用户确认，不要自行假定：

- 操场同时可容纳班数（配置暂留空 = 不限制）。**现状已不影响求解**：体比、体选已改为教务固定占位（坑 6），不进求解器，操场容量在系统求解范围内目前只有普通体育课一门，谈不上并发。场地占用现在按**任务**（即按班）累加计数——合班课的 session 折叠机制已删除（见坑 2），`rules.py` 里 `venue_capacity` 的「个班」描述文案现在是准确的，不用改。若未来真的出现需要求解器排时间的合班课，场地/教师口径要重新设计，不是恢复旧的 session 计法。
- 初一、初二课程计划（配置结构已预留，内容待补）
- 化学/生物是否有独立实验课（现有数据中无）
- ~~周二 T8「教工会」与「体比」的时段冲突~~：已通过坑 6 的「教务固定占位」机制解决——周二 T8/T9 整体在 `reserved_slots` 里挖空，不进求解器，这两者的冲突由教务自行处理，系统不建模。

## M7 前置重构（三年级合排前必须做）

以下三处在单年级下不可见，三年级合排时会静默出错：

- `TeachingTask.class_id` 是裸整数，初一 1 班与初三 1 班会被当成同一个班建互斥约束
- `importer` 的 task id 每次从 0 开始，合并多个年级数据集会静默覆盖 `compiler.x` 的键

现在改动成本比 M7 时小得多，M7 时是全量重测。

注意：这里说的"合排"特指**把多个年级塞进同一个 CP-SAT 模型统一求解**——「多年级操作流程重构」子项目 7 的"跨年级统一校验"不是这个，是各年级分别独立求解完之后，导出前额外跑一次教师时间冲突检查（按真实钟点比对，见上一节），不共享 `class_id`/`compiler.x` 键空间，不受这里两条缺口影响。真要做"多年级合并进一个模型求解"才需要先做这里的重构。
