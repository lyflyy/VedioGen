# P0 垂直切片执行计划

- 状态：部分实现；本地 Fake Provider 垂直切片已通过，完整计划仍待继续执行
- 版本：0.1
- 日期：2026-09-05
- 负责人：待指定
- 前置条件：PRD、体验规格和本计划通过评审

> 2026-09-05 实施说明：当前完成范围和测试证据见 [P0 本地垂直切片开发结果](../discussions/2026-09-05-p0-development-result.md)。真实 Provider、育儿内容包、Blender 探针和异步 Worker 尚未完成，因此本计划不标记为整体完成。

## 1. P0 要回答的问题

P0 不是缩小版完整平台，而是一条可测量的端到端链路，用来回答：

1. AI 创意顾问是否能比直接生成脚本提供更可用的方向。
2. Project Facts、Evidence、Proposal、Brief 和 Storyboard 能否稳定分层并版本化。
3. 两次确认是否在控制生成成本的同时保持日更效率。
4. 混合媒体路由能否生成一条合格的竖屏样片，并支持单镜头重试。
5. 平台核心是否能在不修改业务状态机的情况下替换内容包。

## 2. 范围

### 包含

- 本机单用户项目，不做登录。
- 自然语言输入和图片/视频上传。
- 一个 Account Brief。
- 搜索/网页读取 Provider 接口和至少一个可用实现。
- AI Advisor 多轮对话、2 至 3 个 Proposal、合并和 Brief 确认。
- 脚本/Storyboard 生成、局部修改和确认。
- 4 至 6 个 Shot 的状态与版本。
- 至少一种真实 AI 视频 Provider，加上图片运动/用户素材降级路径。
- FFmpeg 合成、媒体检查、下载和内部资源账本。
- 内部模型管理后台：Provider、API Key、Deployment、能力路由、测试、发布/回滚和调用记录。
- Creator/Admin 两套独立应用壳、统一设计 Token、组件状态目录和关键页面响应式实现。
- 张雪 800X、春风 800MT 两个摩托车验收项目。
- 一个只跑到 Brief 的育儿内容包契约验证。

### 不包含

- 注册登录、多人协作、计费、订阅、自动发布和移动端完整编辑。
- 任意车型自动生成影视级 3D 资产。
- 多供应商智能价格路由。
- Blender 从零资产制作全流程；Blender 作为独立探针，不阻塞第一条 AI 视频链路。
- 播放量预测或平台算法保证。

## 3. 建议技术基线

| 层 | P0 选择 | 选择理由 |
| --- | --- | --- |
| Web | Next.js + React + TypeScript + Vercel AI SDK | 创作者工作台与独立 `/admin` 管理路由；成熟的流式对话和结构化工具状态 |
| UI 基础 | Radix Primitives + shadcn/ui + Lucide + Storybook | 可访问交互原语、项目自有视觉语言、统一图标和组件状态评审 |
| API | FastAPI + Pydantic | 与 AI/媒体 Python 生态一致，Schema 清晰 |
| Advisor 编排 | LangGraph | 适合检索、结构化步骤、Checkpoint 和 Human-in-the-loop；只负责创意层 |
| 模型网关 | 项目 `ModelGateway` + LiteLLM SDK | 业务使用能力别名，底层复用多 Provider、重试和 Fallback 适配 |
| 业务数据 | PostgreSQL | 保存项目事实、版本、确认和运行状态 |
| 对象文件 | 本机 S3 兼容存储或文件适配器 | P0 可本地运行，但接口与后续对象存储一致 |
| 后台任务 | 轻量 Worker + PostgreSQL 状态机 | P0 先验证镜头级任务；满足恢复需求后再决定 Temporal/BullMQ |
| 合成 | FFmpeg 8.1.1 | 当前环境已安装，适合确定性探测和合成 |
| 3D | Blender 稳定版独立探针 | 当前环境未安装；不阻塞 Advisor 和首条成片链路 |
| 观测 | 结构化日志 + 可选 Langfuse | 先保存核心追溯数据，再评估额外平台 |

供应商均通过接口接入：`LlmProvider`、`SearchProvider`、`PageReader`、`ImageProvider`、`VideoProvider`、`TtsProvider` 和 `MediaComposer`。首个具体供应商在凭证与部署条件确认后写入实施记录，不写死在领域模型。

## 4. 开源复用任务

开始编码前为每个候选建立 `dependency-evaluation.md` 记录，至少包含版本、许可证、采用方式和退出方案。

### 直接采用

