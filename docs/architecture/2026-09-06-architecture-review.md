# 架构复核与优化建议

> 后续优先级调整：本文缺陷证据保留，但用户已选择企业内部 MVP、样片质量优先，完整治理不再作为近期阻断。实际实施顺序见[内部 MVP 计划](../plans/2026-09-06-internal-mvp-reset.md)。

- 状态：待确认
- 日期：2026-09-06
- 代码基线：`89d1ca54973ddbf1f17b614298f52cd1086bfa0f`，分支 `ai-video-motorcycle-platform`
- 触发：用户要求在编码助手更换模型后，重新检查架构是否需要优化。
- 范围：代码、既有研究、架构契约、自动测试及历史真实调用记录；本轮没有调用真实 Provider，没有修改应用代码、凭据或路由。

## 1. 结论

保留 Next.js + FastAPI + SQLAlchemy + 自有 ModelGateway + FFmpeg，沿既有“模块化单体控制面 + 独立任务 Worker”方向补齐实现，不整体重写，不因编码助手变强就引入微服务或多 Agent 框架。

当前已经有真实 GPT 创意建议和分镜调用，但还不是可靠的真实视频生产平台。缺口不仅是视频 Key，还包括确认约束、契约一致性、持久任务、真实能力检测、素材执行和质量验收。

编码助手模型与平台 Admin 配置的模型是两回事。更换前者不会自动改变后者的模型、上下文、图片/视频能力、工具权限或价格。平台运行模型升级必须经过能力探测、固定样例评估、预算比较和路由发布。本轮不推断中转站支持尚未验证的接口。

## 2. 主要发现

严重性定义：P1 为影响真实流程正确性、费用或对外开放的高优先级问题；P2 为扩展、交付和维护问题。以下源代码位置均针对上述基线。

### F1 / P1：两次确认没有成为服务端不变量

- [creator.py](../../services/api/src/vediogen_api/creator.py) 第 302 行开始的分镜接口只检查 Brief ID 存在，不检查 `approved`。
- 第 333 行开始的修改接口允许原地修改已确认分镜；第 354 行开始的生成接口只检查分镜状态。
- 第 290、343 行开始的确认接口返回临时 Approval ID，没有持久化对应确认记录及内容哈希。版本号使用计数加一，文档表没有对应组合唯一约束。
- **隔离复现**：草稿 Brief 请求分镜返回 202；确认分镜后提交 `shots=[]`、`totalDurationMs=-1` 返回 200，状态仍为 `approved`。
- 影响：用户没有确认的内容也可能进入付费执行；旧页面提交和并发修改无法可靠识别。
- 建议：不可变版本、持久 Approval、内容哈希和输入版本引用；修改生成新草稿，旧确认仅对应旧版本；当前版本切换使用数据库条件更新。已排队 Run 继续使用冻结快照，不被后来编辑静默改写。

### F2 / P1：202 响应背后仍是同步长请求，不能恢复执行

- [creator.py](../../services/api/src/vediogen_api/creator.py) 第 242 行先调用模型，完成后才创建 AdvisorRun；分镜同样在请求内完成，并只返回临时 Run ID。
- [gateway.py](../../services/api/src/vediogen_api/gateway.py) 第 122 行添加调用记录，但网络请求前没有提交。进程崩溃时可能供应商已计费，本地却没有可恢复记录。
- SSE 第 227 行仅发送项目 ID 和心跳，没有持久进度和断线重放。前端防重不能代替服务端幂等。
- 历史真实请求耗时约 47.2 秒、34.5 秒，出现过后端完成而页面未顺利取得结果的现象。此前关于 build/dev 产物冲突的解释不足以排除代理超时、长请求和重复提交，不作为已定位的唯一根因。
- 建议：事务写入 InputSnapshot + Run + Outbox 后立即返回 202；Worker 执行、轮询和记录 Attempt；前端按 Run ID 恢复。外部提交不保证天然 exactly-once，必须处理“供应商已接收但本地未记下”的未知状态，不能盲目重发。

