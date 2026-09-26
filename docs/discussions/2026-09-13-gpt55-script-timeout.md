# GPT-5.5 脚本超时排查与真实验收

## 用户报告与证据

用户报告生成脚本持续提示 GetTokens GPT / gpt-5.5 模型调用超时。项目为 `12747bf9-bf8c-4766-b371-16a41f901dc8`。

最近三次 storyboard-generator 耗时为 120452、120615、120592ms，均为 TIMEOUT；同一模型的 asset-planner 分别在约 13 至 19 秒成功。项目没有图片，文字输入约 1.2KB，因此不是本次图片体积造成的上传等待。

## 实际对照

1. 将真实部署 `217777e3-04d4-475e-83bf-162078197acc` 的 timeoutSeconds 从 120 调为 300，保持 gpt-5.5、Key、地址、路由不变。探测通过，请求 ID `f8d90a4f-bf1c-47ce-9a3c-09bda06215b1`。
2. 原非流式脚本重试约 125.5 秒收到 Cloudflare HTTP 524，错误页明确 origin web server timed out。CF Ray `a3a688747dc2e367-NRT`；不是本地 300 秒超时。仅增大本地等待不够。
3. 改用流式接收后，从原项目 Brief 页点击“确认并生成脚本”，真实 gpt-5.5 输出完整分镜并保存，页面自动进入 storyboard。

成功调用证据：

- 调用 ID：`7183f787-6e4b-4351-8566-90c1a415817f`。
- 上游请求 ID：`2db1b648-7843-4d47-a1d1-e423b24d3288`。
- 实际模型：`gpt-5.5`；耗时 131432ms；输入 2123 Token，输出 4755 Token。
- 分镜文档 ID：`6d762383-095f-4e90-8683-4d2ef00d3199`。
- 产物：6 个镜头，总时长 12000ms；素材仍待准备，不宣称视频已经生成。

## 实现与验证

新增 `httpx-sse` 依赖，脚本按流式接收，仅聚合实际答案，收齐后沿用 JSON 与业务 Schema 校验。保留非流式兼容，拒绝部分结果、长度截断和未正常结束的流。超时错误展示阶段、上限、耗时和接口。

自动化覆盖分片聚合、Token/模型记录、断流拒绝、流内错误脱敏/冷却、心跳预算及分阶段超时。分镜浏览器两项回归通过；真实项目的页面回显和 Markdown 导出另行执行成功。

最终 API 全量 261 项通过；测试依赖仍有 2 条弃用警告。服务更新前确认没有活动模型、素材或视频任务，检阅 Web 3001 / API 8001 保持运行。

实际产物与截图：

- `.data/internal-mvp/model-configuration/streamed-storyboard-export.md`，已核查六个镜头段落。
- `.data/internal-mvp/model-configuration/streamed-storyboard-desktop.png`。
- `.data/internal-mvp/model-configuration/streamed-storyboard-mobile.png`，390px 无横向溢出。

浏览器首次验证脚本生成完成后，辅助脚本使用了错误的页面标题定位而失败；修正为实际“6 个镜头”标题，只读复查并导出通过，没有再次生成脚本。

本轮访问 OpenAI 官方 gpt-5.5 页面返回 Forbidden，未据不可访问文档推断模型默认推理参数。保留用户模型，不通过盲目切换模型或无限重试规避故障。完整流式契约见 [脚本生成流式接收](../specs/storyboard-streaming.md)。
