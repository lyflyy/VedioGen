# 纯文字入口与本地推理实测增量

日期：2026-09-07。状态：工程验证中，未完成成片质量验收。

本文补充并更新早期[本地环境记录](2026-09-07-local-comfy-implementation.md)中的权重下载状态，以及[素材准备记录](2026-09-07-reference-preparation-implementation.md)中的 GPT 实测范围。历史记录不代表当前状态。

## 用户输入与职责

用户目前只有文字。平台负责从描述提取车型与必需镜头、检索参考素材、向用户展示候选并继续生成；不把用户自行准备照片或模型作为主流程前提。候选参考图仍需辨认车型与版本，搜索匹配不等于正确车型确认。张雪 800X 不以其他摩托车替代。

## 真实 GPT 与搜索链路

- 工程项目：`eebd22c3-bc62-4cb2-86d4-c4ceb0a50378`，标题为“本地实测：春风800MT（待验收）”。
- 真实发现任务：`6446583e-c0f0-47d7-88d2-c2ee0fa9e10f`，状态 ready，主体来自 `model-extraction`，而非手填 subject 绕过模型。
- GPT 调用：`a77a28f1-0bd1-41f3-98ac-24fb7e3b269c`，能力 `asset-planner`，模型 `gpt-5.4-mini`，成功；providerRequestId 为 `e2ff3ea8-297e-4e78-88d1-6a3adabe281f`。输入 361 tokens、输出 82 tokens，耗时 6924ms。未读取或公开 API Key。
- 提取了春风 800MT 及四个必要镜头：360 度环绕、沙漠扬尘与转速表特写、涉水抬头、山林无人机远拉。
- 搜索返回 7 个候选，另有一个查询失败的警告。结果含不同车型版本，不能全部认作用户指定版本。尚未代用户点击采用。
- 真实浏览器候选图 7/7 加载，四个镜头可见，390px 视口无横向溢出。截图：`.data/internal-mvp/gpt-reference-live-desktop.png`、`gpt-reference-live-mobile.png`。
- 页面：`http://127.0.0.1:3001/projects/eebd22c3-bc62-4cb2-86d4-c4ceb0a50378/intake`。这是独立验证环境，不代表原 3000 端口的数据已同步。

## 真实咨询发现的上下文偏差

实际咨询任务 `17a19882-97d6-4833-ab95-6b0cc6439b43` 将工程项目标题“本地实测”误当作车辆实测主题，并提出补实拍/重拍与品牌合规边界。这不符合“内部平台、用户仅有文字、平台准备素材”的定位，不能以 JSON Schema 合格认定建议合格。

据此给顾问与分镜的真实模型输入补充 `executionContext`：素材准备责任、是否只有文字、当前视频后端、启用与调用开关、图生视频支持时长、未实现的媒体策略。该上下文不含服务地址或凭据，也不主动调用本地模型探针。提示词明确内部测试标签不进入成片、困难镜头保留为待准备目标、图片运动不能冒充真实环绕。

重启独立 8001 验证服务后，真实 GPT 咨询任务 `e83f7633-c49c-426e-9ebc-b13ba4b21851` 完成：模型调用 `4b40f889-d3ec-4099-9ecc-ffd10e29f3ad`，1049 输入 tokens、2256 输出 tokens、37626ms。输出明确由平台准备参考素材，未再要求用户重拍，也未把“待验收”写入视频文案。接口中的零费用字段不是实际 GPT 账单证据。

仍有不足：个别方案 close 建议追加车身定格，和指定最后无人机镜头存在冲突；未把本地未启用的状态完整反映在每个方案中。没有确认这些方案，也没有认为提示词已经保证了约束遵守。下一步脚本确认前仍需核对硬镜头和当前能力。

新增 3 项测试验证能力上下文、时长范围以及真实模型调用分支确实传入上下文。API 全套 69 项通过，2 项依赖弃用警告；浏览器 E2E 7 项通过（隔离模型响应）。`git diff --check` 通过，仅有 Windows 行尾提示。

## 本地依赖与续传

Hugging Face 源站连接不稳定后，实际检查了 ModelScope 的 Comfy-Org 仓库文件元信息。三个文件的大小与 SHA-256 均与既有清单一致；Range 请求实际返回 206。这里只证明文件元数据一致，完整文件仍必须逐个校验。

