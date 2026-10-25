# 还原路线（技术方案）

> 差分判定标准见 [restoration-targets.md](restoration-targets.md)「判定标准」；机制依据见 [route-mechanics.md](route-mechanics.md) 与 [third-party-patch-analysis.md](third-party-patch-analysis.md)。
> 状态图例：✅ 已确认 ／ ⚠️ 部分确认 ／ ❓ 未知

---

## 1. 总体形状

**Steam 素材保留 + 就地还原 + 增量补充**：

1. **以 Steam 的 `*_E.ws2` 为脚本基线**（保留其成就调用与英文正文），只在还原范围内改写/插入。
2. **补回被删的整脚本**（`AGS_001.ws2`），并注入成就调用、接入 Steam 调用链。
3. **被新增脚本顶替的场景**：把 Steam 脚本里的跳转**改指**回原版场景，或就地缝合原版段落。
4. **同名素材**一律**整名覆盖**回原版（画面和谐还原）；**被删成员**按并集补入。
5. **中文**走原生 `zh-CN/Rio.arc`（`.lng` + `NameTable.txt`），**每次增删正文后整体重建 lng**。
6. **不碰朱莉线**（`Rio1.arc` / `Chip10.arc` / `AKA_*` / `zh-CN/Rio1.arc`）。

> 与国外补丁的关键差别：**不用英文基线缝日文原文**、**不把中文写进 ws2 窄字节**、**不靠尾跳硬接入口**。

---

## 2. 硬纪律

1. **成就触发点一个不丢**：`CG_ACHIEVEMENT` 调用原样保留；新插入的段落不得改变其位置语义（见 [achievement-mechanics.md](achievement-mechanics.md)）。
2. **偏移重定位不可省**：凡字节增删，`0x01`/`0x02`/`0x06` 的文件内绝对偏移必须重定位，并做四条强不变式自检。
3. **lng 位置对应**：`lng 条数 == 0x14 指令条数 + Σ(0x0f 的 count)`；正文一增删就**整体重建**宿主 lng。
4. **同名素材整名覆盖**，不设隔离改名路线；判定走图像比对，**尺寸/体积差不作判据**。
5. **不引入第三方补丁的产物**（脚本、文本、字体、DLL）；它们只作**线索**。
6. **幂等 + 回读**：改写脚本可重复运行，改后回读校验。

### 2.1 调用链组织（段级就地插入）

- 还原段落以**段级**插入宿主脚本，保持宿主首尾跳转结构不变（降低回归面）。
- 插入段落的**语音指令必须随格迁移**（语音与台词严格绑定），否则语音漂移。
- 插入后：重定位绝对偏移 → 回读反汇编核对 → 重建 lng → 端到端断言（槽位数 ↔ lng 条数）。

---

## 3. 本项目的结构性优势

1. **路线入口尚在**：`mainmenu.ws2` 仍跳 `AGS_001`，`AKA_010_E`（朱莉）也在同一张表 ⇒ 线路完备**不需要改造菜单**（[route-mechanics.md](route-mechanics.md) §0）。
2. **引擎知识可复用**：AdvHD 的 Arc/WS2/LNG/PNA/Lua/存档机制与成就注入工程要求已在 GalRev 沉淀。
3. **官方简中语言包已就位**：中文通路无需自造字体或 DLL 注入。
4. **两个第三方补丁提供了改动面线索**（可反推 Steam 的删改位置），但**不作为依据**。

---

## 4. 流水线

