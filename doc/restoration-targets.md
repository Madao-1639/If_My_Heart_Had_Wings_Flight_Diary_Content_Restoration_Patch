# 还原目标

> 状态图例：✅ 已确认 ／ ⚠️ 部分确认 ／ ❓ 未知
> 本文写**还原目标、范围分层与判定标准**；机制依据见 [route-mechanics.md](route-mechanics.md) 与 [third-party-patch-analysis.md](third-party-patch-analysis.md)，技术方案见 [restoration-route.md](restoration-route.md)。
>
> **逐剧本逐区间的动作定案**（哪个脚本、哪些格号区间、用什么形态处置）见 **[restoration-scope.md](restoration-scope.md)**，机器可读版 = `resource/restore_scope.json`（计划生成器与写盘器的唯一输入）。

---

## 目标

为 Steam 版《在这苍穹展翅 - 飞行日志 -》（If My Heart Had Wings -Flight Diary-）还原被移除的原版内容，同时：

1. **线路完备** —— 既要被删的**姬城姐妹线**（姫城あげは + 姫城ほたる），又要 Steam **新增的朱莉线**（原生全年龄，不做删减还原，只求**保住**）
2. **线路完整** —— 现存路线内被删减、被替换的段落（指令级差分）全部还原
3. **中文覆盖** —— 还原出来的内容都要有中文；缺语料时**以原版日文为唯一依据**就地翻译
4. **保留 Steam 成就** —— 成就触发点（`CG_ACHIEVEMENT`）一个不丢
5. **改动面收敛** —— 只改写**还原范围内**的内容；同名素材冲突一律**整名覆盖**回原版（同名 `.pna` 记录表不等价时改走记录号映射 + 层内修复），重编码噪声不动

---

## 范围分层（按优先级）

| 层 | 内容 | 依据 |
|---|---|---|
| **L0 · 工具链前置** | ✅ **已完成**：本作 WS2 操作数格式表已从 `AdvHD.exe` 标定（`resource/ws2_formats.json`），Steam 侧 111/111 剧本可 100% 反汇编 | [route-mechanics.md](route-mechanics.md) §5 |
| **L1 · 路线级还原** | 姬城姐妹线：`AGS_001.ws2`（あげは，整条被删）补回 + 注入成就调用 | [route-mechanics.md](route-mechanics.md) §2 G1 |
| **L2 · 指令级还原** | 现存路线内被替换/删除的段落（`KAN_3002_1_E`、`AFT_003_E`、`AFT_007_3_E`、`BEF_003_E`、`BEF_004_E`、`HOT_002_E`、`HOT_004_E`、`HUS_001_E`、`KAN_3001_3_E`、`KAN_3001_4_E`）—— **含ほたる线（姫城妹）的 H 内容** | 同上 G5；[third-party-patch-analysis.md](third-party-patch-analysis.md) §2.6 |
| **L3 · 画面还原** | 同名 CG/图层被和谐改画。**本作实测**（按小写折叠同名逐成员比 sha256）：`Graphic.arc` 同名 253 个、**内容不同 80 个（全部 `.pna`）**；`Chip2.arc` 同名 59、内容不同 2；`Chip1.arc` 同名 233、**内容不同 0**；`Chip3/4/5/6`、`Se/Bgm/SysVoice` 均 0；`Effect.arc` 的 15 个 `.fx` 是引擎着色器**不在范围**。
**判定结果（`script/build/build_l3.py`）**：`Graphic.arc` 80 个内容差里 **59 个判 overwrite**（层数/层序等价 + 子图改画）、**21 个判 keep**（层数/层序不等价 ⇒ 覆盖会让 Steam 侧既有 `layer_id` 调用点越界，一律不动）；`Chip2.arc` 2 个判 overwrite。台账 `resource/censor_map.json`（82 条：61 overwrite + 21 keep）。 | [third-party-patch-analysis.md](third-party-patch-analysis.md) §2.3 |
| **L4 · 素材补齐** | 被删归档成员：`Chip7`（298）、`Chip8`（296）、`Chip9`（325）、`Voice`（还原场景语音）。**`.MOS` 成员不补入**（用户决策） | 同上 §2.3/§2.4 |
| **L5 · 中文覆盖** | 还原内容的 `.lng` + `NameTable.txt`；每次增删正文后**整体重建 lng** | [restoration-route.md](restoration-route.md) |
| **L6 · 路线入口/回想** | ✅ **入口已开（实机通过）**：① 按钮图形（中/英两版，`resource/route_entry/` 定版）② Lua 按钮表 7→8（插回 102）+ 滑入动画上界 8 ③ PNA 按钮图层（记录 19/20）④ 角色高亮 Cast 图层（记录 29）+ `StorySelCursor` 的 `id==102` 分支；仅剩回想条目 `AGS_01/02/03` 按需补 | [route-mechanics.md](route-mechanics.md) §0.1/§3、`resource/route_entry.json` |

