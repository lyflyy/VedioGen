# 项目文档索引

本文档目录是项目事实与决策的统一入口。讨论中形成的新信息应更新到对应主题文档，并在 `discussions/` 中保留当次讨论记录。

## 当前状态

- 阶段：真实 GPT 策略与分镜链路已验证，等待视频 Provider 进入单镜头 POC
- 首期方向：摩托车 3D 短视频
- 首期用户：普通自媒体创作者；暂不设计付费功能
- 核心场景：账号日更；用户通常只输入思路和文字描述
- 当前结论：采用“AI 创意顾问 + 两次确认 + AI 生成/用户素材/可选 Blender 3D + 统一分镜与合成”的混合路线
- 扩展要求：平台核心支持垂直内容包，后续可增加母婴、育儿等方向
- 首期边界：不建设素材授权审核、品牌法务审批或法律风险判断功能
- 尚未冻结：真实车型保真等级、视频 Provider 选择、生产成本与时延目标
- 文档状态：v0.1 契约已约束本地 P0 实现；完整生产范围仍需逐项评审
- UI 设计状态：Creator/Admin 企业化界面、关键响应式页面和自动可访问性检查已实现
- 工程状态：Next.js、FastAPI、SQLite/PostgreSQL 选项、真实 OpenAI-compatible 模型网关、加密凭据、上传、FFmpeg 测试预览和 E2E 脚手架已建立

## 文档导航

