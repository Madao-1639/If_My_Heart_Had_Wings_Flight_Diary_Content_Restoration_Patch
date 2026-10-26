# 引擎机制

> ⚠️ **本文自姊妹作项目《在这苍穹展翅》内容恢复补丁迁移，属引擎通用知识，可直接复用；其中出现的本作专属标定值（脚本名、资源名、路线前缀、偏移、常量）必须按本作重新标定。**
> 迁移状态见 [README.md](README.md)「文档清单与来源」。引擎层最新结论以 GalRev（`D:\My_Code\tmp\GamePatch\GalRevserse\GalRev\docs`）为准。


本文档记录游戏引擎在运行时表现出的行为规律，区别于 [file-formats.md](file-formats.md) 记录的静态文件格式。可执行文件 `AdvHD.exe`/`AdvHD.dll` 存在于原版发行版目录中（见 [restoration-targets.md](restoration-targets.md)），必要时可用于运行时验证或静态逆向。

> ⚠️ **两个引擎二进制不等价**：**原版** `AdvHD.exe`（2013）未加壳、可完整静态分析，但**不含成就系统**；**Steam 版** `AdvHD.exe`（VAdvHD 1.72c `Release - Steam`）含成就系统，发行版被 DRM 加壳，**已脱壳**（`AdvHD.exe.unpacked.exe`）后可完整静态分析。
> 本文件只给**成就触发点契约**（工程依据）；成就完整机制见 [achievement-mechanics.md](achievement-mechanics.md)。

## 状态图例

同 file-formats.md：✅ 已确认 / ⚠️ 部分确认 / ❓ 未知

## 资源槏位命名 ❓ 待验证

已从脚本内容中观察到的槏位名包括 `st01`、`bg01`（见 file-formats.md 中 LAYER_ORDER 表的例子），但尚未确认：
- 完整的槏位白名单（有多少个 st/bg 槏位，是否有 ev 类事件专属槏位）
- 是否存在对特定槏位的资源名长度限制

**方法论**：按号段改名的**新增**资源（同名冲突走整名覆盖，不改名）若在某槽位不被识别，优先用 A/B 测试（换成一个**等长的新名字**，看是否成功）来定性问题，而不是纯静态逆向猜测。

## LAYER_ORDER 与 `layer_id` ✅ 已逐字节复核

同引擎（AdvHD）的 CROSS†CHANNEL 项目的实测结论，对本项目**同样成立**（本项目已逐字节复核确认）：

- **`LAYER_ORDER.ws2` 是"引擎已知槽位键"的白名单，不是布局表**：`0x3f <count:u8> <key>\x00 … <key>\x00 0x05 0xff…`。本项目实测：**19 键**（`ev`；`bg01-02`；`st01-12`；`movie`；`text01-03`），**两版逐字节相同**。它**不含位置/坐标**。
- **槽位键由引擎内部硬编码**（Lua 绑定注册表）；`LAYER_ORDER` 只登记引擎**已经认识**的键 ⇒ **不能用它新增槽位**（C+C 侧 A/B 实测：加引擎不认识的新键永远注册不上）。
- 脚本里的 `\x04 LAYER_ORDER\x00` 是 **RunFile 子程序调用**（每个立绘/背景块显式跑一遍登记表）；其后的 `\x09 <index:u16> <float>`（权重）与 `\x46 <槽位名>\x00…`（定位）是**块自身的指令流**，与 `LAYER_ORDER` 表无关。
- **`layer_id` 是纯位置量**：`layer_id = layer_count - 1 - index`，取值**依赖对应 PNA 的图层数**；请求 `layer_id ≥ layer_count` 会使**引擎崩溃**（C+C/ASF 侧实测 0x39；本项目待验证）。

**对本项目的推论**：

1. `LAYER_ORDER` 白名单**两版相同 ⇒ 不需要、也不能做任何"重排 / 加键"处理**。
2. **原版脚本段必须与原版立绘/CG 资源成对回填**：原版段里的 `\x34/\x33/\x39` 及其 `layer_id` 只对**原版 PNA 的图层数**成立——若改用 Steam 同名资源（PNA 记录数不同），会因 `layer_id` 越界而崩溃。
3. 早期记录的"`LAYER_ORDER` 系统性重排（如 407→353）"实为**立绘块 `\x09`/`\x46` 指令的增删**（部分源于内容被删、部分为 Steam 侧改动），**与 `LAYER_ORDER` 表无关**，归入演出指令层差异（❓ 逐位点定性）。

## 图层清屏 `0x37` 的三种目标形态 ✅ 已定案（在屏状态模型的前提）

`0x37 <目标>\0`（ClearLayer）的目标串有**三种**形态，清屏范围完全不同：

| 形态 | 取值 | 语义 | 本作语料（Steam / 原版） |
|---|---|---|---|
| 精确通道 | `ev`、`st01..st12`、`bg01..bg02`、`movie` | 只清该通道 | 3,915 / 4,120 |
| 族级 | `bg`、`st` | 一次清该族**全部**通道 | 1（`st`） / 0 |
| 通配 | `*` | 一次清**全部**通道（场景开头的复位用法） | **340 / 146** |

