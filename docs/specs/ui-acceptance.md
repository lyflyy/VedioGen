# UI 测试与验收规格 v0.1

- 状态：待项目方评审
- 版本：0.1
- 日期：2026-09-05
- 负责人：设计、前端、测试负责人待指定
- 依据：[UI 架构](ui-architecture.md)、[设计系统](design-system.md)、[页面清单](page-inventory-and-navigation.md)

## 1. 质量门

UI 不是“接口能调通”即完成。每个 P0 页面必须依次通过：

1. 组件状态与内容 Fixture。
2. 页面交互和领域状态测试。
3. Playwright 主路径与失败恢复。
4. axe 自动可访问性检查和人工键盘检查。
5. 桌面/平板/手机截图与真实长内容评审。
6. 性能、断线恢复和敏感信息检查。

未通过关键路径、严重/致命可访问性问题、内容重叠、Secret 泄漏或无法恢复的保存/生成失败，均阻止 P0 验收。

## 2. 固定视口

| 名称 | 视口 | 用途 |
| --- | --- | --- |
| Desktop large | 1440 x 960 | 三列 Advisor、Storyboard、Admin 表格 |
| Desktop minimum | 1280 x 800 | 桌面最小承诺 |
| Tablet | 1024 x 768 | Inspector Drawer、折叠导航 |
| Mobile | 390 x 844 | 查看、回复、确认、下载 |
| Mobile narrow | 320 x 568 | 最长词、按钮和错误文案压力测试 |

至少在 Chromium 完成全量 E2E，在 Firefox 和 WebKit 完成 Creator 主路径与 Admin Key/Route 主路径。

## 3. Fixture

### Creator

- `张雪 800X`：长车型事实、360 环绕、细节、高速骑行高潮。
- `春风 800MT`：沙漠、仪表特写、涉水抬头、无人机远拉。
- 育儿样例：验证 Content Pack 替换后无车辆字段。
- 长内容：80 字项目名、300 字镜头描述、长 URL、长错误与中英混排。

### Admin

- Provider A Ready、Provider B Degraded。
- Credential Active、Draining、Revoked；只包含别名和末四位。
- `creative-advisor` Draft 将 Primary 从 A 切换到 B，并保留 A 作为 Fallback。
- Invocation Success、Timeout->Fallback Success、Schema Error、Rate Limited。

### Media

- 有 Poster 的成功视频、黑帧失败、无音轨、处理中、Provider 失败和图片运动降级。
- 测试使用确定性 Fixture；视觉回归不依赖实时生成模型输出。

## 4. 组件验收

每个领域组件在 Storybook 中至少包含：

- Default、Loading、Empty、Error、Disabled/Read-only。
- 键盘 Focus、长中文、窄容器、200% 文本缩放。
- Streaming/Running（适用时）、Conflict、Stale Version（适用时）。

基础组件不重复测试 Radix 内部实现，但必须测试项目变体、文案、组合和领域状态。

## 5. Creator E2E

### 5.1 从想法到 Brief

```gherkin
Given 用户位于新建项目页
When 输入张雪 800X 素材并提交
Then 页面进入 Strategy 且保留用户原文
And AI 流式状态可见但不阻塞继续补充
And 最终显示至少两个叙事机制不同的 Proposal
When 用户合并两个方向并采用
Then Brief 显示来源、版本和待确认状态
When 用户确认
Then 创建不可变 BriefVersion 并进入 Storyboard
```

### 5.2 Storyboard 局部编辑

- 选中任一 Shot 时 URL、舞台和 Inspector 一致。
- 修改涉水镜头不改变其他 Shot 内容或顺序。
- 拖动排序后键盘用户可执行等价的前移/后移操作。
- 总时长实时更新，超范围时指出具体 Shot。
- 确认前显示将启动的镜头数、资源等级和受影响版本。

### 5.3 生成与恢复

- SSE 事件按 Shot 更新；重复事件不产生重复行。
- 断网再恢复后从服务端校正，状态不倒退。
- 单 Shot 失败可重试，不重新运行无关 Shot。
- 使用降级方案时明确显示来源变化。
- 取消 Run 后已完成 Artifact 仍可查看，主状态为已取消。
- 成片完成后可播放和下载，元数据显示 9:16、时长和版本。

### 5.4 上游修订

- 修改已确认 Brief 前显示将过期的 Storyboard/Run。
- 取消操作不产生新版本。
- 确认修订产生新版本，旧版本仍可只读查看。
- `409` 冲突保留本地输入并提供查看最新版本的入口。

## 6. Admin E2E

### 6.1 API Key

- 管理员输入 Key 后请求只发送一次，成功响应不包含 Key。
- 成功后输入框、React 状态、DOM、URL、Local/Session Storage 和错误上报中均无明文。
- 页面只显示别名、Provider、末四位、状态和时间。
- 撤销前显示引用；已被 Published Route 使用时必须阻止或要求先迁移。

### 6.2 Deployment 与探针

- 未探针或探针失败的 Deployment 不能进入 Production Routing。
- 探针显示能力、耗时、标准错误和时间，不显示 Secret/Header。
- 保存表单失败时保留非秘密字段；秘密字段要求重新输入。

### 6.3 Routing 发布/回滚

