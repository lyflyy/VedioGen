# P0 视频与渲染输出规格 v0.1

- 状态：待项目方评审
- 版本：0.1
- 日期：2026-09-05
- 负责人：待指定
- 平台：抖音优先，下载 MP4

## 1. 输出档位

| 项目 | Preview | Final |
| --- | --- | --- |
| 画幅 | `9:16` | `9:16` |
| 分辨率 | `540 x 960` | `1080 x 1920` |
| 帧率 | 30fps CFR | 30fps CFR |
| 视频 | H.264, yuv420p | H.264 High, yuv420p |
| 音频 | AAC, 48kHz | AAC-LC, 48kHz, 192kbps |
| 容器 | MP4 + faststart | MP4 + faststart |
| 字幕 | 硬字幕 | 硬字幕，可选保留 SRT Artifact |
| 色彩 | Rec.709 | Rec.709 |

Preview 用于确认构图、节奏和字幕，不作为最终质量判断。用户上传与 Provider 输出统一归一化后再进入时间线。

## 2. 时间线

- 时间单位为整数毫秒，最终按 30fps 对齐到帧。
- 视频使用恒定帧率；禁止把可变帧率素材直接拼接。
- Shot 总时长必须等于 Storyboard 总时长；最终误差不超过 1 帧。
- 转场计入相邻 Shot 时长，不能使总时长悄然增加。
- 默认总时长 20 至 30 秒，Schema 支持 5 至 60 秒用于后续扩展。

## 3. 视频编码

Final 基线：

```text
codec: libx264
profile: high
pixel format: yuv420p
rate control: CRF 18-22（P0 默认 20）
preset: medium
GOP: 60 frames
movflags: +faststart
color primaries / transfer / matrix: bt709
```

不能使用只在特定设备可解码的像素格式作为默认交付。Provider 输出即使是更高分辨率，也按已批准 Profile 统一缩放与裁切。

## 4. 构图与裁切

- 默认 `cover` 适配竖屏；关键主体必须受 Shot 的安全构图约束。
- 不允许无提示拉伸画面。
- 横屏用户素材优先智能裁切；无法保持主体时使用背景扩展或 `contain`，并在预览中显示。
- 车型整车镜头保留轮胎、车头和车尾，不让界面安全区裁掉主体识别特征。

## 5. 字幕安全区

P0 采用可配置的保守默认区，不声称是平台永久固定规则：

- 左右至少 90px。
- 顶部至少 160px。
- 底部至少 320px。
- 重要车型名、CTA 和多行字幕不得进入安全区外。
- 单行优先；最多两行，不能遮挡当前镜头主要机械细节。
- 字体、字重、字号、描边和行高在 UI 设计实现时建立视觉基线截图。

平台 UI 变化时只更新 Profile，不修改 Storyboard 文案。

## 6. 音频

- 中间 TTS 优先 WAV/无损，最终编码 AAC-LC 48kHz。
- Final 内部建议目标：综合响度 `-14 LUFS ± 1 LU`，True Peak 不高于 `-1 dBTP`；需通过首批样片听感确认。
- 旁白优先于音乐；发动机与环境音可在无旁白段提高，但不能造成削波。
- 无旁白模式仍必须检查是否存在有效音乐/环境音，除非 Brief 明确静音。
- 合成前对不同来源音频重采样，避免时间轴漂移。

## 7. FFmpeg 合成顺序

1. 探测所有输入并拒绝损坏文件。
2. 统一旋转元数据、SAR、帧率、色彩和时间基。
3. 按 Shot 裁切、缩放和补帧。
4. 合成转场和视觉层。
5. 混合 TTS、环境音和音乐，执行响度处理。
6. 渲染硬字幕和 Logo/文字层。
7. 编码临时文件，完整解码检查。
8. 写 `+faststart` 成片并生成最终 Hash/ffprobe 报告。

合成失败不重新生成成功 Shot。

## 8. Blender Profile

Blender 当前未安装，以下为探针约束而非已验证参数：

- 固定 Blender 稳定版本、插件、字体、OCIO 和 GPU 驱动。
- Preview 使用 Eevee 或低采样 Cycles；Final 候选为 Cycles。
- 首选输出 PNG/EXR 图像序列，不让 Blender 直接编码最终 MP4。
- Motion Blur、景深和采样必须属于 Scene Template 白名单。
- 渲染前检查摄像机、缺失纹理、材质、帧范围、显存估算和输出目录。
- POC 记录 Preview/Final 构图偏差、每帧耗时、峰值显存和噪点。

具体 Cycles Samples、Denoiser 和 EXR 通道在安装 Blender 并完成同场景基准后冻结，不能预先猜测。

## 9. 自动验收

Final 必须满足：

- MP4/H.264/AAC，可从头到尾完整解码。
- `1080 x 1920`、30fps CFR、Rec.709、yuv420p。
- 时长与批准 Storyboard 误差不超过 1 帧。
- 有视频流和符合 Brief 的音频状态。
- 无连续异常黑帧、长冻结帧、削波和字幕越界。
- 编码日志、ffprobe JSON、质量报告和 SHA-256 Artifact ready。

## 10. 待评审项

1. 是否接受 Preview `540 x 960` 与 Final `1080 x 1920`。
2. 是否接受 Final 默认 CRF 20，视觉基准后允许在 18-22 调整。
3. 是否接受内部音频目标 `-14 LUFS`；这不是平台强制公开标准。
4. 字幕默认安全区需要在 UI 原型截图中最终确认。
5. Blender Profile 等实际安装和基准完成后再升为已接受。