> **姬城姐妹线的构成**：姫城あげは（姉，`AGS_*`）**整条被删** ⇒ 只需补脚本 + 入口（无路线内差分）；
> 姫城ほたる（妹，`HOT_*`）脚本**仍在**，只是 H 内容被全年龄版顶替 ⇒ 属 **L2 指令级还原**。
> **朱莉线**（`AKA_*`）内容全部来自 Steam 且自带官中 ⇒ **不存在"还原"**，只需**保住**（不动）。


### 贯穿各层的约束

- **成就触发点完整**：`CG_ACHIEVEMENT` 调用**原样保留、不新增**（Steam 侧原有调用在删格时被保留；ORIG 侧注入是空操作，见 [restoration-scope.md](restoration-scope.md) §6.7）。
- **不碰朱莉线**：`Rio1.arc`、`Chip10.arc`、`AKA_*` 脚本与语音、`zh-CN/Rio1.arc` 全程保持 Steam 原样。
- **中文只走宽字符通路**：`.lng`（UTF-16LE，key `0x3E`）+ `NameTable.txt`；**不采用**第三方补丁"把中文写进 ws2 窄字节"的做法（CP932 写不出简体专用字，见 [third-party-patch-analysis.md](third-party-patch-analysis.md) §3.2）。
- **幂等与回读**：所有改写脚本必须可重复运行，改后回读校验。

### 不做

- 不还原 Steam 的**界面改版**（`SysGraphic.arc` 的 UI 重做、`Script.arc` 的 Lua 重构）——除非路线入口需要。
- 不统一两版**语音命名方案**（原版 `AGE_xxxx.ogg` ↔ Steam `AGEHA_xxxx.ogg`）；还原语音以 Steam 侧命名为准，原版名按映射表转换。
- 不动重编码噪声（同名归档里仅因重压缩而不同的成员）。
- 不做**英文化**：不引入国外补丁的英文文本，也不引入其日文原文缝合段。

---

## 判定标准：差分形态与采用口径

| 形态 | 判据 | 口径 |
|---|---|---|
| **A 整脚本缺失** | 脚本名只在原版存在 | 从原版补回，注入成就调用，接入 Steam 调用链 |
| **B 脚本被新增顶替** | Steam 新增 `X_2_E`/`X_3_E` 之类，原版链被改指 | 保留 Steam 脚本，**把跳转改指回原版场景**（或就地缝合原版段落） |
| **C 脚本内删段/缝合** | 同名脚本两侧**跳转结构一致**但正文体量差、`0x14` 槽位数不同 | 以 Steam 脚本为基底**就地插入**原版段落；**必须整体重建 lng** |
| **D 同名素材换内容** | 同名成员 SHA 不同且非重编码噪声 | **整名覆盖**回原版（[resource-naming.md](resource-naming.md)） |
| **E 归档成员删除** | 成员只在原版存在 | 并集补入（`Voice`）；CG 按 `Chip*` 对应关系补入 |

> ⚠️ 形态 C 与 D 的判据都**不能只看体量差**：C 要核对跳转结构与 `0x14`/`0x0f` 槽位数，D 要过五步图像比对（[resource-naming.md](resource-naming.md)）。

---

## 工作范围明细

### L1 · 路线级还原

| 对象 | Steam 现状 | 原版 | 处置 |
|---|---|---|---|
| `AGS_001.ws2` | **不存在**（入口 `mainmenu.ws2` 仍跳它） | 152 066 B，自包含，尾跳 `EVRET`/`TITLE` | 补回（跨版本重编码，**不注入成就**——该线路 Steam 侧无任何对应成就） |
| `HOT_001..005_E` | 存在（英文） | 存在（日文，含 H 内容） | 逐脚本指令级差分 |

### L2 · 指令级还原（Steam 侧已知被改动的同名脚本）