| 阶段 | 输入 | 产出 |
|---|---|---|
| **S0 标定** ✅ | 本作 `AdvHD.exe`（IDA） | FD 版 WS2 操作数格式表 → `resource/ws2_formats.json`；反汇编器 `tool/ws2fmt.py`（Steam 侧 111/111 剧本 100% 平铺，且 `0x14` 计数与官方 `.lng` 条目数逐一相等） |
| **S1 差分扫描** | `backup/`（Steam）+ 原版目录 | 脚本级/成员级/像素级差分报告（脚本级已可用 `tool/ws2fmt.py` 做**指令级**比对） |
| **S2 计划生成** ✅ | `resource/restore_scope.json` + `backup/` + 原版目录 | `resource/restore_plan.json`（逐脚本 `drops`/`inserts`/成就数）+ `tmp/restore_plan.md`；工具 `script/build/build_restore_plan.py` |
| **S2b 立绘记录映射** ✅ | 计划 + `censor_map keep` 的 21 个同名 PNA + 两侧 `Graphic.arc` | `resource/pna_id_map.json`（原版记录号 → Steam 记录号、改画清单、层内修复/豁免清单）；工具 `script/build/build_pna_id_map.py`。**必须在 S3 之前**（写盘器要按表换算 `0x39`） |
| **S3 写盘** ✅ | 计划 + `pna_id_map.json` + 原版脚本 | `asset/Rio.arc`（14 个 `*_E.ws2` 就地重建 + 新增 `AGS_001.ws2`；原版来源块的 `0x39` 记录号已按表换算、`0x46` 子层槽绑定标志已跨引擎归一（`0x80→0xf0`，见 [lessons-learned.md](lessons-learned.md) §50）；**回想出口三连按 `resource/replay_guards.json` 剥离**；**选项帧内的 `0x16` 按 `tool/ws2.drop_choice_frame_op16()` 剔除**（Steam 侧它会永久关闭输入门，删后提示句与选项同屏）、**末尾 8 字节明文尾表按新条数重写**、**动画离场→CG 转换点按 `resource/anim_exit_clears.json` 在 CG 显示前补 `37 <通道>`**（Steam 引擎上搬入动画终点与原版不一致，见 [lessons-learned.md](lessons-learned.md) §51））；工具 `script/build/build_patch.py` + `tool/writer.py` + `tool/pnaids.py`；槽位表 `resource/slot_sources.json` |
| **S3b 画面覆盖** ✅ | `censor_map.json` + 两侧图像归档 | `asset/Graphic.arc`/`Chip*.arc` 同名整名覆盖；工具 `script/build/build_l3.py --write-asset` |
| **S3c 素材补入** ✅ | `asset/` + 原版目录 | 缺失成员按原版名补入（`Graphic.arc`/`Chip1`/`Chip2`/`Se`）；工具 `script/build/build_l4_extra.py` |
| **S3d 层内修复** ✅ | `pna_id_map.json` 的 `repair` + `asset/Graphic.arc` + 原版 | 把被 Steam 改画的子图/box 换回原版（不改记录数/顺序/画布）；工具 `script/build/build_pna_repair.py`。**必须在 S3b/S3c 之后**（以它们的产物为底），并把 `GRAPHIC.arc` 的文件名规范回 backup 的 `Graphic.arc` |
| **S4 文本** ✅ | 槽位表 + 官方 lng + 本项目语料 | `asset/zh-CN/Rio.arc`（15 个 `.lng` **整体重建** + 新增 `AGS_001.lng`）；工具 `script/build/build_lng.py` |
| **S5 校验** | `asset/` | 验收闸（见 §5） |
| **S6 发布** | `asset/` | `payload/` 增量包 + 安装器 |

**测试阶段**：`asset/` 只含相对 `backup/` 有差异的交付文件，测试时直接覆盖到游戏目录。
**发布阶段**：三种交付形态＝整档覆盖（体量小的归档 + 玩家目录原本不存在的新档）／资源级合并（成员类型 `added`/`modified`/`keep`/`deleted`）／裸文件（`RIO/` 之类磁盘目录）。

---

## 5. 验收

按 [acceptance-criteria.md](acceptance-criteria.md)：归档完整性、调用链完整性、**成就触发点完整性**、**路线完备性**、资源配对正确性、**lng 位置对应（条数等式）**、改动面收敛核实、实机测试。

内容面闸（构建前/后各一，均须通过）：

