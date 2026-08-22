# Web 前后端 · 批次一 — 设计文档

日期：2026-08-22
状态：设计已确认，待编写实施计划
对应总设计文档：`2026-08-21-中小学排课系统-design.md` 第 10 节「界面」、第 13 节 M5

---

## 1. 目标与范围

给已经完成的 M1–M3 引擎（领域模型/Excel导入/规则解析/编译器/求解/校验器/预检/L2冲突集/多解生成/模板导出）套一层可在浏览器里操作的前后端，取代目前必须敲命令行的方式。

这是 M5（Web 界面）范围内的**第一批交付**，不是 M5 全部：

**这批要做的**

- 网页分别上传「任课表」（谁教哪个班）与「排课说明」（周课时/固定节次/禁排/要求等规则来源），两边按 `(班级,课程)` 合并，**合并时发现教师对不上要挡下来**，不能静默选一个
- 中文规则文本解析支持两种引擎：现有正则解析器（默认，0 误报）与新增的 AI 解析（可选），两者产出同一套结构化规则格式，回显确认这一步不因为换引擎而省略
- 网页上编辑课程计划（每门课周课时）与查看教务固定占位时段，写盘前跑 `cfg.validate_plan` 校验
- 网页上点一下触发排课（可指定生成几个候选方案），过程通过 WebSocket 推送
- 网页上查看课表（班级 × 时间格网格），多候选可切换
- 网页上直接导出 Excel（简单网格版 / 按教务模板版）

**这批不做，留到后面**

- 拖拽微调（M5 后续批次，需要后端局部重排接口）
- AI 审核课表合理性（M6——跟这批的「AI 解析规则文本」是两回事：这批 AI 只做「这句话是什么规则」的翻译，不判断课表本身合不合理）
- 初一、初二数据、三年级合排（M7）
- PyInstaller 打包为单 exe（M7）——这批仍是本地开发模式运行

**不影响的东西**：`scheduler/core/` 与 `scheduler/cli.py` 一行不改。API 是 `core/` 的新消费者，与 CLI 平级，互不干扰。

---

## 2. 运行方式

本地开发模式，不是打包产物：

```bash
# 后端：PyCharm 直接运行 scheduler/api/app.py，或
uvicorn scheduler.api.app:app --reload --port 8000

# 前端
cd scheduler/web && npm run dev    # Vite dev server，默认 :5173
```

前端通过 `fetch`/`WebSocket` 访问 `http://localhost:8000`，开发环境用 Vite 的 proxy 配置转发 `/api` 前缀，避免手写 CORS 白名单以外的麻烦（后端仍需开 CORS 允许 `localhost:5173`，供不走 proxy 的场景/未来联调用）。

AI 解析引擎需要环境变量 `ANTHROPIC_API_KEY`；本地开发模式下从进程环境读取，不做密钥管理界面（不是这批的范围）。

---

## 3. 整体架构与数据流

```
浏览器 (Vite dev server :5173)
   │ REST (fetch) + WebSocket
   ▼
FastAPI (uvicorn :8000)
   │ 调用 scheduler/core/*（importer / config / precheck / solver / verifier / exporter）
   │      scheduler/ai/*（rule_parser，仅在 rule_engine=ai 时调用）
   ▼
scheduler/config/*.yaml ←→ 磁盘
```

核心流程：

1. 用户在网页分别选择「任课表」和「排课说明」两份 Excel，选定规则解析引擎（正则/AI）→ 上传 → 后端解析两份文件并按 `(班级,课程)` 合并（**不写盘**）→ 返回预览
2. 前端展示预览：教师/班级/任务数概览 + 四段中文规则解析对照 + 警告 + **冲突列表**（若两份文件对同一 `(班级,课程)` 给出不同教师）
3. 若有冲突 → 「确认导入」按钮禁用，只能回去改源文件重新上传；若无冲突 → 用户点「确认导入」→ 后端把这次已经解析好的结果写盘（`teaching.yaml`/`rules.generated.yaml`）
4. 用户在设置页查看/编辑课程计划（每门课周课时），保存前端校验总课时不超可用格位
5. 用户点「开始排课」（可设定候选数量、最小差异度）→ 后端立即返回任务号，真正求解在后台线程跑
6. 前端用任务号开 WebSocket，依次收到：预检结果 →（若通过）逐个候选方案的求解+校验结果 → 完成
7. 前端收到候选就渲染网格，可切换 tab 查看不同方案，每个方案可点「导出 Excel」下载