**为什么必须写进文档**：凡「按位置追踪在屏图」的模型（写盘器的演出同步、`tool/perfsync.py`、内容一致性闸）都要把族级与通配**展开**再落状态，否则「`37 *` 之后画面已空」在模型里根本不存在 ⇒ 模型会把已清的图继续算作在屏。实测代价：本作 `37 *` 平均每个脚本 3 处、最密的 `HUS_001_E` 有 11 处，漏展开会让闸门对「刚补回的显示被随后的 `37 *` 抹掉」这类**黑背景**缺陷结构性沉默（见 [lessons-learned.md](lessons-learned.md) §43）。

另一条推论：`37 *` 是**复位**语义（先清后画），它与显示指令的**先后顺序有意义**。还原/改写演出时必须保住宿主原有的「复位 → 显示」次序，不能为了插入补块把显示提前到复位之前。

**更一般的推论（演出是成套的、有序的）**：拖拽 `45`／特效 `47`/`48`/`57`/`66`／渐变 `65`／计时 `11`/`12`／图层权重 `09` 是**同一套动画的组成部分**——`09` 写参数变量、`45` 按参数拖、`47`/`48` 挂特效、`65` 收尾。改写演出时只能**整段按原顺序**换，不能把不同版本的指令拼在一起：参数/拖拽还在、被拖的那张图已经被删，就是「动画作用在空通道上」（实机表现为动画错乱）。见 [lessons-learned.md](lessons-learned.md) §44。

## 已读消息位图（`MessageFlag.dat`）与脚本尾表的耦合 ✅ 已定案（实机指纹）

引擎在**加载剧本脚本时**读成员**末尾 8 字节明文尾表** `[u32 消息数][u32 选项条目数]`，据此给
「已读消息位图」分配 `(消息数 + 选项条目数 + 7) / 8` 字节；写位 `bitmap[idx>>3] |= 1 << (idx&7)`
**不做边界检查**。

存档目录的 `MessageFlag.dat` 是逐脚本记录的串接：

```
记录 = 脚本名 UTF-16LE + NUL + u32 A(=8+位图字节) + u32 B(已标记次数) + u32 Y + 位图[A-8 字节]
```

- 记录**按首次写入时的尾表定长**，引擎不会随脚本变大而重算 ⇒ 装了补丁后旧记录可能偏小（引擎按新尾表分配、按旧记录存位）。
  ⚠️ **存档与已读表属引擎存档系统，不在本项目工作范围**：本项目只保证**脚本尾表正确**（见下），
  不去读写/转换 `MessageFlag.dat`；下文只作为诊断依据。
- 尾表偏小（小于真实 `0x14` 条数）⇒ 高位下标写到相邻堆块 ⇒ 延迟到某次 `free` 才崩
  （事件 `0xc0000374` / `0x0000d06d@lua5.3.dll`），在此之前常表现为**随机的 Lua nil 错误或闪退**。
- 上游通识：GalRev `docs/engines/advhd/file-formats.md`「末尾 8 字节」、`save-system.md`「MessageFlag.dat」。
- 读/写纪律与闸：见 [file-formats.md](file-formats.md)「尾部 8 字节」、`tool/ws2.py` 尾表段、
  `script/checks/ws2_tail_check.py`、[lessons-learned.md](lessons-learned.md) §47。

## 资源缺失时的运行时行为 ❓ 待验证

尚未故意构造缺失资源的测试用例来观察引擎实际反应（卡死/报错/静默容忍）。这是排查"游戏卡死无响应"或"画面显示异常但无报错"类问题时需要提前摸清的行为基线，建议在开始改写脚本前先做一次故意的资源缺失测试。

## `.MOS` 马赛克变体的选用机制 ⚠️ 身份已确认，触发条件待调查

已在 [file-formats.md](file-formats.md) 中确认 `.MOS` 是与部分立绘同名的马赛克遮罩变体文件（本身也是合法 PNG，但分辨率/文件大小明显更小）。已确认脚本内容中不包含对 `.MOS` 扩展名的直接引用，说明选用逻辑在引擎内部而非脚本层。需要通过运行时观察（例如切换游戏内的"隐藏敏感画面"设置项，若存在）或对 `AdvHD.exe` 做针对性逆向来确认触发条件。

## 成就触发点契约 ✅（工程依据）

### 定位与边界

| 项 | 归属 | 本补丁能否干预 |
|---|---|---|
| 成就定义、API 名、显示名、图标、解锁状态 | **游戏开发者 + Steam 共同管理** | ❌ 不能，也不应 |
| **成就触发点**（脚本里的成就指令） | 脚本层 | ✅ **能，且这是唯一关注对象** |

⇒ **本补丁对成就的目标只有一个：保留 Steam 版已有的成就触发机制。** 不需要理解成就机制本身，不需要新增触发指令，也不需要"补齐"任何东西。

> 完整机制（引擎 handler、成就表如何由 Steam 构建、`idx` → 成就名的全量映射）**另见 [achievement-mechanics.md](achievement-mechanics.md)**——那只是背景资料，仅在需要核对"某条指令到底触发了什么"时才查。

### 必须原样保留的指令形态（函数签名）

改造脚本时，以下三类指令必须**逐字节原样保留**，其操作数（即成就 id）必须与 Steam 版**逐一对应**，不得改写、不得重排、不得重新计算：