- `script/checks/preflight_corpus.py`（构建前）：语料逐条与 `jp` 在控制标记（`%K`/`%P`）与换行结构（字面 `\n`）上一致；`restore_plan` 全部插入原版行在语料中、非空、无假名、非占位；插入锚点不落在删格集内。
- `script/checks/verify_restore_content.py`（构建后）：每个 `mixed_censor` 区间的插入槽数 == 原版行数、产物行文本非空、插入槽 `.lng` 中文与语料逐槽一致；`pure_add` 区间的 Steam 新增行仍在产物里。

移植自姊妹作的三个闸（已按本作数据模型重标定，不是路径替换）：

- `script/checks/perf_sync_check.py`（演出同步 + **顺序闸**）：逐产物槽比对 `slot_sources` 声明的来源行（`steam` 槽 / `orig` 行），槽自带的语音/显示/清屏/SE/BGM 必须与来源行一致（HARD）；`orig` 槽在屏出现原版与 Steam 两侧都没有的图名判「产物自造」（HARD）；其余在屏差异登记 REVIEW。本作 `perf_sync_map.json` 41 站点全部落地（名单 41 / 落地 41）。**顺序闸**：`replace` 槽（53 条）的产物演出序列必须与原版行 r 的序列**按序一条不差**（`replace_order_diff`：把原版序列当连续块在产物里匹配、允许跳过骨架指令与插入行正文，再断言块后到该槽 `14` 之间只剩骨架），判据与产出端共用 `tool/writer.py::perf_is_presentation` / `_perf_replace_zone`（见 §5.1）。
- `script/checks/cg_seq_check.py`（CG 序列）：以 `restore_plan` 的 host/whole 脚本为范围，产物 vs 原版按名按序比对。行归属用**前缀模型**（演出/语音/名字 → `0x14`；`0x14` 之后的指令属下一行，见 `doc/file-formats.md`「格内指令的归属次序」）；`CSEV_*` 纳入 CG 类并单列 `steam-censor-variant`。差异按 Steam 侧解释——产物段 ⊆ Steam 序列 ⇒ 继承的审查差异，登记 baseline；两侧都不解释 ⇒ REVIEW；两侧都没有的图名 ⇒ HARD。默认只报告，`--strict` 时 REVIEW 也失败。
- `script/checks/cg_unlock_check.py`（CG 解锁）：产物每处 CG 显示必须紧跟固有解锁对 `0x0b A 01 0x0b B 01`（白名单 `FDSDEV14_02B/S`：原版与 Steam 两侧都没有该对）；`04 CG_ACHIEVEMENT` 钩子总数与逐脚本数必须等于 Steam 基线 723。另报告 Steam 有、产物无的 B 编号（鉴赏页按 Steam 编号索引）与原版显示点中完全消失的 CG 名——这两项属鉴赏面，只报告不判失败。
- `script/checks/perf_consistency_check.py`（CG/立绘 内容一致性）：按语音锚点把产物槽对齐原版行（**先剔除 `resource/orig_deleted.json` 登记的原版被删行**，再应用 `resource/align_fixes.json` 的人工定案；否则整行删除会让等长缺口把后续槽整体映射错 1 行），比较在屏 CG 与立绘；**对齐的是内容不是文件名**——`tool/imgcmp.same_content` 判水印级 PNG（mean<3、>16 像素<3%）与 PNA 图层集相同者等价，不纠正；差异按根因行（own 显示/清屏）归类；`resource/perf_waivers.json` 的槽级豁免直接跳过。
- `script/checks/pna_id_check.py`（立绘记录号 / 层内修复）：产物所有 `0x39` 记录号必须落在产物 PNA 记录表内；`repair` 记录的子图/box 必须等于原版、非 repair 记录必须等于 Steam 基线；产物引用到「改画记录」时必须已修复或成员已登记 `perf_waivers`；`repair` 不得与 `waive` 重叠。
- `script/checks/ws2_tail_check.py`（WS2 尾表）：产物每个 `.ws2` 的**末尾 8 字节明文** `[u32 消息数][u32 选项条目数]` 必须等于实算的 `0x14`/`0x0f` 条数。偏小 ⇒ 引擎「已读位图」容量不足 ⇒ 写位越界写坏堆 ⇒ 概率性闪退；见 [file-formats.md](file-formats.md)「尾部 8 字节」与 [lessons-learned.md](lessons-learned.md) §47。
- `script/checks/replay_guard_check.py`（回想守卫/出口）：`resource/replay_guards.json` 的 `action=drop` 脚本，产物里 `07 NextFile EVRET` 必须为 0；`action=keep` 脚本的 EVRET 处数必须等于 Steam 基线；**全局**任何宿主不得比 Steam 基线多出 EVRET（= 不得出现孤立的回想出口，见 [route-mechanics.md](route-mechanics.md) §1.5）。
- `script/final_verification.py`（全量验收）：归档完整性、调用链、成就触发点、资源配对、零破坏性、可复现性（`--stage build` 时 payload 未重建 ⇒ 明确 SKIP，`--stage release` 强制）、交付项完整性、WS2 线性自洽、语音重指。本作基线：`CG_ACHIEVEMENT` 723 处、`0xF0` 33 处；交付归档 13 个。

