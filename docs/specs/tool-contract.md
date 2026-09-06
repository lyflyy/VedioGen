# 外部工具与媒体 Provider 契约 v0.1

- 状态：待项目方评审
- 版本：0.1
- 日期：2026-09-05
- 负责人：待指定
- 范围：搜索、网页读取、媒体分析、图片、视频、TTS、Blender、合成和质检

## 1. 目标

平台业务与具体供应商 SDK 隔离。每种能力使用统一请求、异步任务、Artifact、Usage 和 Error 语义，使供应商切换、录制回放、局部重试和成本统计不修改领域流程。

LLM 调用遵循[模型接入规格](model-provider-routing.md)；本文约束 LLM 之外的工具和媒体 Worker。

## 2. 通用 Envelope

```typescript
type ToolRequest<T> = {
  schemaVersion: "1.0.0";
  toolCallId: string;
  idempotencyKey: string;
  projectId: string;
  generationRunId?: string;
  shotId?: string;
  capabilityAlias: string;
  payload: T;
  deadline: string;
  budget: {
    maxCostCny: string;
    maxAttempts: number;
  };
  provenance: {
    promptVersion?: string;
    routingPolicyVersionId?: string;
    inputArtifactHashes: string[];
  };
};

type ToolResult<T> = {
  toolCallId: string;
  status: "succeeded" | "failed" | "cancelled";
  output?: T;
  artifacts: ArtifactRef[];
  usage: ToolUsage;
  provider: ProviderSnapshot;
  error?: ToolError;
};
```

禁止在 Envelope 中传递明文 Key、本地任意路径、Shell 命令或 Python 代码。

## 3. 执行模式

Provider 支持同步或异步，但业务层统一看到以下接口：

```typescript
interface AsyncToolProvider<I, O> {
  submit(request: ToolRequest<I>): Promise<ToolJob>;
  get(jobId: string): Promise<ToolJob<O>>;
  cancel(jobId: string): Promise<CancelResult>;
}
```

- 同步供应商由 Adapter 包装为立即完成的 ToolJob。
- 异步供应商保存外部 Job ID，通过 Webhook 优先、轮询降级更新。
- Webhook 必须校验签名并按 Provider Event ID 幂等。
- 超时后先查询供应商，未知状态不得直接重复提交昂贵任务。
- 外部结果先写临时 Artifact，Hash 和媒体探测通过后再标记 ready。

## 4. 能力接口

### 4.1 SearchProvider

输入：查询、语言、地区、时间范围、结果数和内容类型。输出每项包含 URL、标题、摘要、发布时间、来源站点和排序信号。

不变量：搜索摘要不能直接成为 Project Fact；需要 PageReader 验证或明确标注只基于摘要。

### 4.2 PageReader

输入：URL、语言、最大正文长度。输出最终 URL、标题、正文、发布时间、抓取时间、内容 Hash、状态码和提取警告。

Adapter 必须限制重定向、响应体大小、超时和可访问网络范围，不能让模型读取任意本机/内网地址。

### 4.3 MediaAnalyzer

输入：一个或多个 AssetVersion。输出主体、画面质量、角度、关键特征、可用时段、转录/文字和技术元数据。分析结论保存模型版本和置信度。

### 4.4 ImageProvider

输入：Prompt、负面 Prompt、参考图、宽高、数量、种子和风格约束。输出图片 Artifact、真实种子、供应商参数、费用和内容警告。

同一请求幂等重放不得静默产生新计费任务；需要新结果时使用新 Idempotency-Key。

### 4.5 VideoProvider

输入：Prompt、参考图片/视频、时长、宽高、帧率意图、运动描述和种子。输出视频 Artifact 和供应商原始媒体元数据。

Adapter 必须声明：最大时长、支持比例、参考素材数量、是否支持种子、取消、音频和水印。最终规格归一化由合成 Worker 完成，不能假设供应商输出已经符合交付规格。

### 4.6 TtsProvider

输入：文本、语言、Voice ID、语速、情绪和输出格式。输出音频 Artifact，以及供应商支持时的句级/词级时间戳。

P0 输出至少 48kHz 单/双声道 WAV 或无损中间格式；最终 AAC 由合成 Worker 编码。

### 4.7 BlenderRenderer

输入只接受通过 `shot-manifest.schema.json` 校验且 `render.kind = blender-3d` 的 Manifest。Worker 根据已审核的 Scene Template、Camera Preset 和参数白名单执行固定入口。

禁止字段：任意脚本、命令、表达式、插件下载 URL。输出为帧序列、代理视频、渲染日志和资源用量。

