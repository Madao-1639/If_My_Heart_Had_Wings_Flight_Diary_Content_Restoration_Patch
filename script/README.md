# script/ 目录说明

## 生产流水线（构建/验收，必须可重复运行）

| 目录/脚本 | 用途 |
|---|---|
| `build/` | 还原流水线：`build_restore_plan` → `build_pna_id_map` → `build_patch` → `build_l3` → `build_l4_extra` → `build_pna_repair` → `build_lng` |
| `checks/` | 验收闸：内容一致性、演出同步、CG 序列/解锁、PNA 记录号、**回想守卫/出口（`replay_guard_check.py`）**、**WS2 尾表（`ws2_tail_check.py`）**、**选项头（`choice_header_check.py`）**、**选项文本/人名规范（`choice_spec_check.py`）**、**人名帧一致性（`name_frame_check.py`）**、**跳转自洽/槽位等式（`choice_jump_check.py`）**、**选项帧内无 `0x16`（`choice_frame_check.py`）**、语料预检/回读、资源覆盖 |
| `final_verification.py` | 全量验收（归档/调用链/成就/资源/零破坏/可复现） |
| `generate_payload.py` | `asset/` vs `backup/` → `payload/` 增量包 + 回读重放校验 |
| `pack.sh` | PyInstaller 打包 `tool/install.py` → `releases/` |

这些脚本**只读** `backup/` + `resource/`（原版目录仅用于重建 `resource/` 的入库素材），
报告写到 `tmp/`；**不读 `tmp/` 作为输入**，`tmp/` 被清空后仍可完整重建。

## 开发期脚本（非流水线，保留作溯源）

| 目录 | 用途 | 注意 |
|---|---|---|
| `scan/` | 差分/勘察、WS2 格式表导出 | 部分依赖 IDA MCP 或外部原版目录 |
| `scope/` | 还原范围标定 → `resource/restore_scope.json` | 分步脚本使用 `tmp/scope/` 中间稿；表已入库，日常构建不再运行 |
| `corpus/` | 中文语料构建/合并 | 产出已入库 `resource/corpus/`；分步脚本可能引用 `tmp/` 复审稿 |

## 未适配的姊妹作脚本（仅保留作移植参考，当前不可运行）

| 脚本 | 状态 |
|---|---|
| `verify_sync.py` | 依赖姊妹作 `restore_plan` 的 `hosts`/`A1`/`resources` 结构与 `resource/fan_cn/*.json`；本作未移植 |
| `checks/check_carrier_ledger.py` | 依赖同一结构与 `resource/carrier_quirks.json`；本作未入库 |

本作验收以 `final_verification.py` + `checks/*` 为准；这两个脚本在文件头已标注，不会静默产生错误结论。
