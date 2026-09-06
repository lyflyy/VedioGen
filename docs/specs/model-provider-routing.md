# 大模型接入、切换与 API Key 规格 v0.1

- 状态：待项目方评审
- 版本：0.1
- 日期：2026-09-05
- 负责人：待指定
- 术语说明：本文将项目方所说的“K”理解为模型平台 API Key

## 1. 结论

业务代码不直接调用 OpenAI、通义千问、DeepSeek、Gemini、Claude 或其他平台 SDK。所有大模型请求经过平台自己的 `ModelGateway`，业务只指定“要完成什么能力”，不指定供应商名称。

P0 已采用小型 `openai-compatible` Adapter 直接接入首个中转站，因为当前只有一个已验证协议，直接实现能保持错误、Schema 和图片输入行为可审计。LiteLLM/Portkey 保留为多平台扩展候选；出现第二种不兼容协议或需要集中限流、熔断和计费时再做 POC，不为单一中转站提前引入网关依赖。平台继续掌握能力别名、路由策略、Key 引用、调用记录和错误语义。

```text
Web 创作台
  -> Creative Advisor / Script / Storyboard Service
  -> ModelGateway（本项目契约）
  -> Routing Policy + Prompt Registry + Credential Reference
  -> OpenAI-compatible Adapter（当前）/ LiteLLM 或独立 Gateway（多平台候选）
  -> OpenAI / DashScope / DeepSeek / Gemini / Anthropic / 本地模型
```

## 2. 为什么使用网关

不同平台在鉴权、模型名、结构化输出、工具调用、流式协议、Token 统计、错误码和限流方式上不一致。LiteLLM 已提供统一接口和大量 Provider 适配，Portkey 等成熟网关也验证了重试、Fallback、负载均衡和条件路由的通用做法。

我们不重复实现这些协议差异，但以下内容必须由平台自己掌握：

- 哪个业务阶段需要什么能力。
- 哪些 Project Facts、Evidence 和 Prompt 被发送。
- 输出 Schema 与业务校验。
- 每次运行实际使用的路由配置快照。
- 用户确认版本与模型输出之间的追溯关系。
- 单次任务预算和是否允许降级。

## 3. 能力别名

业务代码使用稳定别名，不出现物理模型名：

| 能力别名 | 任务 | 必需能力 | 默认质量倾向 |
| --- | --- | --- | --- |
| `fact-extractor` | 从输入提取 Project Facts | 中文、结构化输出 | 快速、低成本 |
| `research-planner` | 生成检索词和整理 Evidence | 工具调用、结构化输出 | 快速、低成本 |
| `creative-advisor` | 诊断并生成 Strategy Proposal | 中文、长上下文、结构化输出 | 质量优先 |
| `brief-compiler` | 合并选择并生成 Creative Brief | 严格 Schema | 稳定优先 |
| `script-writer` | 旁白、字幕和节奏 | 中文创作、结构化输出 | 质量优先 |
| `storyboard-generator` | 旁白、字幕、原子 Shot 与镜头规划 | 严格 Schema、视觉语言 | 质量优先 |
| `video-generation` | 图生视频/文生视频异步任务 | 视频输出、任务查询 | 质量与车型一致性优先 |
| `visual-reviewer` | 检查图片/视频输出 | 图片/视频输入 | 多模态优先 |

同一物理模型可以承担多个能力，也可以逐步替换。业务对象只保存能力别名，同时在调用快照中保存真实 Provider 和模型版本。

## 4. 核心调用契约

`ModelGateway` 对业务层提供四类能力：

```typescript
interface ModelGateway {
  generateObject<T>(request: StructuredModelRequest<T>): Promise<ModelResult<T>>;
  streamConversation(request: ConversationRequest): AsyncIterable<ModelEvent>;
  analyzeMedia<T>(request: MediaModelRequest<T>): Promise<ModelResult<T>>;
  checkCapability(alias: ModelCapabilityAlias): Promise<CapabilityStatus>;
}
```

每个请求至少包含：

- `requestId`、`projectId`、`runId`、`stage`。
- `capabilityAlias`、`promptVersion`、输入 Schema 版本、输出 Schema。
- 消息、工具白名单和媒体引用。
- 超时、最大输出 Token、温度/随机性范围。
- 单次预算、是否允许 Fallback、最多尝试次数。
- 数据和日志标签，不包含明文 API Key。

归一化响应至少包含：

- 通过 Schema 校验的结果或流式事件。
- Provider、物理模型、路由策略和凭证引用 ID。
- 输入/输出 Token、缓存 Token、供应商请求 ID。
- 开始/结束时间、首 Token 延迟、总耗时和估算成本。
- 重试/Fallback 链、停止原因和标准错误类型。