| # | 指令形态 | 出现规模 | 说明 |
|---|---|---|---|
| 1 | `0x33 <槽位> <资源.PNG> <u8> <u8>`<br>`0x0b <u16 A> 01`<br>`0x0b <u16 B> 01`<br>`0x04 "CG_ACHIEVEMENT" 00` | **920 处 CG 显示 / 51 脚本**（`CG_ACHIEVEMENT` 名 922 次） | CG 显示后无条件注入的成就调用。**`A`（1089…1189）= 场景/图库分组、`B`（1190…2674）= CG 编号**，两者都是引擎侧约定的键，不可重算 |
| 2 | `0xF0 <u8 idx>` | **29 处**（`CG_Achievement` 6 + 剧情/菜单 23） | 直接成就触发指令。`idx` = Steam 成就枚举序的 0 基序号 |
| 3 | `CG_Achievement.ws2` 文件本身 | 1 个（Steam 版已含） | 不改动、不需还原（Steam 版未被删改） |

### 保留纪律（硬约束）

1. **保留指令本身，也保留其成就 id 的对应关系** —— 不是"只要还在就行"，改写成等价但 id 不同的形式是**不允许**的。
2. **不新增任何成就触发指令** —— 还原插入的原版内容里若出现 Steam 版没有的 CG 显示点，**不补钩子**。被 Steam 删除的 5 个脚本（`ASA_002/004`、`YOR_003/005/007`）内的 **332 处 CG 显示位点一律不补**。
3. **不删除、不合并、不重排** 任何既有成就指令；原地插入还原内容时，插入点不得切断 `0x33 CG 显示 → 0x0b A → 0x0b B → 0x04 CG_ACHIEVEMENT` 这一**四连**。显示头虽不参与成就判定（id 来自 `0x0b` 变量对），但**不摘**——画面还原在归档字节层解决，删指令不是还原画面的手段（见 [restoration-route.md](restoration-route.md) §7 V-9）。
4. **不需要理解机制** —— 只要保留指令的字节形态与 id 与 Steam 版一致，成就行为即完整复现（引擎侧只做"按 id 查运行时表 → `SetAchievement` + `StoreStats`"）。
5. 越界 `idx`（如 `CG_PAGE09` 的 `F0 28`，成就总数只有 20）是**空操作的遗留触发点**，同样**原样保留**，不要"修正"成合法值。

### 校验方法

- `tool/ws2dis.py --arc <Rio.arc>` 复扫全库，比对改造前后 `0xF0` 站点数与 `idx` 取值集合不变（基线：**29 处**）。
- 比对 `CG_ACHIEVEMENT` 调用次数与 `0x0b` 变量对取值集合不变（基线：**920 处 / 51 脚本**）。
- 机器可读基线：`resource/achievement_map.json`。

### 引擎身份与 DRM（背景，已解除）✅

- **引擎身份 = VAdvHD 1.72c，`Release - Steam` 构建**（PDB 路径 `D:\Backup\VAdvHD-OldVersion\VAdvHD-1.72c\Release - Steam\AdvHD_S.pdb`）；用 `ISteamUserStats` **v011**（`STEAMUSERSTATS_INTERFACE_VERSION011`）。
- 引擎内实现的是 **Valve Steamworks SDK 官方样例类 `CStatsAndAchievements`**（RTTI：`CCallback<CStatsAndAchievements, UserStatsReceived_t>` / `…UserAchievementStored_t>`）。Lua 事件名 `LUA_PROCESS_ACHIEVEMENT`（`Script.arc` 全部 Lua **无**成就相关代码）。
- 原版 `AdvHD.exe`（2013-01-30，1,208,320 B，无 `.bind`、`.text` 熵 6.5）**未被保护、可完整静态分析**，但其 `Steam`／`ACHIEVEMENT`／`steam_api` 字符串计数**均为 0** ⇒ 成就系统是本 Steam 构建独有的新增，原版引擎不含，**不能作为替代样本**。
- Steam 版发行二进制 `AdvHD.exe`（1,769,840 B）被 **Steam DRM（SteamStub 系）** 加壳：`.text` 熵 ≈7.999、`.bind` 熵 ≈7.96、入口点落于 `.bind`（RVA 0x190310），IDA 自动分析仅覆盖 430 个函数、对 `steam_api` 导入与成就字符串引用数全为 0。
- **现已脱壳**（`AdvHD.exe.unpacked.exe`，1,626,112 B，imagebase `0x400000`，IDA 自动分析 3,637 函数、Hex-Rays 可用）⇒ 成就的引擎侧实现已**完整静态闭合**，见 [achievement-mechanics.md](achievement-mechanics.md)。脱壳 exe 的 IDB 位于游戏目录（`AdvHD.exe.unpacked.exe.i64`）。

## 后日谈（After Story）入口机制 ✅ 已确认

完整机制见 [afterstory-mechanics.md](afterstory-mechanics.md)。要点：