- Vercel AI SDK：对话流和结构化 UI 消息。
- LangGraph：Advisor Graph，不负责媒体长任务。
- LiteLLM SDK：统一 LLM Provider 协议；平台仍保留自己的路由和调用契约。
- FastAPI/Pydantic：API 与数据校验。
- FFmpeg：探测、缩放、拼接、音频、字幕和编码。
- Radix/shadcn：唯一 UI Primitive/组件代码基础；不混装第二套整包视觉组件。
- Storybook：领域组件状态目录；Playwright + axe：关键路径、截图和可访问性测试。

### 代码级评估

- NarratoAI：检查 Provider Registry、Prompt Registry、字幕/FFmpeg Service 和测试，确定可参考或可复用文件。
- Short Video Maker：以其 Scene 和 Remotion 合成作为对照探针，不直接替换 Shot Manifest。
- Crawl4AI：验证中文网页抽取、动态页失败率和超时。

### 明确不整体 Fork

- Dify、n8n、Flowise、MoneyPrinterTurbo 和 ComfyUI 前端。

原因与许可证边界见[市场与开源复用研究](../research/2026-09-05-market-and-reuse-study.md)。

## 5. 工作包与顺序

### WP0：开发门与环境探针，0.5 至 1 天

- 评审三份核心文档并记录修改。
- 评审 UI 架构、设计系统、页面清单、验收规格和四个关键线框。
- 确认输出规格、保真标准、运行位置和首批 Provider。
- 验证 API 凭证、FFmpeg；安装并固定 Blender 版本只作为并行任务。
- 建立依赖评估和环境变量清单。

**完成条件**：Gate P0 全部满足，四个关键线框和 Token 方向通过，至少一个 LLM 和一个视频 Provider 在开发环境可调用。

### WP1：领域契约与持久化，1 至 2 天

- 按已评审的领域模型实现 Project、AccountBrief、ProjectFact、Evidence、StrategyProposal、CreativeBriefVersion、StoryboardVersion、Shot、Run 和 Artifact。
- 按状态机实现 Brief 与 Storyboard 的版本失效规则。
- 从已评审 JSON Schema 生成/校验类型，建立数据库迁移和固定样例 Fixture。
- 为 Project Fact 优先级和版本关系编写单元测试。

**完成条件**：两个摩托车 Fixture 可通过 Schema；确认事实不能被 Evidence 更新覆盖。

### WP1A：UI 基础与应用壳，1 至 2 天

- 建立 Creator/Admin route groups、导航壳、错误边界和权限守卫接口。
- 落地颜色、字体、间距、圆角、状态与媒体舞台 Token。
- 接入 Radix/shadcn、Lucide 和 Storybook，完成 Button、Form、Status、Drawer、Table 基础变体。
- 从 OpenAPI 生成前端类型，建立 Fake API/SSE 与固定 Fixture。

**完成条件**：Projects、Strategy、Storyboard、Admin Routing 四页骨架在固定视口无重叠；基础组件状态通过 axe 和键盘检查。

### WP2：Creative Advisor 垂直切片，2 至 3 天

- 建立 Intake、Search、Diagnose、Propose、Revise/Merge、Brief Compile Graph。
- 接入流式对话和结构化 Proposal UI。
- 实现搜索失败降级、来源查看和一个阻塞问题规则。
- 实现 Brief 确认与修订。
- 按 UI Spec 实现 Conversation/Proposal/Facts 三列、响应式 Drawer 和版本冲突恢复。

**完成条件**：两个摩托车样例均能产生不同方向并完成合并；一个育儿样例替换 Playbook 后不出现车辆字段。

### WP2A：模型网关与管理后台，2 至 3 天

- 实现 ModelGateway、能力别名、Deployment、Credential Reference 和 RoutingPolicyVersion。
- 实现模型平台、API Key、模型部署、能力路由、测试台和调用记录页面。
- 使用独立 Admin Shell、数据表格、详情 Drawer、Draft Diff 和固定底部发布栏。
- 实现 Key 写入/测试/轮换、日志脱敏、Draft/Publish/回滚。
- 用一个真实 Provider 跑通，并准备第二 Provider 或 Fake Provider 的 Fallback 契约测试。

**完成条件**：管理员无需修改文件或重启服务即可从界面切换 `creative-advisor` 路由；Key 不在响应、数据库明文或日志中出现。

### WP3：脚本与 Storyboard，1 至 2 天

- 从 Brief 生成脚本和原子 Shot。
- 实现时间线编辑、排序、单 Shot 重写和确认。
- 实现稳定 `9:16` 舞台、Shot 缩略图、Inspector 和键盘等价排序动作。
- 实现总时长、镜头数和策略校验。

**完成条件**：春风 800MT 的沙漠外景和仪表特写被拆分，用户指定镜头顺序保持不变。

### WP4：媒体执行与成片，2 至 4 天