供应商原始响应可加密短期保存用于排障，但不能作为业务代码的输入格式。

## 5. Provider 与模型配置

### 5.1 配置对象

```yaml
routingPolicyVersion: 1
bindings:
  creative-advisor:
    requirements: [text, streaming, structured-output, tools, zh-CN]
    primary: advisor-quality-cn
    fallbacks: [advisor-balanced-cn]
    timeoutSeconds: 90
    maxAttempts: 2
    budgetClass: medium

deployments:
  advisor-quality-cn:
    provider: provider-a
    model: model-name-a
    credentialRef: secret://llm/provider-a/primary
    enabled: true
  advisor-balanced-cn:
    provider: provider-b
    model: model-name-b
    credentialRef: secret://llm/provider-b/fallback
    enabled: true
```

仓库只保存无密钥模板。模型平台、真实模型、Provider API Key 和路由必须通过管理界面新增或修改。用于启动 Secret Store 的根加密密钥属于基础设施 Secret，可以从部署环境注入，但它不能替代界面中的 Provider Key 管理。

### 5.2 能力矩阵

每个 Deployment 必须声明并通过探针验证：

- 文本、图片/视频输入支持情况。
- Streaming、Tool Calling、JSON Schema/结构化输出。
- 中文质量与上下文长度。
- 超时、速率限制、并发限制和最大输出。
- 计价单位和价格版本。
- 数据部署区域与网络可达性。

路由器只会把请求发给满足必需能力的 Deployment。OpenAI-compatible 不代表行为完全一致，结构化输出和工具调用仍必须分别测试。

## 6. 平台切换流程

切换不通过修改业务代码完成，而是发布新的 `RoutingPolicyVersion`：

1. 管理员通过管理界面新增 Provider、Deployment 和 API Key，初始状态为 `draft`。
2. 执行连接、Streaming、结构化输出、工具调用、中文样例和成本探针。
3. 将 Deployment 标记为 `ready`。
4. 创建新路由版本，把能力别名的 Primary 或 Fallback 指向新 Deployment。
5. 使用固定 Fixture 做影子测试或小流量验证。
6. 原子激活新路由版本；新请求使用新版本，执行中的 Run 继续使用旧快照。
7. 观察错误率、Schema 通过率、延迟、成本和人工质量评分。
8. 异常时回滚到上一版本，不需要重新部署业务应用。

每个 Project Run 保存完整路由快照，因此日后可以解释“这条脚本由哪个平台、哪个模型、哪个 Prompt 生成”。

## 7. API Key 管理

### 7.1 存储

- 浏览器永远不持有供应商 Key，所有调用从服务端发出。
- P0 本机开发使用 Secret Store 适配器加密保存界面写入的 Provider Key；根加密密钥从未提交的进程环境注入。
- 外部测试/生产使用 Secret Manager、Vault 或部署平台的 Secret 存储保存界面写入的 Provider Key。
- 数据库和路由配置只保存 `credentialRef`、Provider、状态和可选末四位，不保存明文。
- 日志、Trace、异常和管理 API 必须统一脱敏 Authorization、Key 和签名参数。

### 7.2 生命周期

Key 状态为 `draft -> active -> draining -> revoked`：

1. 新 Key 写入 Secret Store。
2. 运行最小权限连接测试。
3. 激活新 Key，停止向旧 Key 分配新请求。
4. 等旧请求结束后撤销旧 Key。
5. 保留轮换审计记录，不保留旧 Key 明文。

首期使用平台自己的 Key，不支持普通用户输入个人 Key。后续若增加 BYOK，需要独立的加密、权限与删除设计。

### 7.3 多 Key

只有单个供应商确有并发或配额需求时才建立 Key Pool。路由可按权重和健康度选择 Key，但费用仍归一到同一个 Deployment。认证失败会立即隔离对应 Key，不应在错误 Key 上重复消耗重试次数。

## 8. 重试、Fallback 与熔断

| 标准错误 | 默认处理 |
| --- | --- |
| `RATE_LIMITED` | 按 Retry-After 退避；超过当前阶段等待上限后切 Fallback |
| `TIMEOUT` | 同 Deployment 重试一次或直接切 Fallback，取决于是否已产生输出 |
| `PROVIDER_UNAVAILABLE` | 标记健康度下降并切 Fallback |
| `AUTH_FAILED` | 隔离 Key 并告警；不对同一 Key 重试 |
| `INVALID_REQUEST` | 不 Fallback，由调用方修正契约 |
| `SCHEMA_INVALID` | 使用校验错误修复一次；仍失败再切兼容模型 |
| `CONTENT_REJECTED` | 返回业务可理解状态；不通过换平台绕过明确拒绝 |
| `BUDGET_EXCEEDED` | 立即停止，等待用户/系统选择低成本策略 |

