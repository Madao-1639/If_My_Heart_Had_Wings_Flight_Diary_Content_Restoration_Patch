# 验收标准

> ⚠️ **本文自姊妹作项目迁移：机检项已按本作重标定（见下「本作机检基线」），其余条目仍含姊妹作专属结论（`ASA_*`/`YOR_*`/922 处等），待逐条重做。** 引用前先核对本作事实。
> 迁移状态见 [README.md](README.md)「文档清单与来源」。

## 本作机检基线（现行）

| 闸 | 命令 | 本作基线 |
|---|---|---|
| 全量验收 | `python script/final_verification.py` | 构建阶段 33 PASS / 0 FAIL / 2 SKIP；发布阶段（`--stage release`，payload 已重建）**41 PASS / 0 FAIL / 1 SKIP**（仅无语音重指表）；含 5c 层内修复回读（repair 3）、**2b 回想出口不得多于 Steam 基线**（`replay_guards.json` 7 条声明）、**9b 尾表**（112 个 `.ws2`）、**9c 选项头**、**9d 选项文本/人名规范**、**9e 人名帧一致性**、**9f 跳转自洽**、**9f2 `.lng` 槽位等式**、**9g 选项帧内无 `0x16`**、**9h 新增选项规则可复用（演练）** |
| 演出同步 | `python script/checks/perf_sync_check.py` | 14,129 槽对账，HARD 0 / REVIEW 0；判定表 41 条逐条落地；**顺序闸**：53 条 `replace` 槽的产物演出序列 = 原版行序列（逐条逐序，`perf_sync_checked 53`）；**前置检验**：命中「文本无需还原 + 演出序列已相同 + 素材原生」的站点不改字节、不跑顺序闸（当前 `perf_sync_noop 0`，纯回归保护） |
| CG 序列 | `python script/checks/cg_seq_check.py` | 25 脚本，同序 25；HARD 0；REVIEW 0；继承审查差异 0 |
| CG 解锁 | `python script/checks/cg_unlock_check.py` | 1,617 个 CG 显示点，1,616 带解锁对（白名单水印 CG）；成就钩子 723 = Steam 723，逐脚本一致；CG 名零缺失 |
| CG/立绘 内容一致性 | `python script/checks/perf_consistency_check.py` | 14,001 槽全部内容一致；CG 差异 0 行、立绘差异 0 行；槽级豁免 5（`perf_waivers.json`：翻译拆行 2 / 水印 CG 1 / Steam 新增行 1 / 句序 1）。**在屏状态模型必须展开 `0x37` 的族级（`bg`/`st`）与通配（`*`）清屏**（`tool/perfsync.py`，见 [engine-mechanics.md](engine-mechanics.md)「图层清屏 `0x37`」）；不展开时「显示被 `37 *` 抹掉」这类黑背景缺陷是静默假绿 |
| 立绘记录号 / 层内修复 | `python script/checks/pna_id_check.py` | keep 成员 21 / 映射 839 / 层内修复 3；记录号越界 0；未修复改画引用 0；成员豁免 7 |
| 回想守卫 / 出口 | `python script/checks/replay_guard_check.py` | 7 条声明（drop 5 / keep 2）；`action=drop` 脚本产物 EVRET = 0；任何宿主 EVRET 不得多于 Steam 基线（无孤立回想出口） |
| WS2 尾表 | `python script/checks/ws2_tail_check.py` | 112 个 `.ws2`：末尾 8 字节明文 `[消息数][选项数]` == 实算值（基线已有偏差 0） |
| 选项头 | `python script/checks/choice_header_check.py [--pay]` | 每张 `0f` 前必须是 `0e 0b 00 <count> 00 01`，且 count 与表内一致（`final_verification` 9c） |
| 选项文本/人名规范 | `python script/checks/choice_spec_check.py [--pay]` | 选项帧内无 `0x28` / 无名字非空 `0x15`；提示句以 `%K` 收尾；条目落点 = `0b…` + 纯标记 `%P`（`final_verification` 9d） |
| 人名帧一致性 | `python script/checks/name_frame_check.py` | 每个 `_E.ws2` 与同名原版按正文对齐：原版旁白（空名字框）的行产物必须为空；原版有名的行产物也必须有名（`final_verification` 9e） |
| 跳转自洽 / 槽位等式 | `python script/checks/choice_jump_check.py [--pay]` | 所有绝对偏移（`01` 字段 7/11、`02`/`06` 字段 0、`0f` 条目 `06`）必须落在指令起点；每个脚本 `lng 条数 == 0x14 条数 + Σ(0f count)`（`final_verification` 9f/9f2） |
| 选项帧内无 `0x16` | `python script/checks/choice_frame_check.py [--pay]` | 每张 `0f` 的「提示句 → 选项头」区间不得含 `0x16`（Steam 侧它会关闭输入门 ⇒ 选项点不动）；写盘期由 `tool/ws2.drop_choice_frame_op16()` 剔除（`final_verification` 9g） |
| 构建前语料 | `python script/checks/preflight_corpus.py` | 5,348 条语料格式一致；4,227 个插入格全覆盖 |
| 构建后内容 | `python script/checks/verify_restore_content.py` | 20 个 `mixed_censor` 区间 / 154 个插入槽落位；lng 逐槽=语料 |
| 文本槽位等式 | `python script/build/build_lng.py`（内建断言） | 逐脚本 `lng 条数 == 0x14 条数 + Σ(0f count)`；`BEF_004` = 556 官方 + 390 语料 + **2 选项** = 948 |
| 资源覆盖 | `python script/checks/restore_asset_coverage.py` | 0 缺口 |
| 转换纯度 | `python script/checks/convert_purity.py` | 199,983 条指令 0 异常 |

