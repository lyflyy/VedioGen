# 项目文档索引

本文档目录是项目事实与决策的统一入口。讨论中形成的新信息应更新到对应主题文档，并在 `discussions/` 中保留当次讨论记录。

## 当前状态

- 2026-09-12 项目筛选/搜索/分页、可恢复回收站、项目执行日志及上游错误详情已实现。真实复现 GetTokens `gpt-5.4-mini` 的 429：上游报告所有可用账号受限，页面可查看脱敏原文及请求 ID，不推断为余额不足。[实测记录](discussions/2026-09-12-project-management-and-errors.md) · [功能契约](specs/project-management-and-activity.md)。

- 2026-09-12 混合路线基础能力已实现，浏览器复用历史真实 GPT 脚本与官网参考，完成 11 秒竖屏展示片、本地配乐、播放及下载；新文字 GPT 入口仍遭遇 429/502，本地动态试片因伪影拒绝采用。未宣布准确环绕、驾驶或 80 分验收完成。[实施与真实产物](discussions/2026-09-12-quality-route-implementation.md) · [执行契约](specs/quality-route-execution.md) · [长期目标](plans/2026-09-11-quality-route-execution.md)。

- 2026-09-11 提出本地优先路线的下一批调整：保留现有架构，将自动配图生成升级为主体参考检查、逐镜头选路、关键试片和声音合成。先修质量决策，再做张雪样片与春风复用验证；方案待检阅，未修改生产代码。[路线与分批验收](plans/2026-09-11-quality-first-route.md) · [讨论与未决事项](discussions/2026-09-11-route-adjustment.md)。

- 2026-09-11 通过 GitHub CLI 复核 MoneyPrinterTurbo、NarratoAI、Short Video Maker、ComfyUI、Wan2.2、OpenCut 的当前 README 与关键源码。结论：现有技术分层合理，但镜头制作策略、素材语义匹配、音画质量尚非本项目目标下的最佳实践；本轮仅研究，未修改生成代码。[版本、证据和优先级](research/2026-09-11-video-workflow-practices.md)。

- 2026-09-10 原项目六镜头已实际通过本地 Wan 推理、合成、浏览器播放和下载；修复小数秒与错误素材绑定，增加后台准备、一键生成、逐镜头结果和免重复推理的画幅整理。技术链路完成，车型一致、真实 360 度与 80 分质量仍未验收。[真实执行记录](discussions/2026-09-10-original-storyboard-execution.md) · [本轮目标](plans/2026-09-10-storyboard-to-film.md) · [执行契约](specs/storyboard-material-preparation.md)。

- 2026-09-10 已启动检阅服务并排查春风 450MT 的 429：历史 7 条失败调用不是活动任务；新增凭据级持久冷却、额度暂停/手动恢复、严格失败切换与次数限制，移除管理页静态“可用”。本轮未调用真实模型。[排查与执行规则](discussions/2026-09-10-model-429-and-scheduling.md)。

- 2026-09-08 策略横向比较、脚本后台进度、上传绑定、保存反馈、分镜执行检查及自动素材准备已修复；真实 GPT + 官网三张图片 + 本地 FFmpeg 完成 12 秒 1080p 竖屏短片，177 项 API / 14 项 E2E 通过。简单图片片不等于完整 360° 与驾驶样片。[设计、接口与实测记录](discussions/2026-09-08-workflow-ui-and-real-video.md)。

- 2026-09-08 用户允许第一支样片任选真实张雪车型，不再限定 800X。已选红色 820RR，新增品牌官网适配，真实下载 30 张参考并通过页面将 8 个红色整车视角和 6 张细节图入库新项目；169 项 API、3 项素材页 E2E 通过。车型身份阻塞已解除，三维与驾驶片段仍未完成。[确认与实测](discussions/2026-09-08-zxmoto-model-selection.md)。

- 正式样片只读复核：张雪早期分镜仍有骑行结尾后追加 CTA 的遗留问题且无准确几何；春风工程项目仅仪表镜头绑定素材，其余四镜缺片段。公开名称变体检索未获得匹配几何，没有活动任务可等待。下一步需文字确认车型身份与版本范围，再由平台准备资产。[缺口与证据](discussions/2026-09-07-sample-readiness-audit.md)。

