# AI 视频创意咨询与开源复用研究

- 状态：待评审
- 调研日期：2026-09-05
- 范围：创意咨询、脚本/分镜确认、工具编排、短视频合成
- 说明：Star 数为调研日快照，只用于衡量社区关注度；正式采用前仍需按锁定版本复核许可证和维护状态

## 结论

市面产品已经证明“一句话生成脚本、画面、配音和成片”是基础能力，但它们的公开流程大多仍由用户先选受众、平台或风格，再生成并编辑。HeyGen 更进一步，公开强调逐场景蓝图、渲染前预览和通过对话修改。CapCut 则把选题、Storyboard 大纲和内容创意纳入生成前的 Brainstorm 环节。

本项目不应只复刻一句话成片。推荐建立独立的 `AI 创意顾问` 阶段：理解账号和目标，检索公开信息，诊断内容机会，给出 2 至 3 个有取舍说明的方向，让用户讨论、合并或修改，然后锁定 Creative Brief。脚本和 Storyboard 在此之后生成，高成本媒体生产仍需二次确认。

开源层面没有一个项目可以原样复刻为本产品。最稳妥的做法是采用成熟的 UI/Agent/媒体基础库，借鉴开源项目的数据契约和 Provider 组织方式，保留自己的 Project Facts、Strategy Proposal、Creative Brief、Storyboard、Shot 和 Run 领域模型。

## 市场产品流程观察

| 产品 | 官方公开流程/能力 | 可复用的方法 | 本项目不照搬的部分 |
| --- | --- | --- | --- |
| Invideo AI | 输入想法和时长等细节；生成前选择受众、平台、外观；AI 写脚本、选择画面、配音、字幕和音乐；生成后用文本命令编辑 | 低门槛入口、少量关键选项、文本式修改、端到端自动化 | 它偏向直接生成，未公开展示“多方案诊断与比较”这一完整决策层 |
| HeyGen Video Agent | 从提示生成脚本和逐场景画面；渲染前可预览 scene-by-scene blueprint；通过自然语言反馈反复修改；渲染后元素仍可编辑 | 生成前蓝图、对话修订、局部可编辑、品牌一致性 | 主要能力集中在数字人和通用视频，不解决真实摩托车跨镜头保真及 Blender 资产控制 |
| CapCut AI Video Generator | 输入主题或脚本，选择比例和风格；提供 AI 脚本；Brainstorm 能生成选题、Storyboard 大纲和内容创意；自动完成画面与节奏 | 把灵感阶段产品化、以模板降低参数复杂度、跨端编辑 | 模板和“一键完成”不能替代车型事实、资产版本和镜头级可复现工作流 |
| TikTok Creative Center Top Ads | 按行业、地区和目标查看高表现广告案例 | 将公开案例作为创意参考和 Evidence，而非靠模型臆测平台趋势 | Top Ads 是广告案例库，不等价于自然流量预测，也不能保证具体视频表现 |

### 共通交互模式

1. 先收集一个低门槛主题或目标，不要求用户先写完整脚本。
2. 通过受众、平台、风格、时长等少数高影响参数补足上下文。
3. 在正式渲染前展示脚本或逐场景蓝图。
4. 用自然语言完成修改，同时保留局部编辑能力。
5. 把视觉、旁白、字幕、音乐和节奏作为一个整体生成。
6. 用模板和默认值隐藏底层模型参数。

### 我们需要增加的决策层

普通自媒体创作者通常知道“想讲什么”，但未必知道哪个角度适合账号、素材和日更节奏。因此系统在脚本前输出 2 至 3 个 `Strategy Proposal`，每个方向必须包含：

- 目标受众与本条内容目标。
- 前 1 至 3 秒 Hook。
- 一个清晰的核心承诺或观点。
- 可被画面证明的视觉回报。
- 节奏、情绪峰值和结尾动作。
- 所需素材、真实车型保真风险、生成难度、预计耗时和相对资源消耗。
- 为什么适合，以及在哪些条件下不适合。