本作成就基线：`CG_ACHIEVEMENT` **723 处 / 39 脚本**，`0xF0` **33 处**（逐脚本与 `backup/` 相同；`AGS_001.ws2` 为新增脚本，0 处）。交付归档 **13 个**（`asset/` 11 个 + `zh-CN/` 2 个）。
`resource/carrier_map.json` 为**实表**（107 脚本 / 8,579 锚点），管演出判定表生成；产物侧逐槽对账走 `slot_sources`。

> ⚠️ `script/verify_sync.py` 与 `script/checks/check_carrier_ledger.py` 为姊妹作迁移、**未适配本作 schema**，不计入本作验收；下方提到它们的能力项视为「待移植/待完善」。


补丁完成后应满足以下条件才能视为完成。以下标准是每次改动都应遵循的检查清单：**机检项**由 `script/final_verification.py` 逐条断言（闸的编号与次序见 [restoration-route.md](restoration-route.md) §5），**文本-语音-CG 三元组一致性**在姊妹作由 `verify_sync.py` 断言，本作**尚未移植**（当前以 `final_verification.py` + `script/checks/*` 为准；三元组剩余项见文末「待完善」），**人工核对项**（「文本还原」与画面判定）在对应机检接入前按判据逐场／逐名手工核对，**实机项**（见文末「实机测试」）只能手工跑图，不由脚本断言。

## 归档与文件完整性

- [ ] 改写后的 `.arc` 文件通过 `tool/arcbuild.verify()`，无成员越界、无表尾多余 null padding
- [ ] 改写后的 `.ws2` 脚本可正常用 `tool/ws2.decode()` 解码，不抛异常
- [ ] 改写后的 `.pna` 文件可正常用 `tool/pna.load()` 解析，且 `layer_count` 与实际条目数、图层数据边界一致

## 调用链完整性

