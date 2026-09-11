# 内部 MVP：图生视频执行增量

- 日期：2026-09-07。
- 状态：代码与隔离契约测试已实现，未进行真实付费生成验证。
- 与 [本地素材执行](internal-media-execution.md) 叠加生效。
- fal / Kling 2.1 Standard 是首个可选适配器，不代表用户已选定供应商，也不声称是最新或画质最好的模型。

## 1. 官方接口依据

本轮读取以下公开资料，无 Key、无付费请求：

1. [fal 异步队列文档](https://docs.fal.ai/model-apis/model-endpoints/queue.md)，地址会重定向至现行文档。采用提交、保存任务 ID、轮询、取结果的生命周期。
2. [Kling 图生视频接口页](https://fal.ai/models/fal-ai/kling-video/v2.1/standard/image-to-video/api)，确认支持 Base64 Data URI 图片输入，首版不要求公网对象存储。
3. [对应 OpenAPI](https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=fal-ai/kling-video/v2.1/standard/image-to-video)，确认 `prompt`、`image_url`、字符串 `duration=5|10` 以及 `video.url`。

教程与生成 OpenAPI 的结果/取消路径示例存在差异。实现使用实际提交响应的 `status_url / response_url / cancel_url`，不猜测模型子路径；地址必须在官方队列主机且匹配请求 ID。适配器取消 REST 方法为 PUT，但本轮界面仅停止本地等待，不调用上游取消，避免把取消信号误说成停止计费。

## 2. 管理配置

复用现有 Provider / Credential / Deployment，无新增凭据系统或复杂路由版本：

| 字段 | 当前要求 |
| --- | --- |
| Provider.adapterType | `fal-video` |
| Provider.baseUrl | `https://queue.fal.run` |
| Deployment.physicalModelId | `fal-ai/kling-video/v2.1/standard/image-to-video` |
| Deployment.capabilities | 包含 `image-to-video` |
| Credential | 用现有 Admin 加密保存；GPT Key 不代表有视频权限 |
| 视频执行页 | `/admin/video-settings` |

`GET /api/v1/admin/video-settings` 返回配置与 `externalCallsAllowed`。

`PUT /api/v1/admin/video-settings` 请求示例（默认停用，不是推荐价格）：

```json
{
  "enabled": false,
  "deploymentId": null,
  "estimatedUsdPerSecond": "0",
  "maxRunUsd": "0"
}
```

启用必须有有效部署、正数参考单价和预算。配置存入启动时创建的 `video_settings` 表。保存仅校验配置，不提交生成任务。fal 凭据探测返回 `not-run`，部署探测返回 `configuration-only`；不能据此声称鉴权或画质通过。部署可为 draft 或 ready，不要求先跑扣费探测。

## 3. 镜头与运行契约

新增执行 `sourceStrategy=image-to-video`：

- `sourceAssetId`：当前项目 JPEG/PNG，不超过 10 MB，哈希一致且可解码。
- `durationMs`：5000 或 10000；不自动改时长。
- `videoPrompt`：非空，最多 2500 字符。GPT 分镜画面、运镜和连续性规则组合为初稿，用户编辑并确认；超限需精简，不静默丢弃要求。
- `fit=contain|cover`：仅控制最终竖屏适配，不提高上游分辨率或保证车型准确。
- 创建任务请求新增 `confirmVideoCost=true`，未确认则 422，不提交上游。

任务快照保存部署、凭据 ID、参考价、预算和估算，不保存明文 Key。返回 `mode=ai-video`，`estimatedUsd` 为累计预留估算，实际 `costCny=null`。镜头返回 `providerRequestId / providerStatus / submissionState`；内部队列 URL 不返回浏览器。

## 4. 费用与恢复

1. 首次估算为图生视频秒数乘参考单价，超过上限不创建任务。
2. 付费 POST 前保存 `submitting`，拿到任务 ID 立即落库，再轮询。
3. 查询/下载失败可恢复原任务，不重提。等待超过 10 分钟后暂停，恢复仍查原 ID。
4. POST 响应丢失或在提交边界中断，不能确认是否受理时需人工核对，不自动重提。同项目不能绕开原任务直接创建新生成。
5. 主动重做请求为 `POST .../shots/{shotId}/retries?confirmVideoCost=true`，新估算加到任务累计预留；超过原预算则拒绝。尚未结束的上游任务只能继续查询。
6. 停止只结束本地等待/发布，上游可能继续生成和计费。后台操作收尾期间禁止恢复同一任务；之后恢复原 ID。

这是单任务估算拦截，不是实际扣费硬上限、账户总额度或退款系统。参考价可能过时，不含汇率、税费及附加费用；供应商账户侧仍需设实际可用额度。未确认的提交需到供应商后台核对，本轮不提供任意手填 ID 修复入口，不通过删除数据来处理。

## 5. 媒体与能力边界

- 实际下载上游视频后，用已有 FFmpeg 转码、字幕及背景音频合成。
- 下载仅接受 HTTPS fal.media 及子域，不携带 Key，不跟随重定向；限制 100 MB、读取超时和下载等待，ffprobe 校验后入库。
- 保留 `.source.mp4` 原片和规范化片段，未实现自动存储回收。
- 当前仅该图生视频接口；纯文字视频、自动生图、素材搜索、TTS、Blender 尚未接通。
- 单图视觉环绕不是可验证的真实 360 度；后侧结构、车标、骑手与动作真实性仍需人工评审。
- 单 API 进程、单媒体执行器；不新增 Redis、分布式工作流、审批版本树。

## 6. 验证分层

- httpx MockTransport 模拟上游，不接触真实视频账户。
- 下载、转码与合成使用真实可解码测试视频，证明执行链路，不证明 AI 画质。
- 浏览器测试验证管理表单、Key 不回显、配置持久化、响应式和原有创作合成流程。
- 真实验收仍需供应商、额度、参考资产和用户 80 分评分，不能用上述测试完成长期 Goal。