系统可以依据公开案例、账号历史和素材条件给出判断，但只能表达“建议、假设和理由”，不能承诺播放量或转化结果。

## 通用创意方法

这套方法放入平台核心，垂直内容包负责提供领域实现：

1. **Audience**：这条内容具体给谁看。
2. **Goal**：本条只选择一个主要目标，例如认识车型、形成记忆、促进评论或建立专业感。
3. **Hook**：开头立即给出冲突、结果、视觉奇观或明确问题。
4. **Promise**：观众看完能得到一个什么价值。
5. **Proof**：用镜头、用户素材、事实或演示支撑承诺。
6. **Progression**：每 2 至 4 秒出现信息、景别、动作或声音变化。
7. **Payoff**：在后半段安排最强视觉或情绪镜头。
8. **Close**：用车型记忆点、问题或明确 CTA 收束。

摩托车内容包强调车型识别、机械细节、速度/通过性和发动机感官；母婴/育儿内容包则可强调问题共鸣、步骤清晰、演示可信和容易保存。两者共用方法和数据对象，但评分规则与镜头库不同。

## 高关注开源项目复用矩阵

| 项目 | 调研日 Star | 适合复用/借鉴 | 结论 |
| --- | ---: | --- | --- |
| n8n | 203,406 | 通用工作流、节点生态、凭据和运行记录 | 不作为产品底座；其 Sustainable Use License 与产品化边界需要单独确认，且通用自动化 UI 不适合普通创作者 |
| Firecrawl | 176,660 | 网页抓取、清洗、结构化提取 | 只作为可替换搜索/抓取 Provider 候选；AGPL-3.0，不复制进闭源核心 |
| Dify | 154,489 | Prompt IDE、RAG、工具、工作流、运行观测 | 不整体 Fork；其修改版 Apache 2.0 对多租户服务有额外条件，且 Dify 的 Workspace/Agent 模型不能替代视频领域模型 |
| Crawl4AI | 81,392 | 网页清洗和结构化抓取 | Apache-2.0，适合在检索 POC 中直接试用；仍需配合搜索入口和来源质量排序 |
| Flowise | 55,423 | 可视化 Agent Flow、工具节点、运行调试 | 仅借鉴内部运营界面；普通用户不接触节点图，企业目录另有商业许可 |
| LangGraph | 41,080 | 可恢复 Agent 状态、Memory、Human-in-the-loop | P0 创意顾问编排候选，MIT；媒体长任务仍交给任务系统 |
| SearXNG | 36,538 | 自托管聚合搜索 | 作为成本可控的后续候选；AGPL-3.0，部署运维和中文结果质量需 POC |
| Langfuse | 34,218 | Prompt、Trace、评估、成本和版本观测 | P1 接入候选；核心大部分为 MIT，但企业目录单独授权 |
| Vercel AI SDK | 26,586 | 多模型流式对话、结构化输出、工具调用 UI | 前端对话层优先采用，Apache-2.0 |
| LiteLLM | 约 58,000 | 100+ Provider 的统一接口、虚拟 Key、费用跟踪、负载均衡和网关 | P0 模型适配首选；固定版本，企业目录另有许可 |
| Portkey AI Gateway | 约 13,000 | 重试、Fallback、条件路由、负载均衡和多模态网关 | 作为独立 Gateway 对照候选；MIT，P0 不同时引入两个网关 |
| NarratoAI | 10,984 | Python Provider Registry、Prompt Registry、搜索/字幕/FFmpeg Service 和测试组织 | 借鉴并按文件评估复用，MIT；不能直接当作平台核心 |
| Short Video Maker | 1,332 | TypeScript REST/MCP、Scene 模型、Pexels、TTS、Whisper、Remotion 合成 | 可做独立合成探针或参考实现，MIT；当前偏英文、库存素材且不支持完整用户媒体工作流 |
| MoneyPrinterTurbo | 120,729 | 从主题到脚本/素材/TTS/字幕/合成的一体流程和多供应商模式 | 不整体 Fork；可借鉴 Provider 和任务阶段，MIT；Streamlit 与单体任务编排不适合作为平台产品架构 |