- 原版 `SL_AGE_001`／`SL_AMA_001`／`SL_HUT_001`／`SL_KOT_001` 以**磁盘裸目录 `RIO/` 覆盖归档**的形式发行（`tool/arcbuild.py` 确认四者不在 `Rio.arc` 内）。
- 入口不是引擎内建概念，而是**标题菜单的 `sweet` 按钮**（id = 105，图形 `Sys_title.pna` 层 54/55/56）；点击后由 `mainmenu.ws2` 的 `ExecuteFunction "openAfter"` 打开 Lua 选择界面，再由 `var99 = 1..4` 派发到四个 `SL_*`。
- 另有独立路径：`REPLAY_EXE.ws2` 的 `var101 == 3` 段按 `var110 = 1..4` 直达同名 `SL_*`，不经过标题菜单与选择界面。
- 无需还原任何"菜单系统"——入口代码、按钮图形、选择界面、派发表在 Steam 版**全部存在**，缺口仅三处（2 字节 + 1 行 Lua + 4 个脚本）。

## 磁盘裸 `RIO/` 目录：构成、来源与是否被引擎读取 ✅ 已确认

原版发行目录下存在一个磁盘裸目录 `RIO/`（11 个 `.ws2`）。该目录**不是构建残留**，而是**两个官方补丁的散装覆盖层**——依据是同级的 `请读我.txt`（UTF-16LE）明载：「已打官方修正补丁 v1.02」「已打官方予約特典 アペンドディスク『スウィートラブパッチ』」。

### 目录构成与来源

| 来源 | 文件 | 与 `Rio.arc` 的关系 | 差异 |
|---|---|---|---|
| 予約特典「スウィートラブパッチ」 | `start.ws2` | 覆盖（arc 内为旧版） | `SetFlag 1000` = **1**（arc = 0）＋ 头尾各一条 `0xfb` 指令（arc 无） |
| 同上 | `SL_KOT/AGE/AMA/HUT_001.ws2` | **新增**（两版 arc 均无） | 后日谈本体（L4 素材） |
| 官方修正补丁 v1.02 | `CO1_001/002/003/015`、`HUT_004/005` | 覆盖（arc 内为 v1.02 前旧版） | 合计 **6 字节 + 删 1 行台词**（见下表） |

**v1.02 覆盖版逐项差异**（`loose` = 裸文件，`arc` = 原版 `Rio.arc`；解码后逐字节比对）：

| 文件 | 大小 loose / arc | 差异 |
|---|---|---|
| `CO1_001` | 87355 / 87355 | 1 B：`0x48 Effect2`（`st03`/`effect05`）5 字节参数第 3 字节 `00→02` |
| `CO1_002` | 118196 / 118196 | 1 B：`0x33 bg01 BG15B_02S.PNG` 之前参数块的 1 字节 `00→02` |
| `CO1_003` | 120036 / 120036 | 2 B：两处 `0x48 Effect2`（`st02`/`effect02`、`st01`/`effect01`）参数 `00→02` |
| `CO1_015` | 126437 / 126437 | 1 B：`0x48 Effect2`（`st01`/`effect01`）参数 `00→02` |
| `HUT_004` | 89960 / 90002 | **−42 B**：删除一句台词「なんだってなによ」（碧）及说话人标记，其后 `0x14` 行号顺移 |
| `HUT_005` | 104639 / 104639 | 2 B：同音字勘误 `検討` → `見当` |

- 时间戳佐证：`Rio.arc` = 2012-05-10；`CO1_*` = 2012-05-22；`HUT_*` = 2012-05-29（v1.02 晚于 `Rio.arc`）⇒ **裸文件是较新的修正版**。
- ⇒ **对位基线**：这 6 个文件在 Steam 侧的对位对象应是**裸 `RIO/`（v1.02）版**，而非 `Rio.arc` 内的 v1.02 前旧版。
- Steam 版 `start.ws2` **含** `0xfb` 头尾指令但 `SetFlag 1000` = 0 ⇒ Steam 构建基于**已打 v1.02** 的原版，仅移除 Sweet Love 开关与 H 内容。
- ⚠️ **衍生影响（`HUT_004` 行号错位）**：v1.02 删行后 `0x14` 行号顺移 ⇒ 对话行数 loose/Steam = **552**、arc = **553**，错位起点 **idx 121**（arc idx 121 =「なんだってなによ」；loose/Steam idx 121 =「振り返ると、そこには佳奈子さんがいた。」）。`resource/fan_cn/HUT_004.json`（**553** 条）按 **arc** 索引 ⇒ 若对位基线改用 v1.02（裸文件），该语料需自 idx 121 起整体 **−1** 平移。其余 5 个文件行数一致，不受影响。

### v1.02 改动的性质（效果判读）

| 改动 | 层面 | 在游戏里的效果 |
|---|---|---|
| 4 个 `CO1_*` 的 `0x48 Effect2` 参数 `00→02` | **演出（视觉特效）参数** | 该处「对某图层施加具名特效」的**模式/变体**由 0 变 2；纯视觉，不动台词／分支／旗标／存档 |
| `HUT_004` 删 1 行（−42 B） | **台词** | 该句「なんだってなによ」（碧）不再显示；其后 `0x14` 行号整体前移 1 |
| `HUT_005` 2 字节 `検討→見当` | **台词用字** | 同音字勘误（kentou）；显示文本被订正 |
| `start.ws2` `SetFlag 1000` 0→1 ＋ 头尾各 1 条 `0xfb` | **开关 / 脚本版本标记** | flag 1000 = Sweet Love 入口总开关（置开）；两条 `0xfb` 在 **Steam 版同样存在** ⇒ 来自官方修正补丁而非特典 |