### F3 / P1：管理后台的配置和验证结果不完全真实

- [gateway.py](../../services/api/src/vediogen_api/gateway.py) 第 99 行的路由执行器只遍历主备部署，没有执行配置中的 `fallbackOn`、`maxAttempts`、路由总超时及预算规则；能力要求只在发布检查中做声明集合比较。
- [admin.py](../../services/api/src/vediogen_api/admin.py) 的 `create_playground_run` 忽略所选草稿和 Fixture 的实际内容，调用最小探针后把所有请求检查项写为 `passed`，耗时固定为 28ms。
- **隔离复现**：不存在的 Draft ID、Fixture ID 和检查名也返回 202，检查结果为 `passed`。
- Deployment Probe 只验证模型列表和最小 JSON 返回，却把全部声明能力对应的部署标成 ready；没有逐项实测图片、工具或视频能力。[openai_compatible.py](../../services/api/src/vediogen_api/openai_compatible.py) 的探针也未对返回对象做本地 Schema 与期望值断言。
- 建议：分开记录 `declared / verified / unavailable / failed`；ProbeResult 持久化具体输入、检查器版本、Request ID 和结果；发布规则依赖实测能力。路由策略只由一个执行层负责，避免适配器与任务系统叠加重试。

### F4 / P1：Fake 与真实生产没有强制隔离

- [main.py](../../services/api/src/vediogen_api/main.py) 启动时自动种入 Fake Provider；没有环境级禁止 Fake 的开关。
- [creator.py](../../services/api/src/vediogen_api/creator.py) 第 195 行仅根据当前全局 creative-advisor 主路由是不是 Fake 判断预览可执行，不检查每个镜头的能力和来源。切换创意路由就可能改变已有真实项目的执行门。
- 生成流程为所有镜头直接写成功，再输出固定 FFmpeg 预览；[test_creator_flow.py](../../services/api/tests/test_creator_flow.py) 甚至同时断言 Storyboard 为 12 秒、输出为 6 秒，没有要求两者一致。
- 建议：Fake 仅允许显式 test/demo 环境，生产路由和生产 Run 禁止 Fake。逐镜头执行前计算 CapabilityPlan；用户视频拼接、真实图片动画、视频生成、Blender 独立判断，不把“缺视频模型”当作所有媒体策略都不可用。

### F5 / P1：对外开放前缺少管理权限与错误脱敏

- [main.py](../../services/api/src/vediogen_api/main.py) 和 Creator/Admin 路由未建立身份验证、管理员授权、项目归属检查；AccountBrief 使用全局 default。CORS 不构成访问控制。
- [openai_compatible.py](../../services/api/src/vediogen_api/openai_compatible.py) 的 `_raise_for_status` 直接拼接供应商错误文字；网关还可能把它存入所谓脱敏摘要。
- **隔离复现**：使用非真实凭据标记模拟上游回显 Authorization，异常字符串保留该标记。未读取或发送真实 Key。
- 修改 Provider URL、Credential 与 Deployment 的关联缺少统一验证；有必要限制服务器出站目标，避免配置或模型工具被滥用。
- 建议：公开访问前具备登录、Creator/Admin 权限和资源归属；API 只返回标准错误码与安全摘要，敏感字段按结构清洗，必要时丢弃上游自由文本。本文不新增用户已排除的法务审批功能。

### F6 / P1：结构化与事实准确度仍有明显断层

