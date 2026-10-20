# 文档索引

本目录是《在这苍穹展翅 - 飞行日志 -》（If My Heart Had Wings -Flight Diary-）内容恢复补丁的文档体系。

**基线**：Steam = `E:\SteamLibrary\steamapps\common\IF MY HEART HAD WINGS FLIGHT DIARY`（只读，补丁仓库内另存 `backup/`）；
原版 = 原版发行版目录（**不在本仓库内**）；国外还原补丁 / 中文汉化补丁见 [third-party-patch-analysis.md](third-party-patch-analysis.md)。

状态图例：✅ 已确认 ／ ⚠️ 部分确认 ／ ❓ 未知

---

## 阅读路径

| 目的 | 先读 |
|---|---|
| **了解要还原什么、范围如何分层** | [restoration-targets.md](restoration-targets.md) |
| **还原范围定案（逐剧本逐区间动作）** | [restoration-scope.md](restoration-scope.md) |
| 了解怎么还原、流水线与验收 | [restoration-route.md](restoration-route.md) |
| **了解路线机制与「线路完备」可行性** | [route-mechanics.md](route-mechanics.md) |
| **L6 入口的规格 / 素材 / 命令** | [route-mechanics.md](route-mechanics.md) §0.1、[../resource/README.md](../resource/README.md) |
| **了解两个第三方补丁改了什么、哪些不能沿用** | [third-party-patch-analysis.md](third-party-patch-analysis.md) |
| 引擎层面通识（可跨作复用） | [engine-mechanics.md](engine-mechanics.md)、[file-formats.md](file-formats.md) |
| 验收 | [acceptance-criteria.md](acceptance-criteria.md) |
| 踩坑记录 | [lessons-learned.md](lessons-learned.md) |

---

## 文档清单与来源

### A. 本作专属（本次新建/重写）

| 文档 | 内容 |
|---|---|
| [restoration-targets.md](restoration-targets.md) | 还原目标、范围分层（L1–L4）、判定标准 |
| [restoration-route.md](restoration-route.md) | 还原路线、差分标准、流水线、发布链 |
| [route-mechanics.md](route-mechanics.md) | 路线入口机制、Steam 侧缺口、可行性判定、实现方案；**L6 已落地并实机通过**（§0.1 交付与复现、§3.5 按钮、§3.8 base 入口、§3.9 角色高亮） |
| [third-party-patch-analysis.md](third-party-patch-analysis.md) | 国外还原补丁 / 中文汉化补丁的改动面与缺陷成因、不可沿用的做法 |
| [patch-verification-protocol.md](patch-verification-protocol.md) | **第三方补丁逐处核验协议**（判据 V-1..V-5、缺陷清单 D-1..D-14、结论格式） |
| [patch-en-alignment.md](patch-en-alignment.md) | **英文行 ↔ 原版行 对应性核对**（语音锚点对齐、拆/合行缺口、抽样语义判定） |
| [restoration-scope.md](restoration-scope.md) | **还原范围定案**（134 差分区间形态判定、逐剧本动作、Steam 删减清单、Gemini 汉化补丁覆盖评估、中文交付路径） |
| [acceptance-criteria.md](acceptance-criteria.md) | 验收标准（含成就触发点、lng 位置对应） |
| [afterstory-mechanics.md](afterstory-mechanics.md) | 后日谈/回想机制（**待按本作重写**，见文首横幅） |
| [pna-resources.md](pna-resources.md) | PNA 图层命名与层序、子层号=记录下标（**已按本作重标定**） |
| [resource-naming.md](resource-naming.md) | 资源命名与号段规范、同名冲突处置（**待按本作重标定**） |
| [script-text-extraction.md](script-text-extraction.md) | 脚本文本提取与译文匹配（**待按本作重标定**） |

### B. 引擎通用（自姊妹作项目《在这苍穹展翅》迁移，可直接复用）

| 文档 | 内容 | 迁移状态 |
|---|---|---|
| [engine-mechanics.md](engine-mechanics.md) | WS2 VM 结构、LAYER_ORDER、文本编码路径、语言包目录 | ✅ 通用；**本作 opcode 表需重读**（见 route-mechanics §3） |
| [file-formats.md](file-formats.md) | Arc / WS2 / LNG / Lua 5.3 / NameTable / PTF 字体 | ✅ 通用；LNG 密钥本作 = **0x3E** |
| [achievement-mechanics.md](achievement-mechanics.md) | Steam 成就机制与安全注入 | ✅ 通用；`CG_ACHIEVEMENT` 注入点模式需按本作核对 |
| [lessons-learned.md](lessons-learned.md) | 问题记录（方法论红线） | ✅ 通用 |
| [sem-review-protocol.md](sem-review-protocol.md) | 全量逐行通读评审判据 | ✅ 通用 |

> **引擎层知识的上游**：`D:\My_Code\tmp\GamePatch\GalRevserse\GalRev`（按引擎组织的逆向知识库 + `galrev` Python 库 + 引擎级数据表）。本项目 `tool/` 中与引擎格式相关的部分应优先复用 `galrev`，只在需要本作标定值时在项目内提供参数。

---

## 文档写法约定

只写**最新结论、工作范围、目标、标准/方针/原则、分层与工程约定**；**不写过程叙述**（逐轮进展、发现经过、实测方法与分歧裁决过程）。过程证据与逐轮记录一律放 `tmp/`（草稿区，不提交）。唯一例外是 [lessons-learned.md](lessons-learned.md)——它就是"问题记录"的指定位置。

**方针改动必须三处同步**：产出端脚本、入库表（`resource/*.json`）、消费端脚本一起改；只改一两处的缺口是静默的，唯一能拦住的是端到端断言。同源教训见 [lessons-learned.md](lessons-learned.md)。