- [ ] 所有新插入的跳转/调用目标脚本在归档中确实存在
- [ ] **文本槽位等式**：每个宿主脚本 `lng 条数 == 0x14 条数 + Σ(0f count)`（选项条目**各占一槽**，`strid` 与 `0x14` 的 `id` 共用按文件顺序的计数器）；选项中文来自 `resource/corpus/choice_cn.json`，缺译即构建失败（见 [file-formats.md](file-formats.md)「`0x0f` 选项表」与「选项编写规范」）
- [ ] **选项处实机验收**：两项均可悬停、均可点中、两条分支各进入对应剧情、动画正常、**上一句提示文本与选项同框**（`%K` 留框）；被验配置须与 `asset/`、`payload/`、游戏目录三者同一份字节
- [ ] **新增选项（非还原）实机验收**：手写两选项插入真实脚本后必须可显示、可点击、进入对应分支；文本必须经构建链（槽位重排 + `.lng` 补齐 + 尾表重写）后正确——绕过构建链会因槽位错位显示成别的台词
- [ ] **WS2 尾表正确**：每个被改写的 `.ws2` 末尾 8 字节明文 `[u32 消息数][u32 选项条目数]` == 实算的 `0x14`/`0x0f` 条数（`script/checks/ws2_tail_check.py`、`final_verification` 9b）。偏小 ⇒ 引擎「已读位图」容量不足 ⇒ 写位越界写坏堆 ⇒ 概率性闪退（`doc/file-formats.md`『尾部 8 字节』）
- [ ] **宿主脚本不得出现孤立的回想出口**：产物 `07 NextFile EVRET` 处数不得超过 Steam 基线（`script/checks/replay_guard_check.py` + `resource/replay_guards.json`，见 [route-mechanics.md](route-mechanics.md) §1.5）
- [ ] 原地插入的还原内容片段之后，脚本原有的其余部分（包括 Steam 版新增的成就调用指令）未被破坏或误删。删格**只移除被删文本行的正文指令 `14` 与其名字框指令 `15`**（守卫＝不改变任何存活格的生效名字框），**格内其余指令（演出、变量与布尔写入、图层调用、跳转、成就调用）逐字节原位**（见 [restoration-route.md](restoration-route.md) §7 V-9）
- [ ] **删格演出摘净**：被删行的演出前缀区（语音 `2e`+`28`、显示 `33`/`34`、BGM `1e`、图层定位 `46`、特效）随该行一并摘除（`tool/writer.drop_units()` 的 `KEEP_OPS` 之外全删）；状态写入／跳转／成就调用逐字节原位
- [ ] **无对白语音连播 = 0**：产物里不得出现「同一格携带多条**残留**语音触发」（名字属被删格）的段——`script/verify_sync.py` 的 `R.residue_voice_burst` ＝ 0 且 `R.residue_voice` ＝ 0。合唱行（原版自身一格多触发）不算
- [ ] **残留显示点 = 0**：`R.residue_cg`／`R.residue_sprite`／`R.residue_bgm` 全为 0，`B9-drop-residue`／`B8-picture`／`B8-bgm`／`B4`/`B6`/`B7-*-residue` 无 HARD。**只有顶包名（判定表 `class=reuse`）需要逐点核对**，且核对的作用域＝**还原后仍保留的 Steam 格**；每个需改写的格都有对应的**调用点级**改写结论或人工定案
- [ ] **1:1 块的内容面存疑对被处理**：`resource/carrier_map.json` 里带 `content_suspect` 的对（两侧语音号都存在且不同 ⇒ 非同一行）**必须走还原**（drop/rebind，原版行进产物），**不得**用民汉覆盖（`text_override`）消化——民汉覆盖只挂在 verified 保留格（`action=keep` + `text_override=true`）上，对 content_suspect 对无效（计划器 `build_host_plan` 对「保留格 + text_override 但槽在 content_suspect」直接断言失败）；既未还原又未合法覆盖 ⇒ 计划器**中止写盘**。复算：`script/build/build_carrier_map.py`、`script/build/build_restore_plan.py`
- [ ] **注入块的槽位终态**：随行注入的原版演出不得让同一立绘族同时占两个槽（换槽前先清**注入来源**占的槽）；Steam 骨架自有的绑槽次序与原生同族双槽未被改动
- [ ] 用脚本扫描全部路线前缀，确认没有遗留指向不存在脚本名的跳转（调用链组织见 [restoration-route.md](restoration-route.md) §2.1）

## 路线完备性（L6 入口）

> 姬城姐妹线入口 UI（按钮 + Lua 表 + PNA 图层 + 角色高亮 Cast）的验收；机检＝`script/checks/check_route_entry.py`，写盘＝`script/build/build_route_entry.py`，规格＝`resource/route_entry.json`，素材＝`resource/route_entry/`（定版，5 个 PNG）。“脚本本体 `AGS_001.ws2` 已补回”属 L1，另条。
> **状态：本组已全部通过并实机验证**（中文 + 英/默认两套 UI）。下方清单保留为回归闸。

