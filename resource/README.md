# resource/ 数据索引

本目录存放**还原流水线的输入表**：判定结果、映射表与语料。表是**产出端脚本的产物、消费端脚本的输入**；改表必须同步改两端脚本（见 [AGENTS.md](../AGENTS.md) §1「方针改动必须三处同步」）。

> **状态**：标定与差分阶段的核心表已产出；逐条改写计划表待计划生成器落地。每张表落地时在此补「字段 / 生产者 / 消费方」。

---

## 已产出

| 表 | 用途 | 生产者 | 消费方 | 状态 |
|---|---|---|---|---|
| `ws2_formats.json` | **Steam 版 WS2 操作数格式表**（opcode → 类型码串）。从 Steam `AdvHD.exe` 的 `.rdata 0x57ada8` 导出（160/256 项有定义） | `script/scan/dump_formats.py`（IDA MCP） | `tool/ws2fmt.py`、全部差分/计划脚本 | ✅ 已产出（Steam 侧 119/119 剧本 100% 平铺） |
| `ws2_formats_orig.json` | **原版 WS2 操作数格式表**。从原版 `AdvHD.exe` 的 `.data RVA 0x12DAD8` 导出（102/256 项有定义）；与 Steam 表 **96 项相同、7 项仅差尾字段**（`0x14`：原版 `[4,6,8,6,8]` vs Steam `[4,6,8,6,8,0]`） | `script/scan/export_orig_formats.py` | 跨版本搬运（原版→Steam）的字段对齐 | ✅ 已产出（原版 107/108 剧本 100% 平铺） |
| `restore_plan.json` | **还原计划**：逐脚本 `kind`（host/whole）、`drops`（删的 Steam 槽号）、`inserts`（`[锚槽, 原版行0, 原版行1]`）、成就注入数、`meta.name_map`（`%LC` 日文名 → Steam 罗马字键） | `script/build/build_restore_plan.py` | `script/build/build_patch.py`、`tool/writer.py` | ✅ 已产出（25 脚本：24 host + AGS_001 whole） |
| `replay_guards.json` | **「回想入口/出口」搬运纪律**：逐脚本 `action=drop|keep` + `var110` 值 + 原版三连位置 + 症状。原版头部的回想分派与场景末尾的出口三连是一对，Steam 删了头部 ⇒ 只搬出口会变成孤儿（`flag127=1` 且 `var110=k` 时正常播放也提前回主菜单）；`BEF_003`/`KAN_3002_2` 因 Steam 自带入口分派而 keep | 手工维护（全库扫描 `01(127)`/`01(110)`/`07 EVRET`） | `script/build/build_patch.py`（识别 + 按表剥离，交 `writer.skip_orig`）、`script/checks/replay_guard_check.py` | ✅ 已产出（7 条：drop 5 / keep 2） |
| `slot_sources.json` | **槽位表**：逐脚本「最终槽位序 → `('steam', 旧槽号)` / `('orig', 原版行号)`」 | `script/build/build_patch.py` | `script/build/build_lng.py`（按槽取中文） | ✅ 已产出 |
| `corpus/char_fix2.json` | **字级错字修正表** `{错字: 正字}`（逐字映射的一形对多义残留，44 字） | 逐行判定（subagent） | `script/scope/apply_cn_fixes.py` | ✅ 已产出 |
| `corpus/row_fix.json` | **逐行错字修正表** `{"<script>#<row>": "<修正后的完整 cn>"}`（上下文相关，262 条） | 逐行判定（subagent） | `script/scope/apply_cn_fixes.py` | ✅ 已产出 |
| `censor_map.json` | **L3 同名素材判定台账**：逐成员 `action=overwrite|keep` + 判据 + 证据（`members` 列表 + `meta`/`series`） | `script/build/build_l3.py`（`--emit-map --schema canonical`） | `script/final_verification.py`、`script/checks/pna_id_check.py`（按 `members` 读） | ✅ 已产出（82 条：61 overwrite + 21 keep） |
| `julie_guard.json` | **朱莉线保护名单**：不得触碰的归档/成员/脚本（`Chip10.arc`、`Rio1.arc`、`AKA_*`、`zh-CN/Rio1.arc`） | 手工维护 | 写盘器（硬拒绝） | ✅ 已产出 |
| `route_entry.json` | **L6 路线入口定案**：中文按钮的文案 / 来源与目标图层记录 / PNA 记录与 box / Lua 原型路径与逐按钮 FOR 上界 / **base（英）PNA 的原版日文入口记录与 box**、**角色高亮 Cast 图（原版记录 → 目标记录/box/Lua 分支）** | 手工维护（中文按钮几何量由 `tool/agsbutton.py` 运行时实测；base 入口取自原版发行目录 `tool.paths.orig_dir()`） | `script/build/build_route_entry.py`、`script/checks/check_route_entry.py` | ✅ 已产出 |
| `restore_scope.json` | **还原范围定案**：逐剧本逐区间的 `form`/`action`/`h_level`/格号范围/补丁行为（134 区间）+ 整脚本动作 + 路线 UI + 实现红线 + Gemini 补丁覆盖评估 | `tmp/scope/build_scope.py`（机械区间 `scope_mech.py` + 判定 `verdicts.py`，语义核验报告 `tmp/verify/scope_*.md`） | 计划生成器、写盘器、验收闸 | ✅ 已产出（结论摘要见 [doc/restoration-scope.md](../doc/restoration-scope.md)） |
| `corpus/cn_draft/<script>.jsonl` | **中文底稿对齐表**：in-scope 的 5 194 个 ORIG 行 ↔ Gemini 中格（语音锚点对齐；`jp`/`cn_gemini`/`speaker`/`voice`/`h_level`） | `script/scope/build_cn_corpus.py` | 审校分块（`build_cn_packs.py`） | ✅ 已产出 |
| `corpus/choice_cn.json` | **选项条目（`0x0f`）的中文**：`{脚本: {原版 strid: {jp, cn, branch}}}`。原版无 `.lng`（日文即条目内联文本）⇒ ws2 保留原文、中文只写 `.lng`；每个条目占一个文本槽位（`lng 条数 == 0x14 + Σ(0f count)`） | 手工维护（原版内联日文 + 就地翻译） | `script/build/build_lng.py`（槽位来源 `['choice', strid]`） | ✅ 1 脚本 / 2 条（`BEF_004` 606/607） |
| `corpus/cn/<script>.jsonl` | **最终中文语料**：逐格 `{script, orig_row, jp, cn, h_level, src}`（`gemini_norm` 4 520 / `reviewed` 615 / `punct` 59）——`.lng` 生成器的输入。质检：5 194 行中 5 133 合格 + 60 纯标点行，控制标记（`%K%P`/`%P`/`\n`/`\d`）与 JP 逐行一致 | `script/scope/{merge_cn2,fix_merge_residual,finalize_cn}.py`（合并 32 个复审 diff + 修残 + 质检） | `.lng` 生成、验收闸 | ✅ 已产出 |
| `script_diff.json` | 脚本级差分：逐脚本的跳转结构、`0x14`/`0x0f` 槽位数、语音 token 数、还原范围 | 差分扫描脚本 | 计划生成脚本 | ⬜ |
| `member_diff.json` | 归档成员级差分：`added`/`deleted`/`modified`/`keep`（含同名换内容） | 差分扫描脚本 | 计划生成、`asset/` 生成 | ⬜ |
| `same_name_overwrite.json` | **同名素材整名覆盖名单**（画面和谐还原）：`{归档, 成员, 判据, 依据}` | 图像比对脚本（五步） | 写盘器 | ⬜ |
| `restore_plan.json` | 逐条改写计划：位置（脚本+偏移 / 归档+成员）+ 操作（插入/替换/改指/补回）+ 依据 | 计划生成脚本 | 写盘器 | ⬜ |
| `carrier_quirks.json` | 承载图/语音配对机械不可用的特例 | 人工 | 计划生成 | ⬜ |
| `carrier_map.json` | 承载图：语音 / CG / 跳转 / 调用四类锚点保序对齐（Steam 槽 ↔ 原版行） | `script/build/build_carrier_map.py` | `script/build/build_perf_sync_map.py`、`script/build/build_restore_plan.py` | ✅ 107 脚本 / 8,579 锚点 |
| `perf_sync_map.json` | 演出同步判定表：保留槽自带的 st/bg 演出与原版行不一致 ⇒ `replace`（整段换原版）/ `drop`（删多余通道） | `script/build/build_perf_sync_map.py` | `script/build/build_restore_plan.py` → `plan.perf_sync` → `tool/writer.perf_sync_apply` | ✅ 41 站点 / 9 review |
| `perf_sync_manual.json` | 人工/闸驱动的演出处置：`drops` / `replaces` / `keeps`，用于判定表覆盖不到或对齐修复的槽（**BEF_005 的 drop@1121/replace@1122 已撤销**：原版 O#1116 被 Steam 删去，原闸内插错 1 行，Steam 自己的显示点是对的） | `script/checks/perf_consistency_check.py` 根因行 + 人工复核 | 同上 | ✅ 12 replaces + 1 drop |
| `pna_id_map.json` | **PNA 记录号映射与层内修复表**：逐 keep 成员的 `原版记录号 → Steam 记录号`（`rank`／`content` 策略）、`changed`（Steam 改画/裁切的记录）、`repair`（允许换回原版子图的记录）、`waive`（有差但不得修复的记录及引用核对） | `script/build/build_pna_id_map.py` | `script/build/build_patch.py`（0x39 号换算）、`script/build/build_pna_repair.py`（层内修复）、`script/checks/pna_id_check.py` | ✅ 21 成员 / 839 映射 / 3 repair |
| `perf_waivers.json` | **已复核、不纠正的演出差异**：槽级（翻译拆行/Steam 新增行/水印 CG/句序）、成员级（朱莉线新美术、W 立绘画布重心裁切）、全局（无语音自证的文本块） | 人工定案（全量演出评审） | `script/checks/perf_consistency_check.py`、`script/checks/pna_id_check.py` | ✅ 5 槽 + 7 成员 + 1 全局 |
| `align_fixes.json` | **人工定案对齐**：`{脚本: {Steam 槽: 原版行｜null}}`；机械对齐（承载图锚 + 语音自证 + 等长内插）给不出映射时使用。当前登记 BEF_005 的 27 个槽（原版 O#1116 整行删除 + O#1119 被 Steam 拆成两格） | 人工复核 | `tool/perfsync.py`、`script/checks/perf_consistency_check.py` | ✅ BEF_005 27 条 |
| `orig_deleted.json` | **原版有、Steam 整行删去的行号**（逐脚本）：对齐闸/内插先剔除，避免等长缺口把后续槽整体映射错位 | 人工复核 | `script/checks/perf_consistency_check.py` | ✅ BEF_005 O#1116 |
| `corpus/jp/*.json` | 原版日文逐脚本条目底稿（`script` / `total` / `texts[]`） | 文本提取脚本 | 译文匹配、翻译 | ⬜（已由 `corpus/cn_draft` 的 `jp` 字段覆盖） |
| `corpus/zh/*.json` | 中文条目底稿（官方 `zh-CN` lng 提取） | 文本提取脚本 | 译文匹配 | ⬜ |
| `corpus/pairing.jsonl` | 日↔中逐行配对（`script`/`kind`/`idx`/`off`/`seq`/`jp`/`cn`/`src`/`crc`） | 配对脚本 | 翻译、lng 生成 | ⬜ |
| `fan_cn/{SCRIPT}.json` | 逐脚本中文产物（含 `lng_idx` 槽位对齐） | 文本构建脚本 | 写盘器 | ⬜ |
| `fan_cn/NameTable.json` | 人名替换表（UTF-16LE 产物） | 文本构建脚本 | 写盘器 | ⬜ |
| `fan_cn/manifest.json` | 中文产物总账（`key` = `0x3E`、逐脚本计数、验收项） | 文本构建脚本 | 验收闸 | ⬜ |

