# 本地视频执行实现与实测记录

## 本轮推进

上一轮已经完成文字到参考素材的检索入口。本轮继续本地优先路径，不要求用户补照片、模型或购买视频服务。保留张雪 800X 与春风 800MT 的原始目标；本轮没有新车型样片。

已接入 ComfyUI 管理配置和 Wan 工作流适配，沿用原有图生视频、后台任务、单镜头重做与合成下载。完整契约见 [本地执行增量](../specs/local-comfy-video.md)。

## 实际安装

- 软件目录：`D:\VedioGen-local\ComfyUI`，独立 `.venv`，不改系统 Python、不把依赖或权重放进 Git。
- Python 3.12.3；ComfyUI v0.34.0、commit `12d5279438bfefc058a269eae805ceab6047777f`。
- PyTorch `2.14.0+cu130`，torchvision `0.29.0+cu130`，torchaudio `2.11.0+cu130`。版本来自本次官方 CUDA 索引实际解析；实际 GPU 张量运算成功，ComfyUI 可启动。不能仅由这三项版本号推断所有算子都兼容。
- 首轮 PyTorch 及依赖安装约 17 分钟，ComfyUI 其余依赖约 3 分钟；下载速度不代表推理速度。
- 服务 `http://127.0.0.1:8188`；启动时 PID 25012，后续以实际监听状态为准。
- 启动禁用 API 节点、自定义节点和视频元数据；采用 lowvram、2GB 显存预留、积极卸载。日志位于 `D:\VedioGen-local\ComfyUI\vediogen-logs`。
- 检测 GPU 为 RTX 4070 Laptop，8188 MiB 显存、约 16GB RAM；`torch.cuda.is_available()` 为 true，CUDA 上的实际 `torch.ones` 运算完成。

启动脚本：[start-comfy.ps1](../../scripts/local-video/start-comfy.ps1)。再次启动若端口已占用会拒绝，不会结束已有进程。

## 权重下载状态

模型来源采用官方 Comfy-Org 模板链接；Hugging Face 源站本次连接失败，镜像可查询元信息并间歇下载。镜像元信息中的 LFS SHA-256 用于完整性校验，未额外从独立渠道核验哈希，不能宣称镜像具备额外认证。

| 权重 | 预期大小 | 本轮状态 |
| --- | ---: | --- |
| Wan 2.2 TI2V 5B FP16 | 9,999,658,848 字节 | 首次约 85MB 后连接重置；续传又收到约 406MB，最终 `.part` 为 491,350,986 字节，不可用于推理 |
| UMT5 XXL FP8 scaled | 6,735,906,897 字节 | 未下载 |
| Wan 2.2 VAE | 1,409,400,960 字节 | 下载尝试连接超时，未就绪 |

三个文件合计约 18.1GB 十进制，不能把可用显存 8GB 与磁盘权重体积混淆。运行时 FP8 加载和 offload 是否足够，需要完整权重后验证。

[download-models.ps1](../../scripts/local-video/download-models.ps1) 支持逐文件、断点续传、超时、磁盘余量检查、完整大小与 SHA-256 校验。校验通过才把 `.part` 激活为 `.safetensors`；已有模型校验不通过则保留原文件并报错，不自动覆盖。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/local-video/download-models.ps1 -Model diffusion -Endpoint https://hf-mirror.com -MaxSeconds 900
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/local-video/download-models.ps1 -Model encoder -Endpoint https://hf-mirror.com -MaxSeconds 900
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/local-video/download-models.ps1 -Model vae -Endpoint https://hf-mirror.com -MaxSeconds 900
```

默认 endpoint 为官方源站；以上显式选择本次可部分访问的镜像，未发送任何 API Key。续传时先确认上次进程已经终止，不同时写同一 `.part`。

## 真实服务证据

1. 适配器实际调用 `/system_stats`、`/object_info`，确认 ComfyUI 0.34.0、CUDA 设备、核心节点存在，准确列出上述三项缺少权重。
2. 实际浏览器在 `http://127.0.0.1:3001/admin/video-settings` 保存本地配置，PUT 返回 200，点击检查看到三项缺失；保持**未启用**。原生实验尺寸设为 256 × 448，20 步。未修改 GPT 密钥或开启付费视频。
3. 截图位于 `.data/internal-mvp/local-comfy-admin-desktop.png` 和 `local-comfy-admin-mobile.png`，390px 视口无横向溢出。
4. 第一次真实 core 编码调用发现 SaveVideo 动态参数格式错误，并暴露 history/queue 读操作之间的竞态；根据服务源码及实际错误修复，补充回归测试。
5. 修复后真实编码任务 `ea8a13d4-8ab2-4e0d-82cb-87b8ce0c3c69` 完成，下载到 `.data/internal-mvp/comfy-transport-smoke.mp4`，64 × 64、1042ms，SHA-256 `4b68fb9d2e4eb93ba01cc26c317dc152053dbe18955022351aebd193f81e6384`。该文件是 25 帧纯色编码通道测试，**不是 AI 生成视频，不属于车型样片，不计入 80 分交付**。
6. 真实参考图上传和完整画幅试验任务 `b7e65cb0-29d2-4ada-8fa9-ff406019eafe` 完成。输入为仓库测试图片，未作为用户车型确认。输出 `.data/internal-mvp/comfy-reference-fit-smoke.mp4` 为单帧、256 × 448、42ms，SHA-256 `6d66b306035b46629ebe4929e7182517041557bbaf443a14d722cd03c3233a14`。仅证明上传、缩放填充及编码路径，不是运动或推理测试。

## 验证与剩余项

收尾 API 回归 62 项通过（2 项依赖弃用警告），Playwright 全套 7 项通过，Vitest 3 项、lint 与生产构建通过；`git diff --check` 通过，存在 Windows 行尾提示。隔离测试中的 ComfyUI 推理部分使用桩，真实服务测试仅证明本地通道、编码与缺失依赖检查。取消/恢复补充覆盖了恢复任务在 worker 开始前已取消时，仍定向取消其原有 ComfyUI 任务的情况。

下一步优先续传完整权重并校验，使用候选参考图做明确标为实验的 1 至 2 秒真实推理，检查 GPU 峰值、耗时、首帧与后续帧车型一致性。参考图选择仍由用户确认；工程试验不替用户确认版本。单张照片不能证明真实 360° 几何；Blender 正确车型资产、骑手驾驶、沙漠/涉水/无人机等硬镜头仍未完成。Goal 保持 active。