- [ ] `LegacyGame.lua` `StoryMenuInit`（`142/8`）：按钮表长 8、内容 `[108,101,103,104,105,106,107,102]`、`SETLIST` 覆盖 8；且 i=8 的 sublayer 公式给出 on=19 / def=20
- [ ] `LegacyGame.lua` **逐按钮数值 FOR 循环上界全为 8**：表构造循环（`142/8`）**与** `MenuEffectStart` 的滑入动画循环（`142/4`）都不得残留上界 7（否则新按钮没有滑入动画）
- [ ] `SYS_C_Story.pna`：记录 19/20 为真实图层（`u0=0`、带完整 PNG、box 与规格一致、`layer_id = count-1-index`、不透明度 1.0）；**其余 43 条记录与 `backup` 逐字节相同**，记录数与画布尺寸不变
- [ ] 第 8 个按钮图形：掩膜核心内**逐字节 = 来源按钮对应字位的整数平移**、掩膜外**逐字节 = 官中目标按钮**（`tool/agsbutton.verify` 第 4 条）⇒ 底板颜色一致、背景与字体分界清晰，无重采样噪点
- [ ] 第 8 个按钮 PNG 的**辅助块与官中目标一致**（`gAMA/cHRM/bKGD/pHYs/tEXt`；`verify` 第 5 条）——尤其 `bKGD=(255,255,255)`，否则不支持 alpha 的查看器会把半透明底板合成到黑底，近透明像素看上去是黑点
- [ ] base（英/默认）UI：`SysGraphic.arc` 的 `SYS_Story.pna` 记录 19/20 = **原版日文**入口图形，且与原版对应记录（7/8）**逐字节一致**（`check_route_entry.py::check_base_pna`）；其余 43 层与 backup 相同、记录数/画布不变（英文模式下按钮可见、可点）
- [ ] **角色高亮（Cast）**：`SYS_Story` / `SYS_C_Story` 记录 **29** = 原版 `SYS_Story.pna` 记录 **23**（AGS 那张 Cast 图）**逐字节一致**；`StorySelCursor` 有 `id==102 → sublayer 29` 分支（`check_cast_lua` 断言 `id!=102` 落到块尾、块尾落到 hide-31..39 的 FORPREP）；两处 hide 循环上界为 **29**、不再有 28
- [ ] `mainmenu.ws2` 的 `var[98]==102 → AGS_001` 分派未被本步骤改动（反混淆后能搜到 `AGS_001`）
- [ ] 朱莉线保护：`asset/` 未含 `Rio1.arc` / `Chip10.arc` / `zh-CN/Rio1.arc`
- [ ] **实机**：剧情选择界面出现 8 个按钮（第 8 个文案「姬城姐妹的日常」在左下末端、字体/颜色/旋转/字距与其余一致）；8 个按钮均可点；**第 8 个按钮有与原生一致的滑入动画**；**悬停第 8 个入口时高亮姬城姐妹那张 Cast 图、切到其它入口时它正确消失**（中英两种 UI 都要看）；背景预览动画正常

## 成就触发点完整性

> 原则：成就由开发者与 Steam 共同管理，本补丁**只保留触发点**（不修改、不新增、不重算 id）。见 `AGENTS.md`「项目目的」第 1 条、[engine-mechanics.md](engine-mechanics.md) §成就触发点契约。
> 基线数据：`resource/achievement_map.json`。

- [ ] 全部 `CG_ACHIEVEMENT` 调用点（基线 **723 处 / 39 脚本**）逐字节保留，未被删除、合并或重排
- [ ] 每个调用点的 `0x0b` 变量对（A = 场景分组、B = CG 编号）取值与基线**逐一对应**，未改写、未重算
- [ ] 全部 `0xF0 <idx>` 触发点（基线 **33 处**）保留，`idx` 取值集合与基线一致；越界点**原样保留**，不得"修正"为合法值
- [ ] **四连不被切断**：`0x33 <CG 显示> → 0x0b A → 0x0b B → 0x04 "CG_ACHIEVEMENT"` 四条指令逐字节原位、相对次序不变。删格不摘显示头（画面还原走归档字节层，见 [restoration-route.md](restoration-route.md) §7 V-9）
- [ ] **未新增**任何成就触发指令：被删 5 脚本（`ASA_002/004`、`YOR_003/005/007`）内回填的 CG 显示点未补钩子（332 处）
- [ ] `CG_Achievement.ws2` 未被改动

**校验手段**：`tool/ws2dis.py --arc <Rio.arc>` 复扫改造前后，比对 `0xF0` 站点数/`idx` 集合与 `CG_ACHIEVEMENT` 调用数、`0x0b` 变量对取值集合是否不变。

## 文本还原（玩家视角）

> 判据是**玩过原版的人，能不能在这一版里重拾原版体验**。冲突时按项目总原则：**游戏体验 > 还原原版 > 其他**。
> 本节只管**文本差分**：形态（改写／整段删+新写／压缩概述／格数 > 行数）与处置（改绑／删／keep 加演）见 [restoration-targets.md](restoration-targets.md)「判定标准」。**画面维度的差分（改画／顶包／重编码噪声）另有判据**，见「资源配对正确性」与 [resource-naming.md](resource-naming.md) §1–§3；**两个维度互不推定**——文本逐行对位一致不代表画面没被动过，画面覆盖落地也不代表文本对齐正确。

