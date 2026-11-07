"""
《在这苍穹展翅 - 飞行日志 -》Steam 版内容恢复补丁安装器
If My Heart Had Wings -Flight Diary- Content Restoration Patch Installer

安装说明：
0. 先选**安装器界面语言**（中文 / English）—— 之后全流程只显示这一种语言
1. 运行安装器，自动检测游戏路径（Steam 注册表 / Linux 常见库目录）
2. 或手动选择游戏根目录（包含 AdvHD.exe）
3. 确认安装
4. 逐文件哈希回读校验

Installation:
0. Choose the **installer language** (Chinese / English); the rest of the run uses only that one
1. Run the installer to auto-detect the game folder
2. Or manually select the game root directory (contains AdvHD.exe)
3. Confirm installation
4. Hash-verify every written file by reading it back

本安装器**不写注册表、不改游戏默认语言**：语言包（`zh-CN/`）与其余交付条目一样，
由 `payload/METADATA.json` 决定，装完按游戏自身设置生效。英文形态请通过 `--ui-lang=en`
只改**安装器界面**语言。

This installer writes no registry keys and does not set the in-game default language: the
`zh-CN/` language pack is delivered like any other metadata entry. Use `--ui-lang=en` to change
the **installer UI** language only.

交付条目形态（`payload/METADATA.json`，键 = 相对游戏根目录的交付路径，一律正斜杠）：
- merge：资源级合并。补丁档 = 交付名 + `_patch.arc`，按 `members` 记录的 **asset 成员
  顺序**重组「玩家原档 + 补丁档」⇒ 与 asset 逐字节一致。
- copy：整档覆盖。补丁档与交付路径同名（含玩家目录原本不存在的新档）。
- loose：裸文件目录（键 `RIO`），`files` = {相对路径: sha256}，逐个复制。

除键 `RIO` 外，每个键都当游戏根目录下的一个文件处理，所以 METADATA 只放可校验的交付
条目；非交付元信息（指纹、出处等）会让校验环节报「文件不存在」。
"""

import sys
import shutil
import json
import hashlib
from pathlib import Path
import arcbuild

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass


def get_version():
    packed = Path(__file__).parent / 'VERSION'
    if packed.exists():
        return packed.read_text(encoding='utf-8').strip()
    dev = Path(__file__).parent.parent / 'VERSION'
    if dev.exists():
        return dev.read_text(encoding='utf-8').strip()
    return 'dev'


CURRENT_VERSION = get_version()
TARGET_APPID = '923810'
GAME_FOLDER_NAME = 'IF MY HEART HAD WINGS FLIGHT DIARY'
GAME_EXE = 'AdvHD.exe'

# 待处理清单的显示名（未列出的键按形态名显示）：(中文, English)
LABELS = {
    'rio.arc': ('脚本还原+中文文本', 'story scripts: restoration + Chinese text'),
    'zh-cn/rio.arc': ('中文覆盖层(.lng+名牌表)', 'Chinese overlay (.lng + name table)'),
    'script.arc': ('引擎 lua(门控与归档路由)', 'engine lua (gating and archive routing)'),
    'graphic.arc': ('分层立绘/图形', 'layered sprites / graphics'),
    'chip1.arc': ('背景/立绘差分', 'backgrounds / sprite variants'),
    'chip2.arc': ('CG/立绘差分', 'CGs / sprite variants'),
    'chip7.arc': ('姬城线立绘差分', 'Himegami-route sprite variants'),
    'chip8.arc': ('姬城线立绘差分', 'Himegami-route sprite variants'),
    'chip9.arc': ('姬城线立绘差分', 'Himegami-route sprite variants'),
    'se.arc': ('音效', 'sound effects'),
    'voice.arc': ('语音', 'voice tracks'),
    'sysgraphic.arc': ('系统界面图层', 'system UI layers'),
    'zh-cn/sysgraphic.arc': ('系统界面图层(简中)', 'system UI layers (Simplified Chinese)'),
}
KIND_LABELS = {
    'copy': ('整档覆盖', 'full overwrite'),
    'merge': ('资源级合并', 'member-level merge'),
    'loose': ('裸文件', 'loose files'),
}


# ---------------------------------------------------------------------------
# 双语输出：**单语**（先选界面语言，之后只印这一种）
# ---------------------------------------------------------------------------

#: 安装器界面语言：`'zh'` / `'en'`。由 `choose_ui_language()` 在**第一步**定下，
#: 之后整个流程只印这一种语言（不再中英并排）。
UI_LANG = 'zh'


