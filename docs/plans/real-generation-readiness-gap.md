# 真实模型与视频生成执行差距

> 当前执行优先级见[企业内部 MVP 计划](2026-09-06-internal-mvp-reset.md)：先验证关键真实镜头和 80 分成片，本文 Gate 不再要求完整治理全部完成后才接视频。

- 状态：Gate 0 有历史入口验证；Gate 1 部分完成，需补事实、确认与契约验收；Gate 2 等待视频 Provider 及持久任务实现
- 日期：2026-09-05；2026-09-06 复核修订
- 适用范围：用户照片与文案生成可交付摩托车短视频

## 1. 现场核查结论

2026-09-06 修订：真实 GPT 调用成功不等于本文件 Gate 1 全部完成。事实仍由 Fixture 创建，Brief 为确定性编译，分镜运行结构尚未对齐中央契约；确认约束、任务恢复、Fake 隔离和错误脱敏也有缺口。详见[架构复核](../architecture/2026-09-06-architecture-review.md)。以下保留历史调用证据，不能据此宣称生产闭环已完成。

首次核查时实现是技术垂直切片，不是真实 AI 生成链路。2026-09-05 完成整改后的状态如下：

- 正常 Creator 页面已经持久化用户项目和一张 350,216 字节 JPEG，AssetVersion 状态为 `ready`，刷新后可恢复。
- 已实现 `openai-compatible` Adapter；Creative Advisor 和 Storyboard Generator 均通过发布路由调用真实模型。Fake 预期只用于测试/演示，但运行时尚未强制隔离。
- Credential 探测真实请求 `/models`；Deployment 探测真实执行最小严格结构化生成，失败不会标记为 `ready`。
- 成功创意/分镜调用记录保存实际模型、Provider Request ID、Token 和耗时；正常路径不写密钥，但供应商自由文本错误的脱敏尚不可靠，异常调用的用量也可能丢失。
- 新建项目入口加入创建、哈希、上传和进入分析的分步进度；此前观察到开发页面未水合，不能据此排除长请求、代理超时等其他流程故障。
- 生成阶段仍没有图片/视频生成 Provider。生产路由现在会在此处明确阻断，不再把内置图片 FFmpeg 预览冒充真实成片；Fake 测试环境保留确定性媒体检查。
- 上传文件只保存在本机。多数云端视频模型无法访问 `localhost`，需要对象存储和短期签名 URL，或使用支持直接文件上传的 Provider。
- 生成任务当前同步执行，没有真实视频任务所需的队列、轮询、取消、超时恢复和 SSE 进度。

## 2. 真实执行所需能力

最小可用链路分为四层：

1. 多模态理解：读取用户照片和文案，提取车型、颜色、角度、可见部件和缺失事实，并输出结构化 Project Facts。
2. 创意与脚本：根据已确认事实生成 Proposal、Creative Brief、旁白、字幕和 Storyboard。
3. 媒体生成：针对每个 Shot 调用 image-to-video 或 text/image-to-video Provider，轮询任务并保存真实输出。
4. 组装质检：统一比例、帧率、音轨和字幕，检查黑帧、时长、编码与镜头完整性，再交付 MP4。

真正的 360 度车型环绕不能从一张照片保证结构准确。第一版可以做“基于单图的视觉环绕感”，但若要求灯组、车架、排气和另一侧结构真实，需要多角度照片、环车视频、现成 3D 模型或 Blender 车辆资产。

## 3. 必需凭据

通常至少需要以下三类配置：

| 能力 | 必需配置 | 用途 |
| --- | --- | --- |
| 多模态 LLM | Base URL、API Key、模型 ID | 照片理解、事实提取、脚本和结构化分镜 |
| 图片/视频生成 | Provider API Key、模型/版本 ID | 参考图生视频、文生视频、任务查询与下载 |
| 对象存储 | Bucket、Region、Access Key/Role | 为云模型提供短期可访问的输入 URL，保存生成素材 |

TTS Key 在第一版可选；可以先做纯音乐/字幕版本。搜索 API 也可后置，首个闭环先由用户确认车型事实。

密钥不应发在聊天中。选定 Provider 并实现对应 Adapter 后，由项目方在 Admin 界面写入；探测必须显示真实请求 ID、延迟和标准错误，才算接入成功。

## 4. 推荐实施顺序

### Gate 0：修复创作入口

- 将“创建项目”和“上传素材”拆为可观察步骤。
- 显示文件上传进度、失败原因和服务端 AssetVersion。
- 项目保存成功后再启用“分析素材/下一步”。
- 浏览器控制台错误和 API Problem Detail 在页面可见。

完成条件：用户项目和上传文件真实出现在数据库与项目工作区，刷新页面后仍存在。

### Gate 1：真实 LLM 与视觉理解

- 确认一个支持图片输入和结构化输出的 Provider。
- 实现 Provider Adapter、超时、错误归一化和真实 Credential/Deployment probe。
- 上传照片后生成可确认 Project Facts，不再调用 Fixture。
- Advisor、Brief、Storyboard 保存真实 `ModelInvocation` 和 Provider Request ID。

完成条件：关闭 Fake Provider 后，张雪 800X 样例仍能从用户照片和文案生成通过 Schema 的三套策略。

### Gate 2：单镜头真实视频