- [x] **保留行的事件 CG 显示点缺口**：Steam 把原版**事件 CG** 显示点换成背景时，两侧**异名** ⇒ `censor_map`（只管同名冲突）与两条文本机检都看不见。已入库 `resource/cg_site_rewrites.json`（13 条）并由 `script/build/build_restore_plan.py` 消费（按 `rebind` 同形：drop 保留槽 + 插回原版行，随行带入 `0x33` 显示指令，成员并入 `resources.copy`）；13/13 产物已引用该 CG。**机检**：`python script/checks/cg_seq_check.py`——两侧 CG 显示**序列**（按名按序）逐项对比，同时把每段按 **CG 系列键**（`<角色>_<场景>`）分类：同系列 ⇒ 版本差异（号位/差分/位移，良性）；**异系列/类别级** ⇒ 缺陷候选。
- 另有 1 处**结构性**缺口（不属 CG 表）：`AGE_007` `s421` 是替代戏 `s379–s424`（已判「同拍去 H 版 ⇒ 全 drop」）里的**存活格**（原台账因承载图假锚 `o425↔s421` 把它当「接回点」保留），自带 `AGE_10_001S`；**补 drop** 后 CG 序列与原版一致。见 [lessons-learned.md](lessons-learned.md) §17
- [ ] **逐场未承载行 = 0**：还原范围内**每一行原版文本都能在某一格读到**。口径**按宿主脚本逐场聚合**（一个脚本被多处切片，单点覆盖与全局平均都无意义）。⚠️ 这是**必要条件、不是充分条件**：该闸只看原版行有没有格承载，**看不见顶替它的那段替代文本还在不在屏上**（见下条）
- [ ] **零双写：差分必须「覆盖」回去，禁止「追加」**：Steam 删改一段原版时往往**不留空**，而是**写一段摘要／替代文本占住那些格子**。这类站点必须**先把替代文本从格子里删掉、再落原版**（判读台账 `cells` 的 `drop` + `rebind`），**不得**在别处插一份原版而把替代段留在屏上——那会让玩家把同一件事读两遍（一遍精简且无必要、一遍详细），属**严重困扰**级缺陷。**例外（seam 桥接行）**：该格与还原的原版行**不是同一拍**（拿掉它前后原版行仍能直接对话）时，走「`insert` 补回原版行 + 保留该格」，并逐格登记——收口判据见 [restoration-targets.md](restoration-targets.md)「块类判别」
- [ ] **上两条必须同时成立**：只查「未承载行 = 0」对差分是**结构性盲区**。差分候选可由机械扫描枚举——**P 型**＝替代段紧邻缺失段；**现状即双写**＝缺失段已被 `insert` 补回而替代段仍在。**枚举结果只给置信度**，每一处都要人工读原文裁定「是同一件事的摘要／改写」还是「Steam **独立成段的新写场景**」，后者**不还原版、不得删**（`drop` **不可批量套用**）
- [ ] **机械形状只圈位置、不定案**：**不能用「语义对不上」判「Steam 新增」**（被改写／被压缩的格语义本来就对不上），要问「**这几格是不是在替掉缺口里的那几行**」；「该行语音号在原版全库查无」是**整段删**的硬证据与位置线索，**不构成**「该格属新增 ⇒ 保留」的结论
- [ ] **两类扫描盲区单独核对**：① 缺口里**没有文字格**的**纯空缺口**不会被差分扫描报出；② **无 CG／无语音锚点的纯文本段**对锚点回查是结构性盲区（承载图的锚点全是 token：语音名／PNG 名／跳转目标／调用名），必须走未承载行的语义核查
- [ ] **删格判据只认整行，子串＝半行**：判「这格能不能删」看它**承载**的是哪条原版行，但「不承载任何行」**不等于可删**——若它的正文恰是某条**仍被承载**的原版行的**真子串**（被切开的半行），删了句子会从半句开始或收尾。`equal` 整句才算重复、可删；只是子串 ⇒ **禁删**
- [ ] **允许的缺口只有两类**：① 已登记的工作项（承载图 `ambiguous` 的中部缺口，逐段读定形态，见 [restoration-route.md](restoration-route.md) §7 V-5）；② 已人工裁定为 **keep（加演）** 并逐槽登记在判读台账的独立新写段
- [ ] **承载图 × 台账只读对账**：`python script/checks/check_carrier_ledger.py` 退出码 0——A 覆盖对账无 ALARM（台账条目区间能被承载图块拼出）、B 已知假锚/拆行无 UNFIXED（`resource/carrier_quirks.json` 的每条 `ledger_rule` 均已落地）。A 的 `span`（台账区间跨相邻多块的并集，覆盖一致）与另一种「区间须与承载图块**逐字相等**」的口径是同一现象的两种口径，**都不是缺口**；`--content-scan` 输出的是人工待读候选（机器只能再发现的信号），不作为闸
- [ ] **1:1 块逐对过内容面核对**：承载图按 token 形状配对，**行数相等 + 锚点对齐不排除整段换写**（见 [lessons-learned.md](lessons-learned.md) §14、§26）。⇒ 每个 1:1 对须核两个维度：**两侧语音号归属**（不同即候选）与 **Steam 侧文本形状**（拉丁改写行＝该行被 Steam 重写）；命中且计划按 `carried-1to1` 承载（原版行从未进产物）⇒ 判**还原缺口**，交判读定形态，不得由校验器直接改处置。核对输出必须**逐对带两侧原文**供人工目视核对，只给号位读数不被采信。本条是「逐场未承载行 = 0」那条必要条件对面的补口——该闸看不见顶替段还在不在屏上。**`anchor` 块的文本面抽查**：`anchor` 默认 1:1 承载、且只有带 `content_suspect` 者进判读面 ⇒ 以下四类会静默未承载／零双写：① 两侧**语音号相同或缺失**但内容异；② 承载格藏在 `ambiguous` 段内、未登记 `bind_orig_row`；③ 落在还原区内的默认 keep 逐槽未登记；④ 区间边界漏行（原版行夹在两段插入之间）。抽查口径＝逐对读两侧原文（不靠语音号），无官中者回原脚本上下文并排；抽查与修复见 [restoration-targets.md](restoration-targets.md)

