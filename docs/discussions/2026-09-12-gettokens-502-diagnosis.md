# GetTokens 502 排查与错误诊断修复

## 输入与历史证据

用户报告项目 `12747bf9-bf8c-4766-b371-16a41f901dc8` 的创意建议失败，并指出同一中转站当前对话正常，要求核查并修复。

- 08:48:24（北京时间）：调用 `73a41d00-a867-4949-882a-cf7e0b7403ef`，HTTP 502，耗时 12683ms。
- 23:33:22（北京时间）：调用 `96cb9eb4-fbd6-4719-88b2-247e9d631a5b`，HTTP 502，耗时 12406ms。
- 两条均记录模型 `gpt-5.4-mini`，没有上游 Request ID，没有保存错误响应的格式与原文。
- 当前部署配置为 GetTokens、`https://www.gettokens.cc/v1`、`gpt-5.4-mini`、120 秒超时；调用 `/chat/completions`。
- 代码明确区分收到 HTTP 502 和本地超时异常，所以这两条不是触发 120 秒本地超时；不能凭状态码反推历史 502 的具体网关原因。

## 本轮真实对照

使用服务端已有加密凭据，不输出 Key，不修改模型或路由。有限诊断调用如下；未在相同错误下循环重试。

| 请求 | 结果 | 上游 Request ID |
| --- | --- | --- |
| GET `/v1/models` | 200，列表包含 `gpt-5.4-mini` 及其他 GPT-5 系列 ID | `70a51ae6-abff-4345-8b09-01d6ca644d70` |
| POST `/v1/chat/completions`，最小结构化输出 | 429 | `3c3eebbd-9eef-486f-a790-707a5df243bd` |
| POST `/v1/responses`，最小结构化输出对照 | 429 | `293484b1-7c29-496e-80ad-3b4ecb29ba0d` |
| 23:54:33 经 Web 3001 的原项目创意建议入口 | 429，9954ms | `401e7c38-514e-4566-943f-2254d84942aa` |

三个生成请求的上游原文一致：

> All available accounts are currently rate-limited. Please retry later.
> type: rate_limit_error

真实项目新调用记录为 `321b7f89-8858-4d61-adfa-acbdbfc8125e`，CF Ray `a3a017861cb89f96-AMS`。页面已显示该记录及上游响应诊断，并按原调度规则进入 60 秒凭据冷却。

模型列表可访问不代表生成通道可用；当前两个协议都限流，不能据此用协议切换修复。对话所用具体模型 ID 尚待用户提供，也不能因对话成功就认定其与项目同模型同路由。不将当前 429 作为历史 502 的已证实成因。

## 已修复部分

原错误采集仅处理特定 JSON 字段与 text/plain，HTML 错误页、缺省 Content-Type 的文本以及其他常见错误字段会丢失。现已：

- 用标准 HTMLParser 提取错误页文本，移除脚本、样式与 HTML 标签；仍按纯文本显示。
- 兼容 JSON `detail`、`title`、`error_description` 和字符串错误，以及无 Content-Type 的文本。
- 明确区分空响应体与未包含可展示字段的响应，不再将所有情况归为“上游未提供说明”。
- 记录请求方法和不含查询/凭据的接口地址、响应类型、响应字节数；仅白名单记录 server、via、CF Ray 及 Request ID。
- 对 Key、请求提示词、Authorization、图片 base64 等脱敏，正文限制长度；不记录 Cookie 或任意 JSON 字段。
- 沿用原日志存储，无数据库迁移；旧记录保留，不补造原文。

## 验收与剩余依赖

- API 全量 250 项通过（新增 8 项错误采集测试）；原测试依赖有 2 条弃用警告。
- 浏览器项目日志回归覆盖隔离 502 诊断文字、接口与 CF Ray，以及原 429 脱敏显示。
- 原项目真实调用后，在桌面和手机视口核查日志，截图位于 `.data/internal-mvp/model-configuration/relay-diagnostic-*.png`。
- 检阅 API 已更新，Web 3001 与 API 8001 保持运行。更新前确认没有活动任务。
- 仍未恢复真实模型生成。需要对照用户正在正常使用的确切模型 ID，或由中转站根据上述 Request ID 排查账号池/路由限流。不能由本地代码解除供应商限流。

本轮尝试访问 OpenAI 官方 Responses 文档，两处分别被 Forbidden / Cloudflare 拦截；没有据此新增或迁移生产协议。协议对照只代表该中转站的实测结果，不推断 OpenAI 官方服务状态。