- 接入一个支持参考图的 image-to-video Provider。
- 建立对象存储、签名 URL、异步提交、轮询、超时、取消和结果下载。
- 先只生成一个 5 至 8 秒镜头，验证车型一致性和实际单次成本。

完成条件：输出视频确实来自用户上传照片，Provider 调用和下载均可追溯，失败可恢复。

### Gate 3：多镜头成片

- 按 Storyboard 生成四至六个 Shot。
- 加入单 Shot 重试、降级使用用户素材、字幕/TTS 和 FFmpeg 合成。
- 显示逐镜头状态、实际成本和总耗时。

完成条件：完成“照片与文案 -> 用户确认 -> 多镜头生成 -> 下载 MP4”的真实端到端验收。

### Gate 4：车型保真与 3D

- 定义车型结构保真等级和拒绝条件。
- 对多角度素材做一致性检查；评估现成 3D 资产、摄影测量、Gaussian Splatting 或 Blender 管线。
- 将真正的 360 环绕与单图视觉运镜明确区分。

完成条件：指定车型的关键部件在多角度镜头中一致，并通过人工验收。

## 5. 自动测试边界

- CI 继续使用 Fake Provider，保证状态机、错误、上传和合成可重复。
- 真实 Provider 增加受预算控制的手动/定时验收，不把非确定性外部调用伪装成普通单元测试。
- 真实验收必须保存 Provider Request ID、输入 Asset 哈希、输出 Artifact、耗时和成本。
- 至少验证成功、鉴权失败、额度不足、超时、内容拒绝和任务失败六类路径。

## 6. 项目方需要确认

1. 首个多模态 LLM Provider，以及账号是否已开通图片输入 API。
2. 首个视频生成 Provider，以及账号是否已开通 API 和测试额度。
3. 部署在中国大陆还是海外，决定对象存储和 Provider 网络路径。
4. 首个真实样片允许的最高成本和最长等待时间。
5. 单张照片只要求“视觉上有环绕感”，还是必须保证真实车型另一侧结构。
6. 首条样片是否需要旁白；若需要，确认 TTS Provider 或允许先使用本地语音方案。

## 7. 2026-09-05 Provider 方向更新

- 多模态 LLM 方向：GPT，通过项目方自有中转站 `https://www.gettokens.cc` 接入。
- API Key：已经由 Admin/Secret Store 加密保存，数据库仅有 Credential ID 与末四位；本文不保存明文。由于 Key 曾出现在聊天中，真实验收后应轮换。
- 中转站公开页面标识为 Sub2API AI API Gateway；未认证访问 `/v1/models` 返回 `API_KEY_REQUIRED`，说明模型清单需要凭据才能核验。
- 公开页面未发现视频模型或视频任务端点说明，因此不能假设 GPT Key 同时具备视频生成能力。
- 已验证 Base URL 为 `/v1`，当前部署模型为 `gpt-5.4-mini`；图片输入与严格结构化输出均已通过真实请求。
- 经鉴权的 `/models` 返回 20 个模型，其中包含 GPT 与图片模型，但没有名称含 `video` 或 `sora` 的模型。不能据此假设中转站支持视频生成。

GPT 在本项目中负责照片理解、事实提取、创意建议、脚本、Storyboard、镜头 Prompt 和结果复核。普通 GPT 文本/多模态调用不直接输出 MP4。即使中转站同时代理 OpenAI 视频服务，平台仍需把视频能力建模为独立 Deployment 和异步 Video Provider Adapter；同一 Key 是否可复用取决于中转站权限与计费配置。

## 8. Gate 1 真实验收记录

- Credential probe：HTTP 成功，返回 20 个模型，约 5.3 秒。
- Deployment probe：历史最小结构化探测成功，约 7.9 秒，接口返回 Provider Request ID；当前探针实现没有单独持久化该调用记录，也没有实测全部声明能力。
- Creator intake：正常页面创建 Project，并上传 JPEG；项目与 AssetVersion 已写入 `.data/vediogen.db` 和 `.data/assets/`。
- Creative Advisor：真实图片 + 中文文案输入，2722 input tokens、2296 output tokens、约 47.2 秒，输出三个 Proposal 并通过本地 `creative-advisor.schema.json` 校验。
- Storyboard Generator：3235 input tokens、1837 output tokens、约 34.5 秒，输出 5 个镜头、旁白、字幕、机位、素材策略和连续性约束。
- 真实输出识别出需要 `blender-3d`、`image-to-video` 和 `generated-video`；由于没有视频 Provider，生成页正确显示阻断原因。
- 真实响应未提供费用字段，当前成本为 `unavailable/0.0000` 占位；不能把它解释为免费。需由中转站账单或价格配置补齐。

历史验收中修复了打开已有策略页重复调用 Advisor 的前端竞态，现在以 `latestAdvisorRunId` 防重，但尚无服务端幂等。另曾观察到 build/dev 并用及页面未水合；先 build 再重启 dev 是操作规避措施，不视为所有页面等待故障的已证实根因，仍需长请求和任务恢复整改。

历史上传样例使用仓库参考 JPEG，并非已核实的用户真实车型素材。真实样片的车型一致性、镜头顺序、总时长、费用和影视级质量尚未通过验收；当前费用 `0.0000` 是未知占位，不表示免费。