## 资源配对正确性

- [ ] 改动涉及的同名资源已逐一核实 hash，确认是否存在"同名不同内容"冲突（见 [restoration-targets.md](restoration-targets.md)「资源范围」）
- [ ] **图像类同名冲突逐名有类别与处置**：判定表 `resource/censor_map.json` 逐名登记 `class`（和谐／顶包／噪声）与 `action`（`overwrite` 覆盖非噪声者／`keep` 噪声），核对类别与人工看图结论一致；候选**只按内容哈希筛**（按体积或尺寸筛会整批漏检），「尺寸不同即不同内容」与「最近邻命中别的帧即号位复用」都**不作判据**，**引用点数（Steam 原生或还原后产物）也不作判据**，只当报警量（判据见 [resource-naming.md](resource-naming.md) §2）
- [ ] **语音类同名冲突逐名有类别与处置**：判定表 `resource/voice_conflict_map.json` 逐名登记 `class`（`noise` 仅容器差／`recode` 同录音被重编码或剪辑／`rerecord` 换录音）与 `action`（`overwrite` 非噪声者／`keep` 噪声）；候选**只按内容哈希筛**（同名 ∧ SHA256 不同即入候选，不得按体积筛）；**噪声判定须同时满足「解码 PCM 相关 ≥0.98」与「时长差 ≤0.15 s」**——只看相关会把「同一录音被剪掉一截」误判成噪声（重叠段相关仍近 1，但时长差大）。复算：`script/build/build_voice_conflict_map.py`
- [ ] **覆盖子集逐名对齐**：两张判定表（图像 `resource/censor_map.json`／语音 `resource/voice_conflict_map.json`）`action=overwrite` 的每一名都在产物里被换成原版字节，且**覆盖名单条数＝实际替换次数**（逐名对齐）；一条未落地即中止，**不得由"已覆盖大多数"推定无漏**。计划器另有一道前置闸：**语音覆盖名单数须等于语音判定表 overwrite 数**（名单外不得漏）
- [ ] **顶包名有存活格核对结论**：判定表 `class=reuse` 的成员逐个登记「还原后仍保留的 Steam 格里，该号位要对上的是哪一帧」（判定表成员的 `surviving_sites`，逐点 `decision` ∈ `rewrite`／`cover_ok`）；需要对上别的帧时，那一格的显示名已在**产物**里改写为对应原版名（写盘器按 `restore_plan.reuse_rewrites` 的偏移做等长 NUL 定界替换并回读校验）。**同名冲突一律不进改名表**（改名路线已取消，见 [resource-naming.md](resource-naming.md) §7）
- [ ] **对齐证据经过核实**：存活格调到的原版行来自承载图的 1:1 块，而 1:1 块可能是 Steam 自写段落被误判成逐行互译 ⇒ 顶包核对的结论必须在对齐修正后重跑（核对口径见 [resource-naming.md](resource-naming.md) §2）
- [ ] `B`/`S` 是同一张图的两个分辨率变体 ⇒ 处置按帧**成组**（同覆盖或同不动），不得只换一半；该帧只有单一分辨率形态时按判定表 `pair` 为空处置单个名字
- [ ] 涉及 PNA 图层替换的操作，已确认记录号对应关系没有因为记录表变化而错位；**同名 `.pna` 整名覆盖前已确认两侧记录数与层序等价**，不等价者**不得覆盖**，改走 `resource/pna_id_map.json` 的记录号映射 + 层内修复（没有改名隔离这条退路，见 [resource-naming.md](resource-naming.md) §3、[pna-resources.md](pna-resources.md)「同名 PNA 的跨版本记录表差异与处置」）
- [ ] **PNA 记录号/层内修复（`script/checks/pna_id_check.py`）**：产物所有 `0x39` 记录号 < 产物 PNA 记录数；原版来源块的号已按 `pna_id_map.map` 换算；`repair` 记录子图/box == 原版、非 repair 记录 == Steam 基线；产物引用到「改画记录」时必须已修复或成员已登记 `perf_waivers`；`repair` 不得与 `waive` 重叠。**层内修复的硬约束**：被换图不得出现在 Steam 新增段/未还原段复用的记录上（生产者按 `0x39` 引用分类核对）
- [ ] **已复核不纠正的差异逐条登记**：槽级/成员级/全局豁免落在 `resource/perf_waivers.json`，每条带类别与依据；评审闸按表跳过，不得靠"口头已知"消化
- [ ] **演出同步（保留槽演出：删多余 / 换回原版行）逐条落地**：判定表 `resource/perf_sync_map.json` 的 `action=drop`／`replace` 子集逐条进入 `plan.perf_sync` 并由写盘器处理（**名单条数＝落地条数**，`script/final_verification.py` 第 4b 项；**补块数＝期望补块数**由计划器断言）；`replace` 补块照抄**原版资源名** ⇒ 对应原版素材必须已补入产物归档（第 4 项「资源引用全部可解析」覆盖）。`replace` 的写入契约＝**整段演出替换**（宿主侧该槽前缀区的演出指令全删、只留状态写入/流程/成就与引擎调用/名字框；原版行区间**按原顺序**整段搬入并占被删指令原位）——顺序本身是演出的一部分，只换显示块会把宿主残留的拖拽/特效作用在空通道上（见 [restoration-route.md](restoration-route.md) §5.1、[lessons-learned.md](lessons-learned.md) §44）；`replace` 原版区间引用的素材同样必须落在交付面（`script/checks/restore_asset_coverage.py` 已覆盖该扫描面）。闸 `script/checks/perf_sync_check.py` 在**内容层被还原动过的宿主**上逐槽对账**「通道→图名」**（判据见 [restoration-route.md](restoration-route.md) §6 V-10）——产物显示了原版**全脚本都不出现**的图（Steam 新增素材）或名单未落地 ⇒ HARD 必须为 0（`ev`/CG 不计 HARD，交 `cg_seq_check.py`）；「原版在屏有、产物没有」／残留（`missing`／stale）⇒ REVIEW（逐条带根槽）。**残余必须逐条归因**：`ev`（CG）／已定案的声明内偏差（`no_counterpart`／`false_anchor`，记在 `resource/align_fixes.json`／`carrier_quirks.json`）／仍未定案（须列出）