- [fixtures.py](../../services/api/src/vediogen_api/fixtures.py) 的 `build_project_facts` 仍靠字符串分支生成车型事实并标成 confirmed；它不是模型抽取或用户确认。没有春风匹配时会使用整个项目标题作为车型名。
- Brief 当前是从方案确定性编译，而不是独立 LLM 调用。这种实现可以保留，但必须记录来源、保留用户约束并通过中央契约，不能宣称整个阶段都已真实模型化。
- [gateway.py](../../services/api/src/vediogen_api/gateway.py) 第 179 行给各方案补相同的第一条事实依据，`blockingQuestion` 永远为 null；第 210 行将分镜拍扁，丢失 `subject/action/scene`，并把中央契约的 `frameRate` 变为 `fps`。目前没有对转换后的 Brief/Storyboard 做完整中央 Schema 校验。
- AccountBrief 未进入创意调用上下文；[model_contracts.py](../../services/api/src/vediogen_api/model_contracts.py) 固定摩托车提示词，ContentPack ID 尚不等于领域扩展已经实现。
- 图片输入最多取前四个素材，不支持的文件被静默略过；上传成功不等于视频已经抽帧或照片已被模型看见。
- 建议：FactSet 区分用户陈述、素材观察、外部证据和已确认事实；Constraints 单独保存“最后镜头高速驾驶”等硬条件。模型 JSON 必须经过结构、引用、时长、顺序和策略可执行性校验，不能以 Prompt 强调代替服务端检查。

### F7 / P2：持久化、测试隔离和文档存在漂移

- 上传 Intent、Playground Run 在进程内字典中；Intent 在校验完成前就被移除，重启/多 Worker 和失败重试不可靠。Messages、Assets、ShotRuns 的 JSON 数组读改写存在并发覆盖风险。
- [database.py](../../services/api/src/vediogen_api/database.py) 依赖启动建表和临时加列，没有版本化迁移；新增约束前需要 Alembic 与既有数据迁移验证。
- [playwright.config.ts](../../apps/web/playwright.config.ts) 非 CI 会复用 3000/8000 服务。如果复用了真实环境，E2E 的隔离数据库变量不会作用于它，测试可能修改真实路由或触发付费调用。
- API 重试测试依赖前一测试创建的数据；上传样例是伪造 JPEG 字节，不能证明媒体内容验证或视觉理解。
- 当前费用用零占位，未知不能解释成免费。文档对 LiteLLM、LangGraph、Gate 1 和 Fake 隔离的部分表述领先于实现。

## 3. 建议目标结构

```text
Creator / Admin Web
    -> Control API: ownership, versions, approvals, runs, configuration
    -> PostgreSQL: snapshots, outbox, attempts, approvals, events, costs
    -> Durable workers
         Advisor: intake -> facts/clarifications -> evidence -> proposals
         Script: approved Brief -> Storyboard -> semantic validation
         Media: approved Storyboard -> CapabilityPlan -> ShotManifest
                -> user-media / image-motion / video / Blender adapters
                -> artifacts -> FFmpeg -> QC -> delivery
    -> Object storage: immutable assets and outputs, scoped access URLs
```

### 模型与确定性程序各自负责什么

模型负责理解需求、提出澄清问题、比较创意方向、建议搜索、生成脚本和复核画面。系统负责权限、事实状态、预算、版本、Schema、任务提交、重试、执行与保存。

工具采用类型化输入和白名单：搜索只产生带来源的 Evidence；图片/视频分析记录具体 Asset ID；生成工具只能消费已确认快照，不能由聊天模型绕过确认直接付费执行。给每轮咨询设置调用次数、Token/费用和检索范围上限。

支持工具调用、流式或更强推理的部署可以作为能力升级，但必须实测中转站兼容性；暂时不支持工具协议时，由服务端分阶段调用适配器。模型不能通过文字声称已搜索、已渲染或已验证来改变任务状态。

### 内容包扩展

核心只理解 Facts、Constraints、Proposal、Brief、Storyboard、Shot 和 Run。ContentPackVersion 提供输入 Schema、创意方法、Prompt、素材策略、领域术语与评分器。先用摩托车和一个育儿演示包证明切换领域不改核心流程；不能将育儿质量检查等同于车型视觉一致性。

### 前端不推翻，改为运行状态驱动

保留 Creator/Admin 分离和两次确认。Creator 明确展示素材处理状态、建议依据、硬约束、当前确认版本、每镜头能力缺口、恢复/取消/局部重试和实际产物。先通过轮询可靠恢复，随后按需要接持久事件 SSE。

