# 设计系统规格 v0.1

- 状态：待项目方评审
- 版本：0.1
- 日期：2026-09-05
- 设计负责人：待指定
- 技术负责人：待指定
- 基础：Radix Primitives、shadcn/ui 代码分发、Lucide Icons

## 1. 设计方向

产品视觉关键词是：**精密、克制、可追踪、以作品为中心**。

- 创作页像现代剪辑与制作工具：媒体预览是最强视觉信号，控制界面安静稳定。
- 管理页像可靠的运营控制台：表格、状态、版本与差异优先，不做展示型 Dashboard。
- 摩托车的速度感来自真实预览、镜头节奏和声音，不靠全局霓虹渐变或装饰动效。
- 后续切换育儿内容包时，基础界面不换主题；内容模板、示例和预览资产改变领域表达。

## 2. 基础 Token

### 2.1 颜色

| Token | 浅色值 | 用途 |
| --- | --- | --- |
| `--canvas` | `#F5F6F7` | 页面底色 |
| `--surface` | `#FFFFFF` | 工具面板、表格、弹层 |
| `--ink` | `#171A1F` | 主文字与高强调图标 |
| `--muted` | `#5B6470` | 次要文字 |
| `--line` | `#D6DBE1` | 分隔线与边框 |
| `--action` | `#0B6B5C` | 主要动作、选中态 |
| `--action-hover` | `#085347` | 主要动作 Hover |
| `--focus` | `#2563EB` | 键盘焦点环，不承担业务状态 |
| `--success` | `#087A55` | 成功、Ready |
| `--warning` | `#8A5B00` | 警告、Degraded |
| `--danger` | `#B42318` | 删除、失败、撤销 |
| `--stage` | `#0E1116` | 视频预览舞台 |
| `--stage-ink` | `#F7F8FA` | 舞台控制与文字 |

规则：

- 状态不能只用颜色表达，必须同时提供图标或文字。
- `action` 不用于错误，`danger` 不用于普通选中。
- 视频缩略图色彩不参与控件对比度计算；其上的控制必须有稳定遮罩。
- 正文与背景达到 WCAG 2.2 AA；普通文字至少 4.5:1，非文字控件至少 3:1。
- 深色模式 Token 可在 P1 补齐；P0 只有媒体舞台使用固定暗色，不做全站伪深色。

### 2.2 字体

- 中文正文：`Noto Sans SC`，回退到 `PingFang SC`、`Microsoft YaHei`、sans-serif。
- 拉丁、数字和技术 ID：`IBM Plex Sans`，回退到系统 sans-serif。
- 不为小标签使用等宽字体；只有日志片段、Correlation ID 和代码值使用 `IBM Plex Mono`。
- 字号不随视口宽度缩放，禁止 `vw` 字号。
- 全局字距为 `0`，不使用负字距压缩标题或控件文字。

| 层级 | 大小/行高 | 字重 | 使用 |
| --- | --- | --- | --- |
| Page title | 24/32 | 600 | 页面唯一 H1 |
| Section title | 18/26 | 600 | 主区域分段 |
| Panel title | 15/22 | 600 | 属性区、弹层、表格标题 |
| Body | 14/22 | 400 | 默认正文 |
| Compact | 13/20 | 400/500 | 表格、时间线、元数据 |
| Caption | 12/18 | 400/500 | 时间、辅助信息；不可承载关键操作 |

### 2.3 间距、圆角与层级

- 4px 基准网格；常用间距 `4, 8, 12, 16, 24, 32, 48`。
- 圆角只使用 `2, 4, 6, 8px`；卡片和弹层最大 8px。
- 页面区段不做悬浮卡片；边框或分隔线表达结构。
- 阴影只用于浮层和拖动对象：`0 8px 24px rgba(23,26,31,0.12)`；普通面板无阴影。
- 焦点环 2px，外偏移 2px；任何组件不得移除可见焦点。

## 3. 布局 Token

| Token | 值 | 说明 |
| --- | ---: | --- |
| Global sidebar | 224px / 收起 56px | Creator 和 Admin 共用尺寸，不共用菜单 |
| Project step bar | 48px 高 | 桌面项目内步骤 |
| Conversation rail | 320px | Advisor 左栏，最小 280px |
| Inspector | 336px | 右属性栏；中屏变 Drawer |
| Content max | 1440px | 列表/详情内容上限；编辑器可全宽 |
| Toolbar | 48px 高 | 图标按钮与状态不导致高度变化 |
| Icon button | 36 x 36px | 指针设备；触摸目标外框至少 44 x 44px |
| Shot thumbnail | 96 x 170px | `9:16`，加载和失败时尺寸不变 |
| Video stage | `aspect-ratio: 9 / 16` | 高度受可用视口约束，不挤压工具栏 |

断点：

- `>= 1280px`：完整三列 Creator 工作台。
- `768-1279px`：右 Inspector 变 Drawer，左栏可折叠。
- `< 768px`：单列 + 顶部 Segmented Tabs；只保证查看、回复、确认和下载。

## 4. 组件规则

### 4.1 Button

