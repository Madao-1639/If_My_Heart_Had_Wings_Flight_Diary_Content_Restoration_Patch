# 在这苍穹展翅 - 飞行日志 - 内容恢复补丁项目

## 项目目的

为 Steam 版《在这苍穹展翅 - 飞行日志 -》（If My Heart Had Wings -Flight Diary-）制作内容恢复补丁，在保留 Steam 成就系统与**新增的朱莉线**的前提下：

1. **线路完备**：补回被删的**姬城姐妹线**（姫城あげは `AGS_*` + 姫城ほたる `HOT_*`），**同时保住**朱莉线（`AKA_*` / `Rio1.arc` / `Chip10.arc`）
2. **线路完整**：还原现存路线内被删减、被替换的段落（指令级差分）
3. **中文覆盖**：还原内容都有中文；缺语料时**以原版日文为唯一依据**就地翻译
4. **保留 Steam 成就**：成就触发点（`CG_ACHIEVEMENT`）一个不丢
5. **改动面收敛**：只改写**还原范围内**的内容；同名素材的内容差**一律整名覆盖**回原版，重编码噪声不动

## 项目背景

### 与姊妹作的关系

本项目与《在这苍穹展翅》（`..\..\If_My_Heart_Had_Wings\...Content_Restoration_Patch`）**同引擎**（AdvHD.exe），知识体系与工具链同源：

- 引擎层通识与工具已抽到 `..\..\GalRevserse\GalRev`（`galrev` Python 库 + `docs/` 分卷文档 + `data/` 引擎级数据表），**优先复用**；
- 本项目 `doc/` 中的引擎通用文档（`engine-mechanics` / `file-formats` / `achievement-mechanics` / `lessons-learned` / `sem-review-protocol`）自姊妹作迁移，可直接复用；
- **本作标定值必须重验**（opcode 表、脚本名正则、资源前缀、lng 密钥、语音命名、路线前缀），不得照抄。

### 已确认的技术挑战

- **剧本整体改名 + 整脚本删除**：Steam 把全部剧情脚本改为 `*_E.ws2`（英文版），并**删除了 `AGS_001.ws2`（姬城あげは线整条）**；`mainmenu.ws2` 的入口表**仍保留 `AGS_001` 跳转**（悬空引用）
- **全年龄化用"新增顶替脚本"实现**：如 `KAN_3002_2`（H 场景）在 Steam 被 `KAN_3002_2_E` + **新增的 `KAN_3002_3_E`** 顶替；两侧跳转结构一致，**差分扫描看不见**，必须读调用链
- **同名素材冲突**：`Graphic.arc` 同名 68 个内容不同（含 20 个被改画）；处置**一律整名覆盖**（噪声不动，**没有隔离改名这条路线**），判定走图像比对，**尺寸差与体积差都不能作分类判据**
- **素材以"归档成员删除"为主**：`Chip7` 删 298、`Chip8` 删 296、`Chip9` 删 325、`Voice` 增删互见；`.MOS` 成员（`Chip7` 118 / `Chip8` 138）用途未定
- **成就触发点与内容显示耦合**：还原内容时不能整体替换脚本，必须原样保留 `CG_ACHIEVEMENT` 调用
- **中文通路**：官方简中 = `zh-CN/` 语言包（`AdvHDLang.dll` + `Fonts.arc` + `Rio.arc` 的 `.lng`/`NameTable.txt` + `Script.arc` + `SysGraphic.arc`）；`.lng` 与脚本**按位置对应**，正文一增删就整体错位
- **WS2 指令集需重新标定**：GalRev 现有操作数格式表在本作 `mainmenu.ws2` 上遇 `0x82` 报 `UnknownInstruction`，**必须先读本作 `AdvHD.exe` 的格式表**

以上均为直接对比 Steam 版归档、原版发行版归档与两个第三方补丁得出的实测结论，详见 `doc/` 目录；第三方补丁的改动面与**不可沿用的做法**见 `doc/third-party-patch-analysis.md`。

## 素材来源

- Steam 版基线（只读参考）：`backup/`（另见环境变量 `IMHFD_STEAM_DIR`）
- 原版发行版素材：环境变量 `IMHFD_ORIG_DIR`，或与补丁目录同级自动发现（见 `doc/restoration-targets.md` §素材来源）
- 第三方补丁参考（**不可信，冲突时以我们的为准**）：见 `doc/restoration-targets.md`
- 引擎逆向知识：`D:\My_Code\tmp\GamePatch\GalRevserse\GalRev`

