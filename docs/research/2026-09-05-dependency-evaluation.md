# P0 依赖采用评估

- 状态：待锁定版本
- 日期：2026-09-05
- 目的：在创建工程脚手架前明确 Adopt、POC 和 Deferred，避免无边界 Fork

## 结论

2026-09-06 实现核对：下表是 2026-09-05 的采用意向，不是已安装清单。当前 LLM 使用直接 OpenAI-compatible Adapter，未采用 LiteLLM、LangGraph 或 Vercel AI SDK；这些组件按实际复杂度再评估。可靠长任务已成为整改项，队列/Temporal 的最新评估门见[架构复核](../architecture/2026-09-06-architecture-review.md)，不再以“P0 延后”为由保留请求内执行。

P0 采用主流框架和库完成基础能力，领域模型、确认流程和媒体契约由本项目维护。具体版本在脚手架创建当天根据兼容性测试锁入 lockfile；本文不提前写可能过期的版本号。

## Adopt

| 依赖 | 用途 | 采用方式 | 退出方案 |
| --- | --- | --- | --- |
| Next.js / React / TypeScript | 创作者与 `/admin` Web | 官方包，单一 Web 应用、路由隔离 | UI 通过 OpenAPI 调用后端，可替换框架而不改领域协议 |
| Vercel AI SDK | 流式对话和结构化 UI 事件 | 只用于 Web/对话传输层 | SSE 与领域事件是自有协议，可改为原生客户端 |
| FastAPI / Pydantic | 控制 API、校验和 OpenAPI | 官方 Python 包 | 业务服务与框架 Handler 分离 |
| LangGraph | Advisor Checkpoint 和 Human-in-the-loop | 仅创意顾问内部编排 | Project/Brief 状态保存在本项目数据库，可换为显式状态机 |
| LiteLLM SDK | 多 LLM Provider 统一适配 | 放在自有 ModelGateway 后 | ModelGateway 契约隔离，能替换 Portkey 或原生适配器 |
| PostgreSQL | 业务、版本、Outbox、运行状态 | 正式状态来源 | 标准 SQL 与迁移工具，避免专有扩展成为核心依赖 |
| FFmpeg / ffprobe | 合成、转码和确定性媒体检查 | 独立 Worker 进程 | MediaComposer 接口允许替换或增加实现 |
| Playwright | Web E2E 与截图回归 | CI 和本机测试 | 不进入运行时 |

## POC 后决定

| 候选 | 要验证的内容 | 接受条件 |
| --- | --- | --- |
| Crawl4AI | 中文正文提取、动态页、超时和资源 | 固定样例成功率、延迟和部署成本可接受 |
| NarratoAI 部分代码 | Provider/Prompt/FFmpeg 服务组织 | 逐文件确认来源、测试价值大于重写成本 |
| Short Video Maker | Scene/Remotion 合成思路 | 能映射 Shot Manifest、支持中文和用户素材 |
| Langfuse | Prompt、Trace、成本和评估 | 不成为业务状态来源，部署/托管成本可接受 |
| Blender | 360 环绕与产品镜头 | 固定版本、资产、命令行渲染和时间/质量达到基线 |

## Deferred / Reject for P0

| 项目 | 结论 | 原因 |
| --- | --- | --- |
| Dify | 不整体 Fork | 多租户许可条件、领域模型和终端 UI 不匹配 |
| n8n | 不作为产品底座 | 通用工作流和许可边界不适合终端创作产品 |
| Flowise | 不使用终端节点 UI | 普通用户不应理解节点连接，企业目录另有授权 |
| MoneyPrinterTurbo | 不整体 Fork | 可借鉴服务分层，但 Streamlit 与任务模型不适用 |
| ComfyUI 前端 | 不暴露给普通用户 | 仅可作为内部媒体 Worker |
| Remotion | P0 默认不采用 | FFmpeg 先覆盖合成；正式采用需复核其当前许可和主体资格 |
| Temporal | P0 延后 | 首期用 PostgreSQL 状态机验证需求，避免过早增加运维复杂度 |
| MinIO | 不设为 P0 必需 | 本机文件适配器先满足 P0，外部对象存储再按部署选型 |

## 版本与供应链规则

1. 依赖必须写入 lockfile，禁止生产镜像在启动时拉取 latest。
2. Python 与 Node 依赖启用自动漏洞/更新提示，但升级必须经过契约和 E2E 测试。
3. 容器、FFmpeg、Blender、字体和色彩配置都使用固定版本或镜像 Digest。
4. 复制第三方代码时保留来源、Commit、许可证和修改说明；优先使用正式包而非复制。
5. 对 LiteLLM、LangGraph 和 Vercel AI SDK 建立最小封装，禁止其类型扩散到领域层。
6. 上游停止维护、关键漏洞无法修复或协议破坏性变化时，依据退出方案替换。

## 脚手架前检查

- [ ] 选择 Python 和 Node LTS/稳定版本。
- [ ] 确认 LiteLLM 与首个真实 Provider 的 Responses/Chat、Streaming 和 JSON Schema 支持。
- [ ] 确认 LangGraph Checkpoint 与 PostgreSQL 版本组合。
- [ ] 记录 FFmpeg 构建配置和可用 Codec。
- [ ] 确认 Playwright 浏览器安装方式。
- [ ] 生成第三方依赖清单与 Notice 基线。
- [ ] 为所有外部依赖建立 Adapter 或边界测试。

## 来源

- [Next.js](https://github.com/vercel/next.js)
- [Vercel AI SDK](https://github.com/vercel/ai)
- [FastAPI](https://github.com/fastapi/fastapi)
- [Pydantic](https://github.com/pydantic/pydantic)
- [LangGraph](https://github.com/langchain-ai/langgraph)
- [LiteLLM](https://github.com/BerriAI/litellm)
- [PostgreSQL](https://www.postgresql.org/)
- [FFmpeg](https://ffmpeg.org/)
- [Playwright](https://github.com/microsoft/playwright)

访问日期均为 2026-09-05；正式锁版时重新核对版本、许可证和维护状态。
