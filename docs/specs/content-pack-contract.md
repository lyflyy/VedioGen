# 垂直内容包契约 v0.1

- 状态：待项目方评审
- 版本：0.1
- 日期：2026-09-05
- 负责人：待指定
- 首个实现：`motorcycle@0.1.0`

## 1. 目标

平台核心维护项目、对话、策略、Brief、Storyboard、运行和 Artifact。摩托车、母婴、育儿等垂直方向通过 Content Pack 提供领域输入、Advisor 方法、镜头目录、路由规则和质量检查，不修改核心状态机。

Content Pack 是受版本控制的配置与已审核代码集合，不是终端用户上传的任意插件。

## 2. 包结构

```text
content-packs/<pack-id>/
  manifest.yaml
  schemas/
    intake.schema.json
    reference-pack.schema.json
  prompts/
    advisor/<version>.md
    script/<version>.md
    storyboard/<version>.md
    visual-review/<version>.md
  playbooks/
    content-types.yaml
    scoring.yaml
  shots/
    catalog.yaml
    routing.yaml
  quality/
    rules.yaml
    rubric.yaml
  fixtures/
  ui/
    labels.zh-CN.json
    field-layout.yaml
```

Prompt 和配置文件在发布时计算 Hash，并由 ContentPackVersion 引用。

## 3. Manifest

```yaml
id: motorcycle
version: 0.1.0
displayName: 摩托车
platformCoreRange: ">=0.1.0 <0.2.0"
locales: [zh-CN]
entrypoints:
  intakeSchema: schemas/intake.schema.json
  referenceSchema: schemas/reference-pack.schema.json
  advisorPrompt: prompts/advisor/1.md
  scriptPrompt: prompts/script/1.md
  storyboardPrompt: prompts/storyboard/1.md
  contentTypes: playbooks/content-types.yaml
  shotCatalog: shots/catalog.yaml
  routingRules: shots/routing.yaml
  qualityRules: quality/rules.yaml
```

发布检查确保所有路径存在、Schema 可解析、Prompt 版本固定、Fixture 通过。

## 4. 核心扩展点

| 扩展点 | 输入 | 输出 |
| --- | --- | --- |
| Intake Extension | 用户消息、素材分析 | 领域候选 Fact、待确认歧义 |
| Reference Builder | Facts、用户/公开素材 | Reference Pack |
| Advisor Playbook | Account Brief、Facts、Evidence | 诊断规则和 Proposal 评分 |
| Content Type Catalog | 通用目标 | 领域内容类型与侧重点 |
| Shot Catalog | Brief | 允许的 Shot 类型和参数 |
| Render Router | Shot、素材、预算 | 首选与降级 Strategy |
| Prompt Set | 阶段结构化输入 | 版本化 Prompt |
| Quality Rules | Artifact、Reference Pack | 领域 Quality Findings |
| UI Extension | Pack Schema | 标签、选择器和属性区字段 |

扩展点返回结构化数据，不允许直接更新数据库、发布 Route 或执行任意命令。

## 5. 通用与领域字段边界

平台核心拥有：受众、目标、Hook、承诺、视觉回报、节奏、CTA、输出规格、Shot 时长、运镜、音频、策略、版本和审批。

内容包拥有：

- 领域 Fact Key，例如 `subject.vehicle.name`。
- Reference Pack Schema。
- 内容类型、术语、推荐问题和评分权重。
- 镜头类型与模板参数范围。
- 领域真实性和视觉一致性规则。
- 管理与创作 UI 中的领域字段定义。

核心数据库可将内容包扩展数据保存为经 Schema 校验的 JSONB，但常用查询字段需要显式投影，不能把全部业务塞进不可查询 JSON。

## 6. Advisor 方法

每个 Pack 必须将通用 Audience、Goal、Hook、Promise、Proof、Progression、Payoff、Close 方法映射为领域规则。

### 摩托车映射

