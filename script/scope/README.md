# script/scope/ — 还原范围标定（差分 → `resource/restore_scope.json`）

本目录把「Steam 版相对原版删改了什么、每一处该用什么形态还原」定案成机器可读表。结论摘要见 [doc/restoration-scope.md](../../doc/restoration-scope.md)。

## 运行顺序

```bash
python script/scope/scope_mech.py    # 三方差分机械标定 → tmp/scope/{scope_mech.json, regions.jsonl}
python script/scope/packs.py         # 逐剧本语义核验 pack → tmp/scope/packs/pack_<script>.md
python script/scope/build_scope.py   # 机械区间 + verdicts.py 语义判定 → resource/restore_scope.json
```

## 工具

| 脚本 | 职责 |
|---|---|
| `scope_mech.py` | **三方差分标定**：ORIG↔STEAM 用语音名 LCS 锚点、STEAM↔PATCH 用台词文本 LCS 锚点，圈出全部差分区间，记录格数/语音条数/补丁覆盖（jp_cover）/补丁删除的 Steam 行。ORIG 侧用 `resource/ws2_formats_orig.json`，Steam/Patch 侧用 `resource/ws2_formats.json` |
| `packs.py` | 把每个剧本的差分区间导成 markdown（两侧全文 + 元信息），供语义核验逐处判读 |
| `verdicts.py` | **134 个区间的形态判定表**（form / action / h_level / 依据）。subagent 语义核验结论 + 主控复核的固化产物；改判定只改这里 |
| `scope_extra.py` | `restore_scope.json` 的文字性内容（形态/动作定义、整脚本动作、路线 UI、实现红线） |
| `build_scope.py` | 汇总产出 `resource/restore_scope.json`（幂等，可重复运行） |

## 判定口径（六种形态）

改写（`replace_with_orig`）／整段删+新写（`keep_steam_insert_orig`）／压缩概述（`cells_take_orig_firstN_insert_rest`）／纯删（`insert_orig_all`）／纯增（`keep`）／翻译拆行伪差异（`no_action`）。

两条告诫：① 不能用「语义对不上」判「Steam 新增」——要问「这几格是不是在替掉缺口里的那几行」；② 机械形状只圈位置，候选必须逐处语义判断。

## 中间产物（不提交）

`tmp/scope/`：`scope_mech.json`（机械区间全量）、`regions.jsonl`（逐区间上下文）、`packs/`（核验 pack）。
语义核验报告在 `tmp/verify/scope_*.md`。