**`0x48 Effect2` 参数布局**（原版 `AdvHD.exe` 内格式串实证：`06 08 06 08 01 00 00 0a 08` = `str,str,i16,u8,u8,str`）：

```
0x48 <通道>\0 <特效名>\0 <i16> <u8 A> <u8 B> <第三串>\0
```

- 第三串在本作全语料**恒为空**；全语料取值：`i16 ∈ {0(2646), −1(2)}`、**`A ∈ {0:1888, 2:750, 1:5, 3:4, 4:1}`**、`B ∈ {0:2642, 2:6}`。
- ⇒ v1.02 改的正是 **`A`（0→2）**：一个特效**模式枚举**（`A` 与特效名无相关性，逐次调用独立）——不是文本、不是旗标、不是流程。
- `effect01..05` 为具名特效（`effect01` 占 2126/2648 次）；`Effect.arc` 内 25 个 `.fx` 着色器（bloom／模糊／边缘检测／鱼眼／扫描线／色调映射…）是后期处理特效资源。
- 同族指令：`0x47 Effect1` / `0x48 Effect2` / `0x58 Effect3`。

**Steam 侧对照**：4 处特效参数改动中 **3 处 Steam 与 v1.02 同值**（`CO1_003` 第二处 Steam = 0，属 Steam 侧自身改动）；`start.ws2` 的 `0xfb` 头尾指令 Steam 亦有 ⇒ 佐证 **Steam 构建基于「已打 v1.02」的原版**。

### `+` 系列覆盖归档（`Voice+` / `Chip+`）✅ 已实测

> 归属 **L5**（v1.02 修正补丁），**与后日谈（L4）无关** —— 二者只是恰好由同一对路由函数派发。

原版有两个「`+` 后缀」归档，成员与主线归档**同名但内容不同**（= 覆盖新版）：

| 归档 | 成员 | 路由分支（**无条件**，不受 `flag 126` 影响） | 覆盖对象 | 时间戳 |
|---|---|---|---|---|
| `Voice+.arc` | `AGE_1309.ogg`、`KOT_0387.ogg`、`KOT_3837.ogg` | `sub(R1,1,8) ∈ {age_1309, kot_0387, kot_3837}` → `Voice+.arc` | `VOICE.arc` 同名成员 | 2012-05-29 |
| `Chip+.arc` | `Sys_Arrow.pna`、`Sys_ConfigP7.pna`、`Sys_Dialog.pna`、`Sys_Log.pna` | `sub(R1,1,9) ∈ {sys_arrow, sys_configp7, sys_dialog, sys_log}` → `Chip+.arc` | `SysGraphic.arc` 同名成员 | 2012-05-22 |

**两条分支在函数里排在 `flag 126` 分支之前**（先行命中），与后日谈路由互不影响。

**时间戳与 v1.02 修正脚本吻合**：`Chip+` 05-22 ↔ `CO1_001/002/003/015.ws2` 05-22；`Voice+` 05-29 ↔ `HUT_004/005.ws2` 05-29 ⇒ 二者是 **v1.02 修正补丁的载体**。

**实测（原版主线 / 原版 `+` / Steam 主线，三方 md5）**：

| 成员 | 原版主线 | 原版 `+` | Steam 主线 | 结论 |
|---|---|---|---|---|
| `AGE_1309.ogg` | `96269c81…` | `a4b950fb…` | `a4b950fb…` | **Steam == 原版 `+`** ✓ |
| `KOT_0387.ogg` | `f6d2a0a0…` | `99895c6f…` | `99895c6f…` | **Steam == 原版 `+`** ✓ |
| `KOT_3837.ogg` | `bbf0aa86…` | `b58abc1d…` | `b58abc1d…` | **Steam == 原版 `+`** ✓ |
| `Sys_Arrow.pna` | `0f769481…` | `dc8cb860…` | `97530ee2…` | 三方各不同（Steam 重做过 UI） |
| `Sys_Dialog.pna` | `98a1a245…` | `3cc26fa1…` | `9b50e2e4…` | 同上 |
| `Sys_Log.pna` | 存在 | 存在 | **Steam `SysGraphic.arc` 中缺失** | — |

**结论**：
- **`Voice+` 的修正 Steam 已合入 `VOICE.arc`**（3/3 md5 与 `+` 版相同）⇒ Steam 不需要 `Voice+` 机制。
- **`Chip+` 的 UI 资源对 Steam 无意义**（Steam 用自己的 UI 一套，三方都不同）。
- ⇒ **两条 `+` 分支都不需要还原**，属 L5 且工作量 ≈ 0。

### 引擎是否读取该目录

**结论 ✅ 引擎会读取裸 `RIO/` 并覆盖归档**（依据三条）：