---

## 4. 目录结构

```
scheduler/
  api/
    __init__.py
    app.py         # FastAPI 实例、CORS、路由挂载；uvicorn/PyCharm 的运行入口
    schemas.py     # 请求/响应的 pydantic 模型（API 专用，不与 core.models 混用）
    sessions.py    # 内存态：import token → MergedImportResult；job_id → 求解任务状态
    routes.py      # 全部 REST 端点
    ws.py          # WebSocket 端点 + 事件推送
  core/
    importer.py    # 新增：parse_teaching_table()（解析任课表 pivot 格式）
                    #      merge_teaching_and_rules()（两源合并 + 冲突检测）
                    # 现有 import_excel() 不动，CLI 仍用它（单文件路径）
  ai/
    __init__.py
    rule_parser.py # AI 规则解析：输入中文规则文本列，输出与 ruletext.py 相同形状的结构化片段
  web/                          # Vite + Vue3 项目
    src/
      main.ts
      App.vue                   # 顶层状态机（见第 8 节）
      api.ts                    # fetch 封装 + WebSocket 客户端
      components/
        ImportPanel.vue         # 双文件上传 + 引擎选择 + 回显 + 冲突提示 + 确认
        SettingsPanel.vue       # 课程计划编辑（周课时）
        SolvePanel.vue          # count / min_diff / max_seconds 参数 + 开始排课 + 进度文字
        ScheduleGrid.vue        # CSS Grid 渲染课表（班级 × 时间格）
        CandidateTabs.vue       # 候选方案切换 + 校验状态 + 导出按钮
      __tests__/                # Vitest 组件测试
    package.json
    vite.config.ts
    vitest.config.ts
    index.html
```

`sessions.py` 里的 `token`/`job_id` 全部是进程内存态，重启即失效——这是本地单用户工具，不需要持久化会话或数据库。

---

## 5. 双文件导入与合并校验

### 5.1 两份文件各自的角色

| 文件 | 提供什么 | 解析方式 |
|---|---|---|
| 任课表（`初三任课表.xlsx` 一类，班别 × 学科矩阵） | `(班级, 课程) → 教师` 的权威映射 | 新增 `parse_teaching_table()`：按表头取课程列，逐行取班级，构成 pivot 字典 |
| 排课说明（`任课与排课说明.xlsx` 一类，227 行任课记录） | 周课时（决定 `periods`）、固定节次、禁排节次、排课要求、备注——即规则来源 | 复用现有 `import_excel()` 内部的规则构建逻辑，但**教师字段不采信**，只取周课时与四列规则文本 |

### 5.2 合并逻辑

新增 `merge_teaching_and_rules(teaching_pivot, rules_rows, cfg, grade)`：

1. 以排课说明的行为基准，逐行按 `(班级,课程)` 去 `teaching_pivot` 查教师
2. 查到且一致 → 用任课表的教师名构建 `TeachingTask`
3. 查到但不一致 → 记入 `conflicts`（班级、课程、任课表给的教师、排课说明给的教师），**不生成该任务**
4. 任课表里有、排课说明里找不到对应行（周课时缺失）→ 同样记入 `conflicts`（缺周课时数据），因为不知道该排几节

`ImportResult` 模型加一个 `conflicts: List[Conflict]` 字段。`conflicts` 非空时，`/api/import/confirm` 直接拒绝（400），前端「确认导入」按钮本身也禁用——这不是警告，是硬性阻断，跟上次「历史课两表对不上」的真实教训对应。

### 5.3 CLI 不受影响

`cli.py` 的 `import`/`solve` 命令继续用现有单文件 `import_excel()`。双文件合并是 API 层的新能力，不回灌进 CLI（CLI 已经是能用的稳定路径，不需要跟着改）。

---

## 6. AI 规则解析引擎

### 6.1 设计边界

沿用 CLAUDE.md 铁律 5——「AI 不做算术，不做硬性判定」。AI 解析器的职责严格限定为「把一句中文规则文本翻译成结构化片段（`{type, params}`）」，边界与现有正则解析器完全一致：

