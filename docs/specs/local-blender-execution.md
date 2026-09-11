# 本地 Blender 环绕执行

日期：2026-09-07。状态：MVP 已接入并有真实工程渲染证据。此规格取代“Blender 仅为独立 POC”的执行状态，不代表指定车型资产已经准备好。

## 范围

- 用户仍可只输入文字。准确 GLB 的搜集/制作由平台侧承担，不能要求创作者自行建模。当前提供将已准备好的 GLB 导入项目的操作入口，尚未实现自动生成准确车型几何。
- 采用 Blender 4.5 LTS Python API 与 EEVEE，复用此前校准环绕脚本，作为服务包内的 `blender_scene.py`。旧 CLI 入口仍保留兼容转发。
- 仅支持静态主体完整 360 度环绕。骑手、路径驾驶、沙漠、水体、抬头和植被航拍不是此模板能力，不隐式改写为环绕。
- 不引入 Blender UI 嵌入或新渲染队列。运行于现有单媒体队列，与平台 ComfyUI 镜头串行。

## 管理配置

沿用 `GET/PUT /api/v1/admin/video-settings`，新增字段：

```json
{
  "blenderEnabled": false,
  "blenderExecutable": "",
  "blenderTimeoutSeconds": 1800
}
```

Blender 开关独立于图生视频 `enabled/backend`。超时 60 至 7200 秒；启用时必须配置现存 Blender 可执行文件绝对路径。保存配置只检查路径，不自动渲染。管理页还提供 `POST /api/v1/admin/video-settings/blender-probe`，仅执行 `--version`，返回版本与 `verification=executable-only`，不等于渲染/画质通过。

`VEDIOGEN_ALLOW_LOCAL_MODELS=false` 时禁止版本探测和渲染，隔离 E2E 不访问真实 Blender/GPU。GPT 执行上下文暴露 Blender 开关、调用许可、模板和时长范围，不发送可执行文件路径或密钥。

## GLB 与镜头

沿用上传意向和内容 PUT，增加 `mimeType=model/gltf-binary`，扩展名 `.glb`，50 MB 上限。上传后 `kind=model`，记录文件哈希、网格数和 `subjectConfirmed=false`。

上传校验 GLB 2.0 头、JSON/BIN 分块、网格条目和内嵌 buffer；禁止任意 URI 引用，纹理需内嵌。此检查只是传输与结构预检，不证明几何正确，具体网格可渲染性仍由 Blender 验证。失败不写入项目素材数组，也不补默认模型。

分镜字段：

```json
{
  "sourceStrategy": "blender-3d",
  "sourceAssetId": "项目内的 GLB 资产 ID",
  "blenderTemplate": "orbit-360",
  "durationMs": 3000
}
```

必须明确选择模板，不能仅因旧分镜含 `blender-3d` 就执行环绕。时长为 1 至 10 秒的整数秒。预览 540 x 960，标准输出 1080 x 1920，30 fps。相机覆盖完整 360 度，几何按包围盒居中并逐帧检查画框；相机、灯光与输入动画不直接沿用。

采用 GLB 实际导入，不设置平台侧 calibration 参数。注意报告 `calibrationOnly=false` 仅表示从文件导入，而非使用内置方块生成模式，不能推导该文件一定是真实车型。真实工程测试导入的是明确标注的校准 GLB。

## 任务与恢复

- 使用现有 generation-runs、shot-preview、adoption、retries、resumption 与 cancellation。纯 Blender 任务 `mode=local-blender`；混合图生视频沿用原 AI 模式及费用确认，具体镜头 strategy 仍可区分。
- 命令无 shell 拼接，后台执行，禁用自动脚本；只执行服务自带场景脚本。
- 启动意图先持久化，再保存 PID、进程创建时间及帧目录。通过 psutil 检查 PID 与创建时间一致，避免误杀复用 PID 的其他进程。
- 试片页显示已渲染/总帧数。全部帧与报告匹配后才编码 MP4、创建产物；场景文件、PNG、报告和日志保留在运行目录用于诊断。
- 服务重启后原进程仍活跃时，恢复任务继续观察原进程；已完成且匹配的帧可直接编码。不因一次观察超时自动重复启动。
- 发现任何既有 Blender 进程仍运行时，拒绝创建另一个平台生成任务或重做该镜头；可恢复或停止原任务。只管平台已记录进程，不声称管理用户在平台外手动启动的 GPU 作业。
- 取消/超时终止对应进程，已完成片段保留，不能发布取消后的晚到结果。中断的 Blender 任务也可请求停止。手动重做会建立新尝试与新帧目录。
- 启动意图已记录但无 PID/完成报告的极小崩溃窗口，返回“启动结果不明”，需核对本地进程，不能宣称自动恢复无歧义。
- 恢复已被停止且无完整报告的尝试会明确失败；重新渲染使用“按原参数重做”，不将残缺帧当完成。

## 验证与边界

隔离测试覆盖 GLB 拒绝、配置、进程身份、孤立活动进程阻止重做、取消/超时、完整帧复用、混合合成与手动重做。真实浏览器另验证管理配置、真实 GPT、GLB 上传、90 帧 Blender 渲染、试片采用、合成、播放、下载。

没有跨进程多 worker 队列、生产集群调度或 GLB 内容级隔离沙箱。模型、贴图、场景渲染的内存开销仍需逐资产实测；50 MB 文件限制不等于显存预算保证。

真实证据和发现的输入/分镜缺陷见 [实现记录](../discussions/2026-09-07-platform-blender-implementation.md)。两款指定车型的外观资产、驾驶镜头与 80 分人工验收保持未完成。
