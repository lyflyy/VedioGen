# 仪表保真特写：本地图片运动对照

日期：2026-09-07。用户输入仍只有文字，原始参考由平台前序官网检索取得。本轮复用已有工程项目、GPT 分镜和官网图片，没有要求用户上传，没有新调用 GPT、Wan 或付费图片/视频 API。

## 方法与结论

此前 Wan 仪表试片后段凭空生成手部，小字漂移且竖屏填充过多。此次通过已有页面选择“图片运动”，裁剪官网仪表图为竖屏，用现有 FFmpeg 轻推镜输出，未增加新视频供应商或渲染引擎。

- 工程验证通过：真实页面裁剪、保存、仅第三镜头试片、刷新、解码播放、下载；其余四个镜头的数据完全不变。
- 视觉检查：0.05、1.5、2.9 秒抽帧保留原图的 0、N 和右侧转速刻度，没有新增手部；成片画面没有此前横图 contain 造成的大块填充。网页播放器两侧的黑色区域不在竖屏视频文件中。
- 限制：源裁剪只有 455 x 810，输出放大不能增加真实细节；6% 轻推镜末端右侧外框略有裁切，仪表读数区域仍在画面内。原图的样例读数也被保留，不是骑行遥测或真实变化的转速。
- 不代表骑行动作、完整 360 度、沙漠、涉水抬头或航拍已经完成，也不代表整片达到 80 分。没有采用本次试片为正式成片，没有生成 finalArtifact，没有修改项目完成状态。
- ES 仍只是工程参考版本，未将它视为项目方已经确认的正式春风车型。张雪 800X 没有用其他车型替代。

## 可复查证据

工程页面：<http://127.0.0.1:3001/projects/3c21b6ed-7fbd-4a4e-a38d-4983f26340ff/storyboard>，第三镜头。

| 项目 | 实测值 |
| --- | --- |
| 原参考资产 | `1a3fd82b-a570-42c7-a70a-525cbee814db` |
| 原图 | <https://cfimages.cfmoto.com/cfmoto/2_13f851b7f7.jpg>，出处 <https://www.cfmoto.com/motorcycles/800mt-es> |
| 新裁剪资产 | `1d94cf38-44a1-4a50-a701-ba3e0003a592`，455 x 810；保留 sourceAssetId |
| 裁剪 SHA256 | `e091e62328fd985817bd55a78c3204221a83c9fe4f49c8da8ce7bdbad88b3033` |
| 试片任务 | `acfe1a13-3276-448a-9bae-eddc25b2039b`，shot-preview / uploaded-media / image-motion |
| 视频产物 | `f0ad2703-2a23-4e43-8e4c-2db37a4e4a52` |
| 下载 SHA256 | `cd1dfca5f0ed18adbf34fd6390f03fa9df3b6be977b4a58e306e5909e9f3daca` |
| ffprobe | H.264，540 x 960，30 fps，3.000 秒，179622 字节；AAC 标准化静音轨，无旁白/音效 |
| 三帧像素检查 | 非空，红通道方差均超过 7400，三个 PNG 哈希不同；只证明非空/帧变化，不是画质自动评分 |
| 项目状态 | activeGenerationRunId=null，generationReadiness.ready=false，五个分镜保留 |

证据目录：`.data/internal-mvp/instrument-motion-1788742883252/`，包括 `result.json`、`preview.mp4`、三张帧图、裁剪截图和桌面/手机截图。旧失败 Wan 产物继续保留，便于对照。

## 浏览器发现的缺陷

隐藏的素材上传 input 使用绝对定位，却没有定位父级和稳定尺寸。分镜表单的 width:100% 规则使其超出视口，桌面横向检查失败。

修复为上传 label 内定位、1 像素裁切的隐藏 input，并为键盘焦点添加 label 焦点框。第一次修复仍被后置表单选择器覆盖；新增回归断言发现后，使用限定 file 类型的选择器解决，未用全局 overflow-x:hidden 掩盖溢出。

真实脚本通过 `INSTRUMENT_MOTION_REPORT` 恢复同一个任务，没有因 UI 断言失败重新渲染。脚本禁止模型生成类请求，并检查当前镜头的执行模式非 AI 视频。工程项目只新增一次图片运动试片。

## 重放与下一步

本轮验证：Playwright 全量 9 passed（48.5 秒）；单镜头专项在修复后另一次通过；TypeScript 检查和真实验证脚本语法检查通过。隔离 E2E 使用 fixture 模型，但媒体测试实际运行 FFmpeg，不代表模型画质通过。3001 工程页面另行完成真实参考裁剪、播放、下载和三帧像素检查。结束时 ComfyUI running/pending 均为空。后端代码本轮没有修改，未重跑 API 全量测试。

```powershell
$env:RUN_INSTRUMENT_MOTION='1'
$env:INSTRUMENT_MOTION_REPORT='.data/internal-mvp/instrument-motion-1788742883252/result.json'
node scripts/local-video/verify-instrument-motion.mjs
```

重放读取既有任务，不重做模型调用。去掉报告参数会开始新的独立本地图片运动实验，仅用于明确需要重新验证时。

后续应按镜头选择工具：仪表/标识优先保真素材与确定性运动；真实 360 度需要可信指定车型几何或匹配的实拍环绕；骑行类需针对动作逐镜头验证本地模型。不能因为仪表对照成功就把其他难镜头改成照片推拉。正式春风版本仍待确认，下一步优先解决车型身份与整车环绕资产，而非继续堆叠仪表实验。