- 输出格式必须是 `ruletext.py` 现有函数（`parse_time_expr`/`parse_fixed_slots`/`parse_requirement`/`parse_remark`）已经在产出的同一种数据结构
- 解析结果照样要走人工回显确认这一步，不因为换成 AI 就跳过
- 后续编译（规则 → CP-SAT 约束）和校验，两边都不感知规则是哪个引擎解析出来的——`Rule` 对象长什么样，两个引擎产出的必须完全一样

### 6.2 接口

`scheduler/ai/rule_parser.py`：

```python
def parse_time_expr_ai(text: str) -> set[tuple[int, int]]: ...
def parse_fixed_slots_ai(text: str) -> set[tuple[int, int]]: ...
def parse_requirement_ai(text: str) -> list[dict]: ...
def parse_remark_ai(text: str) -> list[dict]: ...
```

签名与 `ruletext.py` 对应函数一致，`importer.py`（供 API 层调用的合并路径）按 `rule_engine` 参数选择调用哪一组函数——两组函数是同一形状的可替换实现，不是分叉出两条不同的处理流程。

### 6.3 提示词与校验

一次 API 调用处理一整行的四列文本（而不是每个格子单独调用，227 行的量级下控制调用次数）。系统提示词里给出 `RULE_TYPES` 的完整清单与每种类型的参数 schema，要求模型只返回这个清单内的类型；返回的 JSON 用 pydantic 模型强校验，字段缺失/类型不对/`type` 不在 `RULE_TYPES` 里 → 直接判定这一行解析失败，不猜测、不用正则结果兜底替换。

### 6.4 错误处理

- 网络错误/超时/API 返回非 200 → 捕获后 `/api/import` 返回 `400 {"detail": "AI 解析失败：<原因>，可切换为正则引擎重试"}`
- 返回内容不满足 schema → 同上，视为失败而非部分采信
- 批次一不做重试/降级到正则自动切换——失败了让用户自己选，不悄悄换引擎，避免用户以为用的是 A 引擎实际上是 B

---

## 7. 设置页（课程计划编辑）

| 方法 | 路径 | 作用 |
|---|---|---|
| GET | `/api/config/plan?grade=初三` | 返回当前 `plans.yaml` 里该年级每门课的周课时 + `reserved_slots`（只读展示，教务固定占位不在这批开放编辑） |
| PUT | `/api/config/plan` | body `{grade, plan: {课程名: 周课时, ...}}`，写盘前跑 `cfg.validate_plan(grade)` |

`validate_plan` 已有的校验（未知课程名报错、总课时超出可用格位报错）直接复用，失败时 `400` 带具体差额，不静默写坏配置——跟 CLI `import` 阶段的既有校验是同一套逻辑，只是这批多了个网页表单入口。

`SettingsPanel.vue`：一张表格，课程名 + 周课时输入框，保存按钮置灰直到有改动，保存失败原样展示后端的错误信息。

---

## 8. REST API（完整列表）

| 方法 | 路径 | 请求 | 响应 | 作用 |
|---|---|---|---|---|
| POST | `/api/import` | multipart：`teaching_file` + `rules_file`；query `grade`、`rule_engine`（`regex`\|`ai`，默认 `regex`） | `ImportPreview` | 解析两份文件并合并（不写盘），返回预览 |
| POST | `/api/import/confirm` | `{token}` | `{ok, teaching_path, rules_path}` | 按 token 取回已解析结果写盘；`conflicts` 非空则 400 |
| GET | `/api/config/status` | — | `{ready, grade, classes, tasks}` | 当前 config 下是否已有可排数据 |
| GET / PUT | `/api/config/plan` | 见第 7 节 | 见第 7 节 | 课程计划编辑 |
| POST | `/api/solve` | `{grade, count, min_diff, max_seconds}` | `{job_id}` | 立即返回任务号，真正求解在后台线程跑 |
| GET | `/api/solve/{job_id}` | — | 任务当前状态 | 轮询兜底 |
| GET | `/api/export/{job_id}/{candidate_index}` | query `template`（可选）| Excel 文件流 | 复用 `exporter.export_excel`；`template=1` 时走 `export_to_template` |

**`ImportPreview`**：