1. **官方预约特典「スウィートラブパッチ」只以裸 `RIO/` 形式发行**（`start.ws2` + 4 个 `SL_*.ws2`）；`Rio.arc` 内既无 `SL_*` 也未置 flag 1000。若引擎不读裸目录，该官方特典将完全无效 ⇒ **必然读取**。
2. 裸 `RIO/start.ws2` 与原版 `Rio.arc:start.ws2` 的实质差异正是 `SetFlag 1000`（裸 **1** / 归档 **0**），而 flag 1000 是标题菜单 `PatchFlag = GetFlag(1000)` 的来源（Sweet Love 总开关）。
3. 目录前缀资源根先例：Steam 版官方中文以 `zh-CN/Rio.arc` 覆盖形式提供（`backup/zh-CN/`）。

**已推翻的旧结论**：早期对 `AdvHD.exe`/`AdvHD.dll` 做 ASCII + UTF-16LE 宽字符串扫描，未发现"扫描 `RIO/` 目录""加载裸文件覆盖归档"一类字符串，曾据此倾向"引擎不读裸目录、裸文件只是构建残留"。该扫描只覆盖**字符串常量**，不覆盖运行时拼接的路径，故**不成立**。

**残留风险（建议实机 A/B 补测）**：覆盖**粒度**——整档覆盖 vs 单体 `.ws2` 覆盖。该粒度决定 L4 的**交付形态**（走 `Rio.arc` 重建，还是走裸 `RIO/` 覆盖）。

## 变量存储与 `0x01` 的比较路径 ✅ 已定案（2026-10-27 实机校正）

| 指令 | 存储 | 语义 |
|---|---|---|
| `0b <id:u16> <val:u8>` | **布尔位图** | `val` 只有 0/1 有意义；写非 0/1 不报错，但**比较会失去区分度** |
| `09 <mode:u8> <id:u16> <val:f32>` | **浮点数组** | `mode 0` 赋值 / `1` 累加；与布尔位图是**两套空间** |
| `01 <mode:u8> <id:u16> <val:f32> <a> <b>` | 读 | `mode & 0x80`（bit7）→ 读浮点数组，否则读布尔位图；`mode & 0x3F` = `>= <= == != > <` |

- **分支极性**：条件**成立 ⇒ 顺序执行**，不成立 ⇒ 跳到 `a`/`b`（`a != 0` 时优先）。本作用它做回想出口三连（`01 mode=2 flag127==1 → 跳过 EVRET`）与变体路由（`01 mode=2 var==0 → Steam 体`）。
- ⚠️ **布尔折叠**：把「两版演绎」编码成 `0b var 1|2` 再判 `var != 2`，两个选项都会走同一支（写 2 与写 1 等效为 true）。**规范：布尔旗标只用 0/1，条件用 `== 0`**（缺省未写入＝0＝原版）。见 [lessons-learned.md](lessons-learned.md) §54 与 GalRev `docs/engines/advhd/branching-and-variants.md`。
- 本作语料统计（产物 119 个 `.ws2`）：`01` 带 bit7 的用法 **0** 处、`09` 仅 9 个 id ⇒ **浮点比较路径无实机先例**，不得当作"等价替代"直接替换布尔方案。

## 选项（`0x0f`）在引擎侧的链路 ✅ 已确认（证据类型逐条标注；`closeMessageWindow` 的**触发命令**尚未定位，但不影响根因与修法结论）

> 反汇编对象：`AdvHD.exe.unpacked.exe`（游戏实际跑的是加壳的 `AdvHD.exe`，代码不可直接读）。
> 反汇编工具：capstone（一次性脚本，不入库）。

### 命令执行器与分派 `[反汇编]`

* 执行器 `0x475940`（虚调用，经 vtable 进来），入参在 `[ebp+8]`：

```
mov  eax, [ebp+8] ; add eax,-0x0D ; cmp eax,0x6E ; ja 0x4766F3
movzx eax, byte[eax+0x4767E8]     ; 字节映射表（按 cmd-0x0D 索引）
jmp  [eax*4 + 0x47679C]           ; 19 项跳转表
```

* `0x4766F3` = **「等待/不推进」**：各 case 检查到"在飞行中"的状态全局非零就跳它，脚本指针不前进，下一帧重试。

### 选项命令 case `0x475E21`（cmd 0x20）`[反汇编]`

```
cmp [0x5B95F0],0 ; jne 0x4766F3      ; 演出/子命令槽 0 在飞行中 ⇒ 等
cmp [0x5B95F4],0 ; jne 0x4766F3      ; 槽 1 同理
call 0x47FA40                         ; 建 UI：→ Lua 全局 initSelect(count)
test eax,eax ; jne 0x4766F3
call 0x47ED30( [0x5B95FC]==0 )        ; 选项态切换
```

* `0x47FC73` 起用除法魔数 `0x2AAAAAAB` 算 `(end - start) / 12` 作为 `initSelect(count)` 的实参 ⇒
  **选项条目在载入期已被解析成 12 字节/条的内部数组**（`[edi+0x214]` 起）。`count` 不对 ⇒ 选项数不对。
* `0x47ED30` 内 `push 0x58D234 ("hideMessageWindow")` + `call 0x4A68A0`（按名调 Lua 全局）
⇒ 引擎在进入选项态时调它（隐藏消息窗的图层），但**它不改变"提示句留框"表现**：选项帧内不含 `0x16` 时，提示句始终与选项同屏（见下文「`0x16` 的副作用」）。

### 引擎每帧调用的 Lua 全局（`[反汇编]` 串表 `0x58D17C..0x58D480`）