- 已修复单进程 API 下相同输入的创意建议重复调用，成功结果可复用，生成期间新输入不会被旧结果覆盖；首次失败有明确重试入口。160 项 API / 13 项浏览器回归通过，本轮未新增真实模型调用。[契约、证据与限制](discussions/2026-09-07-advisor-request-deduplication.md)。

- Blender 已从独立 POC 接入管理配置、GLB 素材、完整环绕模板及现有任务队列。真实工程流程完成 90 帧渲染、试片采用与合成下载；仅使用校准几何，不是车型样片。另修复新建页初始化前输入丢失，以及 GPT 分镜强制至少 5 镜头的旧约束。[执行规格](specs/local-blender-execution.md) · [真实记录](discussions/2026-09-07-platform-blender-implementation.md)。

- 明确版本的春风 SPORT/EXPLORE 官网素材已接入既有资料页，真实下载核查 26 张并验证页面检索。发现官网局部图与配色图配置不完全一致，不能按标题当作准确多视角几何；张雪具体名称与春风版本仍待文字确认。[实测与后续依赖](discussions/2026-09-07-global-model-reference.md)。

- 仪表局部特写已完成官网原图裁剪 + 本地 FFmpeg 图片运动对照，真实播放/下载通过，修复隐藏上传控件导致的横向溢出；没有新调用模型。读数保真优于此前 Wan 试片，仍有分辨率和外框裁切限制，不是完整车型/动作验收。[对照证据与限制](discussions/2026-09-07-instrument-motion-comparison.md)。

- 已实现分镜页单镜头试片、恢复/重做与采用复用，真实 GPT + 官网参考 + 本地 Wan 流程已执行；同时修复网页代理 30 秒超时和分镜主体/动作/场景丢失。仪表试片仍有幻觉与灰边，未通过画质验收。[规格](specs/shot-preview.md) · [实现与实测](discussions/2026-09-07-shot-preview-implementation.md)。

- 官网骑行参考已完成一次真实本地 Wan 试验：约 129 秒生成 3.04 秒短片，桌面/手机播放验证通过；车型细节、扬尘及正式镜头要求未通过验收。[结果与限制](discussions/2026-09-07-official-riding-inference.md)。

- 官网素材已接入项目资料页：支持型号/镜头关键词检索、相关版本显式确认、真实下载入库与来源保留。[平台实测记录](discussions/2026-09-07-official-reference-platform.md)。正式样片采用 ES 与否仍待项目方回复。

- 画面工具进展：Blender 4.5 LTS 已完成真实 GLB 导入与 360 度诊断环绕，仍缺指定车型几何；官网 800MT-ES 高清参考目录已获取，版本采用待确认。见 [实测与检索记录](discussions/2026-09-07-geometry-and-official-references.md)及[环绕 POC](specs/local-blender-orbit-poc.md)。不将校准几何或独立脚本算作平台车型样片。

- 最新输入条件：用户目前只有文字描述。平台需负责素材发现/生成，不能把用户上传图片或 3D 模型设为主流程前提；[确认记录与代码差距](discussions/2026-09-07-text-only-local-generation.md)。

- 最新执行进展：本地 CPU 中文旁白已接入后台配置、分镜与最终 MP4，完成真实浏览器生成/播放/下载；[规格](specs/local-narration.md)与[实测记录](discussions/2026-09-07-local-narration-implementation.md)。这不代表复杂镜头或 80 分样片通过。

- 最新路线（2026-09-07）：用户要求减少付费视频供应商依赖，改为本地 Blender / 本地生成模型优先探索；详见 [本地优先生产计划](plans/2026-09-07-local-first-media.md)。fal 为可选补充，不再是唯一下一步。