```json
{
  "token": "…",
  "teachers": 121, "classes": 32, "tasks": 384,
  "occupancy": [37],
  "rule_engine": "regex",
  "rule_echo": {
    "不能排课节次": [{"raw": "…", "parsed": "周二 1,2,3,4,5"}, …],
    "固定节次": [...], "排课要求": [...], "备注": [...]
  },
  "warnings": [],
  "conflicts": [
    {"class_id": 5, "course": "历史", "from_teaching_table": "廖文峰", "from_rules_sheet": "陈俊彪"}
  ]
}
```

**错误响应**：Excel 学科不在课程目录、格式不对、AI 解析失败等 → `400 {"detail": "..."}`，前端 toast 显示。

---

## 9. WebSocket 协议

`WS /api/ws/solve/{job_id}`，事件按顺序推送：

```jsonc
{"type": "precheck_failed", "issues": [...]}                              // 结束
{"type": "solving"}
{"type": "candidate", "index": 1, "status": "OPTIMAL", "wall_time": 0.41,
 "violations": [], "placements": [{"class_id":1,"course":"语文","slot":0,...}, ...]}
{"type": "candidate", "index": 2, ...}
{"type": "infeasible", "conflict": "..."}                                 // 结束（预检过但无解）
{"type": "done", "count": 3}
```

**这不是空协议**：`solve_many` 本身就是「求一个候选、加差异约束、再求下一个」的节奏，每求出一个候选就够格推一帧——批次一用真实内容跑通这条通道。等 M4 做 Phase2 软约束优化（`SolutionCallback` 逐帧变好）时，往 `candidate` 事件加一个 `phase: "optimizing"` 字段即可复用，协议不用改。

**实现要点**：CP-SAT 求解是同步阻塞调用，不能直接放进 async handler（会卡住事件循环）。用线程池（`loop.run_in_executor`）跑 `solve_many`，每完成一个候选通过 `loop.call_soon_threadsafe` 把事件塞进 `asyncio.Queue`；WebSocket 协程从队列里读了就转发给客户端，直到收到 `infeasible`/`done` 哨兵。

**断线**：批次一不做自动重连。前端提示「连接断开，刷新页面或稍后用 `/api/solve/{job_id}` 查最终状态」。

---

## 10. 前端状态机

```
idle → 查 /api/config/status
  ├─ 无数据 → needs_import → 上传两份文件/选引擎/回显/（有冲突则中止，回去改源文件）/确认 → configuring
  └─ 有数据 → configuring
configuring → 设置页可选编辑课程计划 → ready
ready → 点「开始排课」→ solving（订阅 WS）→ viewing_results（候选 tab + 导出）
```

`ScheduleGrid.vue` 只负责渲染：45 格（5 天 × 9 节）× 班级数的 CSS Grid，props 传入某个候选的 `placements`；不做拖拽、不做本地合法性判定（那是下一批的事）。

---

## 11. 测试策略

**后端**：`pytest` + FastAPI 的 `TestClient`（REST）/ `websocket_connect`（WS）。用小合成数据集测端点行为（不跑初三全量，测试更快、更聚焦）。新增覆盖点：

- `merge_teaching_and_rules` 的一致/不一致/缺失三种分支（对应第 5.2 节三条规则）
- AI 解析器：mock `anthropic` 客户端返回合法/非法 JSON 两种情形，验证 schema 校验与错误透传，不真的打外部 API
- 设置页端点：合法保存、超出可用格位、未知课程名三种情形
- `core/` 现有 229 项测试不受影响，CLI 路径不变

**前端**：Vitest + `@vue/test-utils`。覆盖 `ScheduleGrid` 渲染出正确格数与班级列数、`ImportPanel` 正确展示回显/警告/冲突并在冲突时禁用确认按钮、`SettingsPanel` 的保存态与错误展示、`api.ts` 的请求封装（mock `fetch`/`WebSocket`）。不追求端到端浏览器测试（Playwright 之类），批次一手动过一遍关键路径即可。

---

## 12. 待确认事项

无——本轮 brainstorming（含加做的双文件导入/AI解析/设置页三块）已经把范围、运行方式、协议细节、导出/测试取舍都问清楚了。若实施过程中发现新的分叉点，回来更新本文档或在实施计划里单独记录。
