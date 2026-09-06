# 2026-09-05 P0 本地垂直切片开发结果

- 状态：已实现并自动验证
- 范围：单用户、本地运行、Fake Provider、摩托车内容包
- 入口：Creator `/projects`；Admin `/admin/model-providers`

## 本轮实现

Creator 已打通以下流程：

1. 输入自然语言创意，可附加图片或视频。
2. 文件经 SHA-256 校验后保存为项目 AssetVersion。
3. `creative-advisor` 通过已发布的能力路由选择 Deployment，由 Fake Provider 生成三个可比较方向。
4. 用户选择方向并确认 Creative Brief。
5. 生成、编辑、排序并确认五镜头 Storyboard。
6. FFmpeg 将车型细节图和骑行图确定性合成为 540x960、30fps、6 秒 H.264/AAC MP4。
7. 成片页播放、展示媒体元数据并提供下载。

Admin 已实现 Provider、加密 Credential、Deployment、能力探测、Routing Draft、验证/发布、Playground 和 Invocation 追踪。业务调用保存实际路由版本、Deployment、Credential 引用、Token、耗时和成本；API Key 原文不进入数据库元数据、响应、DOM、Web Storage 或调用详情。

本地默认使用 SQLite。`docker-compose.yml` 提供 PostgreSQL 17 开发选项，文件和密钥由本地适配器保存，后续可替换为对象存储和 Secret Manager。

## 自动验证结果

2026-09-05 本机验证：

- FastAPI/Pytest：4 项通过，覆盖 Creator、Admin、上传、路由调用、单镜头重试、下载和双次媒体哈希一致性。
- Vitest：2 项组件状态测试通过。
- ESLint：通过。
- Next.js 生产构建与 TypeScript：通过。
- Playwright：3 条 Edge/Chromium E2E 通过，覆盖 Creator、Admin、1440/1024/390/320 视口、横向溢出和 Axe Critical/Serious 检查。
- OpenAPI：Redocly recommended 严格 lint 通过。
- 媒体探针：H.264 540x960 30fps、AAC 48kHz mono、6.000 秒；两个时间点抽帧均非空且主体裁切可用。

## 当前边界

这次结果是可运行的 P0 技术垂直切片，不代表完整生产平台已经完成：

- Fake Provider 验证了配置、切换、密钥引用和追踪契约；尚未接入真实 LLM、搜索、图片或视频生成平台。非 Fake Adapter 会明确返回不支持，不伪造真实调用结果。
- 成片使用代表性摩托车图片验证合成链路，不声称图片为张雪 800X 或春风 800MT，也不是 Blender 影视级车辆资产。
- 上传意图保存在单进程内存，文件保存在本地目录；多实例部署前需替换为共享对象存储与持久化上传会话。
- 任务当前同步执行；生产版需要 Worker、重试队列、进度事件和可恢复执行。
- SSE 当前只提供快照与心跳，前端生成页尚未消费镜头级事件。
- 完整 P0 计划中的真实 Provider、育儿内容包契约、Blender 探针和人工质量评分仍未完成。

## 下一开发批次

1. 接入一个真实中文 LLM Adapter，并用同一 Fixture 与 Fake Provider 做契约对照。
2. 将 Advisor、Storyboard 和媒体生成迁入可恢复 Worker，前端接入 SSE 进度。
3. 增加素材分析与车型一致性评估，再接图片/视频生成 Provider。
4. 建立真实车型资产规范和 Blender 探针，不把代表性参考图当作车型保真证据。
5. 用育儿内容包验证平台核心不泄漏摩托车字段和 UI 文案。
