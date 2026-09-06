# 测试与验收策略 v0.1

- 状态：待项目方评审
- 版本：0.1
- 日期：2026-09-05
- 负责人：待指定
- 适用范围：P0 创意顾问、模型管理、Storyboard、媒体执行和成片

## 1. 质量目标

P0 测试必须证明：

1. 用户确认事实不会被搜索或模型静默覆盖。
2. AI 输出满足结构化契约，失败可以恢复或清晰降级。
3. 两次确认和不可变版本不会被绕过。
4. Provider/Key/路由可通过界面管理，Key 不泄漏。
5. 单镜头失败只影响对应 Shot，不重做无关内容。
6. 最终 MP4 满足技术规格且能追溯全部输入与调用。
7. 内容包替换后，平台核心不残留摩托车字段。

测试不以“预测爆款”或单条播放量作为发布门。

## 2. 测试分层

| 层级 | 主要对象 | 执行频率 | 是否阻塞合并 |
| --- | --- | --- | --- |
| 静态检查 | 格式、类型、OpenAPI、JSON Schema、迁移 | 每次提交 | 是 |
| 单元测试 | 事实优先级、版本、路由、预算、状态转换 | 每次提交 | 是 |
| Schema/契约 | LLM 输出、Provider、Worker、管理 API | 每次提交，真实服务按计划 | 是 |
| 集成测试 | PostgreSQL、Secret Store、队列、对象存储、FFmpeg | 每次 PR 或合并前 | 是 |
| 工作流测试 | Advisor 到成片、恢复、取消、重试、回滚 | 每次 PR 的 Fixture；每日真实调用 | 是 |
| UI/E2E | 创作者工作台与 `/admin` | 每次 PR 的关键路径 | 是 |
| 媒体自动检查 | 编码、时长、黑帧、音频、字幕 | 每次真实生成 | 是 |
| 人工内容/视觉评审 | 创意、车型、镜头、节奏、声音 | P0 里程碑 | 是 |
| 性能与成本 | 延迟、并发、Token、媒体成本 | 每日/里程碑 | 超阈值阻塞发布 |

## 3. 固定 Fixture

Fixture 必须版本化且不包含真实 Key。

### F-MOTO-001：张雪 800X

- 输入：用户给出的原始文字，无上传素材。
- 关键事实：`subject.vehicle.name = 张雪 800X`，已确认。
- 必需画面：车辆细节、360° 环绕、皮衣骑手高速驾驶收尾。
- 关键断言：搜索误匹配不能替换车型；至少两个实质不同 Proposal；高速镜头为后半段视觉高潮。

### F-MOTO-002：春风 800MT

- 输入：用户给出的四段镜头要求。
- 必需顺序：360 环绕、沙漠、仪表、涉水、山林无人机远拉。
- 关键断言：沙漠行驶与仪表拆成原子 Shot；用户顺序不变；涉水镜头可单独重试。

### F-PARENT-001：育儿跨垂直样例

- 输入：一个常见育儿知识选题，只有文字。
- 关键断言：Advisor 使用问题共鸣、步骤、演示和收藏价值；不得生成车型、驾驶、Blender 或发动机字段。

### F-ADMIN-001：模型主备切换

- Provider A 为 Primary，Provider B 为 Fallback。
- 模拟 A 成功、限流、超时、鉴权失败和结构化输出错误。
- 关键断言：只在允许错误上 Fallback；调用链、版本和费用完整；Key 永不出现。

## 4. 静态与 Schema 测试

- 所有 JSON 文件可解析，所有 JSON Schema 通过 Draft 2020-12 meta-schema 检查。
- 所有固定成功样例通过对应 Schema，反例因明确字段失败。
- OpenAPI 3.1 可被解析、Lint 并生成客户端类型。
- OpenAPI 引用的本地 Schema 必须存在且可解析。
- 数据库迁移可以从空库执行、回滚开发迁移并重新执行。
- 前后端生成类型与 Schema 版本保持一致。

关键反例：

- Advisor 只返回一个 Proposal。
- Proposal 没有限制或依据。
- Brief 没有 mustNotInvent。
- Storyboard 使用未知 Strategy 或 Shot 时长越界。
- Shot Manifest 包含任意命令/Python 字段。
- 管理 API Credential 响应包含 `secret`。

## 5. 单元测试

### 5.1 事实与版本