- 将确认的 Storyboard 编译为 Shot Manifest。
- 接入一个视频 Provider、用户素材和图片运动降级。
- 实现 Worker 状态、取消、一次自动重试和单镜头人工重试。
- 用 FFmpeg 合成并执行自动媒体检查。
- 按[视频与渲染输出规格](../specs/rendering-profile.md)生成 Preview 和 Final。
- 记录调用耗时、失败、资源量和 Artifact 来源。

**完成条件**：至少一个摩托车项目真实生成并下载合格 MP4；修改一个 Shot 只重做该 Shot 和最终合成。

### WP5：Blender 对照探针，1 至 3 天，可并行

- 安装并固定 Blender 稳定版本。
- 使用现成或临时占位车辆资产验证后台命令行渲染。
- 只实现受控 Scene/Camera 参数，不允许提示词执行任意 Python。
- 对比 360 环绕镜头的质量、耗时和 GPU 资源。

**完成条件**：形成是否把 Blender 纳入 P1 默认路线的测量报告；不要求 P0 影视级资产完成。

## 6. 测试策略

### 自动测试

- Schema：所有 LLM 结构化输出和 Shot Manifest。
- 单元：事实优先级、方案差异检查、版本失效、路由和预算上限。
- 契约：每个 Provider 使用录制 Fixture 覆盖成功、限流、超时和非法响应。
- 工作流：断点恢复、取消、重试和 Search 降级。
- 媒体：`ffprobe` 检查编码、尺寸、帧率、时长和音轨；黑帧/静帧检测。
- UI：Storybook 状态、键盘操作、axe、四视口截图、SSE 断线恢复和敏感数据检查。
- E2E：三个验收场景，媒体 Provider 可在 CI 中使用 Fixture。

### 人工评审

- Proposal 是否真正不同，理由是否与输入和素材一致。
- Hook 是否在首个镜头得到视觉兑现。
- 车型整体和关键特征是否达到已确认保真等级。
- 节奏、字幕可读性、声音和视觉高潮是否适合竖屏短视频。
- 不比较“是否爆款”，比较建议是否清晰、可执行和可修改。

## 7. P0 验收清单

- [ ] PRD、体验规格、P0 计划均已接受。
- [ ] 真实 Provider 和凭证已确定。
- [ ] 两个摩托车样例通过 Advisor、Brief、Storyboard、生成和下载全链路。
- [ ] 一个育儿样例验证内容包边界。
- [ ] 搜索冲突不会覆盖用户确认车型。
- [ ] Proposal 可选择、修改和合并。
- [ ] Provider、Key 和能力路由可以完全通过管理界面配置。
- [ ] 路由发布、Fallback 演练和回滚均有版本化记录。
- [ ] Brief 和 Storyboard 均有不可变确认版本。
- [ ] 单镜头重试不重新调用无关镜头。
- [ ] 成片通过媒体自动检查。
- [ ] 每次 LLM、搜索和媒体调用有耗时与资源记录。
- [ ] 形成 Blender 对照探针结论或明确记录未完成原因。
- [ ] Creator/Admin 两套 Shell、四个关键线框和设计 Token 通过评审。
- [ ] UI 没有阻断级可访问性、重叠、状态恢复或 Key 泄漏问题。

## 8. 成本处理方式

在没有预算数据时，不先设计收费规则，先建立可测量账本：

- LLM：输入/输出 Token、调用次数和重试。
- 搜索：查询、抓取次数和失败率。
- 图片/视频/TTS：模型、数量、秒数、分辨率和供应商返回费用。
- Blender：GPU 型号、渲染秒数、峰值显存和人工准备时间。
- 存储/流量：输入、中间文件和成片大小。

P0 每个 Run 设置硬预算和最大重试数。完成 20 次有效运行后，以 P50/P90 计算单条成本和等待时间，再决定免费额度，不在数据不足时猜测。

## 9. 开发门

### Gate P0：可开始编码

同时满足：

1. 项目方接受或修改 PRD、体验规格、UI 四份规格和本计划。
2. PRD 第 7 节输出规格和两个确认点被确认。
3. 至少一个 LLM、搜索和视频生成路径可在开发环境调用。
4. 明确真实车型 P0 保真标准。
5. Projects、Strategy、Storyboard、Admin Routing 四个关键线框通过评审。

### Gate P1：可扩展平台

P0 完整链路通过，领域 Schema、任务恢复、单镜头重试、成本报告和 UI 体验经评审后，才增加登录、历史项目、多 Provider、部署和更多内容包。

## 10. 估算

在 Provider 可用且不从零制作影视级车型资产的前提下，包含企业化 UI 基础和模型管理后台的 P0 约 11 至 18 个工作日；Blender 对照探针可并行，约 1 至 3 个工作日。若首条样片必须使用从零制作的精细真实车型资产，资产制作应单独估算，不能包含在平台 P0 时间内。