def tr(zh, en):
    """按当前界面语言取一条文案。"""
    return zh if UI_LANG == 'zh' else en


def say(zh, en=None):
    """单语输出：按已选的安装器界面语言打印（`en` 缺省时退回中文，仅作容错）。"""
    print(tr(zh, en or zh))


def ask(zh, en=None):
    """单语提示符 + 读一行（返回去空白的小写串）。"""
    return input(tr(zh, en or zh)).strip().lower()


def hr(ch='='):
    print(ch * 60)


def clear():
    """清屏。**只在真终端**做（管道/重定向时跳过，避免把日志弄脏）。"""
    if not sys.stdout.isatty():
        return
    print('\033[2J\033[H', end='', flush=True)


def stage(zh, en=None):
    """阶段标题：清屏 + 上下分隔线 + 标题 + 空行 —— 阶段之间因此总是干净的。"""
    if sys.stdout.isatty():
        clear()
    else:
        print()          # 管道/重定向：上一行可能停在提示符上，补个换行免得分隔线粘上
    hr()
    print(tr(zh, en or zh))
    hr()
    print()


def banner(zh, en=None):
    """结果横幅：分隔线 + 标题 + 分隔线（**不清屏**，保留前面的结果）。"""
    print()
    hr()
    print(tr(zh, en or zh))
    hr()
    print()


#: `--ui-lang=` 的取值 → 界面语言。
_UI_LANG_CHOICES = {
    '1': 'zh', 'zh': 'zh', 'cn': 'zh', 'chinese': 'zh', 'zh-cn': 'zh',
    '2': 'en', 'en': 'en', 'english': 'en',
}


def _cli_ui_lang():
    """从命令行取 `--ui-lang=zh|en`（无则 `None`）。"""
    for arg in sys.argv[1:]:
        if arg.startswith('--ui-lang='):
            return _UI_LANG_CHOICES.get(arg.split('=', 1)[1].strip().lower())
    return None


def choose_ui_language():
    """启动**第一步**：选安装器界面语言。

    这是整个安装器里**唯一双语并排**的一屏 —— 此时还不知道玩家看哪种语言。
    选完（或 `--ui-lang=` 给定）之后，全部输出只使用它。
    默认值是**固定中文**（本补丁面向中文玩家；英文玩家按 2 或先给 `--ui-lang=en`）。
    """
    global UI_LANG
    forced = _cli_ui_lang()
    if forced:
        UI_LANG = forced
        return

    default = 'zh'

    clear()
    hr()
    print('《在这苍穹展翅 - 飞行日志 -》内容恢复补丁 %s' % CURRENT_VERSION)
    print('If My Heart Had Wings -Flight Diary- Content Restoration Patch')
    hr()
    print()
    print('  安装器语言 / Installer language')
    print()
    print('    1) 中文')
    print('    2) English')
    print()
    answer = input('  1/2 (Enter = %d): ' % (1 if default == 'zh' else 2)).strip().lower()
    UI_LANG = _UI_LANG_CHOICES.get(answer, default)
    print()


# ---------------------------------------------------------------------------
# 交付清单
# ---------------------------------------------------------------------------

def file_sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def entry_kind(info):
    return info.get('kind', 'merge')


def payload_path_for(payload_dir, key, info):
    """METADATA 键 → payload 内的补丁文件路径（与打包侧同一口径）。"""
    payload_dir = Path(payload_dir)
    if entry_kind(info) == 'merge':
        return payload_dir / (key[:-4] + '_patch.arc')
    return payload_dir / key


def entry_label(key, kind):
    """交付条目的显示名（未登记的键退回形态名）。"""
    names = LABELS.get(key.lower())
    if names:
        return tr(names[0], names[1])
    kind_names = KIND_LABELS.get(kind, (kind, kind))
    return tr(kind_names[0], kind_names[1])


# ---------------------------------------------------------------------------
# Steam 游戏目录检测
# ---------------------------------------------------------------------------