**H 场景脚本**（Steam 以同节拍全年龄改写顶替原版 H 段，形态全部为「整段删+新写」）：`AFT_003_E`、`AFT_007_3_E`、`BEF_003_E`、`BEF_004_E`、`HOT_002_E`、`HOT_004_E`、`HUS_001_E`、`KAN_3001_3_E`、`KAN_3001_4_E`、`KAN_3002_2`。

**非 H 脚本的阉割/改写**（本项目独立差分扫描发现，补丁未触及）：`KAN_2001`（处女话题段被换成回忆戏，49 格 + 2 纯删 + 内裤调侃软化）、`KAN_3001_5_E`（澡堂戏 6 格纯删 + 逗弄段改写）、`BEF_005_E`（胸部调侃段改写扩写 + ○ッコロ玩笑被改）、`KAN_2002_E`（朱莉台词商谈对象被改）、`HOT_004_E` O#323（部训语义反转）、`HUS_001_E`/`AFT_003_E`/`BEF_003_E` 的同位改写小区间。

**画廊**：`CG_PAGE01…04_E` 未按原版重建（相对原版缺 71/101/114/113 条、顺序不同）。

> 以上清单来自**本项目自己的三方差分扫描**（ORIG↔STEAM 语音锚点 + STEAM↔PATCH 文本锚点，134 区间逐处语义判定），不再依赖国外补丁的改动面反推；逐区间的形态、处置与格号见 [restoration-scope.md](restoration-scope.md) §3。

### L3 · 画面还原

**本作实测**：`Graphic.arc` 同名 253 个、内容不同 **80 个（全部 `.pna`）**；`Chip2.arc` 同名 59、内容不同 **2 个**（`FDSDEV14_02b.png`/`FDSDEV14_02s.png`）；`Chip1.arc` 同名 233、**内容不同 0**。
`.pna` 是图层容器 ⇒ **字节不同 ≠ 图像不同**，必须解析 PNA 逐层比图（[resource-naming.md](resource-naming.md) 五步判据）。判定台账 `resource/censor_map.json`（`members` 列表形态，消费端 `script/final_verification.py`）。

本作 80 个同名 `.pna` 的处置分两路（实测规模）：

- **59 个**两侧记录数/层序等价 ⇒ `overwrite` 整名覆盖回原版（`build_l3.py`）。
- **21 个**不等价 ⇒ `keep` 保留 Steam PNA，改走 **记录号映射 + 层内修复**（`resource/pna_id_map.json`，下一层 S2b/S3d）：原版来源块的 `0x39` 记录号换算成 Steam 记录号；被 Steam 改画、且**未被 Steam 新增段/未还原段复用**的身体层子图换回原版（本作 3 条）。朱莉线 `H朱莉_01*` 与 `*_W` 的裁切版保留 Steam 字节，登记 `resource/perf_waivers.json`（详见 [pna-resources.md](pna-resources.md)「同名 PNA 的跨版本记录表差异与处置」）。

### L4 · 素材补齐

| 归档 | 原版 | Steam | 需补 |
|---|---|---|---|
| `Chip7.arc` | 462 | 164 | 298 |
| `Chip8.arc` | 361 | 65 | 296 |
| `Chip9.arc` | 399 | 74 | 325 |
| `Voice.arc` | 9431 | 10265 | 并集（原版 ∪ Steam） |
| `Chip1.arc` | 245 | 258 | **+12**（`BG15_03B.PNG`、`BG24_01B.PNG` 等被还原块引用） |
| `Chip2.arc` | 71 | 61 | **+12**（`AGE_16_001S.PNG` 等） |
| `Graphic.arc` | 301 | 275 | **+48**（`CUTIN_98_05A/B.PNG` 等） |
| `Se.arc` | ？ | 223 | **+19**（`SUB-TITLE_*`、`T_SE16/80`、`TRSE_125`、`WBSE_185`、`YUSE_65` 等） |

> **L4 范围由「资源配对正确性闸」反推，不靠猜**：`script/checks/restore_asset_coverage.py` 扫还原块引用的全部资源名（2413 个），凡「交付面没有、原版有」的即列出 ⇒ 据此确定需并集的归档。当前闸为 **0 缺口**。
> 并集写盘 `script/build/build_l4_extra.py`（以 `asset/<归档>` 为底，保留 L3 的画面覆盖结论）。 |

> `.MOS` 成员（`Chip7` 118 个、`Chip8` 138 个）：**用途未定**（❓），需先判定是否被引擎引用，再决定是否补入。

