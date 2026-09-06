# 真实 GPT 接入与执行结果

- 日期：2026-09-05
- 状态：已验证 LLM 链路；视频生成待接入

## 本轮输入

项目方提供自有 OpenAI-compatible 中转站和 API Key，要求平台不再停留在 Fake Provider 与静态页面，而要从上传照片、文案到模型策略和脚本真实执行。

密钥只进入本地加密 Secret Store。源码、文档、数据库业务字段、API 响应和日志均不记录明文。该 Key 曾在聊天中出现，完成当前验收后应在管理后台轮换。

## 已完成

1. 复现“无法点击下一步”：旧 Next.js dev 进程没有完成 React 水合，文本写入 DOM 后状态仍为 0，按钮持续 disabled，网络没有 `POST /projects`。重启干净 dev 服务后恢复。
2. 新建项目显示创建、文件哈希、上传和进入 AI 分析的明确进度；上传失败返回文件名、HTTP 状态和服务端 detail。
3. 实现 OpenAI-compatible `/models`、`/chat/completions`、Bearer 鉴权、图片 data URL、严格 JSON Schema、超时和脱敏错误。
4. `creative-advisor` 与 `storyboard-generator` 均通过版本化路由调用真实 `gpt-5.4-mini`。
5. 管理后台 Credential/Deployment/Playground 探测均执行真实请求；Deployment 只有真实结构化输出成功后才进入 `ready`。
6. 调用记录增加实际模型和 Provider Request ID；自动测试增加适配器 MockTransport 契约。
7. 修复刷新已有策略页重复触发 Advisor 的费用缺陷；补充消息输入框已接通重新生成流程。
8. 真实视频 Provider 缺失时，生成页禁用“开始生成”，API 返回明确 409；不会再把内置图片预览标成真实生成。

## 真实验收结论

同一真实项目已经持久化一张用户图片，并成功生成三个策略方案、Creative Brief 和五镜头 Storyboard。真实模型能返回旁白、字幕、镜头描述以及 `blender-3d`、`image-to-video`、`generated-video` 等素材策略。

普通 GPT 多模态接口完成的是理解和规划，不输出 MP4。当前中转站的鉴权模型清单没有发现视频模型，因此下一步必须选择视频 Provider，或由中转站明确提供视频任务端点、模型 ID、请求/轮询/下载协议和测试额度。

## 下一决策

- 首个视频 POC 只做一个 5 至 8 秒图生视频镜头，先测车型一致性、耗时和单次费用。
- 项目方需给出视频 Provider 或确认中转站的视频 API 文档。
- 一张图只能做视觉环绕感；要求真实另一侧结构时需要多角度照片、环车视频或可用 3D 资产。