## 改动面收敛

- [ ] 判定表 `action=overwrite` 子集与 `pna_id_map.repair` 记录**之外**的 Steam 原有成员/记录未被覆盖或修改（`backup/` 逐字节对照）
- [ ] 覆盖成员：产物字节 **＝** 原版成员字节（逐名断言）、成员名与归档表位置不变；脚本内资源名除**台账登记的顶包存活格调点改写**外未被改动，成就触发点全部原位
- [ ] **改名表不含同名冲突条目**：`rename_map.json` 的图像／`.MOS`／语音表里不得出现判定表内任何成员的原名（改名路线已取消）；现版更严——`voice`／`sprite`／`mos`／`est` **恒为空**、`plan.names` 恒为空，计划器留一道互斥闸作回归保护
- [ ] 覆盖前已备份被改写的归档（`X.arc.before_*`，见 AGENTS.md §工程约定 6）
- [ ] `backup/` 目录中的文件全程保持只读，未被任何脚本写入

## 实机测试

- [ ] 每次重大修改后，实际运行游戏测试受影响场景，确认无卡死、无报错、画面显示正常
- [ ] **画面还原的实机项**：覆盖到的 CG／立绘在进入对应场景时显示为原版画面，该图名在 Steam 保留段落里的调用点**不串图**（语义仍对得上），且没有意外走进打码（`.MOS`）路径；`class=reuse`（顶包）的帧还要核对**那一处存活格**显示的是它该对上的那一帧（走调点改写后的名字），而不是被覆盖收回原版的画面
- [ ] 测试成就触发是否正常（如果游戏支持在非 Steam 环境下模拟触发进行调试）