---

## `resource/route_entry/`（L6 路线入口的二进制素材）

`backup/` 里**没有**这些图层（Steam 删了/替换了），它们的唯一来源是**外部原版发行目录**。
按「构建只读 `backup/` + `resource/`」的约定，先把它们落成本目录里的显式输入，**build 不再直接读原版目录**：

| 文件 | 来源 | 用途 | 重建 / 生成脚本 |
|---|---|---|---|
| `route_entry/ags_button_cn_on.png` | `backup` 中文 PNA 的官方按钮（记录 9/13）拼字生成后**定版入库** | 中文 UI 第 8 个按钮 · 亮态 | 定版（生成脚本已移除）；校验用 `tool.agsbutton.verify` |
| `route_entry/ags_button_cn_def.png` | 同上（记录 10/14） | 中文 UI 第 8 个按钮 · 暗态 | 同上 |
| `route_entry/base_entry_ags_on.png` | 原版 `SYS_Story.pna` 记录 7 | base（英/默认）UI 第 8 个入口 · 亮态 | `script/build/import_route_assets.py` |
| `route_entry/base_entry_ags_def.png` | 原版 `SYS_Story.pna` 记录 8 | 同上 · 暗态 | 同上 |
| `route_entry/cast_highlight_ags.png` | 原版 `SYS_Story.pna` 记录 23 | 角色高亮 Cast 图（AGS/姫城姉妹） | 同上 |