- [项目简报](discovery/project-brief.md)：已知目标、范围假设和成功标准
- [待确认问题](discovery/open-questions.md)：需要与项目方逐项确认的问题
- [对话式输入与确认流程](discovery/conversational-intake.md)：如何把一句自然语言变成可确认的脚本与分镜
- [首批摩托车 Storyboard 样例](examples/2026-09-05-motorcycle-storyboards.md)：张雪 800X 与春风 800MT 示例
- [开源项目与产品研究](research/2026-09-05-landscape.md)：GitHub、商业模式、架构和 UI 研究
- [AI 视频创意咨询与开源复用研究](research/2026-09-05-market-and-reuse-study.md)：市场前置流程、通用方法与 Adopt/Adapt/Reject 结论
- [P0 依赖采用评估](research/2026-09-05-dependency-evaluation.md)：框架采用、POC、延后和退出策略
- [企业化 UI、开源产品与 Agent Skills 调研](research/2026-09-05-ui-skills-and-product-study.md)：Skills 核验、开源界面样本、设计系统选择与 Adopt/Adapt/Reject 结论
- [张雪 800X 搜索试验](research/2026-09-05-zhangxue-800x-search-trial.md)：真实自然语言搜索中的误匹配案例
- [候选平台架构](architecture/proposed-platform-architecture.md)：端到端工作流和系统边界
- [大模型工具编排架构](architecture/llm-tool-orchestration.md)：大模型如何搜索、生成脚本并调用媒体工具
- [成本核算模型](architecture/cost-model.md)：免费阶段的成本账本、限额与 POC 测量方法
- [ADR-0001：资产优先的 3D 生产路线](decisions/ADR-0001-asset-first-3d-pipeline.md)：已被混合路线替代的历史决策
- [ADR-0002：平台核心与垂直内容包](decisions/ADR-0002-core-and-vertical-packs.md)：多内容方向的扩展边界
- [ADR-0003：混合生成与组装路线](decisions/ADR-0003-hybrid-generation-pipeline.md)：当前候选媒体生产方式
- [ADR-0004：视频生成前设置 AI 创意顾问阶段](decisions/ADR-0004-pre-generation-creative-advisor.md)：待评审的前置决策流程
- [启动讨论记录](discussions/2026-09-05-kickoff.md)：用户原始诉求与本轮解释
- [首期定位讨论](discussions/2026-09-05-product-positioning.md)：本轮确认项与新增约束
- [生成平台边界讨论](discussions/2026-09-05-generation-platform-scope.md)：法律流程移出首期后的技术边界
- [首批内容示例讨论](discussions/2026-09-05-first-content-examples.md)：两个自然语言样例形成的产品结论
- [大模型平台定位讨论](discussions/2026-09-05-llm-platform-positioning.md)：平台与工具的职责边界
- [开发准备度讨论](discussions/2026-09-05-development-readiness.md)：进入 P0 和 MVP 的条件
- [P0 本地垂直切片开发结果](discussions/2026-09-05-p0-development-result.md)：已实现能力、自动验证证据、明确边界和下一批次
- [真实模型与视频生成执行差距](plans/real-generation-readiness-gap.md)：现场阻断、所需 Key/基础设施、真实 Provider 接入门和验收顺序
- [真实 GPT 接入与执行结果](discussions/2026-09-05-real-gpt-integration-result.md)：页面阻断根因、真实探测、调用证据、费用缺陷修复和视频 Provider 边界
- [创意顾问前置能力讨论](discussions/2026-09-05-creative-advisor-requirement.md)：本轮新增要求与交付
- [产品需求文档 v0.1](specs/product-requirements.md)：待评审用户旅程、范围与验收指标
- [创作体验规格 v0.1](specs/experience-spec.md)：待评审页面流、状态与交互约束
- [大模型接入、切换与 API Key 规格 v0.1](specs/model-provider-routing.md)：能力别名、Provider 切换、Key、Fallback 与调用追溯
- [模型管理后台体验规格 v0.1](specs/model-management-console.md)：通过界面管理平台、Key、模型、路由、测试和发布
- [核心领域模型 v0.1](specs/domain-model.md)：项目、版本、生成与模型控制聚合
- [Creative Advisor Schema](specs/creative-advisor.schema.json)、[Creative Brief Schema](specs/creative-brief.schema.json)、[Storyboard Schema](specs/storyboard.schema.json)、[Shot Manifest Schema](specs/shot-manifest.schema.json)：中央结构化契约
- [OpenAPI 3.1 契约](specs/api.openapi.yaml)：创作者端与 `/admin` 控制 API
- [工作流状态机 v0.1](specs/workflow-state-machine.md)：确认、运行、取消、重试、发布与回滚
- [测试与验收策略 v0.1](specs/test-strategy.md)：自动测试、Provider 契约、媒体检查和人工质量门
- [外部工具与媒体 Provider 契约 v0.1](specs/tool-contract.md)：搜索、视频、TTS、Blender、合成和质检的统一 Envelope
- [垂直内容包契约 v0.1](specs/content-pack-contract.md)：摩托车与后续育儿方向的扩展边界
- [P0 视频与渲染输出规格 v0.1](specs/rendering-profile.md)：预览、成片、字幕、音频、FFmpeg 和 Blender 探针档位
- [契约有效样例](examples/contracts/creative-advisor.valid.json)：Creative Advisor、Brief、Storyboard 和 Shot Manifest 的可校验实例
- [Spec 入口](specs/README.md)：其余工程契约的建立顺序
- [执行计划入口](plans/README.md)：Spec 通过后维护实施与验收计划
- [P0 垂直切片计划](plans/p0-vertical-slice.md)：待评审的技术基线、工作包、测试与开发门
- [ADR-0005：通过统一模型网关接入大模型](decisions/ADR-0005-use-model-gateway.md)：待评审模型接入决策
- [ADR-0006：采用单一 UI 基础并分离 Creator/Admin Shell](decisions/ADR-0006-ui-foundation-and-separated-shells.md)：待评审 UI 技术与信息架构决策
- [模型管理界面讨论](discussions/2026-09-05-model-management-ui.md)：界面配置化要求与影响
- [企业化 UI 与 Skills 要求讨论](discussions/2026-09-05-enterprise-ui-requirement.md)：本轮要求、调研动作和设计影响
- [工程契约补齐讨论](discussions/2026-09-05-engineering-contract-pack.md)：本轮文档交付与剩余条件
- [从发现到开发路线图](plans/discovery-to-development.md)：剩余决策、文档、开发门和时间估算
- [UI 架构规格 v0.1](specs/ui-architecture.md)：Creator/Admin Shell、组件层级、状态、SSE 与敏感信息边界
- [设计系统规格 v0.1](specs/design-system.md)：视觉方向、Token、组件、响应式与治理规则
- [页面清单与导航规格 v0.1](specs/page-inventory-and-navigation.md)：完整路由、页面职责、线框与移动端边界
- [UI 测试与验收规格 v0.1](specs/ui-acceptance.md)：Playwright、axe、截图、性能和阻断条件

## 文档规则

文档状态使用 `草案`、`待确认`、`已接受`、`已废弃`。架构和产品结论发生变化时，不静默覆盖历史决策；应更新讨论记录，并新增或替代对应 ADR。GitHub Star、价格、模型能力等易变化数据必须记录查询日期和来源。