def parse_vdf(vdf_path):
    """
    解析 Steam libraryfolders.vdf 文件
    VDF 格式类似 JSON，使用递归下降解析

    Returns:
        list: [(library_path, {appid: size, ...}), ...]
    """
    try:
        with open(vdf_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception:
        return []

    def tokenize(text):
        tokens = []
        i = 0
        while i < len(text):
            if text[i].isspace():
                i += 1
                continue
            if text[i] == '"':
                i += 1
                start = i
                while i < len(text) and text[i] != '"':
                    if text[i] == '\\' and i + 1 < len(text):
                        i += 2
                    else:
                        i += 1
                tokens.append(('STRING', text[start:i]))
                i += 1
            elif text[i] == '{':
                tokens.append(('LBRACE', '{'))
                i += 1
            elif text[i] == '}':
                tokens.append(('RBRACE', '}'))
                i += 1
            elif text[i:i + 2] == '//':
                while i < len(text) and text[i] != '\n':
                    i += 1
            else:
                i += 1
        return tokens

    def parse_dict(tokens, pos):
        result = {}
        while pos < len(tokens):
            token_type, token_value = tokens[pos]

            if token_type == 'RBRACE':
                return result, pos + 1
            elif token_type == 'STRING':
                key = token_value
                pos += 1

                if pos >= len(tokens):
                    break

                next_type, next_value = tokens[pos]

                if next_type == 'LBRACE':
                    pos += 1
                    value, pos = parse_dict(tokens, pos)
                    result[key] = value
                elif next_type == 'STRING':
                    result[key] = next_value
                    pos += 1
                else:
                    pos += 1
            else:
                pos += 1

        return result, pos

    tokens = tokenize(content)
    data, _ = parse_dict(tokens, 0)

    libraries = []
    if 'libraryfolders' not in data:
        return []

    libraryfolders = data['libraryfolders']
    for key, value in libraryfolders.items():
        if not isinstance(value, dict):
            continue
        if 'path' not in value or 'apps' not in value:
            continue

        library_path = value['path'].replace('\\\\', '\\')
        apps = value['apps'] if isinstance(value['apps'], dict) else {}
        libraries.append((library_path, apps))

    return libraries


def _steam_roots():
    """Steam 安装根的候选列表：Windows 走注册表，Linux 走常见目录。"""
    roots = []
    if sys.platform == 'win32':
        try:
            import winreg

            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam")
            steam_path, _ = winreg.QueryValueEx(key, "SteamPath")
            winreg.CloseKey(key)
            roots.append(Path(steam_path))
        except Exception as e:
            say("读取 Steam 安装路径失败: %s（改为手动输入）" % e,
                "Failed to read the Steam install path: %s (will ask you instead)" % e)
    else:
        home = Path.home()
        for rel in ('.steam/steam', '.steam/root', '.local/share/Steam'):
            roots.append(home / rel)
    return roots


def find_steam_game_path():
    """自动检测 Steam 游戏路径（Windows 走注册表；Linux 扫常见 Steam 根目录）。

    游戏本体是 Windows 版，但 `steamapps/common/<游戏>` 在 Linux 上也是普通目录，
    因此路径检测与文件替换照常可用。

    Returns:
        Path or None: 游戏路径，如果找不到则返回 None
    """
    for steam_path in _steam_roots():
        libraryfolders_vdf = steam_path / 'steamapps' / 'libraryfolders.vdf'
        if not libraryfolders_vdf.exists():
            continue
        libraries = parse_vdf(libraryfolders_vdf)
        for library_path, apps in libraries:
            if TARGET_APPID not in apps:
                continue
            game_path = Path(library_path) / 'steamapps' / 'common' / GAME_FOLDER_NAME
            if (game_path / GAME_EXE).exists():
                return game_path
    return None


# ---------------------------------------------------------------------------
# 归档合并
# ---------------------------------------------------------------------------

def merge_arc(game_arc_path, patch_arc_path, output_path, metadata_path=None, asset_name=None):
    """
    合并游戏原有的 arc 文件和补丁 arc 文件（资源级替换，按元数据指定的顺序）

    Args:
        game_arc_path: 游戏原有的 arc 文件路径
        patch_arc_path: 补丁 arc 文件路径
        output_path: 输出文件路径
        metadata_path: 元数据文件路径（JSON，包含成员顺序和变化信息）
        asset_name: asset 文件名（如 'CHIP2.arc'，用于查找元数据中对应的条目）
    """
    # 玩家原档不存在（补丁新增的整档）按空表处理
    if Path(game_arc_path).exists():
        game_members = {nb.decode('utf-16le'): (nb, d)
                        for nb, d in arcbuild.read_raw(str(game_arc_path))}
    else:
        game_members = {}

    patch_members = {nb.decode('utf-16le'): (nb, d)
                     for nb, d in arcbuild.read_raw(str(patch_arc_path))}

    metadata = {}
    if metadata_path and Path(metadata_path).exists() and asset_name:
        try:
            with open(metadata_path, 'r', encoding='utf-8') as f:
                all_metadata = json.load(f)
            metadata = all_metadata.get(asset_name, {})
        except Exception as e:
            say("    警告：无法读取元数据 %s: %s" % (metadata_path, e),
                "    Warning: cannot read metadata %s: %s" % (metadata_path, e))

    merged = []
    target_members = metadata.get('members', [])
    deleted_count = sum(1 for m in target_members if isinstance(m, dict) and m.get('type') == 'deleted')

    if target_members:
        # 按元数据中的目标顺序重组
        # target_members 中的每个元素是 {"name": "...", "type": "keep|added|modified|deleted"}
        missing_members = []
        for member_info in target_members:
            if isinstance(member_info, dict):
                name = member_info.get('name')
                member_type = member_info.get('type', 'keep')
            else:
                # 兼容旧格式（直接是字符串）
                name = member_info
                member_type = 'keep'

            if not name:
                continue

            if member_type == 'deleted':
                # 已删除：不写入输出
                continue

            if member_type in ('added', 'modified'):
                # 新增或修改：优先用补丁版本，找不到则降级用原版
                if name in patch_members:
                    merged.append(patch_members[name])
                elif name in game_members:
                    merged.append(game_members[name])
                    missing_members.append((name, member_type, 'patch'))
                else:
                    missing_members.append((name, member_type, 'both'))
            else:  # 'keep'
                # 保持原版：优先用原版，找不到则用补丁版本
                if name in game_members:
                    merged.append(game_members[name])
                elif name in patch_members:
                    merged.append(patch_members[name])
                    missing_members.append((name, member_type, 'game'))
                else:
                    missing_members.append((name, member_type, 'both'))

        if missing_members:
            say("    警告：%d 个成员未能在预期位置找到" % len(missing_members),
                "    Warning: %d member(s) not found where expected" % len(missing_members))
            for name, mtype, missing_from in missing_members:
                say("      - %s (type=%s): %s 中不存在" % (name, mtype, missing_from),
                    "      - %s (type=%s): missing from %s" % (name, mtype, missing_from))
    else:
        # 降级方案：如果没有元数据，按游戏原顺序处理
        for name, (name_bytes, data) in game_members.items():
            if name in patch_members:
                merged.append(patch_members[name])
            else:
                merged.append((name_bytes, data))

        for name, (name_bytes, data) in patch_members.items():
            if name not in game_members:
                merged.append((name_bytes, data))

    arcbuild.write_arc(merged, str(output_path))

    return len(game_members), len(patch_members), deleted_count, len(merged)


# ---------------------------------------------------------------------------
# 阶段：选目录 / 确认 / 安装 / 校验
# ---------------------------------------------------------------------------

def select_game_directory():
    """
    选择游戏目录（阶段一）

    Returns:
        Path or None: 游戏路径
    """
    stage('选择游戏目录', 'Choose the game folder')

    say("正在检测游戏路径...", "Detecting the game folder ...")
    print()

    auto_path = find_steam_game_path()

    if auto_path:
        say("检测到游戏路径：", "Detected game folder:")
        print("  %s" % auto_path)
        print()
        if ask("使用此路径？(Y/n): ", "Use this path? (Y/n): ") not in ('n', 'no'):
            return auto_path
        print()
    else:
        say("未能自动检测到游戏路径", "Could not auto-detect the game folder")
        print()

    say("请输入游戏根目录路径（包含 %s 的目录）：" % GAME_EXE,
        "Please enter the game root directory path (the folder containing %s):" % GAME_EXE)
    print()
    say("提示：", "Hints:")
    say("  1. 直接输入路径，例如", "  1. Type the full path, e.g.")
    print(r"     E:\SteamLibrary\steamapps\common\IF MY HEART HAD WINGS FLIGHT DIARY")
    say("  2. 输入 '.' 使用安装器所在目录", "  2. Type '.' to use the installer's own folder")
    say("  3. 留空取消安装", "  3. Leave it empty to cancel")
    print()

    user_input = input(tr("路径: ", "Path: ")).strip()

    if not user_input:
        return None

    if user_input == '.':
        return Path.cwd()

    user_input = user_input.strip('"').strip("'")

    game_path = Path(user_input)

    if not game_path.exists():
        say("错误：路径不存在：%s" % game_path,
            "Error: path does not exist: %s" % game_path)
        return None

    if not (game_path / GAME_EXE).exists():
        say("错误：该目录下未找到 %s" % GAME_EXE,
            "Error: %s not found in this directory" % GAME_EXE)
        return None

    return game_path


def build_files_to_process(metadata, payload_dir, game_path):
    """METADATA → 待处理清单（name / game_path / patch_path / output_path / kind）。

    交付面由打包侧决定，不在此写死归档名单；loose 条目展开为逐文件。
    """
    files_to_process = []
    for key, info in metadata.items():
        kind = entry_kind(info)
        if kind == 'loose':
            for rel in sorted(info['files']):
                files_to_process.append({
                    "name": tr("%s (裸文件)" % rel, "%s (loose file)" % rel),
                    "kind": kind,
                    "asset_name": key,
                    "game_path": game_path / rel,
                    "patch_path": payload_dir / rel,
                    "output_path": game_path / rel,
                })
            continue
        files_to_process.append({
            "name": "%s (%s)" % (key, entry_label(key, kind)),
            "kind": kind,
            "asset_name": key,
            "game_path": game_path / key,
            "patch_path": payload_path_for(payload_dir, key, info),
            "output_path": game_path / key,
        })
    return files_to_process


def apply_entry(metadata_path, file_info, game_path):
    """安装一个交付条目：merge 走成员重组，其余整份复制。"""
    if file_info["kind"] == "merge":
        game_count, patch_count, deleted_count, merged_count = merge_arc(
            file_info["game_path"],
            file_info["patch_path"],
            file_info["output_path"],
            metadata_path,
            file_info["asset_name"]
        )
        say("  原文件成员: %s" % game_count, "  original members: %s" % game_count)
        say("  补丁成员: %s" % patch_count, "  patch members: %s" % patch_count)
        say("  删除成员: %s" % deleted_count, "  deleted: %s" % deleted_count)
        say("  合并后成员: %s" % merged_count, "  merged: %s" % merged_count)
        return

    file_info["output_path"].parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(file_info["patch_path"], file_info["output_path"])
    say("  已覆盖: %s" % file_info["output_path"].relative_to(game_path),
        "  written: %s" % file_info["output_path"].relative_to(game_path))


def verify_install(metadata, game_path):
    """逐文件哈希回读校验（merge/copy 用 checksum，loose 用 files 表）。"""
    all_verified = True
    for asset_name, asset_info in metadata.items():
        if entry_kind(asset_info) == 'loose':
            for rel, expected_hash in sorted(asset_info['files'].items()):
                installed_path = game_path / rel
                if not installed_path.exists():
                    say("  [FAIL] %s: 文件不存在" % rel,
                        "  [FAIL] %s: file not found" % rel)
                    all_verified = False
                    continue
                file_hash = file_sha256(installed_path)
                if file_hash == expected_hash:
                    print("  [OK] %s" % rel)
                else:
                    say("  [FAIL] %s: 哈希不匹配" % rel,
                        "  [FAIL] %s: checksum mismatch" % rel)
                    say("    预期: %s" % expected_hash, "    expected: %s" % expected_hash)
                    say("    实际: %s" % file_hash, "    actual:   %s" % file_hash)
                    all_verified = False
            continue

        expected_hash = asset_info.get('checksum')
        installed_path = game_path / asset_name

        if not installed_path.exists():
            say("  [FAIL] %s: 文件不存在" % asset_name,
                "  [FAIL] %s: file not found" % asset_name)
            all_verified = False
            continue

        file_hash = file_sha256(installed_path)
        if file_hash == expected_hash:
            print("  [OK] %s" % asset_name)
        else:
            say("  [FAIL] %s: 哈希不匹配" % asset_name,
                "  [FAIL] %s: checksum mismatch" % asset_name)
            say("    预期: %s" % expected_hash, "    expected: %s" % expected_hash)
            say("    实际: %s" % file_hash, "    actual:   %s" % file_hash)
            all_verified = False

    return all_verified


def install():
    """执行安装（阶段：选目录 → 确认要改的文件 → 安装中 → 校验 → 完成）"""

    game_path = select_game_directory()

    if not game_path:
        print()
        say("安装已取消", "Installation cancelled")
        return False

    if getattr(sys, 'frozen', False):
        base_dir = Path(sys._MEIPASS)
    else:
        base_dir = Path(__file__).parent.parent
    payload_dir = base_dir / "payload"

    stage('确认要修改的文件', 'Files that will be modified')
    say("游戏目录: %s" % game_path, "Game folder: %s" % game_path)
    print()

    if not payload_dir.exists():
        say("错误：找不到 payload 目录", "Error: payload directory not found")
        say("预期位置：%s" % payload_dir, "expected at: %s" % payload_dir)
        return False

    metadata_path = payload_dir / "METADATA.json"
    if not metadata_path.exists():
        say("错误：找不到元数据文件", "Error: METADATA.json not found")
        say("预期位置：%s" % metadata_path, "expected at: %s" % metadata_path)
        return False

    with open(metadata_path, 'r', encoding='utf-8') as f:
        metadata = json.load(f)

    files_to_process = build_files_to_process(metadata, payload_dir, game_path)

    say("检查补丁文件...", "Checking patch files ...")
    print()
    for file_info in files_to_process:
        if not file_info["patch_path"].exists():
            say("错误：缺失补丁文件 %s" % file_info['patch_path'],
                "Error: missing patch file %s" % file_info['patch_path'])
            return False

        # 资源级合并要在玩家原档上重组，原档必须在位；
        # 整档覆盖（Rio.arc / zh-CN/Rio.arc / Script.arc）与新增档不要求
        if file_info["kind"] == "merge" and not file_info["game_path"].exists():
            say("错误：游戏文件不存在 %s" % file_info['game_path'],
                "Error: game file not found %s" % file_info['game_path'])
            return False

    say("所有文件检查通过", "All files present")
    print()

    say("即将安装内容恢复补丁，这将修改以下文件：",
        "About to install the content restoration patch. The following files will be modified:")
    for file_info in files_to_process:
        say("  - %s" % file_info['name'], "  - %s" % file_info['name'])
    print()
    say("建议：安装前通过 Steam 校验游戏文件，以便需要时恢复",
        "Recommendation: verify the game files via Steam first, so you have a way back")
    print()

    if ask("确认安装？(Y/n): ", "Install now? (Y/n): ") in ('n', 'no'):
        print()
        say("安装已取消", "Installation cancelled")
        return False

    stage('安装中', 'Installing')

    try:
        for file_info in files_to_process:
            say("处理 %s ..." % file_info['name'], "Processing %s ..." % file_info['name'])
            apply_entry(metadata_path, file_info, game_path)
            say("%s 完成" % file_info['name'], "%s done" % file_info['name'])
            print()

        stage('校验安装文件', 'Verifying installed files')

        if not verify_install(metadata, game_path):
            banner('校验失败：部分文件不正确', 'Verification failed: some files are incorrect')
            say("请按以下步骤恢复后重新安装：",
                "Please follow these steps to recover, then reinstall:")
            print()
            say("  1. 打开 Steam，找到《If My Heart Had Wings -Flight Diary-》",
                "  1. Open Steam and find 'If My Heart Had Wings -Flight Diary-'")
            say("  2. 右键点击游戏 -> 属性 -> 已安装文件 -> 校验游戏文件完整性",
                "  2. Right-click the game -> Properties -> Installed Files -> Verify integrity")
            say("  3. 等待 Steam 完成校验与修复",
                "  3. Wait for Steam to finish verifying and repairing the files")
            say("  4. 重新运行本安装程序",
                "  4. Run this installer again")
            print()
            return False

        banner('安装完成', 'Installation completed')
        say("现在可以启动游戏体验还原内容。",
            "You can now launch the game to experience the restored content.")
        print()

        return True

    except Exception as e:
        banner('安装失败', 'Installation failed')
        say("  错误：%s" % e, "  Error: %s" % e)
        print()
        say("请通过 Steam 校验游戏文件完整性以恢复原始文件。",
            "Please verify the game files via Steam to restore the originals.")
        return False


if __name__ == "__main__":
    try:
        choose_ui_language()
        success = install()
        input(tr("\n按任意键退出...", "\nPress Enter to exit..."))
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print()
        say("安装已取消", "Installation cancelled")
        input(tr("\n按任意键退出...", "\nPress Enter to exit..."))
        sys.exit(1)
    except Exception as e:
        print()
        say("未预期的错误：%s" % e, "Unexpected error: %s" % e)
        import traceback
        traceback.print_exc()
        input(tr("\n按任意键退出...", "\nPress Enter to exit..."))
        sys.exit(1)
