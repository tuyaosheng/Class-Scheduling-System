# Web 前后端 · 批次一 — 设计文档

日期：2026-08-22
状态：设计已确认，待编写实施计划
对应总设计文档：`2026-08-21-中小学排课系统-design.md` 第 10 节「界面」、第 13 节 M5

---

## 1. 目标与范围

给已经完成的 M1–M3 引擎（领域模型/Excel导入/规则解析/编译器/求解/校验器/预检/L2冲突集/多解生成/模板导出）套一层可在浏览器里操作的前后端，取代目前必须敲命令行的方式。

这是 M5（Web 界面）范围内的**第一批交付**，不是 M5 全部：

**这批要做的**

- 网页上传 Excel，回显中文规则解析结果供人工核对，确认后固化成配置
- 网页上点一下触发排课（可指定生成几个候选方案），过程通过 WebSocket 推送
- 网页上查看课表（班级 × 时间格网格），多候选可切换
- 网页上直接导出 Excel（简单网格版 / 按教务模板版）

**这批不做，留到后面**

- 拖拽微调（M5 后续批次，需要后端局部重排接口）
- AI 审核（M6）
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

---

## 3. 整体架构与数据流

```
浏览器 (Vite dev server :5173)
   │ REST (fetch) + WebSocket
   ▼
FastAPI (uvicorn :8000)
   │ 调用 scheduler/core/*（importer / config / precheck / solver / verifier / exporter）
   ▼
scheduler/config/*.yaml ←→ 磁盘
```

核心流程：

1. 用户在网页选择 Excel → 上传 → 后端调 `import_excel`（**不写盘**）→ 返回解析回显
2. 前端展示回显（教师/班级/任务数概览 + 四段中文规则解析对照 + 警告），人工核对
3. 用户点「确认导入」→ 后端把这次已经解析好的结果写盘（`teaching.yaml`/`rules.generated.yaml`）
4. 用户点「开始排课」（可设定候选数量、最小差异度）→ 后端立即返回任务号，真正求解在后台线程跑
5. 前端用任务号开 WebSocket，依次收到：预检结果 →（若通过）逐个候选方案的求解+校验结果 → 完成
6. 前端收到候选就渲染网格，可切换 tab 查看不同方案，每个方案可点「导出 Excel」下载

---

## 4. 目录结构

```
scheduler/
  api/
    __init__.py
    app.py         # FastAPI 实例、CORS、路由挂载；uvicorn/PyCharm 的运行入口
    schemas.py     # 请求/响应的 pydantic 模型（API 专用，不与 core.models 混用）
    sessions.py    # 内存态：import token → ImportResult；job_id → 求解任务状态
    routes.py      # 全部 REST 端点
    ws.py          # WebSocket 端点 + 事件推送
  web/                          # Vite + Vue3 项目
    src/
      main.ts
      App.vue                   # 顶层状态机（见第 7 节）
      api.ts                    # fetch 封装 + WebSocket 客户端
      components/
        ImportPanel.vue         # 上传 + 中文规则解析回显 + 确认
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

## 5. REST API

| 方法 | 路径 | 请求 | 响应 | 作用 |
|---|---|---|---|---|
| POST | `/api/import` | multipart 文件 + query `grade` | `ImportPreview` | 调 `import_excel`（不写盘），返回预览 |
| POST | `/api/import/confirm` | `{token}` | `{ok, teaching_path, rules_path}` | 按 token 取回之前解析好的结果，写盘 |
| GET | `/api/config/status` | — | `{ready, grade, classes, tasks}` | 当前 config 下是否已有可排数据，决定前端先显示导入面板还是排课面板 |
| POST | `/api/solve` | `{grade, count, min_diff, max_seconds}` | `{job_id}` | 立即返回任务号，真正求解在后台线程跑 |
| GET | `/api/solve/{job_id}` | — | 任务当前状态 | 轮询兜底：WebSocket 断了也能查到最终状态 |
| GET | `/api/export/{job_id}/{candidate_index}` | query `template`（可选）| Excel 文件流 | 复用 `exporter.export_excel`；带 `template=1` 时走 `export_to_template` |

**`ImportPreview`**（对应 CLI `render_import_report` 的结构化版本）：

```json
{
  "token": "…",
  "teachers": 121, "classes": 32, "tasks": 384,
  "occupancy": [37],
  "rule_echo": {
    "不能排课节次": [{"raw": "…", "parsed": "周二 1,2,3,4,5"}, …],
    "固定节次": [...], "排课要求": [...], "备注": [...]
  },
  "warnings": []
}
```

**错误响应**：Excel 学科不在课程目录、格式不对等 → `importer` 抛出的 `ValueError` 原样透传成 `400 {"detail": "..."}`，前端 toast 显示。

---

## 6. WebSocket 协议

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

## 7. 前端状态机

```
idle → 查 /api/config/status
  ├─ 无数据 → needs_import → 上传/回显/确认 → ready
  └─ 有数据 → ready
ready → 点「开始排课」→ solving（订阅 WS）→ viewing_results（候选 tab + 导出）
```

`ScheduleGrid.vue` 只负责渲染：45 格（5 天 × 9 节）× 班级数的 CSS Grid，props 传入某个候选的 `placements`；不做拖拽、不做本地合法性判定（那是下一批的事）。

---

## 8. 测试策略

**后端**：`pytest` + FastAPI 的 `TestClient`（REST）/ `websocket_connect`（WS）。用小合成数据集测端点行为（不跑初三全量，测试更快、更聚焦）；`core/` 现有 229 项测试不受影响，新增测试只覆盖 `api/` 里新写的路由/会话/事件序列逻辑。

**前端**：Vitest + `@vue/test-utils`。覆盖 `ScheduleGrid` 渲染出正确格数与班级列数、`ImportPanel` 正确展示回显与警告、`api.ts` 的请求封装（mock `fetch`/`WebSocket`）。不追求端到端浏览器测试（Playwright 之类），批次一手动过一遍关键路径即可。

---

## 9. 待确认事项

无——本轮 brainstorming 已经把范围、运行方式、协议细节、导出/测试取舍都问清楚了。若实施过程中发现新的分叉点，回来更新本文档或在实施计划里单独记录。
