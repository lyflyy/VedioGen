# VedioGen

面向抖音等内容平台的 AI 辅助短视频创作平台。目前处于产品发现与技术验证阶段，首期以摩托车为垂直方向：AI 先帮助用户选择内容策略并确认脚本/分镜，再通过用户素材、生成式媒体、可控 Blender 3D 和确定性合成生成竖屏视频。

当前仓库用于企业内部 MVP：已有 GPT 咨询接入，以及真实上传图片/视频的后台处理、片段预览/重做、字幕、可选背景音频与竖屏 MP4 合成。AI 视频 Provider、Blender 和 80 分样片仍未验收，不能把上传图片运动当作 AI 驾驶视频。

新增可选 fal / Kling 图生视频适配器和 `/admin/video-settings` 管理页，默认停用；接线及模拟上游测试不代表真实模型已验证。配置步骤、费用确认与恢复限制见 [图生视频执行契约](docs/specs/internal-video-execution.md)。

视频执行页现支持切换本地 ComfyUI / Wan 与可选云端 fal。全部本地权重已校验，真实 GPT、GPU 短镜头生成、页面确认、FFmpeg 合成及浏览器下载已完成工程验证；竖屏构图、完整 360 度和 80 分样片仍未验收。见 [本地执行契约](docs/specs/local-comfy-video.md) 与 [真实推理及平台实测](docs/discussions/2026-09-07-local-inference-evidence.md)。隔离测试同时禁用 `VEDIOGEN_ALLOW_LOCAL_MODELS`。

项目“资料”页新增文字到参考素材准备：GPT 提取主体、免 Key 图片搜索、用户确认后下载入库。检索不代表已找到准确 3D 模型；见 [参考素材契约](docs/specs/text-reference-preparation.md)。隔离测试设置 `VEDIOGEN_ALLOW_EXTERNAL_SEARCH=false`。

## 本地运行

环境要求：Node.js 20+、Python 3.13+、[uv](https://docs.astral.sh/uv/)、FFmpeg/ffprobe，以及可用的中文字幕字体与 subtitles 滤镜。媒体 MVP 使用单个 API 进程，不启用多个 Worker 共用数据库。

```powershell
npm install
uv sync --project services/api
npm run api:dev
```

另开终端启动 Web：

```powershell
npm run dev
```

打开 `http://localhost:3000`。默认使用 SQLite，真实模型通过 Admin 配置。Fake 不再默认启用；无费用文字演示需显式设置 `VEDIOGEN_ALLOW_FAKE_PROVIDER=true`，隔离测试同时设置 `VEDIOGEN_ALLOW_EXTERNAL_MODELS=false`。素材可上传或由文字检索后确认导入，并在分镜中选择，不能空素材生成固定测试片。

本次隔离试用入口为 `http://127.0.0.1:3001`，数据位于 `.data/internal-mvp/`，不与原环境同步；见[本轮实现记录](docs/discussions/2026-09-06-mvp-media-implementation.md)。

## 验证

```powershell
npm run api:test
npm run lint
npm run test
npm run build
npm run test:e2e
```

Playwright 默认使用本机 Microsoft Edge，独占 3107/8107 测试端口，不复用正在运行的服务。端口被占用会失败；CI 使用文字 Fixture 和真实本地素材合成，不调用付费 Provider。产品规格、架构决策、研究记录与计划统一维护在 [docs/README.md](docs/README.md)。
