# 本地 Blender 环绕执行器 POC

状态：草案（独立脚本已实测，尚未接入平台生成任务）

## 目标与边界

为正确车型资产提供可重复的完整 360 度环绕路径。资产几何决定车辆外观，Blender 不负责从车型名称精确创造不存在的模型文件。本 POC 不改变原 `blender-3d` 未接通时的明确错误，不增加一个没有真实资产可用的生成按钮。

工具脚本：`scripts/local-video/blender-orbit.py`。

它接受本地 `.glb` 或显式 `--calibration` 校准模式。校准模式只建立三个不对称色块，禁止将输出登记成摩托车样片。GLB 模式缺少文件即失败，无默认车型、无图片缩放替代、无付费 API 兜底。

## 环境

- 便携目录：`D:/VedioGen-local/Blender/blender-4.5.13-windows-x64`。
- Blender 4.5.13 LTS，build `daeeeca98fb0`，EEVEE Next。
- 下载来源：`https://ftp.halifax.rwth-aachen.de/blender/release/Blender4.5/blender-4.5.13-windows-x64.zip`。
- ZIP SHA-256：`b5fdf800ce65fa2f209e8f68d02667e4d720fa1c42f247c72d1882ab04decba6`，匹配同发布目录 `.sha256` 清单。
- Windows 对 `blender.exe` 的 Authenticode 检查为 `Valid`，签名者 `Blender Foundation`。
- 官方主下载目录和在线 CLI 手册本次 HTTP 403；使用可访问发布镜像，实际 CLI 参数由本机成功执行验证。不以镜像可下载证明车型资产已存在。

便携安装不修改原工作软件，不向 Git 提交二进制或渲染帧。

## 执行契约

```powershell
D:/VedioGen-local/Blender/blender-4.5.13-windows-x64/blender.exe --background --factory-startup --disable-autoexec --python-exit-code 1 --python scripts/local-video/blender-orbit.py -- --asset PATH_TO_CONFIRMED_MODEL.glb --output EMPTY_OUTPUT_DIRECTORY --frames 96 --width 540 --height 960
```

此命令中的模型路径与输出目录是参数，不是仓库自带车型。工程校准时将 `--asset ...` 替换为显式 `--calibration`。

- 必须使用空输出目录，避免覆盖旧证据。
- 用 Blender 内置 glTF 导入器加载 GLB，保留材质；不从远程服务生成几何。
- 清除导入对象的动画与摄像机/灯光；此模板面向静态资产环绕，不承担骑手绑定或车辆行驶动画。
- 按模型包围盒统一位置、地面与尺度；完整主体优先，不为填满竖屏裁掉车轮。
- 采用中性地面、三盏面积光和固定俯角；包围球与实际画幅决定安全相机距离。
- 相机运动覆盖完整 360 度；每帧关键位置均校验所有包围盒角点在画面内。该检查证明几何边界不被画框裁掉，不证明材质、部件或车型身份正确。
- 输出逐帧 PNG、可检查的 `orbit.blend`、`orbit.json`；进度行格式 `VEDIOGEN_PROGRESS N/TOTAL`。
- `subjectConfirmed` 始终为 false；脚本不会自行为输入模型背书。
- FFmpeg 独立编码为 H.264 MP4；当前 POC 不生成音频，平台已有旁白合成能力尚未与此 POC 连接。

示例编码与浏览器验证：

```powershell
ffmpeg -nostdin -n -framerate 24 -i OUTPUT_DIRECTORY/frame-%04d.png -c:v libx264 -pix_fmt yuv420p -crf 18 -movflags +faststart OUTPUT_DIRECTORY/orbit.mp4
node scripts/local-video/verify-blender-orbit.mjs OUTPUT_DIRECTORY
```

当前浏览器验证器固定校验 540 x 960、24 fps 的 48 帧/2 秒诊断输出。96 帧是模板默认值，不应直接拿 2 秒验证器去断言更长输出合格。

## 实测范围

本机实际运行：校准场景 48 帧输出成功；随后只导出三个校准网格为 GLB，再通过真实 GLB 导入分支输出第二份 48 帧视频。二者都不是指定车型。

检查包括：解码帧数/尺寸/时长、不同角度像素差、首尾一致、所有帧几何画框边界、桌面和移动浏览器播放与截图。缺失 GLB 的真实执行退出码为 1，没有生成输出目录。

未验证：高面数真实车辆性能、贴图完整性、多资产规模、复杂骨骼动画、完整场景美术、服务内任务取消/超时/恢复。校准场景存在可见地面/背景边界，不能称为影视级棚拍模板。

## 接入前提

1. 平台获得准确车型资产，展示可辨认的参考预览并由用户确认版本。用户不需要自行制作模型，但资产缺口必须保留，不能随意换车。
2. 核查 GLB 外部依赖、自包含纹理、坐标/单位和静态几何。当前脚本不是用于执行任意不可信模型的隔离沙箱。
3. 在现有单媒体 Worker 接入受控命令、时间限制、停止/恢复、逐镜头结果，避免和 Wan 并发抢显存。
4. 后台配置 Blender 路径、可用资产与参数；创作端按分镜选择真实模型和运镜，再和现有旁白、字幕、合成下载连接。
5. 用两款目标车实际输出验收，不能以校准场景替代身份/运动质量评分。