- 重建：`python script/build/import_route_assets.py`（原版 → resource，幂等、逐字节保真）。中文按钮两件**已定版**，不再就地生成（生成脚本随定版移除；要改就重做成品再入库）。
- 校验：`import_route_assets.py --check`（与原版一致）；中文按钮由 `tool.agsbutton.verify` 在 build 时对 `backup/` 官方按钮复核五道闸。
- **build 只读本目录**：`build_route_entry.py` 的内容全部来自这 5 个文件；中文按钮仍会用 `tool.agsbutton.verify` 对 `backup/` 的官方按钮复核四道闸（字位 / 同位 / 平移后位置 / 掩膜内外逐字节），所以入库件不可能悄悄漂移。
- 消费方：`script/build/build_route_entry.py`（`res_file()`；文件缺失即中止并提示跑生成/导入脚本）、`script/checks/check_route_entry.py`。
- 规格登记：`route_entry.json` 的 `base_ui_entry.resource_files` 与 `cast_highlight.resource_file`（路径相对 `resource/`）。

## 约定

- **`.lng` 密钥**：本作 = `0x3E`（`tool/lng.py::KEY_FD`）。写档必须显式传 key，不要依赖默认值猜测。
- **位置对应**：`lng 条数 == 0x14 指令条数 + Σ(0x0f 的 count)`；正文一增删必须整体重建宿主 lng（见 [restoration-route.md](../doc/restoration-route.md) §2）。
- **朱莉线隔离**：任何写盘操作都要先过 `julie_guard.json` 的硬拒绝检查。朱莉线立绘 `H朱莉_01*` 只做记录号映射，不改 PNA 字节（见 `pna_id_map.json` / `perf_waivers.json`）。
- **立绘 PNA 构建顺序**：`build_restore_plan` → `build_pna_id_map`（产 `pna_id_map.json`）→ `build_patch`（按表换算 `0x39`）→ `build_l3 --write-asset` → `build_l4_extra` → `build_pna_repair`（层内修复 + 归档名规范）。`pna_id_map.json` 必须在 `build_patch` 之前存在/更新。
- **`NameTable.txt` 遵循原生存放方式，不搬位**：官方范式在 `zh-CN/Rio.arc`，本作原生在基础 `Rio.arc`。用 `tool/lng.load_nametable()` 按「语言包优先、基础档兜底」返回**实际归档路径**；要改表就写回同一归档。键覆盖闸缺键即失败（`build_lng.py`）。
- **外部素材先入库**：凡 `backup/` 里没有、只能从原版发行版取得、且**不可由脚本再生**的二进制素材，必须先落成 `resource/` 下的显式输入（本目录），build 只读 `resource/`；原版目录仅用于重建这些文件。缺文件时 build 直接中止，不静默回退去读仓库外路径。