- [Wan 2.2 仓库](https://modelscope.cn/models/Comfy-Org/Wan_2.2_ComfyUI_Repackaged)
- [Wan 2.1 编码器仓库](https://modelscope.cn/models/Comfy-Org/Wan_2.1_ComfyUI_repackaged)
- 便携 aria2 1.37.0 来自[官方 GitHub release](https://github.com/aria2/aria2/releases/tag/release-1.37.0)，位于 `D:\VedioGen-local\aria2`。
- 下载脚本支持 `-Endpoint https://modelscope.cn -Downloader aria2`，限时运行、分片续传、最终大小与 SHA-256 校验后激活。存在 `.aria2` 控制文件时拒绝 curl 续传；稀疏文件的逻辑长度不是已完成字节数。
- Wan VAE 已完整下载并校验：1,409,400,960 字节，SHA-256 `e40321bd36b9709991dae2530eb4ac303dd168276980d3e9bc4b6e2b75fed156`。
- Diffusion 与 UMT5 续传已完成，均通过完整大小和 SHA-256 校验并激活。Diffusion 为 9,999,658,848 字节、SHA-256 `456f901338bd9eadbded3828b819109a9b68e8a525ca5cf8d0049a69fcfeca1e`；UMT5 为 6,735,906,897 字节、SHA-256 `c3355d30191f1f066b26d93fba017ae9809dce6c627dda5f6a66eaa651204f68`。下载时长不代表生成耗时。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/local-video/download-models.ps1 -Model diffusion -Endpoint https://modelscope.cn -Downloader aria2 -MaxSeconds 3600
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/local-video/download-models.ps1 -Model encoder -Endpoint https://modelscope.cn -Downloader aria2 -MaxSeconds 3600
```

每个文件同一时间只运行一个下载任务。续传前确认上一任务已终止，保留分片控制文件。

## 已发生的 GPU 实验

工程参考图来自 `https://cdn.motor1.com/images/mgl/b3pWl/s1/cf-moto-mt800.jpg`，已下载并目视检查，为横向摩托车照片。它不等于用户已确认的车型年份或版本，也没有在创作项目内自动采用。

- ComfyUI 任务：`e7c3a74c-1ce5-490f-a612-c01e2b35d2ac`。
- 图：上传、等比适配、Wan VAEEncode、VAEDecodeTiled、视频编码保存。
- 服务日志确认 CUDA、bf16、1344MB VAE staged，执行耗时 2.91 秒。
- 输出：`.data/internal-mvp/comfy-vae-real-smoke.mp4`，256 × 448，42ms，只有一帧。SHA-256 `55c617bb140b7930ebe59e8109a654e25a2afdcf2cc3c4113dfcee0ee42597fe`。
- 目视发现横图完整保留，但竖画幅上下大片灰色填充，车身占画面比例偏小。它证明 VAE GPU 编解码通道，不证明动态生成，更不证明可用竖屏构图。

本机约 16GB RAM、8GB VRAM；一次采样仅剩约 2.1GB 物理内存、约 5.9GB 可用虚拟内存。启动器增加 `--cache-none --disable-pinned-memory`，与已有 lowvram/offload 配合。没有关闭用户其他程序，也不将“能启动”解释为“能稳定生成”。

后续检查源码发现当前动态显存模式下 `--lowvram` 不生效，实际内存调度来自 ComfyUI DynamicVRAM；不能把成功归因于该单一参数。磁盘为 NVMe SSD。大尺寸采样时一次可用虚拟内存下降至约 1.3GB，仍需要关注多任务内存压力。

文本编码器独立 GPU 任务 `afd5b195-df9d-4ad4-abfb-830ca904ac7d` 通过 core CLIPLoader / CLIPTextEncode / PreviewAny 完成，约 3.76 秒，实际返回 conditioning 张量文本摘要。它不是视频生成。

## 四组真实视频对比

同一参考图、同一英文小幅相机移动提示词、种子 20260907、49 帧/24fps、20 步。除以下列出的设置外，使用相同采样方式。报告和接触表位于 `.data/internal-mvp/local-benchmarks/<任务ID>/`。

| 任务 ID | 原生尺寸 | 精度 / 解码 | 等待秒数 | 最大显存采样 MiB | 目视结果 |
| --- | --- | --- | ---: | ---: | --- |
| `689f1ea0-9f12-4d9a-b792-8b9de8b35634` | 448 × 256 | FP8 / 分块 | 36.05 | 7087 | 色带、过饱和、车体变形，不可用 |
| `3874076c-527d-458a-96c6-df42d55c09ec` | 448 × 256 | 默认 / 分块 | 51.71 | 7257 | 相同类型损坏，精度变化没有解决 |
| `a64c4ea0-2dd6-451a-8e15-28e9979a837f` | 448 × 256 | FP8 / 普通 | 30.83 | 7085 | 相同类型损坏，单独改解码没有解决 |
| `7e504d87-4c24-482a-8e50-6fb69f03740d` | 832 × 480 | 默认 / 普通 | 92.86 | 7360 | 未见前述大面积色带，车体较稳定，运动幅度小；仅初步工程可用 |

最后一组实际 MP4：832 × 480、2042ms、无声，SHA-256 `82716bf87156159444469b019360ffb8503e17e860e14fe65f697e59a38e75ff`。16 个抽样帧均不同，但这不是 360 度环绕或身份保真验收。服务侧耗时 88.23 秒，92.86 秒是客户端轮询等待口径。

结论：低分辨率失败不能简单归因于 FP8 或分块 VAE。第四组同时改变了尺寸和设置，不能据此宣布唯一根因；以实际较稳定的组合推进平台实验。没有下载更多模型或调用付费视频服务。

使用 GitHub CLI 查询到 [ComfyUI issue 15010](https://github.com/Comfy-Org/ComfyUI/issues/15010) 也报告类似色带，但其环境为 Apple Silicon/MPS，不能当作本机 CUDA 问题的根因证据。

## 推理测试工具

新增 [benchmark.py](../../scripts/local-video/benchmark.py)，复用生产 ComfyVideoClient 和工作流，不额外实现一套模型接口。只有显式运行才提交真实任务。

- 提交前持久化 UUID 与报告；`--resume` 只查询同一个任务，不重提。
- 报告记录原生尺寸、种子、等待耗时、GPU 采样、输出哈希和 ffprobe 信息。
- 下载或检查失败保留报告，恢复时仍下载原任务；已有完成文件需哈希正确才直接返回。
- 生成接触表和抽样帧差异。像素改变仅是诊断，不能证明运动合理或车型保真。
- 默认改为已得到较稳定结果的 832 × 480、2 秒、20 步、默认精度/普通解码。`--weight-dtype` 和 `--vae-decode` 用于受控比较，报告保存实际工作流；不自动改管理后台配置。这不是最终抖音竖屏样片。

```powershell
uv run --project services/api python scripts/local-video/benchmark.py --reference .data/internal-mvp/cfmoto-reference-engine.jpg --prompt "A stabilized cinematic dolly moves slowly around the front-left of the same parked blue CFMOTO 800MT adventure motorcycle on gravel. The motorcycle stays stationary, both wheels remain circular and still, its geometry, luggage and paint stay unchanged. Natural daylight."
```

新增工具测试最终为 5 项，包括真实 FFmpeg 帧差异检查、缺少权重不提交、精度/解码参数实际进入工作流、下载失败恢复不重提。网络生成在这些隔离测试中使用桩，不冒充真实推理。

## 平台真实浏览器闭环

新建独立工程项目 `01c9fc34-d50e-4157-8395-f09d7c30e9eb`，标题“本地视频链路实验（非正式样片）”，不修改两个正式车型需求，也不代表用户确认参考图身份。

1. 通过项目 API 创建纯文字输入；工程脚本把平台已找到的参考图导入该测试项目，资产 ID `beef28d4-8983-47a5-a7bc-146aae935035`。虽然复用了上传接口，但照片不是用户提供，也没有冒称用户已确认车型。
2. 实际 GPT 顾问任务 `f39ac917-8053-491d-8dab-6878cb9c3d61` 完成。工程选择方案后生成 Brief `427566e3-7345-48ca-80e8-239c715905e0`，确认备注明确仅为工程测试；实际 GPT 生成分镜 `68b58ad4-7f61-490d-82ec-f70a9d9eece3`，原始为 5 镜头。
3. 为控制实验范围，通过编辑接口把草稿改为单个 2 秒小幅运镜。该单镜头是工程编辑结果，不能说它由 GPT 自动选定或是完整用户脚本。
4. 实际浏览器在 Admin 保存 ComfyUI、832 × 480、20 步并启用本地生成，探测成功。未启用云视频、未更换 GPT Key。
5. 首次浏览器发现草稿缺少镜头 status 时页面崩溃。根因是保存接口接受缺少展示状态的镜头。已修复：保存时统一重建 draft 状态、order、startMs，补回归测试；重新保存同一草稿后页面恢复。
6. 浏览器点击“确认分镜”和“开始生成”，创建 `d3bf5f74-8d70-4274-a506-b93164d3b5be`，HTTP 202；刷新后继续追踪同一任务。实际 ComfyUI ID `d1d03770-20f7-4579-b27e-8cb45e030c57`，种子 `10359612924891`，原生 832 × 480，本地等待约 88 秒；平台总计约 89 秒完成。
7. 最终 Artifact `a267dd69-3b8f-4b40-9a2a-06f7ad661caa`：540 × 960、30fps、2005ms、H.264/AAC、133512 字节。SHA-256 `048a885e2f96d2fb7f0240f5c6eff9d9840f0fc36abaffc280040dc4bff734a4`，与浏览器实际下载文件一致。音轨为静音，不是已合成配音。
8. 桌面 1440px 与手机 390px 均实际播放，currentTime 超过 0.6 秒，paused=false，无媒体错误。Canvas 采样比较 0.2/1.8 秒，RGB 范围 255，差值超过 3 的通道数 10086；两种视口均无页面横向溢出。下载事件成功，无下载错误。

测试脚本中途有一次使用相对 API URL 导致 `Invalid URL`，发生在模型已完成之后；后续查询并验证原任务，未为此重复生成。

- 预览页：`http://127.0.0.1:3001/projects/01c9fc34-d50e-4157-8395-f09d7c30e9eb/final`。
- 下载副本：`.data/internal-mvp/local-platform-real-download.mp4`。
- 目视证据：`local-real-final-desktop.png`、`local-real-final-mobile.png`、`local-platform-real-contact-sheet.jpg`，均位于 `.data/internal-mvp/`。
- 本轮最终 API 72 项、隔离浏览器 E2E 7 项通过。真实调用证据独立于这些桩测试。
- 独立预览环境保持本地执行启用，后端 8001、前端 3001、ComfyUI 8188。默认新安装仍关闭视频生成；未改原 3000/8000 环境。

质量结论：参考车体在第二个种子下仍基本可辨识，但镜头运动很小，竖屏上下留白很大，字幕位置和画面关系不够好，没有声音设计。仅证明本地动态生成和平台闭环，不属于可发布广告片，更不计入 80 分。

## 增量：搜索连接与竖屏运动实验

状态：工程验证，未达到样片验收。用户仍只提供文字，本节所有参考照片由平台侧检索和工程准备，不要求用户补拍，也不代表用户已确认车型版本。

### 搜索连接

实测 DDGS 的 Bing 连接曾出现 `SelectedUnofferedKxGroup`，另一搜索连接超时。同一搜索源使用 HTTPX 可访问，因此在默认搜索异常时增加 HTTPX 备用连接，复用 DDGS 的 `BingImages.extract_results`，不自行编写 HTML 解析器。只访问固定搜索地址，保留 TLS 校验，禁止重定向，限制 HTML 响应与解码后 2 MiB 大小；原有品牌、型号、地址和重复项过滤继续生效。不新增搜索供应商或依赖。

备用连接解决传输可用性，不保证搜索相关性。英文扩展词有时返回无关结果，被过滤为空是合理结果，不能因此换用其他车型。

独立 API 8001 在确认没有运行中的生成和搜索任务后重启，已加载修复；未动原 8000 环境。真实 API 搜索任务 `7e70357a-0bcd-4f16-a775-1c3e0293dea6` 在工程项目 `01c9fc34-d50e-4157-8395-f09d7c30e9eb` 返回 ready、8 个候选。该次显式传入「春风800MT」，origin 为 user-input，未调用 GPT 提取，也未触发备用连接警告；不能把它记录成备用连接实际命中的证据。候选包含不同版本，未导入或自动确认。前文真实 GPT 提取证据独立保留。

### 完整时长目视检查

修复 benchmark 接触表的抽样范围：原固定 4 fps 的 4×2 接触表只覆盖约前两秒，现在按完整视频时长抽取 8 帧。增加真实 FFmpeg 测试，用三秒红转蓝片验证最后一个格子包含末段。已重新生成下面两项实验的完整时长接触表。

| 任务 | 设置 | 轮询等待 | 目视结论 |
| --- | --- | ---: | --- |
| `ae4f4daa-b35f-473b-a43c-f90ba54efef8` | 832×480，3 秒，20 步，default/native；要求 20 度运镜与视差 | 128.51 秒 | 仍只有小幅变化，末段没有形成显著环绕；不是 360 度能力证据 |
| `3bbdc1aa-d152-4094-9066-7ea4e144c26f` | 480×832，3 秒，20 步，default/native；森林骑行、相机升高后拉 | 128.80 秒 | 骑手、车体和背景有明显运动，视频内部没有先前的大面积上下填充；车体细节漂移，拉远和升高不足，不能验收为无人机远拉 |

竖屏参考来自爱卡试驾文章 `https://info.xcar.com.cn/202110/news_2062763_1.html?viewtype=all`，图片地址 `https://img1.xcarimg.com/motonews/25007/24530/39662/846_635_20211027160706186470095542844.jpg`。工程输入 `cfmoto-detail-reference-engine.jpg` 实际是森林骑手全车照片，不是零件特写；使用 FFmpeg `crop=326:564:258:0` 生成 `cfmoto-rider-portrait-crop-engine.png`，保留骑手与双轮。照片和结果仍带来源水印，不作为可发布成片素材。相关文件均在 `.data/internal-mvp/`，裁剪尚未产品化到界面。

竖屏输出为真实 MP4，480×832、3042ms、无音频、1,717,181 字节，SHA-256 `58fab625eb734ea343f6318c4adb8572bdc05ab91046e3146ebb596d78b951d4`。24 个抽样帧均不同，但帧差不代表运动或车型合格。没有重新提交已在运行的任务，没有使用付费视频服务。

实际浏览器在 1440×900 和 390×844 视口播放同一原生文件，currentTime 分别超过 0.83/0.82 秒，paused=false，媒体错误为空。连续播放约 0.6/2.6 秒时采样 Canvas，RGB 范围均为 255，变化通道数分别为 44245/44248。截图为对应 benchmark 目录内 `playback-1440.png`、`playback-390.png`。这是独立原生视频诊断页，不是新增的平台成片流程；移动端播放器外的空白与视频内部填充不同。诊断过程中先遇到跨域 Canvas 污染，再遇到暂停跳转采样未获得有效帧，最终改为同源连续播放采样，未为诊断重生成视频。

### 回归与后续优先级

- 完整 API 测试 77 项通过，2 项依赖弃用警告；浏览器 E2E 7 项通过。隔离 E2E 使用模型桩，真实生成证据来自上述 GPU 任务，二者不混淆。
- 下一步将参考图构图、裁剪与逐镜头选图接入现有素材准备流程，避免只在终端准备图片。用户只需确认平台准备的方案与素材，不承担素材制作工作。
- 然后验证一个完整森林骑行分镜，补声音和字幕，再扩展沙漠与涉水镜头。以上镜头不能仅以 API 成功或像素变化判定完成。
- 真正 360 度优先验证可靠的同车型 3D 资产与 Blender 路线；尚未安装或验证 Blender，也没有可靠的张雪 800X 几何资产。不得用其他车型代替，不把单图生成的背面当作真实几何。
- 本轮不新增裁剪 UI、不修改正式脚本、不自动接受候选，不宣称两款车型样片完成或达到 80 分。长期 Goal 保持 active。

## 剩余验收

后续增量：[参考图构图实现与真实验证](2026-09-07-reference-framing-implementation.md) 已将裁剪接入分镜页面，并验证新的真实生成、失败重做和竖屏下载；本文件上文保留当时的实现边界。

Wan 动态推理及平台单镜头生成到合成下载已经真实执行，原生竖屏骑行实验也已有可见运动。下一步将逐镜头参考图与构图准备产品化，改善车型细节保持和指定运镜，再补声音与完整脚本。真实 360 度几何、皮衣骑手高速驾驶、沙漠、涉水抬头、森林无人机镜头未完成，车型身份仍待确认。Goal 保持 active，不以链路或测试通过宣称达到 80 分。
