# 内部 MVP 素材执行契约

- 状态：本地素材执行已实现；2026-09-07 起另见 [图生视频增量](internal-video-execution.md)，真实供应商调用仍待验证
- 日期：2026-09-06
- 适用范围：上传图片运动、上传视频剪辑、字幕与可选背景音频混合、片段重做和合成下载。
- 本文记录当前素材执行行为；历史 OpenAPI 中更完整的版本审批、幂等 Header 等不代表本批次全部实现。

## 镜头输入

当前分镜继续覆盖保存，不建立版本历史。`PUT /api/v1/projects/{projectId}/storyboards/{storyboardId}` 的每个镜头可包含：

| 字段 | 当前含义 |
| --- | --- |
| `id` | 本次镜头唯一 ID |
| `sourceStrategy` | 本地执行为 `image-motion`、`user-video`；`image-to-video` 依新增契约配置启用，其余策略明确阻断 |
| `sourceAssetId` | 本项目上传图片或视频的 ID，不能跨项目引用 |
| `sourceStartMs` | 视频入点，默认 0；不能超过素材剩余时长 |
| `fit` | `contain` 默认保留完整画面；`cover` 居中裁切 |
| `durationMs` | 单镜头 500 至 15000ms，总片不超过 60 秒，最多 12 镜头 |
| `caption` | 最多 40 字；合成时烧录中文字幕，最多按 20 字一行排列 |

仅作执行必需的字段检查，不引入内容审核。保存后当前草稿需重新点击确认；生成中拒绝编辑同一项目。用户可主动修改素材策略，但系统不能把所要求的 AI 驾驶镜头静默变成图片运动。

Workspace 返回素材 ID、文件名和 `previewUrl`，不返回本机路径。素材内容入口：`GET /api/v1/projects/{projectId}/assets/{assetId}/content`。

## 创建与查询

`POST /api/v1/generation-runs`：

```json
{
  "projectId": "project-id",
  "storyboardVersionId": "current-storyboard-id",
  "quality": "standard",
  "audioAssetId": null
}
```

`quality` 为 `standard`（1080 × 1920）或 `preview`（540 × 960），均为 30fps。输出尺寸不是画质承诺。`audioAssetId` 可选，指定本项目音频时混合背景音，否则保留用户视频原声，图片及无声视频使用静音轨；旁白文字不自动变成 TTS。

接口先保存任务再返回 202 和 queued Run；Worker 顺序处理镜头，界面轮询 `GET /api/v1/generation-runs/{runId}`。同项目已有活动 Run 时返回该 Run，其他项目已有活动任务时返回 409。

Run 新增 `mode=uploaded-media`、`errorMessage`、`output`、`audioMode`；本地计算费用尚未计量，`costCny=null`、`costStatus=unavailable`。每个 ShotRun 保存状态、Attempt、素材 ID 及成功后的 `artifactId`，不在处理前写 succeeded。

## 停止与重做

- `POST /generation-runs/{runId}/cancellation`：停止后不发布迟到结果；当前 FFmpeg 命令可能继续到结束/超时，不保证立即释放计算资源。
- `POST /generation-runs/{runId}/resumption`：继续失败、中断或已停止的本地任务，复用已经成功的片段。
- `POST /generation-runs/{runId}/shots/{shotId}/retries`：新增目标镜头 Attempt，重新处理后合成；未完成片段也需要完成才能交付整片。该接口现在返回整个 GenerationRun，不再返回伪造成功的单条 ShotRun。
- 成功片段和每次合成文件独立保存；重做期间清空当前最终产物指针，旧文件不覆盖。
- 源文件丢失/改变、解码失败、素材时长不足时写真实错误，不能回退到内置图片。

状态：`queued -> running -> composing -> completed`，可进入 `failed`、`cancelled`。服务重新启动后未完成任务标为 `interrupted`，由用户手动继续；旧无输入数据的测试任务不可重做。

## 单机边界

当前采用单个 FastAPI 进程、一个线程执行器、SQLite 与本地文件。只支持一个 API Worker，不能用多个 Uvicorn Worker 或多个服务实例共享同一个数据库执行任务。进程锁仅服务当前单机 MVP，不宣称分布式 exactly-once。

任务保存这次脚本、素材引用和输出参数，仅用于执行，不建设正式文档版本体系。服务优雅关闭会等待正在执行的 Worker，异常退出后需要人工恢复。图片/视频由 FFmpeg、ffprobe 处理，需本机可用的中文字形和 subtitles 滤镜。

测试通过 `VEDIOGEN_ALLOW_FAKE_PROVIDER=true` 显式启用文字 Fixture，`VEDIOGEN_ALLOW_EXTERNAL_MODELS=false` 禁止网关和 Admin 的真实模型调用。正常环境默认不启用 Fake。媒体执行不使用 Fake 视频路径。

真实视频 Provider、外部异步任务 ID/查询、Blender、TTS 仍未接入；这份契约不能作为这些能力或 80 分成片已经通过验收的证据。