`resource/carrier_map.json` 在本作是**实表**（107 脚本 / 8,579 锚点），用于 `build_perf_sync_map.py` 生成演出判定表；产物侧的逐槽对账仍以 `slot_sources`（计划器产出、逐槽权威）为准，闸不直接用承载图推断在屏状态。

### 5.1 演出同步 `replace` 的写入契约（`tool/writer.py`）

`replace` 的语义是**「该槽的整段演出 = 原版行 r 的整段演出」**——不是「在屏图集合相同」。
创作者把**复位 → 显示 → 拖拽/特效 → 渐变 → 计时 → 音频**写成一条有序的指令流；**顺序本身
就是演出的一部分**。因此落到字节上是**整段替换**，两条缺一不可：

1. **宿主侧整段作废**（`_perf_zone_kill`）：该槽前缀区里的演出指令（显示 `33`/`34`、清屏
   `37`、拖拽 `45`、特效 `47`/`48`/`57`/`66`、渐变 `65`、计时 `11`/`12`、图层权重 `09`、
   音频 `1e`/`1f`/`28`/`29`、立绘帧号 `39`、`16`/`64`/`3e`）**全部删掉**；只逐字节保留
   **非演出**：状态写入（`0b`）、流程（`07`/`0f`/`ff`，以及目标在区外的 `01`/`02`/`06`；
   目标全在区内的 `01`/`02`/`06` 属「演出内分支」，随演出删）、成就与引擎调用
   （非 `LAYER_ORDER` 的 `04`、`1c`）、名字框（`15`）、`05`、`f0`。
2. **原版侧整段搬入并保序**（`_perf_replace_zone`）：原版行 r 的前缀区按**原顺序**发出，
   只排除流程（`01`/`02`/`06`/`07`/`0f`/`ff`）、名字框（`15`，等价且与外层 lng 槽绑定）、
   非 `LAYER_ORDER` 的引擎调用。落到宿主里占**第一个被删指令的位置**（`_perf_add_anchor`），
   于是宿主的复位/初始化指令仍在补块之前执行，不会「先画后复位」。

> 为什么必须整段、不能只换显示块：宿主残留的 `45`（拖拽）/`47`（特效）/`09`（参数）会作用在
> **已经被删掉的通道**上——实机表现是**动画错乱**（`HUS_001` 第三行「グライダーって…」前的
> 上抛动画被丢在空的 `bg02` 上）。详见 [lessons-learned.md](lessons-learned.md) §43／§44。

> 为什么不能只「保序插入显示块」：`37 *`（通配清屏）与显示块的先后有意义，见
> [lessons-learned.md](lessons-learned.md) §43；`37` 的三种目标形态见
> [engine-mechanics.md](engine-mechanics.md)「图层清屏 `0x37`」。