- `primary`：每个可视区域最多一个，文案描述结果，如“确认并生成脚本”。
- `secondary`：可逆或次级命令。
- `ghost/icon`：工具栏动作；熟悉图标不重复放文字，必须有 Tooltip/可访问名称。
- `danger`：取消运行、撤销 Key、删除草稿等破坏性动作。
- Loading 保留原宽度，禁止按钮文字变化导致布局跳动。

### 4.2 Form

- Label 永远可见，Placeholder 不能代替 Label。
- 帮助文本只解释格式/影响，不重复功能说明。
- 保存错误就近显示，同时页面级错误摘要聚焦到第一个错误。
- Secret 使用密码输入框；提交成功立即清空，不提供查看已保存值。
- 数值用 Input/Stepper，枚举用 Select，二元值用 Switch/Checkbox，模式选择用 Segmented Control。

### 4.3 Table/List

- 表格用于同类资源比较；卡片只用于有真实缩略图或独立可操作内容的重复项。
- 行点击和行内按钮不能冲突；如果整行可进入详情，行内菜单仍必须可键盘区分。
- 默认 25 行分页；筛选写入 URL；横向滚动只发生在表格容器内。
- Loading 使用固定行高 Skeleton；Empty 与 Error 保留表头和筛选上下文。

### 4.4 Status

- 使用 `图标 + 文本`，必要时加低饱和背景；不使用只有颜色的圆点。
- 动词时态统一：`等待中`、`生成中`、`已完成`、`需要处理`、`已取消`。
- 实时进度不逐帧播报；仅阶段变化进入 `aria-live`。

### 4.5 Dialog/Drawer

- Dialog 用于短且必须完成/取消的任务。
- Drawer 用于保留列表上下文的详情或中屏 Inspector。
- 长表单进入独立页面，不塞入多层 Dialog。
- 不允许 Dialog 内再打开同层 Dialog；改为页面或 Popover。

### 4.6 Media

- 视频预览保留真实画面，不用暗色模糊图替代可检查内容。
- 当前 Shot、Poster、加载、缺失、失败和降级来源均有明确状态。
- 播放、暂停、静音、全屏使用 Lucide 图标和 Tooltip。
- 字幕安全区、9:16 裁切和关键主体框只在编辑模式显示，不进入最终导出。

## 5. 页面组合模式

- `List page`：PageHeader -> FilterBar -> Table/List -> Pagination。
- `Detail page`：Breadcrumb -> Header/Status/Actions -> Tabs -> Main + Context panel。
- `Editor`：Project step bar -> Toolbar -> Media/Content workspace -> Inspector -> Sticky approval bar。
- `Admin edit`：Header -> status/validation summary -> sections -> separate danger zone。
- `Run detail`：summary -> Shot runs -> human-readable event timeline -> technical details。

禁止卡片嵌套卡片。页面 Section 使用留白和 Divider；只有 Proposal、媒体项目、独立 Fixture 等真正重复单元可以使用 Card。

## 6. 交互与动效

- 即时反馈 120ms，Popover/Drawer 180ms，页面级状态过渡最大 240ms。
- 只使用 opacity、transform 等不引起重排的属性。
- 拖动排序、确认成功和运行状态变化可以有功能性动效。
- 禁止页面元素依次上浮、持续发光、背景漂浮物和自动轮播。
- 尊重 `prefers-reduced-motion`；此时移除非必要位移与循环动效。

## 7. 文案与语言

- 面向创作者使用内容语言：`策略`、`镜头`、`素材`、`成片`；不显示 `DAG`、`Provider`、`Token`。
- 面向管理员使用准确技术名词，首次出现提供简短解释或 Tooltip。
- 按钮使用动词和结果，通知复用同一词汇：`发布路由` -> `路由已发布`。
- 错误说明“发生了什么 + 能做什么”，避免“未知错误”“操作失败，请重试”作为唯一信息。
- 不写“保证爆款”“预计必火”等无法验证的内容。

## 8. 组件治理

- Storybook（调研日 91,011 Star，MIT）作为组件目录和状态评审工具。
- 每个领域组件至少提供 Default、Loading、Empty、Error、Long content、Keyboard focus Story。
- 新 Token 先更新本 Spec 和 `tokens.css`；组件不得私自加入近似颜色、间距或圆角。
- shadcn 组件进入仓库后属于项目源代码，修改需有测试；更新不能覆盖本项目变体。
- 禁止同时引入整套 Ant Design/MUI/PatternFly。

## 9. 开放问题

1. 产品正式名称、Logo 与品牌字体尚未确定。
2. 深色全站主题是否进入 P0；建议延后，先完成浅色和媒体舞台。
3. 主要动作色 `#0B6B5C` 是否符合品牌预期；线框评审时需用真实摩托车素材验证。

## 10. 验收标准

- 关键页面只使用本 Spec Token，不出现无法解释的组件级硬编码颜色。
- 同一语义状态在 Creator/Admin 中颜色、图标和文案一致。
- 所有图标按钮具有 Tooltip、可访问名称和稳定 36px 可见尺寸。
- 1280px 桌面、768px 平板和 390px 手机宽度无内容重叠。
- 长车型名、长中文错误、200% 文本缩放不遮挡相邻内容。
- 组件状态在 Storybook 中完整，并通过键盘和 axe 检查。