- confirmed Project Fact 优先于任意 Evidence。
- 只有用户动作能 supersede confirmed Fact。
- 批准 Brief/Storyboard 后对象不可更新。
- 新 Brief 批准会使依赖旧 Brief 的 Storyboard stale。
- 修改一个 Shot 创建新 StoryboardVersion，并正确计算受影响 Shot。
- 内容 Hash 与 Approval 绑定，内容变化后旧 Approval 无效。

### 5.2 路由

- 能力不满足时 Deployment 不可选择。
- disabled/degraded Deployment 不可作为默认 Primary。
- Fallback 顺序稳定，不重复。
- 路由 Publish 原子化，新请求读取新版本，旧 Run 保留快照。
- 总尝试次数和总预算达到上限后停止。
- `AUTH_FAILED` 隔离 Key；`INVALID_REQUEST` 不切换平台。

### 5.3 状态机

- 每条允许转换成功，每条未声明转换失败。
- 重复 Idempotency-Key 返回同一结果。
- 乐观锁冲突返回 409，不覆盖新数据。
- Cancel 后不创建新 ShotRun。
- 迟到 Provider 结果变为 orphaned。

## 6. Provider 契约测试

每个 LLM Provider 必须通过同一套测试：

- 鉴权成功与失败标准化。
- 非流式文本和 Streaming 事件顺序。
- JSON Schema/结构化输出成功与修复失败。
- Tool Calling 参数和工具白名单。
- 中文输入输出与 Unicode。
- Token/费用字段存在或明确标记 unavailable。
- 429、5xx、超时、连接中断和取消。
- 响应、异常和 Trace 不包含 API Key。

测试顺序：Fake Provider 在 CI 每次运行；录制响应用于稳定回归；真实 Provider 使用最低成本 Fixture 每日或手动运行。录制文件必须脱敏，并记录 Provider 和模型版本。

搜索、图片、视频、TTS 和对象存储也采用相同 Adapter Contract 思路，至少覆盖成功、限流、超时、坏响应、取消和幂等。

## 7. Secret 与管理后台测试

- 浏览器请求只在写入动作中包含 Key；响应和后续 GET 不包含。
- 数据库 Credential 表不存在 secret/ciphertext 业务列，只保存 secretRef 和末四位。
- Secret Store 失败时事务不创建可用 CredentialMetadata。
- 日志、Trace、Problem Detail、SSE 和导出内容运行敏感字段扫描。
- Key 轮换先测试新 Key，再 draining 旧 Key；并发请求无中断。
- 撤销被 Route 引用的 Key 时，系统阻止发布空路由或要求迁移。
- 非 model-admin 无法写 Key、测试 Deployment、发布或回滚 Route。
- Draft 路由不影响生产调用；发布和回滚写入审计记录。

P0 本机模式也执行上述测试，只是身份使用固定本机 Actor。

## 8. 工作流与恢复测试

### 正常路径

```text
创建项目
-> Advisor Proposal
-> 合并并批准 Brief
-> 生成并批准 Storyboard
-> 编译 Manifest
-> 生成 Shot
-> 合成
-> 质检
-> 下载
```

### 故障注入

- 搜索服务不可用：Advisor 以 degraded 模式继续并标注依据范围。
- LLM 在 Streaming 中断：发送 restart，不能拼接两模型输出。
- LLM 返回错误 JSON：修复一次，失败后按路由策略 Fallback。
- Worker 在 Shot 运行中退出：lease 过期后恢复，不重复成功 Artifact。
- 单 Shot Provider 超时：只重试该 Shot。
- 合成失败：不重新生成已成功镜头。
- 质检指出特定镜头：只重试指定镜头并重新合成。
- 取消 Run：后续 Shot 不启动，迟到结果隔离。
- 服务重启：所有非终态 Run 从数据库恢复。

## 9. UI 与 E2E

详细门槛见 [UI 测试与验收规格](ui-acceptance.md)。使用 Playwright 覆盖 1440x960、1280x800、1024x768、390x844 和 320x568，关键场景包括：

- 一句话创建项目并看到 Project Facts。
- 比较、展开、采用和合并 Proposal。
- 批准 Brief 后生成 Storyboard。
- 修改/排序 Shot，批准后启动生成。
- 生成进度、失败、降级、重试和下载。
- `/admin` 添加 Provider、写入 Key、测试 Deployment、配置 Route、发布和回滚。
- 键盘导航、焦点、Tooltip、`aria-live` 和非颜色状态表达。
- axe Critical/Serious 问题、200% 文本缩放、SSE 断线恢复和 API Key 浏览器侧泄漏检查。