**前置检验（no-op 跳过，`perfsync.site_noop`）**：`replace` 站点在改写前先过三条件——
① 文本侧无需还原（该 Steam 槽不落在任何非 `no_action` 的 `restore_scope` 区间里，`scope_text_clean`）；
② 该槽的**演出序列**已与来源原版行逐条相同（含顺序，`writer.perf_zone_sig` / `perf_expected_sig`）；
③ 演出引用的素材在交付面且是**原生**的（在 `backup/` 里存在、且 CG/立绘没被 Steam 改画而我们又没覆盖回原版，`perfsync.site_noop` 查 `delivery_names` / `censored_kept_names`）。
三条全中 ⇒ 该站点「本来就对」：**不改字节**（不删不补），构建报告记 `noop=`；素材缺/被改画而其它条件满足时打 `! <脚本> 槽 <n> 不能判 no-op：<原因>`，照旧整段替换（不静默降级）。
**判定结果不落表**（`perf_sync_map` / `restore_plan` / `restore_scope` 已三表同源，再派生一张必然漂移）：产出端与闸各自用同一批函数现算。当前 53 条 `replace` 站点实测 **no-op = 0**，该检验是纯回归保护。

闸门：`script/checks/perf_consistency_check.py` 逐槽断言「在屏集合 == 原版行 r 的在屏集合」
（状态模型已展开族级/通配清屏）；`script/checks/restore_asset_coverage.py` 已把
`replace` 的原版区间纳入资源引用扫描（原版 SE/遮罩/特效名必须能在交付面找到）。

**插入边界状态规范化（移植姊妹作 V-11「对齐状态」机制，两处对齐点）**：`tool/writer.rebuild_host` 在**插入块开头**（对齐「原版第 `r0-1` 行 `14` 落笔时」）与**`replace` 补块发完之后**（对齐「原版该行 `14` 落笔时」——补块＝原版行演出，发完即该行态）按原版在屏状态对齐——逐通道发**清屏**（`37 <通道>`），只对「原版该点无图、产物在屏有图」的通道发（**只发「清」是刻意的**：清屏不向格子添加演出 token；需要补/换的情形必须能被闸看见，归 `perf_sync` / `perf_sync_manual` 入库表，不静默补；`replace` 连删带补只补原版行**自带**的演出，原版行没有对应清时净丢一次「清」——被删 Steam 槽承担的清就此消失，由该处对齐兜底）。在屏状态沿**已发出的整条产物流**跟踪（宿主保留段 + 补块 + 插入块，族级/通配清屏展开）。⇒ 边界净状态不再依赖任何一条指令的存活。当前全库实测两处对齐共发 0 条清屏（边界状态已由逐槽对齐保证），属机制护栏。

闸门（两道，均为 HARD）：

- `script/checks/insert_boundary_check.py`：每个**插入块入口**与 **`replace` 站点入口**的在屏状态必须与原版对应点一致（帧身份归一：`norm_sprite` + `_SC` 水印 + 同编号 `S`/`B` 同帧）；缺失/取值不同＝HARD（写盘器只发清，补/换必须走入库表）。
- `script/checks/op46_flag_check.py`：产物所有 `0x46` 的子层槽绑定标志必须落在 Steam 引擎自身词表（`0x00`/`0xf0`），原版 `0x80` 计数必须为 0（见 [lessons-learned.md](lessons-learned.md) §50）。
- `script/checks/anim_exit_clear_check.py`：`resource/anim_exit_clears.json` 逐条落地——产物中该原版行的前缀区内、第一条 `33/34` 显示指令之前存在对应 `37 <通道>`（位置与通道精确）；`perf_sync_check`/`perf_consistency_check` 按同一张表豁免（见 [lessons-learned.md](lessons-learned.md) §51）。

---

## 6. 已确认的技术结论

