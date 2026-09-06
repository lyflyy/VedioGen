# ADR-0005：通过统一模型网关接入大模型

- 状态：待评审
- 日期：2026-09-05
- 影响范围：LLM 调用、平台切换、API Key、成本与可观测性

## 背景

创意顾问、事实提取、脚本、Storyboard 和视觉检查对模型能力、质量和成本的要求不同。直接在业务模块中调用各平台 SDK 会把鉴权、模型名、错误、流式协议和结构化输出差异扩散到整个代码库，也无法可靠切换或回滚。

## 决策

- 业务层只调用项目自有 `ModelGateway`，并使用 `creative-advisor` 等能力别名。
- P0 使用 LiteLLM SDK 统一底层 Provider；P1 根据规模决定是否部署独立 Gateway。
- Provider、模型、API Key 引用和 Fallback 由版本化 Routing Policy 管理。
- Provider、Deployment、API Key 和 Routing Policy 必须通过内部管理界面配置、测试、发布和回滚。
- 每次运行保存路由快照，配置切换只影响新请求。
- Provider API Key 必须由管理界面写入服务端 Secret Store，不进入浏览器响应、数据库明文字段、日志和 Prompt；只有 Secret Store 的根加密密钥由部署环境注入。
- Prompt Registry、业务 Schema 和模型路由分别版本化。

具体契约见[大模型接入、切换与 API Key 规格](../specs/model-provider-routing.md)。

## 理由

- 复用成熟开源网关对多平台协议和错误的适配。
- 平台可以按能力、质量、成本和可用性切换模型。
- 路由与 Prompt 分离，模型变化不修改业务流程。
- Key 轮换、调用追溯、预算和降级规则有统一入口。

## 代价

- 增加一层网关依赖和配置管理。
- 各平台即使兼容 OpenAI 接口，结构化输出和工具调用行为仍需契约测试。
- LiteLLM 升级可能产生适配变化，需要固定版本和回归测试。

## 验证条件

P0 至少用一个真实 Provider 跑通全链路，并在完成前用第二个平台验证手动切换和故障 Fallback。没有第二个平台凭证时，只能标记契约实现完成，不能标记多平台运行验证完成。