Fallback 不是无条件切换：

- 创意顾问在流式输出前失败可以透明切换。
- 已向用户显示部分内容后失败，需要发送 `restart` 事件并重新开始完整响应，不能拼接两个模型文本。
- 结构化阶段只接受完整且通过 Schema 的结果。
- 每次调用限制总尝试次数和总预算，防止平台故障导致无限费用。

## 9. Prompt、模型与业务解耦

Prompt Registry 单独版本化，包含系统提示、输出 Schema、工具白名单、Few-shot Fixture 和适用内容包。一次输出由以下快照共同确定：

```text
ContentPackVersion
+ PromptVersion
+ InputSchemaVersion
+ RoutingPolicyVersion
+ Provider / Model
+ CredentialRef ID
+ Model Parameters
+ Input Artifact Hashes
```

切换模型时先运行同一组固定 Fixture，比较：事实保持、Schema 通过率、方案差异度、中文文案质量、延迟和成本。模型能返回 JSON 不等于业务结果可用，人工评审仍是 Creative Advisor 的发布门。

## 10. 观测与预算

每次调用写入 `ModelInvocation`：

- 请求、项目、阶段和能力别名。
- 路由/Prompt/Schema 版本。
- Provider、模型、Key 引用 ID和供应商请求 ID。
- Token、耗时、缓存、重试、Fallback 和标准错误。
- 供应商原币种费用、价格版本和归一化人民币估算。
- 输出 Artifact/领域对象 ID 与质量评审结果。

普通用户只看到“处理中、已降级、失败、预计资源等级”等产品状态。具体模型切换和 Key 管理只出现在内部运营界面。

## 11. P0 实施范围

### 必须实现

- `ModelGateway` 业务契约和首个 OpenAI-compatible 适配实现。
- 能力别名、Deployment、RoutingPolicyVersion 和调用快照。
- 服务端 Key 引用与日志脱敏。
- Streaming、结构化输出、超时、一次重试和 Fallback。
- 固定 Fixture 与 Provider 契约测试。
- 一个真实主 Provider；开发门不因第二个平台凭证暂缺而阻塞。
- [模型管理后台](model-management-console.md)：Provider、Key、Deployment、能力路由、测试、发布/回滚和调用记录。

### P0 完成前验证

- 接入第二个真实 LLM 平台，对 `fact-extractor` 和 `creative-advisor` 完成手动切换与故障 Fallback 演示。
- 若无法获得第二个平台凭证，必须以 Fake Provider 完成自动契约测试，并把真实切换保留为未完成验收项，不能宣称多平台能力已验证。

### P1 再做

- 独立网关服务、Key Pool、流量权重、影子流量和自动熔断。
- 用户级配额、团队 Key、BYOK 和多区域路由。
- 基于历史质量/成本的自动模型选择。

## 12. 待项目方评审

1. 是否接受 LiteLLM SDK 作为 P0 底层统一适配器。
2. 首批希望接入的两个平台是什么，以及是否已有测试 Key。
3. 是否允许调用境外 API，还是首期必须使用中国大陆可访问平台。
4. P0 Key 由项目统一提供，是否确认暂不支持用户自带 Key。
5. 管理后台是否先采用同一 Web 应用的独立 `/admin` 路由。

## 13. 验收标准

- 更改路由配置即可切换模型，业务代码和 Prompt 不需要修改。
- 运行中的任务保持原配置快照，新任务使用新路由版本。
- Key 不出现在浏览器、数据库明文字段、日志或错误响应中。
- 主 Provider 模拟限流/不可用时，符合策略的请求切到 Fallback。
- 两个平台的响应都通过同一业务 Schema；失败得到统一错误类型。
- 每次调用可追溯 Provider、模型、Prompt、路由、Token、耗时和成本。

## 14. 调研依据

- [LiteLLM](https://github.com/BerriAI/litellm)：约 58k Star；统一 OpenAI 风格接口、100+ Provider、虚拟 Key、费用跟踪、负载均衡和管理能力；核心非企业目录为 MIT。访问日期 2026-09-05。
- [Portkey AI Gateway](https://github.com/Portkey-AI/gateway)：约 13k Star；重试、Fallback、条件路由、负载均衡、多模态接口；MIT。访问日期 2026-09-05。
- [New API](https://github.com/QuantumNous/new-api)：约 47k Star；多渠道管理和 OpenAI 聚合入口；AGPL-3.0。可参考中国模型渠道管理体验，P0 不作为默认嵌入式依赖。访问日期 2026-09-05。