## Adopt / Adapt / Reject

### Adopt：直接作为依赖或独立服务候选

- Vercel AI SDK：Web 端流式对话、工具状态与结构化结果展示。
- LangGraph：只编排创意顾问的多轮状态、检索和人工确认。
- LiteLLM SDK：统一模型 Provider 协议；自有 ModelGateway 保留业务能力别名和路由快照。
- FastAPI/Pydantic：控制 API 与结构化契约。
- FFmpeg：确定性合成、探测、转码、音频和字幕处理。
- Blender：有生产资产时执行可控 3D 镜头，不让终端提示词直接执行 Python。

### Adapt：先做技术探针，再决定代码复用范围

- 从 NarratoAI 参考 Provider/Prompt/Service 分层与测试，不复制其完整业务流。
- 用 Short Video Maker 的 Scene/合成思路验证时间线，但把输入改为平台自己的 Shot Manifest，并补充用户素材与中文。
- 用 Crawl4AI 验证网页正文抽取；搜索入口保持 `SearchProvider` 接口。
- 用 Langfuse 观测 Prompt 与质量评估，先不让它成为业务状态来源。

### Reject：首期明确不做

- 不整体 Fork Dify、n8n 或 Flowise 来承载终端产品。
- 不把 ComfyUI 节点图直接暴露给普通创作者。
- 不复刻 MoneyPrinterTurbo 的 Streamlit UI 或进程内长任务方式。
- 不用一个超长 Prompt 同时完成检索、策略、脚本、分镜和渲染。
- 不承诺 AI 能预测或保证抖音播放量。

## 推荐产品结构

```text
一句想法 / 用户素材
  -> 账号目标与受众理解
  -> 搜索与 Evidence Pack
  -> 内容机会诊断
  -> 2-3 个 Strategy Proposal
  -> 用户讨论、合并或修改
  -> 锁定 Creative Brief
  -> 脚本 + Storyboard
  -> 用户确认
  -> 逐镜头生成、合成与质检
```

这条链路与成熟产品的“Prompt -> Blueprint -> Edit -> Render”一致，同时增加了本项目需要的主动建议、方案比较、真实车型事实和镜头执行约束。

## 采用开源代码的工程规则

1. 先记录要解决的具体问题，再选择组件；Star 不能替代适配性验证。
2. 优先依赖官方发布包或部署独立服务，避免维护大规模私有 Fork。
3. 复制代码必须逐文件保留许可证和来源记录，并写入 `THIRD_PARTY_NOTICES`。
4. 产品业务状态只保存在自己的领域模型中，外部工作流 ID 只是引用。
5. 对候选组件建立最小 POC，记录功能覆盖、中文效果、延迟、成本、失败恢复和维护活跃度。
6. 只有当上游扩展点无法满足需求且修改长期稳定时才建立 Fork，并记录同步上游策略。

## 主要来源

- [Invideo AI Video Generator](https://invideo.io/ai-video-generator/)，访问日期 2026-09-05。
- [HeyGen Video Agent](https://www.heygen.com/video-agent)，访问日期 2026-09-05。
- [CapCut AI Video Generator](https://www.capcut.com/tools/ai-video-generator)，访问日期 2026-09-05。
- [TikTok Creative Center Top Ads](https://ads.tiktok.com/business/creativecenter/inspiration/topads/pc/en)，访问日期 2026-09-05。
- 上表各 GitHub 仓库的 README 与 LICENSE，访问日期 2026-09-05。
- Star 快照来源为 GitHub 公开仓库页面；部分项目数值来自同日先前检索，API 随后触发匿名限流，正式选型时需复查。