### L5 · 中文覆盖

- 新增/还原脚本的 `.lng`（UTF-16LE，key `0x3E`）+ 人名 `NameTable.txt` 合并。
- **官方中文条目原样保留**；还原段落的中文以**原版日文**为唯一依据翻译。

### L6 · 路线入口/回想 ✅（入口已开）

- 写盘：`script/build/build_route_entry.py`（产 `asset/Script.arc` + `asset/zh-CN/SysGraphic.arc` + `asset/SysGraphic.arc`；素材**全部只读** `resource/route_entry/`，其中原版素材由 `script/build/import_route_assets.py` 重建）；验收：`script/checks/check_route_entry.py`；规格：`resource/route_entry.json`。
- **中文 UI**：按钮文案 `姬城姐妹的日常`（原版 `アフターストーリー：姫城姉妹編` 的对仗译名）。
- **英/默认 UI**：base `SYS_Story.pna` 记录 19/20 放**原版日文**入口图形（字节保真）。本项目不做英文化 ⇒ 英文模式下入口文字与线路内容均为日文，后继者只需补英文化即可用（见 [route-mechanics.md](route-mechanics.md) §3.8）。
- **角色高亮（Cast）**：原版被删的 AGS Cast 图（原版记录 23）补到两份 PNA 的记录 29；`initSubLayer` 循环与两处 hide 循环上界 28→29（**普通子层不 `initSubLayer` 则 `setSubLayerVisible` 静默无效**）；`StorySelCursor` 加 `id==102` 分支（见 [route-mechanics.md](route-mechanics.md) §3.9）。
- **素材形态**：入口相关的 5 个 PNG **定版入库** `resource/route_entry/`，构建只读 `backup/` + `resource/`（外部原版目录只用于 `script/build/import_route_assets.py` 重建素材）。
- 实机已通过（中/英两套 UI）：按钮可点、有滑入动画、悬停高亮姬城姐妹。
- 仅开**入口 UI**；脚本本体 `AGS_001.ws2` 属 L1。
- 待办：回想条目 `AGS_01/02/03` 按需补。

---

## 素材来源

| 用途 | 位置 |
|---|---|
| Steam 版基线（只读） | `E:\SteamLibrary\steamapps\common\IF MY HEART HAD WINGS FLIGHT DIARY`；补丁仓库内 `backup/` |
| 原版发行版（日文） | 环境变量 `IMHFD_ORIG_DIR` 或与补丁目录同级自动发现 |
| 国外还原补丁（参考，**不可信**） | `…\If_My_Heart_Had_Wings_Flight_Diary_Restoration Patch` |
| 中文汉化补丁（参考） | 上者 `Chinese_Localization_Patch/` |
| 引擎逆向知识 | `D:\My_Code\tmp\GamePatch\GalRevserse\GalRev` |

---

## 待决策 / 待补

1. ~~**L0 工具链**~~ ✅ 已完成（本作格式表已导出，`tool/ws2fmt.py` 可反汇编）。
2. ~~**`.MOS` 成员**~~ ✅ 决策：**不补入**。
3. ~~**姬城线按钮图形**~~ ✅ 已完成：从官中既有按钮逐字拼字得到亮/暗两态并**定版**入库 `resource/route_entry/ags_button_cn_{on,def}.png`，落到 `SYS_C_Story.pna` 记录 19/20（见 [route-mechanics.md](route-mechanics.md) §3.5）。
4. ~~**朱莉线中文**~~ ✅ 决策：来源为官方简中，**不校对**、不动。
5. ~~**原版引擎的 WS2 格式表**~~ ✅ 已导出 `resource/ws2_formats_orig.json`（原版 107/108 剧本 100% 平铺）；跨版本搬运规则（7 opcode 补尾字段）见 [route-mechanics.md](route-mechanics.md) §5.1。
6. ~~**`KAN_3001_4_E` 的映射关系**~~ ✅ 已定案：Steam 把原版 104 格 H 段**扩写成** 164 格全年龄顶替（形态 = 整段删+新写），处置 = 新写保留 + 被删还原插入；补丁是整脚本换回原版（偏差，见 [restoration-scope.md](restoration-scope.md) §5）。
7. **tonal 重复决策**：`keep_steam_insert_orig` 会保留 Steam 的全年龄替代场景 + 插入原版 H 段，是否逐处改为 `replace_with_orig`（免重复）——**待你决策**，默认按规则 keep。