- WS2 为逐字节 rot6 混淆；`0x14` 对白、`0x0f` 选项、`0x34` PNA 显示、`0x33` PNG 显示、`0x04` 调用、`0x07` 跳转（`NextFile`）。
- **立绘 `0x39` 的 u16 = PNA 记录下标（0 基，含哨兵/空记录）**，不是 `layer_id` 字段；同名 PNA 的记录表跨版本会变（Steam 删哨兵/加层/重排）⇒ 原版来源块必须按 `resource/pna_id_map.json` 换算，记录表不等价者不整名覆盖、改走层内修复（见 [pna-resources.md](pna-resources.md)）。
- **本作 WS2 操作数格式表**：`AdvHD.exe` 的 `0x57ada8`（.rdata）按原始 opcode 索引，160/256 项有定义；类型码语义为 `0=i8`、`1/2=16位`、`3/4/5=32位`、`6/9/10=NUL 终止串（**含 NUL**，10 大写化）`、`8=占位（0 字节）`、`7=计数标记（先读 u8）`；`0xff`（9 B）与 `0x01`（mode 相关）是表外特例。
- **交叉验证**：Steam 侧 111/111 剧本 100% 平铺，且逐脚本 `0x14` 计数 == 官方 `zh-CN/Rio.arc` 同名 `.lng` 条目数。
- **成就：不注入**。ORIG 与 Steam 的 CG 固有 id 对交集为 0（按 ORIG id 注入是空操作）；
  Steam 侧原有的 `0x0b`×2 + `04 CG_ACHIEVEMENT` 属 `KEEP_OPS`/非 `LAYER_ORDER` ⇒ 删格时已被保留。
  验收 = 产物 `CG_ACHIEVEMENT` 数 == Steam 原有数。
- **WS2 末尾 8 字节 = 明文尾表** `[u32 消息数][u32 选项条目数]`：引擎按它给「已读位图」（存档目录 `MessageFlag.dat`）分配容量，写位**不查边界**。改写脚本（插入/删格/跨版本搬运）后必须按新条数重写这 8 字节（明文、`encode()` 之后写）；偏小 ⇒ 概率性闪退。闸：`script/checks/ws2_tail_check.py`、`final_verification` 9b；机制见 [file-formats.md](file-formats.md)「尾部 8 字节」、踩坑见 [lessons-learned.md](lessons-learned.md) §47。
- **存档/已读表不在本项目范围**：`MessageFlag.dat` 的记录按首次写入的尾表定长、不随脚本增长重算，装了补丁后旧记录可能偏小；这属引擎存档系统的行为，**安装器不读不写**，本项目只负责把**脚本尾表**写对（上一项）。诊断口径见 [engine-mechanics.md](engine-mechanics.md)「已读消息位图」。
- `.lng` 布局：`u32 count` + `u16[count]` 长度表 + 字符串体；字符串 UTF-16LE 逐字节 XOR，**本作密钥 `0x3E`**。
- 语言包目录范式：`zh-CN/{AdvHDLang.dll, Fonts.arc, Rio.arc, Script.arc, SysGraphic.arc}`；中文剧本无 ws2，全部经 `.lng` + `NameTable.txt` 注入。
- 脚本内窄字节按 CP932 解码 ⇒ **简体专用字写不进 ws2**。
- **本作脚本无尾部追加字节**：以 `0xff`（9 字节）收尾即文件末尾（姊妹作那 8 字节尾在本作不存在）。
- **`0x0f`（选项菜单）全语料仅 ORIG `BEF_004.ws2` 一处**（Steam 已删）；条目为 `0x5e`/`0x5f` 指令，
  其中 `0x5e` 操作数**尾部 4 字节**才是条目分支目标（u32 绝对偏移）。
- **跳转目标落在被删区间**（Steam 的存档续玩检查点，如 `BEF_003_E` 头 `06 -> 0xa820`）⇒ 回落到
  同一叙事位置的**还原块起点**。
- **原版格式表缺项**：原版 exe 表只定义 102 个 opcode，`BEF_004.ws2` 用到 `0x5f`/`0x80` ⇒ 经验修补
  `tool/ws2dis.ORIG_TABLE_PATCH`（借 Steam 表形状）。