> **外部素材先入库**：`backup/` 里没有、只能从原版发行版取得、且**不可由脚本再生**的二进制素材（如姬城线的角色高亮 Cast 图、base UI 的原版日文入口图形），必须先落成 `resource/` 下的显式输入（`resource/route_entry/`），**build 只读 `backup/` + `resource/`**；原版目录仅用于由导入脚本（`script/build/import_route_assets.py`）重建这些文件。缺文件时 build 中止，不静默回退去读仓库外路径。**已定版的成品素材**（如路线入口按钮 PNG，即便理论上可由脚本再生）一旦在 `resource/` 入库，build 就只读该定版件，并保留对 `backup/` 官方素材的校验闸。

## 工程约定

### 1. 文档同步要求

**任何大型修改都必须同步到文档中**

- 修改脚本改写逻辑 → 更新 `doc/file-formats.md`
- 修改立绘记录号映射 / 层内修复（`resource/pna_id_map.json`、`0x39` 换算、`pna_repair`）→ 同步 `doc/pna-resources.md`、`doc/resource-naming.md`、`script/build/build_pna_id_map.py`、`script/build/build_patch.py`、`script/build/build_pna_repair.py`、`script/checks/pna_id_check.py`
- 新增资源命名规则 / 修改**同名素材冲突的处置方针** → 更新 `doc/resource-naming.md`，并同步 `doc/restoration-targets.md`、`doc/restoration-route.md`、`doc/acceptance-criteria.md`
- 修改**路线机制认知 / 入口开关 / 回想条目** → 更新 `doc/route-mechanics.md`
- 修改**对齐来源**（承载图锚 / 语音自证 / 等长缺口内插 / 人工定案 / 原版整行删除）→ 同步 `tool/perfsync.py`、`script/checks/perf_consistency_check.py`、`resource/align_fixes.json`、`resource/orig_deleted.json`、`resource/carrier_quirks.json`
- 新增或修改 `resource/` 输入表 → 更新 `resource/README.md`（表结构 + 生产者／消费方）
- 修改调用链结构 → 更新 `doc/restoration-route.md`
- 发现新问题/解决方案 → 更新 `doc/lessons-learned.md`
- 修改验收标准 → 更新 `doc/acceptance-criteria.md`
- 确认新的还原范围 → 更新 `doc/restoration-targets.md`
- 修改交付形态、打包或安装流程 → 更新 `doc/restoration-route.md` 与本文 §3
- 修改引擎机制认知（磁盘裸目录覆盖语义、`LAYER_ORDER` 行为、语言包目录） → 更新 `doc/engine-mechanics.md`
- 重新标定本作 WS2 opcode 表 / lng 密钥 / 语音命名 → 同步 `doc/file-formats.md`、`doc/engine-mechanics.md` 与 `tool/`

**文档写法**：只写**最新结论、工作范围、目标、标准/方针/原则、分层与工程约定**；**不写过程叙述**。过程证据一律放 `tmp/`（草稿区，不提交）。唯一例外是 `doc/lessons-learned.md`。

**方针改动必须三处同步**：产出端脚本、入库表（`resource/*.json`）、消费端脚本必须一起改；只改一两处的缺口是**静默**的，唯一能拦住的是**端到端断言**。

**闸门要能验内容**：凡「产物要被玩家读到」的字段，闸门必须落在**内容面**（逐条非空、不含纯数字占位、无假名残留），条数/长度这类结构量对"内容被整体替换成占位符"结构性沉默。

### 2. 临时文件管理

**生成的临时文件存放在 `tmp/` 目录下，任务结束后清除**（解码后的 WS2、提取的资源、中间结果、调试输出、一次性脚本）。

**脚本存放规则**：

- **长期复用的工具**：`tool/`
- **项目流程脚本**：`script/`
- **一次性/临时脚本**：`tmp/`（任务结束后删除）

### 3. 测试与发布流程

**测试阶段**：`asset/` 只含相对 `backup/` **有差异**的交付文件；「有差异」含同名成员只换内容；测试时直接把 `asset/` 下的文件覆盖到游戏目录。

**发布阶段**：从 `asset/` 生成增量补丁到 `payload/`，三种交付形态＝**整档覆盖**（体量小的归档 + 玩家目录原本不存在的新档）、**资源级合并**（其余归档按成员表重组，成员类型 `added`／`modified`／`keep`／`deleted`）、**裸文件**（`RIO/` 之类磁盘目录）。

**原则**：开发和测试使用完整文件（`asset/`），发布时才制作增量包（`payload/`）。

