# 在这苍穹展翅 - 飞行日志 - 内容恢复与汉化补丁

为 Steam 版[《If My Heart Had Wings -Flight Diary-》](https://store.steampowered.com/app/923810/)还原被移除的原版剧情，补回被整条删除的**姬城姐妹线**，同时保留 Steam 新增的**朱莉线**与**成就系统**，并把还原内容汉化。

本补丁仅供已购买正版游戏的用户使用，不包含任何游戏本体文件。

> **当前版本：v0.0.1** — 内容还原 + 中文落地 + 路线入口/角色高亮，等待全量实机验证。

---

## 安装方式

从 [Releases](../../releases) 下载 `IMHHFD_Content_Restoration_Patch_Installer_vX.X.X.exe`，双击运行。

安装器会依次执行以下步骤：

1. 定位游戏目录（自动读取 Steam 库；未找到时可手动输入）
2. 列出将被修改的文件，等待确认
3. 就地合并资源、覆盖脚本与中文文本
4. 逐文件哈希回读校验

游戏目录一般位于 `<Steam 库>\steamapps\common\IF MY HEART HAD WINGS FLIGHT DIARY`。安装完成后即可删除安装器。

非 Windows 环境可自行构建 `payload/` 后使用 `tool/install.py` 安装（需要 `arcbuild.py`、`payload/` 与脚本位于同级）。

## 卸载与恢复

补丁**不创建备份**，恢复原版通过 Steam 完成：

1. Steam 库中右键游戏 → 属性
2. 已安装文件 → 验证游戏文件完整性

Steam 会检测出被修改的归档并重新下载，恢复到未安装状态。

## 更新补丁

先通过 Steam 验证游戏文件完整性恢复游戏目录原始状态（见上方「卸载与恢复」），然后按「安装方式」重新安装新版本。

## 会被修改的文件

| 文件 | 处理方式 | 内容 |
|---|---|---|
| `Rio.arc` | 整档覆盖 | 113 → 114 个成员：24 个宿主脚本就地重建、新增 `AGS_001.ws2`、`NameTable.txt` |
| `zh-CN/Rio.arc` | 整档覆盖 | 50 → 51 个成员：24 份宿主 `.lng` 重建 + 新增 `AGS_001.lng` |
| `Script.arc` | 整档覆盖 | 14 个成员：`LegacyGame.lua` 按钮表/滑入动画/角色高亮分支 |
| `Graphic.arc` | 资源级合并 | 275 → 323：新增 48、同名换内容 61（含 3 条 PNA 层内修复） |
| `Chip1.arc` | 资源级合并 | 258 → 270：新增 12（还原块引用的背景/立绘） |
| `Chip2.arc` | 资源级合并 | 61 → 73：新增 12、同名换内容 2 |
| `Chip7.arc` | 资源级合并 | 164 → 344：新增 180、同名换内容 3 |
| `Chip8.arc` | 资源级合并 | 65 → 238：新增 173 |
| `Chip9.arc` | 资源级合并 | 74 → 257：新增 183、同名换内容 11 |
| `Se.arc` | 资源级合并 | 223 → 242：新增 19 |
| `Voice.arc` | 资源级合并 | 10,265 → 12,152：新增 1,887 条原版语音 |
| `SysGraphic.arc` | 资源级合并 | 28 个成员：同名换内容 1（base UI 第 8 入口 + Cast） |
| `zh-CN/SysGraphic.arc` | 资源级合并 | 21 个成员：同名换内容 1（中文 UI 第 8 入口） |

以下归档**不做任何改动**：`Rio1.arc`、`Chip3/4/5/6.arc`、`Chip10.arc`、`Bgm.arc`、`zh-CN/Rio1.arc`。

---

## 实现原理

本作与姊妹作《在这苍穹展翅》同引擎（AdvHD.exe），但 Steam 版做了三件事：**剧本整体改名 + 整脚本删除**（`AGS_001`）、**全年龄化用新增顶替脚本**（如 `KAN_3002_2` → `_E` + 新增 `3002_3_E`）、**同名素材改画/删成员**。补丁的策略是**不改 Steam 的调用链骨架**，只在原位置做增量：

### 一、内容还原

- **整脚本补回**：`AGS_001.ws2` 跨版本转换（原版 WS2 → Steam WS2 格式表）后作为新增成员写入 `Rio.arc`；`mainmenu` 的入口跳转保持 Steam 原样。
- **就地插入**：24 个宿主脚本以 Steam `*_E.ws2` 为底，删除被审查替换的 Steam 格，在原位置插入对应原版格；跳转、`0x01/0x02/0x06` 偏移统一重定基，出口与成就调用逐字节保留。
- **演出同步**：保留槽自带的立绘/背景/CG/清屏与原版行不一致时，按 `perf_sync` 判定表整段换回原版行；`0x0b` 解锁对与 `CG_ACHIEVEMENT` 不重复、不丢失。
- **立绘记录表**：同名 `.pna` 被 Steam 删过哨兵、加过层或重排 ⇒ 不整名覆盖，改走 `resource/pna_id_map.json`：原版来源块换算 `0x39` 记录号；被改画且未被 Steam 新增段复用的 3 条子图做层内修复（只换子图/box，不改记录数/顺序/画布）。

### 二、中文覆盖

引擎按 **CP932** 解码脚本内窄字节，简体字写不进 ws2，因此中文只走宽字符通路：

| 通路 | 承载 | 机制 |
|---|---|---|
| `.lng` | 正文与选项 | 无 id 字段，按播放序第 N 条替换为 lng 第 N 条；每个 `0x0f` 选项也占一槽 |
| `NameTable.txt` | 说话人名 | UTF-16LE 替换表；脚本写 `%LC<英文名>`，查表换成中文 |

本作 `NameTable.txt` **原生放在基础 `Rio.arc`**（`zh-CN/Rio.arc` 只有 `.lng`），补丁遵循原生存放位置、不搬位；构建/闸用 `tool/lng.load_nametable()` 按「语言包优先、基础档兜底」取实际归档。

### 三、成就

不修改 Steam 的成就调用，也不改动脚本出口集合：删格时 `0xF0`、`0b` 解锁对、`SCENETITLE`/鉴赏 Hook 逐字节原位。机检：`CG_ACHIEVEMENT` 723、`0xF0` 33，逐脚本与 `backup/` 相同。

---

## 已知情况

### 还原范围

- 姬城姐妹线（`AGS_001` + 姫城あげは `AGS_*` / 姫城ほたる `HOT_*`）补齐；朱莉线（`AKA_*` / `Rio1.arc` / `Chip10.arc`）保持 Steam 原样。
- `KAN_3002_2` 的 H 场景按原版恢复；Steam 的全年龄替代场景 `KAN_3002_3_E` 不再接播。
- 朱莉线新增立绘 `H朱莉_01*` 的 2 个新增层只在新路线使用；原版来源槽按内容映射到原版服装记录，不替换整个 PNA。
- `*_W` 系列保留 Steam 的画布裁切；按重心对齐后与原版无可见差异。

### 文本校验状态

- `.lng` 位置等式全量通过：产物条数 == `0x14` 槽数（含 `0x0f` 条目）。
- 5,348 条语料：控制标记（`%K%P`/`%P`/`\n`/`\d`）与日文逐行一致；无空条目、无假名残留。
- 154 格补译已完成首译与格式闸；**全量逐句语义复审未做**（4,701 个无语音自证格仅按对齐块确认）。

### 画面校验状态

- `perf_consistency_check`：14,001 槽内容一致，CG/立绘差异 0。
- `pna_id_check`：21 个记录表不等价成员、839 条映射、3 条层内修复，越界/未修复引用 0。
- 朱莉线 72 槽与 `*_W` 裁切版为已知版本差，已登记 `resource/perf_waivers.json`。

---

## 目录结构

```
├── AGENTS.md           项目约定
├── README.md           本文件
├── VERSION             版本号（唯一来源）
├── asset/              测试用完整交付文件（构建产物，不进 Git）
├── backup/             Steam 原版基线（只读，不进 Git）
├── doc/                技术文档（索引见 doc/README.md）
├── tool/               通用库与安装器
│   ├── install.py      安装器逻辑
│   ├── arcbuild.py     Arc 读写
│   ├── ws2.py          WS2 编解码
│   ├── ws2dis.py       WS2 反汇编
│   ├── writer.py       宿主脚本写盘器
│   ├── pna.py          PNA 图层容器
│   ├── pnaids.py       0x39 记录号映射
│   ├── lng.py          .lng / NameTable 编解码
│   ├── pnglite.py      纯标准库 PNG 解码
│   └── ...
├── script/
│   ├── build/          构建流水线（S2 计划 → S2b 立绘映射 → S3 写盘 → S3b/c/d 画面 → S4 文本）
│   ├── checks/         验收闸（内容/演出/CG/PNA/语料）
│   ├── scan/           勘察脚本（开发期，非流水线）
│   ├── scope/          还原范围标定（开发期，产出 resource/restore_scope.json）
│   ├── corpus/         中文语料构建（开发期）
│   ├── generate_payload.py  生成增量补丁
│   ├── final_verification.py 全量验收
│   └── pack.sh         打包安装器
├── resource/           入库输入表（判定表、计划、语料、定版素材）
├── payload/            增量补丁产物（构建后生成，不进 Git）
├── releases/           安装器产物（构建后生成，不进 Git）
└── tmp/                草稿区（不进 Git）
```

## 从源码构建

```bash
# 依赖：Python 3.11+；原版发行版目录（IFMH_ORIG_DIR）；GalRev 库（GALREV_DIR）
python script/build/build_restore_plan.py     # S2 还原计划
python script/build/build_pna_id_map.py --write  # S2b 立绘记录映射/修复表
python script/build/build_patch.py            # S3 Rio.arc
python script/build/build_l3.py --write-asset # S3b 同名画面覆盖
python script/build/build_l4_extra.py         # S3c 缺失素材补入
python script/build/build_pna_repair.py       # S3d 立绘层内修复
python script/build/build_lng.py              # S4 中文 .lng
python script/final_verification.py           # 验收
python script/generate_payload.py             # 增量 payload
bash script/pack.sh                            # 安装器 exe
```

`backup/` 只读；`asset/`、`payload/`、`releases/` 由脚本重建。构建只读 `backup/` + `resource/`；原版目录仅用于重建 `resource/` 中入库的素材。

## 测试进度

- [x] 路线入口：第 8 个按钮可点、滑入动画正常、角色高亮 Cast 正常（中/英两套 UI）
- [ ] 主要内容还原段：`AFT_003`、`BEF_006`、`HOT_003`、`KAN_1004`、`KAN_2001`、`KAN_3002_1`、`KAN_3004_2` 等抽样实机
- [x] 中文显示：正文、选项、名牌
- [x] 成就触发点静态完整性（723 / 33）
- [ ] 全流程通关
- [ ] 朱莉线全段回归
- [ ] 12 处 Steam 重录语音替换为原版录音
- [ ] `BEF_005` O#1116 补行

## 反馈

遇到问题请提交 [Issue](../../issues)，附上：

- 补丁版本
- 出现问题的具体场景（角色线 + 大致进度；最好附存档）
- 游戏弹出的错误日志（如有）
- 问题的具体表现

## 致谢

- 引擎逆向知识、工具链与工程经验来自 [GalRev](https://github.com/Madao-1639/GalRev) 与 [A Sky Full of Stars 内容还原补丁](https://github.com/Madao-1639/A_Sky_Full_of_Stars_Content_Restoration_Patch)

## To-Do

- [ ] 全流程通关与全 CG/全成就回归
- [ ] 朱莉线全段回归（确认新增立绘/语音不受影响）
- [ ] 12 处 `V*` 语音替换
- [ ] `BEF_005` O#1116 补行（需新增还原区间 + 译文）
- [ ] 4,701 个无语音自证格的逐句语义复核