- Audience：车型关注者、越野用户、通勤用户、机械审美用户等。
- Proof：真实车型轮廓、可确认部件、动态通过性、仪表/用户素材。
- Payoff：整车环绕、高速跟拍、沙尘/涉水、远景收束。
- 主要风险：车型误识别、跨镜头结构漂移、未核实性能参数。

### 育儿映射样例

- Audience：按儿童阶段与具体问题划分。
- Proof：步骤演示、前后对比、清晰解释和可执行清单。
- Payoff：问题得到解决、形成可收藏总结。
- 主要风险：泛泛而谈、步骤不清、把假设写成确定事实。

育儿 Pack 不得继承车辆、驾驶、Blender 或发动机字段。跨垂直 Fixture 必须验证这一点。

## 7. Shot Catalog

每个条目包括：

- 稳定 `shotType` 和版本。
- 叙事用途、允许内容类型和建议时长。
- 必需/可选 Reference 数据。
- 支持的景别、运镜和动作参数范围。
- 首选/降级 Render Strategy。
- 预算等级和预计失败模式。
- 自动质量规则和人工评审重点。

摩托车 P0 候选：`product-reveal`、`detail-macro`、`studio-orbit`、`riding-follow`、`terrain-action`、`instrument-closeup`、`aerial-pullback`。

## 8. 路由规则

规则按优先级匹配：

1. 可用用户视频且满足镜头目的时使用 `user-video`。
2. 有多角度/关键参考图时优先 `image-to-video`。
3. 有已验证 3D 资产时，稳定环绕和产品特写可选 `blender-3d`。
4. 动态环境镜头使用 `image-to-video` 或 `generated-video`。
5. 失败时降级到 `image-motion` 或经用户接受的替代素材。

路由输出只选择 Shot Manifest 支持的 Strategy，不包含 Provider API 参数。供应商参数由 Worker Adapter 编译。

## 9. 版本与兼容

- 版本遵循 SemVer。
- Prompt、Schema、镜头参数或质量规则变化至少增加 Patch。
- 删除字段、改变语义或破坏 Fixture 必须增加 Major。
- Project 创建时固定 ContentPackVersion；升级需要显式迁移和预览差异。
- 运行中的 Project 不自动切换 Pack。
- 平台核心声明支持的 Pack 版本范围，不兼容时拒绝加载。

## 10. 发布流程

```text
编辑 Pack Draft
-> Schema/Manifest Lint
-> 通用 Fixture
-> Pack Fixture
-> Prompt/输出质量评审
-> 生成 Hash 清单
-> 发布不可变 ContentPackVersion
-> 新项目可选择
```

P0 可以随代码发布 Pack，但运行时仍保存版本和 Hash。P1 再增加内部 Pack 管理 UI。

## 11. 测试契约

每个 Pack 至少提供：

- 2 个正常 Intake/Advisor Fixture。
- 1 个名称或事实冲突 Fixture。
- 1 个素材缺失降级 Fixture。
- 每个 Shot Type 一个合法与一个非法样例。
- Reference 一致性规则样例。
- 从 Proposal 到 Storyboard 的端到端样例。
- 跨 Pack 污染检查。

摩托车 Pack 使用张雪 800X、春风 800MT；育儿验证 Pack 至少跑到 Creative Brief。

## 12. P0 验收

- 删除摩托车 Pack 后，平台核心仍能启动并显示通用创建入口。
- 切换到育儿 Pack 后，不出现摩托车字段和镜头类型。
- Project 固定 Pack 版本，发布新 Pack 不改变已有项目。
- Pack 输出全部通过中央 Creative Advisor、Brief 和 Storyboard Schema。
- 非法 Shot 参数在编译 Manifest 前被拒绝。

## 13. 待评审项

1. P0 是否只实现完整 motorcycle Pack，加一个最小 parenting validation Pack；建议接受。
2. Content Pack P1 是否允许通过管理界面启停；P0 随代码发布即可。
3. 育儿方向具体内容形态尚未确认，因此首期验证 Pack 不进入成片生产。
