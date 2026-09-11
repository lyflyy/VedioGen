# 本地 ComfyUI 视频执行增量

日期：2026-09-07。状态：全部权重已校验，真实 Wan 推理已运行；832 × 480 短镜头初步可用，完整成片画质未验收。

最新真实 GPT、下载与 GPU 编解码证据见[实测增量](../discussions/2026-09-07-local-inference-evidence.md)。顾问和分镜已接收当前执行后端及支持时长的配置上下文，配置不等于可用性或画质验证。

## 路线与依据

不新增独立业务平台，不复制 ComfyUI 节点编辑器。Creator 仍进行咨询、分镜确认、参考素材选择和逐镜头重做；Admin 选择执行方式。ComfyUI 只承担本机推理。

- [ComfyUI v0.34.0](https://github.com/Comfy-Org/ComfyUI/tree/v0.34.0)，本地固定 commit `12d5279438bfefc058a269eae805ceab6047777f`。
- [官方 Wan 2.2 TI2V 5B 模板](https://github.com/Comfy-Org/workflow_templates/blob/main/templates/video_wan2_2_5B_ti2v.json)。采用同一节点结构、24 fps、默认 20 步、CFG 5、uni_pc/simple、shift 8。实测后新任务恢复官方默认权重精度与普通 VAEDecode，使用 ComfyUI 内存调度；不再默认强制 FP8 和小分块解码。旧 FP8 任务快照保留原工作流，不静默改变已有任务语义。
- [服务源码](https://github.com/Comfy-Org/ComfyUI/blob/v0.34.0/server.py)：上传、指定 UUID 提交、任务历史/队列、指定 prompt_id 中断。
- [视频节点源码](https://github.com/Comfy-Org/ComfyUI/blob/v0.34.0/comfy_extras/nodes_video.py)：新版 SaveVideo 动态参数采用 `format=mp4`、`format.codec=h264` 的 API 平铺字段；输出历史在 `outputs.12.images`，不是 `videos`。

不依赖付费 API 节点、自定义节点、云 Key 或云端回退。大模型文本调用继续使用已有 GPT 配置，计费与视频执行分开。

## 配置契约

沿用 `/admin/video-settings` 页及 `GET/PUT /api/v1/admin/video-settings`，在原字段上增加：

| 字段 | 约束 |
| --- | --- |
| `backend` | `comfyui` 或 `fal`；旧配置缺字段按 fal 解释，避免改变历史任务语义 |
| `enabled` | 启用当前执行方式；默认关闭 |
| `localUrl` | 默认 `http://127.0.0.1:8188`；首版限显式回环 IP、HTTP、1024 至 65535 端口，不支持内网远端地址 |
| `width`, `height` | 新配置默认 832 × 480；256 至 832、32 的倍数、总像素最多 480 × 832。旧配置不自动覆盖。448 × 256 实测画面损坏，不能作为合格预览档位；横向实验不等于竖屏构图完成 |
| `steps` | 4 至 30，默认 20；降低步数不代表仍能达到相同画质 |
| `timeoutSeconds` | 300 至 7200，默认 3600；超时不自动重提 |
| `localCallsAllowed` | 只读，来自 `VEDIOGEN_ALLOW_LOCAL_MODELS`；默认 true，隔离测试 false |

`POST /api/v1/admin/video-settings/local-probe` 检查**已保存**的本地地址。返回 `ready/missing/version/devices/verification`，验证范围为服务与模型清单，不执行生成、不证明权重完整或 GPU 推理成功。要求 ComfyUI 至少 0.34.0，以支持当前任务 ID 和定向取消约定。

保存配置不启动下载，也不调用模型。后台本地模式不要求视频 Key、USD 单价或预算，云端规则保持原样。切换不会修改已有任务快照，不会自动降级到云端。

## 镜头与执行

- 继续使用 `sourceStrategy=image-to-video`，按照创建任务时的 `backend` 路由。
- 本地支持 0.5 至 5 秒的剪辑时长（可为小数秒）；平台按 24fps、4n+1 帧向上对齐模型输入，再在合成时裁回原始剪辑时长。云端继续 5/10 秒。参考图来自本项目已上传或用户确认导入的 JPEG/PNG，最多 10MB。
- `videoPrompt` 必填、最多 2500 字。原图校验值与可解码性在使用前检查。
- 原生帧数按 `ceil(durationMs * 24 / 4000) * 4 + 1`，确保 Wan 的 4n+1 帧约束且覆盖分镜时长。
- `fit=contain` 先按比例缩放并填充到原生画幅，保留完整参考车体；`cover` 才居中裁切。不再让 Wan 默认直接裁切横图为竖图。填充区域仍可能影响模型效果，需要实测。
- 本地生成返回 `mode=local-ai-video`，USD 估算为 null，不表示运行总成本为零。
- 新任务快照模型 ID 为 `wan2.2-ti2v-5b-fp16`；历史 `wan2.2-ti2v-5b-fp8-runtime` 快照继续原精度和分块解码。
- 任务记录原生宽高、随机种子、prompt_id、状态和本次等待耗时。最终 1080 × 1920 是合成输出尺寸，不宣称原生生成达到 1080P。
- 生成后通过 ComfyUI `/view` 获取 MP4，限制 200MB，计算 SHA-256、ffprobe 验证，检查片段长度后进入已有 FFmpeg 转码/字幕/音轨合成。片段不足不静帧补足。

## 恢复与取消

单进程媒体执行器继续串行工作，避免平台内多个推理争抢显存。平台不排他控制用户从 ComfyUI 界面手动提交的其他任务。

1. 在 POST `/prompt` 之前持久化指定的 UUID 和提交意图。
2. 网络不确定时恢复只查询相同 ID，不盲目重新提交。
3. 查询先读 history，再读 queue；若均未找到，重新读一次 history，处理任务恰好结束的竞态。
4. 本地服务重启或历史被清理时明确报告找不到任务，用户核对后才能手动重做。重做前查询原任务，仍在运行或排队时拒绝重提。
5. 取消在 worker 观察到请求后调用 `/queue` 删除本任务，再调用带 `prompt_id` 的 `/interrupt`；不发送全局取消。网络错误时不声称上游已停止，晚到结果不发布。
6. 未完成的上游句柄仍阻止绕过原任务创建同项目新任务；使用继续/镜头重做进行处理。

## 验证范围

- 隔离 API 测试：地址约束、配置、缺权重失败、生成计划、原图构图、指定 ID、查询竞态、重做、真实视频字节下载校验与 FFmpeg 合成。模型生成响应使用桩。
- 隔离 Playwright：本地/云端配置切换、保存、刷新恢复、禁止访问本机 GPU 的状态、桌面与手机布局；不执行真实模型。
- 实际服务：ComfyUI GPU 启动、完整权重校验、管理界面探测、真实 VAE 与文本编码器，以及四组短视频推理。832 × 480、2 秒、默认精度/普通解码一组等待约 93 秒；其他低分辨率实验失败的画面也保留为证据。
- 尚缺：稳定原生竖屏构图、跨种子输入保真/可用运动、长镜头资源表现、两款车型关键镜头和用户至少 80 分验收。采样显存不是严格峰值，单次耗时不是日更 SLA。