Admin 分开呈现模型目录、声明能力、实测能力、发布版本、尝试链与费用状态。未测项目显示未验证，不显示通过；费用区分估算、实际、未知。无需先增加节点编辑器或重做一套视觉系统。

## 4. 成熟组件复用决策

依据既有[市场研究](../research/2026-09-05-market-and-reuse-study.md)和[依赖评估](../research/2026-09-05-dependency-evaluation.md)，本轮没有重新抓取 GitHub Star、定价或最新版本；历史关注度不作为已安装或适用性证据。

| 部分 | 本轮建议 | 参考与边界 |
| --- | --- | --- |
| Web/API/合成 | 保留已有正式包 | Next.js、FastAPI、SQLAlchemy、FFmpeg；复用现有界面和领域契约 |
| 多平台 LLM | 保留自有网关和当前 Adapter | 第二种确有协议差异的 Provider 接入时评估 [LiteLLM](https://github.com/BerriAI/litellm)；不同时建设两个独立路由真相源 |
| 长任务 | 先验证 [Celery](https://docs.celeryq.dev/en/stable/) + PostgreSQL Outbox | Python 团队的候选最小路径；须验证重投、去重、取消、崩溃恢复和可用的 Linux/容器运行环境，不能假设原生 Windows 支持满足要求 |
| 长任务备选 | [Temporal](https://docs.temporal.io/) 聚焦 POC | 若轻量队列需要大量补偿代码或长期人工等待编排，再采用 Temporal；同一媒体流程不叠加两套编排引擎 |
| 创意 Agent | 暂不强制引入 [LangGraph](https://github.com/langchain-ai/langgraph) | 多轮工具分支确实复杂时再用；它不代替媒体 Worker 和业务 Approval |
| 数据迁移 | 引入 [Alembic](https://alembic.sqlalchemy.org/en/latest/) | 已有 SQLAlchemy 的常见迁移方案，先备份与验证旧库升级 |
| 质量评估与观测 | 固定样例和 Trace 先行 | Langfuse 为后续候选；不能代替业务账本或人工样片验收 |
| 成片/3D | FFmpeg + 可选 Blender Worker | Blender 只消费固定入口和 Manifest；没有资产时不宣称真实 360 度保真 |

不整体 Fork 通用 Agent 平台。既有开源研究中 NarratoAI 的 Provider/Prompt 分层和 Short Video Maker 的 Scene 合成可作局部借鉴；是否采用代码需针对锁定版本实测，不因为项目关注度高就复制其全部架构。

## 5. 本轮验证与限制

- 执行 `uv run --project services/api pytest services/api/tests -q`：7 passed，2 条依赖弃用警告。
- 额外使用临时目录 SQLite、临时 Secret Store 和 TestClient；禁止 HTTPTransport 外部请求，仅使用 Fake Provider。结束后释放数据库并删除临时目录。
- 检查步骤：创建项目与 Advisor；不确认 Brief 即创建分镜；确认后提交空镜头和负时长；调用不存在草稿/样例/检查项的 Playground；用合成敏感标记构造上游错误。结果见 F1、F3、F5。
- 这些诊断证明当前缺陷，不是新验收通过。永久回归测试应先断言正确行为并观察失败，再随修复变绿。
- 未运行浏览器 E2E、未验证 PostgreSQL 并发、进程崩溃恢复、真实视频或 Blender 输出。避免复用当前端口污染真实环境。
- 历史真实 GPT 样例使用仓库内参考 JPEG，不能当作用户真实车型身份、照片保真或影视级质量已验收的证据。

## 6. 待确认与下一步

建议按[整改执行计划](../plans/2026-09-06-architecture-hardening.md)推进：先补流程正确性与测试隔离，再实现持久任务，随后打通真实单镜头和多镜头。没有视频 Key 不妨碍前两阶段开发。

真实媒体 POC 前仍需确定视频 Provider、运行/存储环境、单条样片费用上限和等待上限、360 度保真等级与可用资产。免费产品同样需要内部费用控制；任何“未知价格”调用都不能自动视为零成本。