## 待完善

- **BEF_005 O#1116 纯删行尚未还原**：Steam 把「またエロサイトを見ていないかどうか。」整行删去，而缺口两侧行数恰好相等（Steam 又把 O#1119 拆成两格）⇒ 现 scope 未登记该 region。按评审建议只撤销了错误的人工演出处置（`drop@1121`/`replace@1122`），**没有补回该行**。若要补：新增 `restore_scope` region（orig 1116 / steam 0 行）+ 中文译文 + 重建 lng，属单独范围裁定。
- **实机场景清单**：见 [restoration-route.md](restoration-route.md) §5 第 7 项（A-1 的 5 个整脚本入口、A-2 插入点前后、后日谈入口链路 `mainmenu` → `start.ws2` → `flag 126` 路由）。
- **文本还原的机检进度**：姊妹作 `verify_sync.py` 路 A 有**1:1 块的内容面核对**（两侧语音号归属 ＋ 文本形状，命中 `carried-1to1` 即 HARD）；**本作尚未移植**，当前按判据人工核对；仍**没有机检**的是「逐场未承载行 = 0」与「零双写」两条，接入前只能按判据人工逐场核对。注意现有表自洽闸（格数自洽／覆盖无空档／行序单调）**查不出「两侧行数相同的改写」**——Steam 的替代段与原版行可以格数＝行数完全守恒，此类站点只能靠「读原文判形态」发现。**「零双写」的机检候选枚举应加一条**：`steam_only`／`ambiguous` 的 keep 块**若前指已被删／已改绑的槽**（文本面点名引用，或把被删格建立的状态当既成事实）即报警，交人工读（成因见 [restoration-targets.md](restoration-targets.md)）；`anchor` 的文本面抽查见上条。
- **删格残留的摘除出口尚未进写盘器**：产物上的**无对白语音连播**、以及残留指令引用 Steam 自有号段（`*_6xxx` 语音／`ST_*` 立绘／自有 BGM 选择）造成的**画面／音乐回退**，姊妹作 `verify_sync.py` 能逐条定位并归因（本作尚未移植）；写盘侧仍缺对应的**按名定点摘除／调用点改写**动作，属待授权工序（扩删除集与改写点都不在写盘器现有出口里）。
- **画面还原的机检位置**：判定表 `resource/censor_map.json` 的 `action=overwrite` 子集已由 `script/build/build_patch.py` 落地——写盘器在 Steam 同名成员上**原位换内容**（成员名与归档表位置不变），并以「**覆盖名单条数＝实际替换次数**」逐名对齐（缺一名即中止）；顶包存活格调点按 `restore_plan.reuse_rewrites` 的偏移做**等长 NUL 定界替换并回读校验**。（姊妹作 `verify_sync.py` 路 D 未适配本作；本作由 `final_verification.py` 第 5/5b/5c 项逐名回读产物字节 = 原版成员字节/层内修复记录，并核对改名表不含判定表成员——改名路线已停用、`plan.names` 恒为空。）⇒ 这几条现在是**构建期断言 + 校验器断言**，其中「覆盖名单条数＝实际替换次数」与「名单外成员不得被替换」已接入 `script/final_verification.py` 的第 5/5b 项；交付／安装侧的「同名成员换内容」由 `merge` 的 `modified` 成员类型覆盖，不需新增（见 [restoration-route.md](restoration-route.md) §6 V-8）。
- **安装器在真实玩家目录的交付回归**：机检覆盖到 `payload/` 的重放校验（`script/generate_payload.py` 按安装器同一口径重算并与 `asset/` 逐字节比对），未在一份真实 Steam 装机上跑过整档覆盖／资源级合并／裸文件三类交付与失败恢复路径。