### 4.8 MediaComposer

输入：已批准时间线、Shot Artifact、Voiceover、字幕、音乐、输出 Profile。输出预览/最终视频和 FFmpeg 探测报告。

合成必须是确定性的：相同输入 Hash、Profile 和 Worker 版本得到相同时间线结果。

### 4.9 OutputInspector

输入：Artifact 和 Rendering Profile。输出机器可读 QualityReport：格式、解码、尺寸、帧率、时长、黑帧、静帧、音轨、响度、字幕安全区及视觉模型补充结果。

## 5. Provider 能力注册

每个 Provider Adapter 注册：

- `providerId`、Adapter/SDK 版本。
- 支持的 Capability Alias 和限制。
- 同步/异步、Webhook/轮询和取消能力。
- 计价单位、价格版本和无法计价标记。
- 默认超时、最大并发和速率限制。
- 输出格式与需要执行的归一化步骤。
- 健康探针和 Fixture 列表。

业务路由只依据 Capability Alias 和约束选择 Provider，不读取供应商专有字段。

## 6. ArtifactRef

```json
{
  "artifactId": "018f0000-0000-7000-8000-000000000001",
  "kind": "video",
  "uri": "artifact://018f0000-0000-7000-8000-000000000001",
  "mimeType": "video/mp4",
  "sha256": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "sizeBytes": 1024,
  "status": "ready"
}
```

Worker 使用受控 Artifact URI 下载，不接收任意文件路径或浏览器传来的对象存储凭证。

## 7. 标准 Usage

```text
requestCount
inputUnits / outputUnits
unitName（token、image、video-second、character、gpu-second）
providerReportedCost
providerCurrency
normalizedCostCny
priceVersion
startedAt / endedAt / queueDurationMs / executionDurationMs
```

供应商不返回费用时仍记录可计量单位，并由 PriceVersion 估算。未知成本必须显式为 unavailable，不能记作 0。

## 8. 标准错误

| 错误码 | 可重试 | 默认动作 |
| --- | --- | --- |
| `RATE_LIMITED` | 是 | 退避后重试或 Fallback |
| `TIMEOUT` | 视状态 | 先查询外部 Job，再决定 |
| `PROVIDER_UNAVAILABLE` | 是 | Fallback |
| `AUTH_FAILED` | 否 | 隔离 Credential 并告警 |
| `INVALID_REQUEST` | 否 | 回到编译/输入修正 |
| `UNSUPPORTED_CAPABILITY` | 否 | 修正路由配置 |
| `CONTENT_REJECTED` | 否 | 返回可理解状态 |
| `SCHEMA_INVALID` | 有限 | 修复一次或切兼容 Provider |
| `OUTPUT_INVALID` | 有限 | 重试、降级或人工处理 |
| `BUDGET_EXCEEDED` | 否 | 停止并等待决策 |
| `CANCELLED` | 否 | 收口任务 |
| `UNKNOWN_EXTERNAL_STATE` | 否 | 对账，不直接重复提交 |

ToolError 包含 `code`、脱敏 message、Provider Request/Job ID、`retryAfterMs`、`retryable` 和 traceId；不包含请求 Secret。

## 9. 路由与降级

- LLM Provider 路由由 RoutingPolicyVersion 管理。
- 媒体 Provider P0 使用 Content Pack 路由规则和 Shot Manifest 固定结果。
- 自动 Fallback 只在同一 Capability 和可接受质量范围内执行。
- 从视频降级到图片运动属于策略变化，必须创建新 ShotRun，并在用户界面显示“已降级”。
- 预算、时长或质量差异较大的降级需要用户确认，不能静默发生。

## 10. 契约测试

每个 Adapter 必须通过：

1. 成功响应归一化。
2. Idempotency-Key 重放。
3. 429、5xx、超时、坏响应和鉴权失败。
4. Webhook 重复、乱序和签名失败。
5. 取消支持与不支持两种路径。
6. Artifact Hash、媒体格式和损坏输出。
7. Usage 与费用缺失/存在。
8. 日志和错误 Secret 扫描。

CI 使用 Fake Provider 和脱敏录制响应；真实 Provider 以低成本 Fixture 定时验证。

## 11. 待评审项

1. 首个 Search、Video 和 TTS Provider 确认后补充能力注册实例。
2. P0 是否需要独立 ImageProvider，还是首期由 VideoProvider 内部生成首帧；建议保留独立接口但不要求首日接入。
3. 媒体 Provider 的管理界面是否与模型管理后台共用“能力路由”；P0 建议只做只读状态和单 Provider 配置，P1 再做完整媒体路由。