- 修改只影响 Draft；Published 仍服务新请求。
- 不满足能力、重复 Fallback、Disabled Deployment 均被阻止。
- 发布前必须有变更说明、配置验证和选定 Fixture 结果。
- 发布生成不可变版本，新 Run 引用新版本，执行中 Run 不变化。
- 回滚前验证 Credential；成功后新 Run 使用目标版本。

### 6.4 Invocation

- 筛选器写入 URL，刷新和前进/后退后保持。
- 列表不拉取完整 Prompt/响应。
- 详情能看到真实路由链、Fallback、Token、费用、耗时和 correlation ID。
- 脱敏规则对 Authorization、自定义 Key Header 和结构化秘密字段有效。

## 7. 可访问性

目标为 WCAG 2.2 AA，自动化只是最低检查：

- axe 在所有 P0 页面和关键 Dialog/Drawer 状态中没有 `critical` 或 `serious` 问题。
- Lighthouse Accessibility 核心页面目标分数 >= 95；分数不能替代人工问题修复。
- 仅用键盘可完成新建、方案选择、Brief 确认、Shot 切换/排序、局部重试、添加 Key 和发布路由。
- 焦点顺序与视觉顺序一致；Dialog 打开时焦点进入，关闭后回到触发器。
- Icon Button 有可访问名称和 Tooltip；Tooltip 不是必要信息的唯一载体。
- 状态、错误、选中和进度不只靠颜色。
- 阶段变化使用克制的 `aria-live`；流式 Token 和逐帧进度不连续打断读屏。
- 200% 文本缩放仍可操作；320px 宽无双向页面滚动。
- `prefers-reduced-motion` 下移除非必要动效。

实现和审查使用已安装的 `accessibility` 与 `web-design-guidelines` Skills。

## 8. 视觉与响应式

- 为四个固定视口保存基线截图；动态时间、视频帧、光标和流式区域必须固定 Fixture 或 Mask。
- 截图差异阈值建议 <= 1%；任何通过阈值但出现重叠、裁切、层级或焦点问题的变更仍失败。
- 页面不能出现嵌套卡片、无理由大圆角、装饰渐变球、营销 Hero 或全站单一蓝紫色。
- 9:16 舞台、Shot 缩略图、图标按钮和状态行在加载/错误/成功间尺寸稳定。
- 表格横向滚动限制在表格容器；页面导航和主要动作始终可访问。
- 真实媒体保持可检查，不用暗色模糊占位覆盖主体。

## 9. 性能预算

在固定 Fixture、生产构建和受控 Lighthouse 环境中：

- `/projects` 的 LCP <= 2.5s、CLS <= 0.1。
- 点击 Proposal、Shot、Tab 后 200ms 内出现本地视觉反馈；远程完成另显示状态。
- Creator 列表首屏客户端 JS 建议 <= 250 KiB gzip；Storyboard/Admin 复杂路由建议 <= 350 KiB gzip，超出需记录原因和拆包方案。
- 非当前视频不自动下载完整媒体；列表只取缩略图和摘要。
- 独立 API 请求并行；测试禁止可避免的串行网络瀑布。
- 100 个项目和 1000 条 Invocation 使用服务端分页，DOM 不一次渲染全部数据。

## 10. 安全与隐私 UI 检查

- 页面源码、Hydration Payload、网络响应、浏览器存储和监控事件中无 API Key 明文。
- 外部 URL、模型文本和上传文件名按文本渲染，不注入 HTML。
- 管理写操作不能仅由前端隐藏控制；直接请求仍由服务端拒绝。
- 下载链接有时效和对象范围；错误页不暴露堆栈、文件路径和 Provider Secret。
- 所有破坏性动作说明影响对象，并通过 Dialog 明确确认。

## 11. 测试实现约定

- Playwright Page Object 按用户任务组织，不按 CSS 结构组织。
- 定位优先 Role、Name、Label；禁止把脆弱 CSS 类作为主定位。
- `data-testid` 只用于无稳定语义的媒体画布和事件数据。
- 使用 Fake LLM/Search/Video Provider 和固定 SSE Fixture，CI 不依赖外部费用服务。
- 每个线上缺陷补一个最小回归测试；视觉问题同时补对应 Story/截图。
- React 代码评审使用 `vercel-react-best-practices`，UI 截图评审使用 `frontend-design`。

## 12. P0 阻断级问题

- Creator 主路径无法完成或刷新后丢失已确认版本。
- 任一 API Key 在 UI/网络/日志中泄漏。
- 单 Shot 重试触发无关镜头生成。
- 路由 Draft 未发布却影响请求，或回滚改变执行中 Run。
- 1280/390 宽度出现主要内容重叠、不可达按钮或正文截断。
- 关键路径存在 axe Critical/Serious 问题或键盘陷阱。
- 实时状态断线后永久错误或倒退。

## 13. 开放问题

1. 性能预算使用 CI 模拟环境还是指定测试机；开发前需要固定基准。
2. Firefox/WebKit 是否每次 PR 全跑，还是夜间跑；建议 Creator 主路径每次 PR 全跑。
3. 视频视觉质量仍需人工门，本规格只覆盖播放器/状态/布局和自动媒体检查。

## 14. 通过条件

- 所有阻断项为零。
- 两个摩托车场景完成端到端；育儿场景完成到 Brief。
- Creator/Admin 主路径在 Chromium、Firefox、WebKit 通过。
- 四视口截图经设计评审，axe/Lighthouse/键盘检查有报告。
- 测试报告关联到具体 Spec、Fixture、构建版本和失败 Artifact。
