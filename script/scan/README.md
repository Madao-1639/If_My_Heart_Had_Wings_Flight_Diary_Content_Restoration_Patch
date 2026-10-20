# script/scan/ —— 差分与勘察脚本

本目录是**勘察/差分阶段的临时性但可复用**脚本：把 Steam 版基线（`backup/`）、原版发行版目录、
两个第三方补丁三者的**归档 / 成员 / 脚本 / 文本**摆在一起比对，产出结论供
[doc/restoration-targets.md](../../doc/restoration-targets.md) 与
[doc/third-party-patch-analysis.md](../../doc/third-party-patch-analysis.md) 使用。

> 这些脚本**尚未接入正式流水线**（`script/build/`、`script/checks/`），也不产出 `resource/` 入库表；
> 正式流水线落地后，本目录的判据应下沉到 `resource/` 表 + `script/build/` 脚本。

## 依赖

- Python 3.13（`C:\Users\MADAO\.workbuddy-ai\binaries\python\versions\3.13.12\python.exe`）
- AdvHD 逆向库：`sys.path` 加入 `D:\My_Code\tmp\GamePatch\GalRevserse\GalRev` 后 `from galrev.advhd import arc, ws2, pna`

## 脚本

| 脚本 | 职责 | 用法 |
|---|---|---|
| `dump_arc.py` | 列出 Arc 成员（名 / 大小 / sha1），可 `--json` 导出 | `python dump_arc.py <arc> [--json out.json]` |
| `cmp_file.py` | **整档级**比对：ORIG / STEAM / PATCH / CN 四方的 (size, sha256)，判定谁与谁逐字节相同 | `python cmp_file.py` |
| `cmp3.py` | **成员级三方**比对（ORIG/STEAM/PATCH）：onlyA / onlyB / 同名内容差 | `python cmp3.py Chip7.arc Chip8.arc …` |
| `cmp_members.py` | 成员级两方比对（按 `chip` / `voice` / `graphic` / `rio` 分组预设） | `python cmp_members.py chip` |
| `cmp_jumps.py` | 比对 Steam 与 PATCH 的同名脚本 **`0x07` 跳转目标**差异（找"跳转改指"） | `python cmp_jumps.py AFT_003_E.ws2 …` |
| `analyze_rio.py` | `Rio.arc` 成员名按前缀分组，三版本对照（找路线脚本增删/改名） | `python analyze_rio.py` |
| `langmix.py` | 提取 ws2 可读串并分类 JP / ASCII（判"英文脚本里缝日文"） | `python langmix.py Rio.arc AFT_003_E.ws2` |
| `ws2text.py` | 从 ws2 提取可读文本串（CP932 + 筛选假名/汉字） | `python ws2text.py <orig\|steam\|patch> Rio.arc <脚本名>` |
| `ws2flow.py` | 列出 ws2 的 `0x04` CALL / `0x07` JUMP 目标（正则，不依赖完整解码） | `python ws2flow.py <orig\|steam\|patch> Rio.arc <脚本名>` |
| `ws2listing.py` | **指令级**反汇编清单（用 `tool/ws2fmt.py` 的 FD 格式表，带操作数解码） | `python ws2listing.py steam Rio.arc mainmenu.ws2` |
| `verify_patch.py` | 核对国外补丁每一处改动：ORIG/STEAM/PATCH 的 `0x14`/跳转对照 | `python verify_patch.py` |
| `mcp.py` | 极简 IDA-MCP 客户端（`http://127.0.0.1:13337/mcp`） | `python mcp.py server_health '{}'` |
| `dump_formats.py` | 从 **Steam** `AdvHD.exe` 导出 WS2 操作数格式表 → `resource/ws2_formats.json` | `python dump_formats.py out.json` |
| `orig_table_probe.py` | 纯 Python 解析 **原版** `AdvHD.exe`（无 IDA），滚动打分定位格式表基址 | `python orig_table_probe.py` |
| `export_orig_formats.py` | 从 **原版** `AdvHD.exe` 导出格式表 → `resource/ws2_formats_orig.json` | `python export_orig_formats.py` |
| `res_seq.py` | **不依赖格式表**的演出资源序列提取（三版本通用） | `python res_seq.py --dump AFT_003` |
| `align_voice.py` | **语音锚点对齐**：用 `0x28 charXXX <VOICE.OGG>` 绑定 `0x14`，检查 ORIG↔PATCH 逐位语音名一致 + 锚点间行数 | `python align_voice.py` |
| `align_strict.py` | 精确文本锚对齐（JP 行逐字相同作锚），报插入/删除 | `python align_strict.py` |
| `align_sem.py` | 生成语义抽样对（A 类=锚点保证可靠；B 类=拆/合行缺口） | `python align_sem.py` |

## 两版格式表（均已产出）✅

| | Steam `AdvHD.exe` | 原版 `AdvHD.exe` |
|---|---|---|
| 表位置 | `.rdata` `0x57ada8`（相对指针） | `.data` RVA `0x12DAD8`（**绝对地址**指针） |
| 有定义 opcode | 160 / 256 | 102 / 256 |
| 平铺验证 | **119/119 剧本 100%** | **107/108 剧本 100%**（`BEF_004.ws2` 用 `0x5f`/`0x80`，疑为更新构建） |

**两表 96 项相同、仅 7 项只差尾部字段**（如 `0x14`：原版 `[4,6,8,6,8]` vs Steam `[4,6,8,6,8,0]`）。
⇒ 此前"原版不可反汇编"的根因是**尾字段差异**，**不是指令集不同**（该说法已更正）。