### 4. 脚本开发规范

**幂等性**：所有工具脚本必须支持重复运行；运行前检查"已满足则跳过"。

**回读校验**：改写资源引用后必须回读验证；修改偏移指针后必须验证指向正确；生成归档后必须验证成员完整性。

**编码规范**：

- 归档成员名、脚本内资源名/对白：Shift-JIS 或 UTF-16LE（视字段，见 `doc/file-formats.md`）
- 控制台输出使用 ASCII，或对 stdout 做 UTF-8 reconfigure；解码出的日文/中文文本不要直接 print，先写入 UTF-8 文件再用文件查看工具核对
- 使用 NUL 前缀的精确替换模式改写脚本内的资源引用，不要用朴素字符串替换
- **中文只写 `.lng`（UTF-16LE）与 `NameTable.txt`**：不要尝试把简体中文编码进 ws2 窄字节（CP932 写不出简体专用字，见 `doc/third-party-patch-analysis.md` §3.2）

### 5. 验收流程

每次重大修改后按 `doc/acceptance-criteria.md` 执行验收：归档完整性、调用链完整性、**成就触发点完整性**、**路线完备性（姬城线 + 朱莉线共存）**、资源配对正确性、**lng 位置对应（条数等式）**、改动面收敛核实、实机测试。

### 6. 备份策略

重要修改前必须备份归档（如 `X.arc.before_xxx`），记录备份时间和修改原因，验证备份文件完整性。

### 7. 版本控制

**不提交的文件**：`tmp/`、备份文件（`*.before_*`）、临时输出文件（见 `.gitignore`）。

**必须提交的文件**：所有 Python 脚本、文档（`README.md` 与 `doc/` 下全部）、配置文件。

**发布链的入库边界**：二进制交付物（`asset/`、`payload/` 里的归档与裸脚本、`releases/` 安装器）**不进版本库**，由脚本按 `backup/` + `resource/` + 原版目录重建；安装器要可在版本库里复原，最小集合是 `VERSION`、`resource/icon.ico`、`payload/METADATA.json`。

### 8. 安全要求

- 不修改 Steam 原版文件（仅读取用于对比），`backup/` 目录全程只读
- 验证所有输入文件的完整性
- 谨慎处理用户路径输入

## 技术栈

- **语言**：Python
- **编码**：Shift-JIS/UTF-16LE（游戏文件）、UTF-8（文档）
- **归档格式**：自定义 Arc 格式（8 字节头部 + 条目表，详见 `doc/file-formats.md`）
- **脚本格式**：WS2 二进制格式（rotate-6 混淆，详见 `doc/file-formats.md`）
- **资源格式**：PNA（图层容器）、PNG（背景/CG/立绘）、OGG（语音/音效/音乐）、Lua 5.3（引擎 UI 逻辑）
- **本地化**：`.lng`（UTF-16LE + 单字节 XOR，本作密钥 `0x3E`）+ `NameTable.txt`

## 参考文档

- [doc/README.md](doc/README.md) - 文档索引与阅读路径
- [doc/restoration-targets.md](doc/restoration-targets.md) - 还原目标、范围分层与判定标准
- [doc/restoration-route.md](doc/restoration-route.md) - 还原路线、流水线与发布链
- [doc/route-mechanics.md](doc/route-mechanics.md) - 路线机制与「线路完备」可行性
- [doc/third-party-patch-analysis.md](doc/third-party-patch-analysis.md) - 第三方补丁改动面与不可沿用做法
- [doc/file-formats.md](doc/file-formats.md) - 文件格式规范
- [doc/engine-mechanics.md](doc/engine-mechanics.md) - 引擎运行时机制
- [doc/achievement-mechanics.md](doc/achievement-mechanics.md) - 成就系统机制
- [doc/resource-naming.md](doc/resource-naming.md) - 资源命名与号段规范
- [doc/pna-resources.md](doc/pna-resources.md) - PNA 图层资源与命名规则
- [doc/afterstory-mechanics.md](doc/afterstory-mechanics.md) - 后日谈/回想机制
- [doc/script-text-extraction.md](doc/script-text-extraction.md) - 脚本文本提取与译文匹配
- [doc/sem-review-protocol.md](doc/sem-review-protocol.md) - 全量逐行通读的评审判据
- [doc/lessons-learned.md](doc/lessons-learned.md) - 问题记录
- [doc/acceptance-criteria.md](doc/acceptance-criteria.md) - 验收标准
- GalRev 引擎逆向知识库：`..\..\GalRevserse\GalRev\docs\README.md`