```
getDefaultFont getNameWindowKey getMessageWindowKey initFontInformation
finalizeLegacyGame initSystemScreen getPKeyInfo getSystemSet
openMessageWindow closeMessageWindow hideMessageWindow getLongPressTime
nameWindowVisible stopClickWaitAnimation startClickWaitAnimation resetMessageWindow
onMouseMove onLButtonDown onRButtonUp onLButtonUp onMouseWheel onKeyDown
onMButtonDown onMButtonUp onX1ButtonDown onX1ButtonUp onX2ButtonDown onX2ButtonUp
isMessageWindowEffect isSelectEffect isGesture onGesture onIMEnd faceRead
willChangeVariable didChangeVariable setButtonState getMessageWindowEffect
refreshCursorPos openConfirm isSystemEffect openMessageLog getMessageLogKey
initSelect disableSelectItem
```

* 其中 `isSelectEffect` = `LegacyGame.lua/96`：`if g_MenuMsgWin==nil then return false end; return g_MenuMsgWin:SelectEffect()`；
  引擎在 `0x47F294` 处按名调用它（同型调用还有 `isMessageWindowEffect`）⇒ **选项态机由引擎逐帧驱动**。
* `onLButtonUp` / `onKeyDown` / `onMouseMove` 也在表内 ⇒ 鼠标/键盘事件是**引擎直接调 Lua 全局**，
  再由 `LegacyGame.lua/62`（`onLButtonUp`）按 `MenuInf.SetName` 分派到 `g_MenuMsgWin:MenuLButtonUp`。

### 输入门 `[Lua 反汇编]`

`GetMenuMouseEnable`（`LegacyGame.lua/15/5`）返回真的条件全部满足才行：

```
MenuInf.enabled == true 且 MenuInf.effect == false 且 MenuInf.select_effect == false
且 MenuInf.tips_effect == false 且 MenuInf.tips_wineffect == false
且 buttonEffect.effect_auto == false 且 buttonEffect.effect_skip == false
且 MenuButton ~= nil
```

`select_effect` 只由 `SelectEffect`（`/15/27`）清：

```lua
if not layers:isEffect('system','SelDisp') then self:SelectEffectEndJob(); MenuInf.select_effect = false end
return MenuInf.select_effect
```

而 `startSelectMenu`（`/15/35`）结尾无条件置 `select_enabled = true; select_effect = true`。

⇒ `select_effect` 由 `SelectEffect`（`/15/27`）在 `isEffect('system','SelDisp')` 结束时清回 false；它不是本作选项失效的原因（强制归零不改变现象），真正的门见下文「`0x16` 的副作用」。

### `0x16` / `0x64` / `0x65` 的用途判定 `[语料]`

Steam 版 119 个 ws2（未改动基线）逐条统计：

| opcode | 出现次数 | **后一条** top | **前一条** top |
|---|---|---|---|
| `0x16`（`16 00 00`） | 3492 | `0x64` **2714（78%）** | `0x15` 1761 / `0x65` 681 |
| `0x64`（`64 00`） | 9238 | `0x34` 4493 / `0x33` 3527 / `0x37` 1172（**全是显示类**） | `0x15` 5546 / `0x16` 2714 / `0x65` 458 |
| `0x65`（14 字节时序块） | 9233 | `0x2e` 5440 / `0x15` 947 / `0x16` 681 | `0x3e` 6210 / `0x46` 1993 / `0x66` 698 |

handler 侧补充（`[反汇编]`）：执行器分派是 `cmd = opcode + 0x0D`（在 `0x63..0x6E` 段成立），
于是 `0x64` → cmd `0x71` → case `0x476131`（`push 4` → `call 0x4805C0`，且先检查
`0x5B95F0/0x5B95F4/0x5B9620/0x5B9604/0x5B9608` 一组"在飞行中"状态），`0x65` → cmd `0x72` → case `0x4761BE`（`push 5`，前置还要求 `0x5B9608 != 0`）。
`0x16` → cmd `0x23` 落进通用分支 `0x4766F3` → `0x47F340`，该函数会构造参数表并
**向 Lua 合成一次 `onKeyDown` 调用**（串 `0x58D310`，调用点 `0x47F472`）——与"文本收尾/推进"语义一致。

判读（`[语料]` + 上述 handler 证据）：

* `0x64` = **显示块起点**：其后 100% 是 `0x33` 背景 / `0x34` 立绘 / `0x37` 清屏；
* `0x16` = **文本收尾/换段**：78% 紧接 `0x64`，即"把这一句落定 → 开始下一段演出"；
* `0x65` = **时序块**：67% 紧跟在 `0x3e`（特效结束）之后。

⇒ 选项帧 `14 <提示句 %K>` → `16 00 00` → `64 00` → `33 …` 的顺序，**原版与产物完全一致**：
玩家看到的"对话框消失"由**选项帧内的 `0x16`** 造成（`[实机]` 剔除后提示句即留框同屏）⇒ 这是**需要修正的还原偏差**，不是原生可接受行为；
不是我们引入的，也不是"人名被提前"。

### 输入事件派发器 `0x47F4F0` `[反汇编]`