- 阶段：真实 GPT 与文字素材发现、本地 Wan 短镜头生成、页面确认、合成播放和下载已实测；原生竖屏构图、完整关键镜头与 80 分样片仍待验收。fal 保留为可选能力，未调用付费视频账户
- 首期方向：摩托车 3D 短视频
- 首期用户：企业内部内容创作者/运营人员，共享工作区；暂不设计付费功能
- 核心场景：账号日更；用户通常只输入思路和文字描述
- 当前结论：采用“GPT 咨询与脚本确认 + 真实逐镜头生成/用户素材/可选 Blender + 人工选片 + 合成下载”的轻量混合路线；不建设正式版本审批
- 扩展要求：平台核心支持垂直内容包，后续可增加母婴、育儿等方向
- 首期边界：不建设素材授权审核、品牌法务审批或法律风险判断功能
- 尚未冻结：真实车型保真等级、视频 Provider 选择、生产成本与时延目标
- 文档状态：v0.1 契约已约束本地 P0 实现；完整生产范围仍需逐项评审
- UI 设计状态：Creator/Admin 企业化界面、关键响应式页面和自动可访问性检查已实现
- 工程状态：Next.js、FastAPI、SQLite/PostgreSQL 选项、真实 OpenAI-compatible 模型网关、加密凭据、上传、FFmpeg 测试预览和 E2E 脚手架已建立

## 文档导航

- [逐镜头素材检索与场景缺口](discussions/2026-09-07-shot-reference-discovery.md)：仪表照片实测、镜头关键词入口、来源页提图未采用与图片 API 待确认
- [逐镜头参考图构图](specs/reference-image-framing.md)：成熟裁剪组件、EXIF/像素契约、当前镜头绑定与执行器复用
- [参考图构图实现与真实验证](discussions/2026-09-07-reference-framing-implementation.md)：页面裁剪、真实 GPU 失败/手动重做、竖屏合成下载与质量缺口
- [纯文字与本地推理实测增量](discussions/2026-09-07-local-inference-evidence.md)：真实 GPT、四组推理对比、平台浏览器生成/下载、缺陷修复与画质边界
- [本地 ComfyUI 执行契约](specs/local-comfy-video.md)：本地/云端配置、Wan 核心工作流、恢复与定向取消
- [本地环境与真实通道实测](discussions/2026-09-07-local-comfy-implementation.md)：独立 GPU 安装、权重续传、管理页探测和真实推理剩余距离

- [纯文字素材准备实现记录](discussions/2026-09-07-reference-preparation-implementation.md)：已实现入口、真实联网证据、测试分层和本地生成剩余差距
- [文字到参考素材契约](specs/text-reference-preparation.md)：GPT 提取、免 Key 检索、候选确认/导入及错误边界

- [本地优先视频生产路线](plans/2026-09-07-local-first-media.md)：实际硬件、开源依据、镜头路线、架构调整和本地实验退出条件

- [视频 Provider 与长期目标检查点](discussions/2026-09-07-video-provider-implementation.md)：阶段进展、退出条件和外部依赖
- [图生视频执行增量契约](specs/internal-video-execution.md)：官方依据、配置、估算预算、恢复/重做和能力边界

- [首批 MVP 能力与长期 Goal 进度](discussions/2026-09-06-mvp-media-implementation.md)：已实现行为、真实测试范围、新预览环境和剩余依赖
- [内部素材执行契约](specs/internal-media-execution.md)：当前镜头参数、后台状态、局部重做、音频和单机限制
- [当前执行：企业内部 MVP 计划](plans/2026-09-06-internal-mvp-reset.md)：最新范围、80 分评分、关键镜头优先顺序和调整后的长期目标；优先于此前整改门
- [内部 MVP 优先级讨论](discussions/2026-09-06-internal-mvp-priority.md)：用户最新定位和后置范围
- [长期路线图与近期行动](plans/2026-09-06-long-term-roadmap.md)：6 至 12 个月滚动目标、首周期待办、资源、指标、运维与阶段决策
- [长期规划讨论](discussions/2026-09-06-long-term-planning.md)：本轮诉求与尚未确认的时间和资源假设
- [产品与模型升级路线图](plans/2026-09-06-product-and-model-evolution.md)：发布批次、新模型收益、评测与灰度、开发节奏及下一切片
- [升级与迭代讨论](discussions/2026-09-06-upgrade-and-iteration.md)：本轮诉求、建议与尚未确认的边界
- [2026-09-06 架构复核](architecture/2026-09-06-architecture-review.md)：代码证据、隔离复现、保留与调整的边界、成熟组件复用建议
- [架构整改执行计划](plans/2026-09-06-architecture-hardening.md)：流程可信度、持久任务、内容包、真实单镜头与多镜头验收门
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