- 本作语音命名（实测）：**原版 = `<角色名>_<4位>.ogg`**（`KOTORI_0140.ogg`、`AGEHA_0468.ogg`、`KANA_0564.ogg`）；**Steam = `V<3字母><4位>.ogg`**（`VASA0009.ogg`、`VYOR0025.ogg`、`VKAN0181.ogg`）——**两套命名，需映射表**（注意 `SUB-TITLE_*.ogg` 不在 `Voice.arc` 内）。
- ⚠️ 原版与 Steam 的 **WS2 指令集几乎一致**（两表 96 项相同、仅 7 项差尾字段；如 `0x14`：原版 `[4,6,8,6,8]` vs Steam `[4,6,8,6,8,0]`），差异只在 **Lua 版本**（5.1 vs 5.3）⇒ **跨版本搬运可行**（见 [route-mechanics.md](route-mechanics.md) §5.1）。


## 7. 待办

1. ~~S0 标定本作 WS2 操作数格式表~~ ✅ 已完成（见 §6）。
2. ~~导出原版 `AdvHD.exe` 的格式表~~ ✅ 已完成 → `resource/ws2_formats_orig.json`（原版 107/108 剧本 100% 平铺）。
3. 差分扫描：脚本级（跳转/`0x14` 槽位/语音指令）+ 成员级 + 像素级（脚本级工具已就绪，**原版亦可反汇编**）。
4. ~~**L1**：补回 `AGS_001.ws2`~~ ✅ 已完成（跨版本转换 + 147 处成就，`asset/Rio.arc` 新成员）；~~**L6** 入口 UI~~ ✅ 已完成并实机通过：按钮图形（中/英两版，定版入 `resource/route_entry/`）+ 按钮表 7→8 + 逐按钮动画上界 8 + PNA 记录 19/20 + 角色高亮 Cast（记录 29）+ `StorySelCursor` 的 `id==102` 分支（见 [route-mechanics.md](route-mechanics.md) §0.1）。
5. ~~**L2**：就地还原~~ ✅ 已完成（14 脚本，`drops`/`inserts` 落地；成就站点覆盖 100%、`%LC` 转 Steam 键、`KAN_3002_2` 尾跳改指 `KAN_3003_E`；**回想出口三连按 `resource/replay_guards.json` 剥离**——Steam 侧头部入口分派已删，只搬出口会在场景末尾提前回主菜单，见 [route-mechanics.md](route-mechanics.md) §1.5）。
6. ~~**L5 中文**：lng 重建~~ ✅ 已完成（`asset/zh-CN/Rio.arc`：15 个 `.lng` 整体重建，条数 == 槽数、逐条非空、无假名残留）。
7. **S5 校验 / S6 发布**：跑 [acceptance-criteria.md](acceptance-criteria.md) 全闸 → `script/generate_payload.py`（`asset/` → `payload/` + `METADATA.json`，自带回读重放）→ `bash script/pack.sh`（PyInstaller 安装器 → `releases/`）。
   ⚠️ `payload/` 已于 2026-10-21 按当时 `asset/` 重建；**`releases/` 的安装器仍早于最近的脚本改动（含回想出口剥离），发布前必须重跑 `bash script/pack.sh`**。
8. ~~**L3 画面还原**~~ ✅ 已完成（`Graphic.arc` 59 覆盖 / 21 层序不等价 keep；`Chip2.arc` 2 覆盖；台账 `resource/censor_map.json`）；~~L4 补漏~~ ✅ 已完成（`Chip1/Chip2/Graphic/Se` 并集，资源覆盖闸 0 缺口）。
9. **残余**：② **语料残留错字**（逐字映射的一形对多义残留：`鹢→裤`、`鳌→厉`、`纽→扭`、`镐→搞` 等约 40 字，收尾修正见 `script/scope/fix_cn_phrases.py`，逐行判定见 `tmp/verify/cn_residual.md`）；③ `BEF_004` 的 `0x0f` 选项菜单文案仍是日文（原版即嵌在脚本窄字节里）。

## 8. 与既有产物的关系

- 本项目**不依赖**国外还原补丁或中文汉化补丁的产物；二者仅作**改动面线索**与**反向验证**（若我们的还原结论与它们一致，说明方向对；不一致时以我们的为准）。
- `tool/` 与 `doc/` 中引擎通用部分来自姊妹作项目；引擎层最新结论以 GalRev 为准，本作标定值以本项目为准。