引擎把**鼠标/按键事件**统一喂给一个派发器，它按事件序号查一张 11 项的"Lua 全局名"表并调用：

| 序号 | Lua 全局 |
|---|---|
| 0 | `onMouseMove` |
| 1 | `onLButtonDown` |
| 2 | `onRButtonUp` |
| **3** | **`onLButtonUp`** |
| 4 | `onMButtonDown` |
| 5 | `onMButtonUp` |
| 6 | `onGesture` |
| 7 | `onX1ButtonDown` |
| 8 | `onX1ButtonUp` |
| 9 | `onX2ButtonDown` |
| 10 | `onX2ButtonUp` |

要点：

* 表地址在 `0x47F533..0x47F579`（11 个 `.rdata` 指针），边界判据 `cmp eax, 0xa`（`0x47F586`）；
* 入口守卫 `cmp dword ptr [ebx+0x6c], 0`（`0x47F520`，为 0 直接返回）；
* 调 Lua 走通用入口 `0x4A68A0`（按名取全局后 `call`），随后 `test al,al` 决定是否继续（`0x47F67F`）；
* 该派发器有 **14 个调用点**（`0x47AB88` / `0x47ABFA` / `0x47BABE` / `0x47BB41` / `0x47BD49` / `0x47C320+ …`），
  每个负责一种事件；参数形如 `(0, …, 事件序号-1, …, 0)`。

⇒ 之后如果要判"选项期鼠标事件到底有没有派到 Lua"，观测点就是这张表 + `0x47F67F` 的返回值：
`onLButtonUp` 返回假会让引擎认为事件未被消费（`je 0x47F696` 分支）。

## `0x16` 的副作用：Steam 侧会关闭输入门（选项不可交互的根因）✅ 已定案

### 机制

选项期实测状态为 `MenuInf.enabled == false` 且 `MenuInf.effect == true`。该值组合在整份 Lua 里只有一个写者：`closeMessageWindow`（`LegacyGame.lua/15/50`）——它把 `enabled` 置 false、`effect` 置 true，并在 `Txt01` 上启动 `WndDisp` 关窗特效；`effect` 由 `MenuEffect`（`/15/0`）在该特效结束时清回 false，而选项场景里这一收尾不会发生，`enabled` 更只有 `openMessageWindow`（`/15/49`）才会重新置 true。

输入门 `GetMenuMouseEnable`（`/15/5`）要求 `enabled == true` 且 `effect == false`，于是恒不通过：`MenuMouseMove` / `MenuLButtonDown` / `MenuLButtonUp` / `MenuKeyDown` 全部直接返回 ⇒ 无悬停、点不动、`selCursor` 不变（第 2 项恒高亮）、消息窗被关掉。

### 代际差异

* 原版（更早一代 Lua，`g_selectInfo`）**没有** `enabled/effect` 这套状态机 ⇒ 同一条 `0x16` 不改输入状态，无害。
* Steam 版（本作 5.3、本篇 5.1 同构）把窗口状态做成显式菜单状态机：**关窗即关输入门**。
* 本篇的选项帧里没有 `0x16`，本作原版有 ⇒ **按原版还原等于把这条指令搬进 Steam 引擎**，本 bug 由此产生。

选项帧（提示句 → 选项头）的 op 序列（`[语料]`）：

| 语料 | 序列 | 含 `0x16` |
|---|---|---|
| 本作 Steam | `14 16 64 33 04 09×4 46 46 34 39 04 46 46 3e 65 0e` | 有 |
| 本篇 `HUT_005`（选项可交互） | `14 64 33 04 09×4 46 37 37 3e 65 0e …` | 无 |
| 本篇 `CO1_020`（同上） | `14 04 0e …` | 无 |
| 本作原版 `BEF_004` | `… 16 00 64 00 …` | 有（老引擎无害） |

### 规则

* **选项帧（提示句 → 选项头）内不得出现 `0x16`**；帧外的 `0x16` 保持原样。
* 写盘期由 `tool/ws2.drop_choice_frame_op16()` 剔除（幂等、全量绝对偏移重定基），闸 9g 守。
* 剔除后提示句留在框内与选项同屏（`%K` 留框语义成立）。
## 待办

- [ ] 枚举完整的资源槏位白名单
- [ ] 实机测试资源缺失时的引擎行为
- [ ] 查明 `.MOS` 变体触发条件（游戏内设置项？还是硬编码判断？）
- [ ] 如需新增自定义资源槏位，先用 A/B 测试验证是否存在命名限制
- [ ] 实测本项目 `layer_id ≥ layer_count` 的崩溃行为与错误码（C+C 侧为 0x39）
- [ ] 逐位点定性两版立绘块 `\x09`/`\x46` 指令的增删差异（与 `LAYER_ORDER` 表无关）
- [ ] 查明回想模式的引擎触发/识别机制（低优先级，见上）
- [ ] 实机 A/B 验证裸 `RIO/` 的**覆盖粒度**（整档 vs 单体 `.ws2`）——决定 L4 交付形态
- [ ] **L5（最低优先级，低于 L4）**：逐点核对 Steam 侧 v1.02 残余差异（4 处 `0x48` 特效参数 `00→02` + `HUT_005` 勘误 + `HUT_004` 删 1 行）并决定是否补齐