每个视口保存关键截图做视觉回归。动态媒体区域使用固定 Fixture，避免模型随机输出造成无意义像素差异。Chromium 运行全量 E2E，Firefox/WebKit 至少运行 Creator 与 Admin 主路径。

## 10. 媒体自动检查

使用 `ffprobe`/FFmpeg 检查：

- 容器和 Codec：MP4、H.264、AAC。
- 分辨率：`1080 x 1920`；帧率 30fps。
- 总时长在已批准 Brief 范围内，Shot 拼接误差不超过 1 帧。
- 文件可完整解码，无截断时间戳。
- 有效音轨、峰值不过载、整体响度在选定 Profile 范围。
- 黑帧、长静帧、冻结帧和异常空音轨。
- 字幕不超出竖屏安全区，关键文字不被 UI 区域遮挡。

视觉模型只能补充检查主体一致性、变形、文字和动作，不替代确定性媒体检测。

## 11. 人工质量量表

每项 0 至 4 分：

| 维度 | 0 分 | 2 分 | 4 分 |
| --- | --- | --- | --- |
| 输入理解 | 违背明确要求 | 大体正确但遗漏 | 事实、顺序和重点完整 |
| Proposal 差异 | 同义改写 | 部分策略差异 | 叙事机制明显不同且可执行 |
| 建议理由 | 无理由/伪保证 | 通用理由 | 结合账号、素材、证据和成本 |
| Hook 与回报 | 开头无目标 | 有 Hook 但兑现弱 | 1-3 秒建立预期并被画面兑现 |
| 车型一致性 | 主体错误/变形 | 整体可认但细节漂移 | 达到已确认关键部件标准 |
| 镜头与节奏 | 不连贯 | 基本可看 | 景别、动作、声音和高潮清晰 |
| 成片可用性 | 无法发布 | 需明显人工修复 | 技术合格且只需可选微调 |

P0 通过建议：每个样例无 0 分，车型一致性和成片可用性至少 3 分，总平均至少 3 分。两名评审差异超过 1 分时记录原因并复评。

## 12. 性能与成本基线

P0 记录而非预设不现实 SLA：

- Advisor 首 Token、Proposal 完成和 Schema 修复耗时 P50/P90。
- Storyboard 生成耗时和一次 Schema 通过率。
- 每种媒体策略每秒视频的耗时、费用和失败率。
- 单条视频总 Token、外部调用、GPU/CPU 时间、存储和人工介入。
- 模型 Route 主备切换时的错误率和额外延迟。

20 次有效运行后冻结首个预算与超时阈值。阈值变化必须带测量依据。

## 13. CI 与发布门

### 每次提交

- 格式、类型、JSON Schema、OpenAPI Lint。
- 单元、Fake Provider 契约、数据库和核心 UI 测试。
- 不允许提交 Secret；扫描 `.env`、日志 Fixture 和录制响应。

### 合并到主分支

- 工作流集成测试、FFmpeg Fixture、关键 Playwright E2E。
- 数据库迁移向前执行通过。

### P0 里程碑

- 两个摩托车全链路和一个育儿 Advisor 样例。
- 一个真实 LLM、搜索和视频 Provider 跑通。
- 第二 LLM 平台真实切换；没有凭证时明确标记未验收。
- 模型管理后台 Key/路由验收。
- 人工质量量表与成本报告通过。

## 14. 缺陷优先级

- `P0 Blocker`：Key 泄漏、事实覆盖、绕过确认、产物不可追溯、数据损坏。
- `P1 Critical`：全链路失败、取消无效、错误路由、不可恢复、成片不可解码。
- `P2 Major`：局部编辑触发全量重做、关键 UI 无法操作、明显质量退化。
- `P3 Minor`：不影响任务完成的显示和文案问题。

任何 Blocker/Critical 未关闭不得通过 P0。

## 15. 待评审项

1. 是否接受人工质量量表平均 3 分作为 P0 门槛。
2. 车型关键部件清单仍需项目方确认后加入 Fixture。
3. 音频响度和字幕安全区在 rendering profile 中冻结。
4. 真实 Provider 测试频率受费用影响，建议 CI 使用 Fake/录制响应、每日少量真实探针。
