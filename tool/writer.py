# -*- coding: utf-8 -*-
"""宿主脚本结构写盘器（本体线）。

把判读台账的处置落到 Steam 宿主脚本字节上：

- **删格**：删被删行的正文指令 `14` ＋**该行的演出前缀区**（上一条 `14` 之后 → 本行 `14`
  之前）内除 `KEEP_OPS` 外的全部指令（语音/显示/BGM/图层/特效——纯表现，删之无副作用）
  ＋它自带的名字框指令 `15`（带「不改动任何存活格名字框」守卫，移植 CC 算法）。
  **状态写入（`09`/`0b`）、跳转（`01`/`02`/`06`/`07`）、菜单（`0f`）、成就（`f0` 与
  非 `LAYER_ORDER` 的 `04` 调用）一律逐字节保留**——删演出残留的原因见
  `doc/lessons-learned.md` §16（残留排在插入的原版块之后执行 ⇒ 把画面/BGM 顶回
  Steam 素材、并造成无对白连播语音）。
- **插入原版块**：台账行区间 → 原版指令 span（行 = 原 `14`，已实证 1:1）→ 逐条过
  `tool.ws2conv.CONV` 格式差 → 块内跳转立即重定基；跨块目标由计划器的
  `external` 表（orig off → steam 槽位）解析到宿主 `14` 的新偏移。
- **池序号全量重算**：`14.id` 与 `0f` 各条目 strid 同一「文件出现序」编号空间。
- **跳转回写**：`01.a/b`、`02`、`06`、`0f` 体内 `06` —— 单遍发出 + 末端按完整
  偏移映射统一回写（前向/后向目标都覆盖）。
- **恢复现场**：插入块之后，若紧随的 Steam 指令不是 `15`，重发进入时的名字框
  （靠继承取名的存活格会张冠李戴，移植 CC 教训）。

产出 `slot_sources`：最终槽位序 → `('steam', old_idx)` / `('orig', row)`，
供 zh-CN 覆盖层按槽现做 `.lng`（保留格直取官方条目、插入格取民汉）。

A-1 整脚本不走本模块（整脚本走 `tool.ws2conv.convert_script`，槽位与
`resource/fan_cn` 1:1）。0f 不得出现在插入块内（实证：全部 orig 源零 0f）。
"""
import struct

from tool import ws2, ws2dis, perfsync
from tool.ws2conv import CONV, REBASE_OPS, parse as conv_parse

BLOCK_STOP = {0x01, 0x02, 0x06, 0x07, 0xFF}   # 原版块在其前截断（其后属宿主结尾）

# 「操作数**尾部** 4 字节 = 解码流内绝对偏移」的补充规则（格式表查不出来的菜单项）。
# 本作实测：`0x0f`（菜单，count 条）的条目是 `0x5e`/`0x5f` 指令；`0x5e` 的操作数
# = `<strid+文本 cstr>` + f32 + f32，其中**最后 4 字节**实为条目分支目标（u32 绝对偏移）。
# 全语料只有 ORIG `BEF_004.ws2` 用到一处（Steam 侧已把该选项删掉）。
TAIL4_REBASE = {0x5e}

# 被删行「演出前缀区」内**保留**的操作码：状态写入（`09` 变量/图层权重、`0b` 布尔）、
# 流程控制（`01`/`02`/`06`/`07`）、菜单（`0f`）、成就（`f0`）、名字框（`15`）、终结符。
# 其余（语音 `2e`+`28`、显示 `33`/`34`、BGM `1e`、图层定位 `46`、特效…）都是**纯表现**，
# 随该行一起删——否则它们排在插入的原版块之后执行，会把画面/BGM 顶回 Steam 素材，
# 并造成「相邻两条语音触发之间没有 14」的无对白连播（见 doc/lessons-learned.md §16）。
KEEP_OPS = {0x01, 0x02, 0x05, 0x06, 0x07, 0x09, 0x0B, 0x0E, 0x0F, 0x15, 0xF0, 0xFF}

# ── 选项头（`0e 0b 00 <count> 00 01`）──
# 证据（`[语料]`，见 tmp/choice_header_spec.txt）：同代且选项实机可用的**本篇** Steam 版
# 6 个含选项的脚本里，每个 `0f` 之前都有这条头（`CO1_020` = `0e 0b 00 04 00 01` +
# `0f 04`；`HUT_005` = `0e 0b 00 02 00 01` + `0f 02`）；另有 4 个脚本是「无 `0f` 文本表」
# 的条件式变体。本作 Steam 侧没有任何选项、原版（更早一代）也不用这条头，所以
# **产物必须自己发这条头**，否则引擎不知道「进入选项态、共几条」。
# `count` 必须等于随后 `0f` 的 count（闸见 script/checks/choice_header_check.py）。
CHOICE_HDR_LEN = 6


def choice_hdr(count):
    """选项头字节：`0e 0b 00 <count> 00 01`。"""
    return bytes([0x0E, 0x0B, 0x00, count & 0xFF, 0x00, 0x01])


def _ends_with_15_frame(out):
    """流末尾是否已经是一条 `0x15`（名字帧）——用于避免重复合成。"""
    return len(out) >= 3 and out[-2] == 0x00 and out[-3] == 0x15


def _ends_with_choice_hdr(out):
    """已发出的流末尾是否已是一条选项头（幂等：不重复发）。"""
    return (len(out) >= CHOICE_HDR_LEN and out[-CHOICE_HDR_LEN] == 0x0E
            and out[-CHOICE_HDR_LEN + 1] == 0x0B)

# ── 演出同步 `replace` 的整段替换口径（见 doc/restoration-route.md §5.1）──
# `replace` 的判据是**该槽的整段演出 = 原版行 r 的整段演出**：创作者把「复位 → 显示 →
# 拖拽/特效 → 渐变 → 计时」的**顺序**写在脚本里，只换显示块会让宿主残留的拖拽/特效
# 作用在已被删掉的通道上（实机表现为动画错乱）。因此：
#   * 原版侧按**演出集**整段搬（保序）：下面这组口径之外的（流程控制 / 名字框 / 成就
#     调用）不搬，避免把原版脚本骨架带进宿主；
#   * 宿主侧只保留**非演出**指令（状态写入、流程、成就、名字框、引擎调用）。
_PERF_TAKE_STEAM_ONLY = {0x05, 0x07, 0x0F, 0x15, 0x1C, 0xF0, 0xFF}   # 宿主逐字节保留
_PERF_FLOW = {0x01, 0x02, 0x06}          # 目标全在本槽前缀区内 ⇒ 属演出分支，随演出删
_PERF_TAKE_ORIG_SKIP = {0x01, 0x02, 0x06, 0x07, 0x0F, 0x15, 0xF0, 0xFF}  # 原版侧不搬

# ── 演出同步（见 doc/restoration-route.md §7 V-10）──
# 显示块 = 显示指令（`33`/`34`）＋ 其图层伴生：`39`（建层）、`04 LAYER_ORDER` 调用、
# `09`（图层权重）、`46`（图层定位）、`3e`/`65`（块尾标记/转场），前置 `64`。这是一段
# **连续**指令（`0b` 状态写入夹在块内时算块的一段，但删块时保留、补块时不重复写）。
_PERF_BLOCK = perfsync.BLOCK_OPS
_PERF_PRESERVE = perfsync.BLOCK_MOVE_SKIP
_is_layer_order = perfsync._is_layer_order


def _perf_zone(instrs, idx, s14off, slot):
    """槽 `slot` 的演出前缀区 → (zone_lo, j_cur) 指令下标区间。"""
    if slot >= len(s14off):
        return None
    j_cur = idx[s14off[slot]]
    j = j_cur - 1
    while j >= 0 and instrs[j][1] != 0x14:
        j -= 1
    return j + 1, j_cur


def _perf_block_kill(instrs, j_cur, zone_lo, chans):
    """`drop` 模式：某槽演出前缀区内、`chans` 各通道的显示块 → 要删的指令偏移集。

    只删**显示块**（显示指令 + 其图层伴生 + 前置 `64`）；清屏（`37`）不动——`drop`
    的语义是「这层多余，别画」，不影响别的通道（`replace` 走整段替换，见
    `_perf_replace_zone` / `_perf_zone_kill`）。
    """
    kill, hit = set(), set()

    def _match(chan, name):
        return bool(chan) and chan in chans

    for j in range(zone_lo, j_cur):
        op, ops = instrs[j][1], instrs[j][3]
        if op not in (0x33, 0x34):
            continue
        chan, name = _chan_name(ops)
        if not _match(chan, name):
            continue
        hit.add(chan)
        s = j
        while s - 1 >= zone_lo and instrs[s - 1][1] == 0x64:
            s -= 1
        e = j + 1
        while e < j_cur:
            o2, x2 = instrs[e][1], instrs[e][3]
            if o2 in _PERF_BLOCK or _is_layer_order(o2, x2):
                e += 1
                continue
            break
        for k in range(s, e):
            o3 = instrs[k][1]
            if o3 in _PERF_PRESERVE:
                continue
            kill.add(instrs[k][0])
    return kill, hit


def _chan_name(ops):
    """显示指令操作数 → (通道名, 图名)。"""
    parts = ops.split(b'\x00')
    out = []
    for p0 in parts[:2]:
        if not p0:
            out.append(None)
            continue
        try:
            out.append(p0.decode('cp932'))
        except UnicodeDecodeError:
            out.append(None)
    return (out + [None, None])[:2]


def _chan_of(ops):
    """显示/清屏指令操作数的首个 NUL 定界串（通道名）。"""
    parts = ops.split(b'\x00')
    if not parts or not parts[0]:
        return None
    try:
        return parts[0].decode('cp932')
    except UnicodeDecodeError:
        return None


def _perf_clear_kill(instrs, j_cur, zone_lo, chans):
    """某槽演出前缀区内、`chans` 各通道的**清屏**指令 → 要删的偏移集（`keep` 模式）。

    只删**精确通道名**的清屏（族级 `clear bg`/`clear st` 会波及其它通道，不动）。
    返回 (kill_offsets, hit_chans)。
    """
    kill, hit = set(), set()
    for j in range(zone_lo, j_cur):
        op, ops = instrs[j][1], instrs[j][3]
        if op != 0x37:
            continue
        chan = _chan_of(ops)
        if chan in chans:
            hit.add(chan)
            kill.add(instrs[j][0])
    return kill, hit


def _perf_order_guard(instrs, zone, killed, anchor, added, slot):
    """补块之后不得再有一条**存活清屏**动到补块刚画上的通道（黑背景/黑立绘的直接成因）。

    `replace` 把所有图像显示块都删了，补块又是唯一的重画来源 ⇒ 只要补块之后还有一条
    存活清屏命中补块设过的通道，那张图必定被抹掉（生产端漏删清屏，或落点排到了清屏
    之前）。这条断言把「实机才发现」的问题前移到构建期（见 doc/lessons-learned.md §43）。
    """
    # 补块**净效果**：按原顺序过一遍显示与清屏，只有「画上去且没被自己清掉」的通道
    # 才算会被后面的清屏误伤（原版行自己 画→清 的成对操作不算）
    state = {}
    for op, ops in added:
        if op in (0x33, 0x34):
            chan = _chan_name(ops)[0]
            if chan:
                state[chan] = True
        elif op == 0x37:
            chan = _chan_of(ops)
            if chan:
                perfsync.pop_clear(state, chan)
    chans = set(state)
    if not chans:
        return
    a_idx = next((j for j in range(zone[0], zone[1]) if instrs[j][0] == anchor), zone[1])
    for j in range(a_idx, zone[1]):
        off, op, _size, ops = instrs[j]
        if op != 0x37 or off in killed:
            continue
        chan = _chan_of(ops)
        if perfsync.clear_hits(chan, state):
            raise AssertionError(
                '槽 %d 的演出同步补块被后续清屏抹掉：清屏 %r @0x%x 排在补块（落点 0x%x，'
                '重画 %s）之后' % (slot, chan, off, anchor, sorted(chans)))


def _flow_inside(ops, op, lo_off, hi_off):
    """`01`/`02`/`06` 的跳转目标是否**全部落在 [lo_off, hi_off) 内**。

    全在区内 ⇒ 这是「演出内的分支」（典型形态：`1c getLanguageParam` 选 `_EN`/`_SC`
    版本的 CG 贴图），属本槽演出，随演出一起删；只要有一个目标在区外，它就是**真流程**
    （存档续玩分支、场景中段跳转），必须逐字节保留。
    """
    for k in REBASE_OPS.get(op, ()):
        if len(ops) >= k + 4:
            v = struct.unpack_from('<I', ops, k)[0]
            if v and not (lo_off <= v < hi_off):
                return False
    return True


def _perf_replace_zone(oinstrs, o14, r):
    """原版行 r 的**整段演出**（保序，见文件头「整段替换口径」）。

    只搬演出与音频；流程控制（`01`/`02`/`06`/`07`/`0f`/`ff`）、名字框（`15`，宿主的
    与之等价且与外层 lng 槽绑定）、非 `LAYER_ORDER` 的引擎调用都不搬。
    """
    i0 = o14[r - 1] + 1 if r > 0 else 0
    i1 = o14[r]
    out = []
    for j in range(i0, i1):
        op, ops = oinstrs[j]
        if op in _PERF_TAKE_ORIG_SKIP:
            continue
        if op == 0x04 and ops.split(b'\x00')[0] != b'LAYER_ORDER':
            continue
        out.append((op, ops))
    return out


def perf_is_presentation(op, ops, lo_off=0, hi_off=0):
    """这条指令是不是**演出**（`replace` 要整段换掉的那一类）。

    判据按「它改的是画面/声音，还是脚本状态」：
      演出 = 显示/清屏/立绘/拖拽/特效/渐变/计时/图层权重/音频/图层命令块；
      非演出 = 状态写入 `0b`／流程 `07`/`0f`/`ff`＋**目标在区外**的 `01`/`02`/`06`／
               成就与引擎调用（非 `LAYER_ORDER` 的 `04`）／名字框 `15`／`05`／`f0`。
    目标**全在区内**的 `01`/`02`/`06` 是「演出内的分支」（Steam 用它选 `_EN`/`_SC`
    版 CG），归演出。`lo_off`/`hi_off` 是该槽前缀区的偏移范围（判区内/区外用）。

    WARNING 产出端（`_perf_zone_kill` / `_perf_replace_zone`）与闸
    （`script/checks/perf_sync_check.py` 的顺序闸）**共用这一个判据**，不得各写一套。
    """
    if op in _PERF_TAKE_STEAM_ONLY or op == 0x0B:
        return False
    if op == 0x04 and ops.split(b'\x00')[0] != b'LAYER_ORDER':
        return False
    if op in _PERF_FLOW and not _flow_inside(ops, op, lo_off, hi_off):
        return False
    return True


def _perf_zone_kill(instrs, zone, lo_off, hi_off):
    """`replace` 的宿主侧删除集：整段演出都算本槽演出，只留**非演出**（判据见
    `perf_is_presentation`）。"""
    return {instrs[j][0] for j in range(zone[0], zone[1])
            if perf_is_presentation(instrs[j][1], instrs[j][3], lo_off, hi_off)}


def perf_sig(op, ops):
    """站点比较用的可比值：`0x39` 的帧号跨版本由 `pna_id_map` 换算，只比通道串。"""
    if op == 0x39:
        return (op, ops.split(bytes((0,)))[0])
    return (op, ops)


def perf_zone_sig(instrs, zone):
    """宿主某槽前缀区 → 演出序列（逐条逐序；跳过骨架与 `0b`）。"""
    if zone is None:
        return None
    lo_off, hi_off = instrs[zone[0]][0], instrs[zone[1]][0]
    return [perf_sig(op, ops) for _off, op, _size, ops in instrs[zone[0]:zone[1]]
            if op != 0x0B and perf_is_presentation(op, ops, lo_off, hi_off)]


def perf_expected_sig(oinstrs, o14, r):
    """原版行 r → 演出序列（与 `_perf_replace_zone` 落盘内容同口径）。"""
    return [perf_sig(op, _conv(op, ops, None))
            for op, ops in _perf_replace_zone(oinstrs, o14, r) if op != 0x0B]


def _perf_add_anchor(instrs, zone, killed, s14off, slot):
    """`replace` 的整段补块应落在宿主流里的哪条指令**之前**（返回该指令的绝对偏移）。

    落点＝**该槽前缀区里第一条被删掉的指令**（宿主原来开始放演出的位置）：宿主的非演出
    指令（`f0`／`15` 等）若排在它前面，仍按原顺序先执行——这就是「先复位后画」不被颠倒
    的保证（`37 *` 通配清屏若被排到补块之后，会把刚补上的画面清掉 ⇒ 黑背景，见
    doc/lessons-learned.md §43）。前缀区内一条都没删（全是非演出指令）时落在前缀区开头。
    """
    zlo, zcur = zone
    for j in range(zlo, zcur):
        if instrs[j][0] in killed:
            return instrs[j][0]
    return instrs[zlo][0] if zlo < zcur else s14off[slot]


def perf_sync_apply(instrs, s14off, oinstrs, o14, perf_sync, noop=()):
    """演出同步 → (kill_offsets, add_blocks, report)。

    `perf_sync = {steam 槽位: spec}`，`spec` 三种：

    * `{'mode': 'drop', 'channels': [通道]}`：删该槽前缀区内这些通道的显示块；
    * `{'mode': 'keep', 'channels': [通道]}`：**只删**这些通道的清屏，保留在屏延续；
    * `{'mode': 'replace', 'orig_row': r}`：该槽**整段演出 = 原版行 r 的整段演出**——
      宿主前缀区内的演出指令（显示 / 清屏 / 拖拽 / 特效 / 渐变 / 计时 / 音频 / 图层权重）
      全部作废，改按**原版顺序**整段搬入原版行 r 的演出（`_perf_replace_zone`）；宿主侧
      只保留非演出指令（`_perf_zone_kill`：状态写入 / 流程 / 成就与引擎调用 / 名字框）；
    * `keep` 可与任一 mode 正交（`spec['keep'] = [通道]`）。

    `add_blocks = {槽位: (落点偏移, [(op, ops), ...])}`：原版格式的补块 + 它在宿主流里
    应占的位置（落点规则见 `_perf_add_anchor`；调用方经 `_conv` 转换后按位发出）。
    """
    if not perf_sync:
        return set(), {}, {}
    idx = {ins[0]: j for j, ins in enumerate(instrs)}
    noop = {int(x) for x in (noop or ())}
    kill, add_blocks, report = set(), {}, {}
    for slot, spec in sorted(perf_sync.items()):
        slot = int(slot)
        if not isinstance(spec, dict):
            spec = {'mode': 'drop', 'channels': list(spec)}
        zone = _perf_zone(instrs, idx, s14off, slot)
        mode = spec.get('mode', 'drop')
        if slot in noop:
            # 前置检验判定「本来就对」⇒ 不删不补，字节保持宿主原样（见 perfsync.site_noop）
            report[slot] = {'mode': 'noop', 'killed': 0, 'hit': [], 'missed': [],
                            'added': 0, 'kept': [], 'kept_missed': [], 'actions': 0}
            continue
        chans = None if mode == 'replace' else set(spec.get('channels') or ())
        keep_chans = set(spec.get('keep') or ())
        if zone is None:
            report[slot] = {'killed': 0, 'hit': [], 'missed': sorted(chans or ()),
                            'added': 0, 'actions': 1 + len(keep_chans)}
            continue
        k3, hit3 = (_perf_clear_kill(instrs, zone[1], zone[0], keep_chans)
                    if keep_chans else (set(), set()))
        kill |= k3
        if mode == 'keep':
            report[slot] = {'killed': len(k3), 'hit': sorted(hit3),
                            'missed': sorted(keep_chans - hit3), 'added': 0,
                            'actions': len(keep_chans)}
            continue
        if mode == 'replace':
            # 整段替换：宿主侧该槽的演出全删（只留非演出），原版侧整段搬入并保序
            added = _perf_replace_zone(oinstrs, o14, spec['orig_row'])
            k = _perf_zone_kill(instrs, zone, instrs[zone[0]][0], instrs[zone[1]][0])
            hit = set()
        else:
            added = []
            k, hit = _perf_block_kill(instrs, zone[1], zone[0], chans)
        kill |= k
        if added:
            anchor = _perf_add_anchor(instrs, zone, k, s14off, slot)
            _perf_order_guard(instrs, zone, k, anchor, added, slot)
            add_blocks[slot] = (anchor, added)
        report[slot] = {'killed': len(k), 'hit': sorted(hit),
                        'missed': sorted((chans or set()) - hit), 'added': len(added),
                        'kept': sorted(hit3), 'kept_missed': sorted(keep_chans - hit3),
                        'actions': 1 + len(keep_chans)}
    return kill, add_blocks, report


def _keep_in_perf_zone(op, ops):
    """演出前缀区内的指令是否保留（保留 = 状态/流程/成就；`04` 只保留非 LAYER_ORDER 调用）。"""
    if op in KEEP_OPS:
        return True
    if op == 0x04:
        return ops.split(b'\x00')[0] != b'LAYER_ORDER'
    return False


def _pfx(ops):
    """`15` 操作数 → 名字框前缀字节（布局 = prefix_cstr + 1 字节 0x00）。"""
    return ops[:-2]


def _mk15(prefix):
    return b'\x15' + prefix + b'\x00\x00'


def eff_names(instrs, skip=frozenset()):
    """每个 `14` 槽位的生效名字框（其上最近一条未跳过 `15` 的前缀；0f 条目继承）。"""
    out, cur = [], None
    for off, op, size, ops in instrs:
        if off in skip:
            continue
        if op == 0x15:
            cur = _pfx(ops)
        elif op == 0x14:
            out.append(cur)
        elif op == 0x0F:
            out.extend([cur] * ops[1])
    return out


def drop_units(instrs, drop_slots):
    """删格偏移集。

    三项内容：
      1. 被删槽的正文指令 `14`；
      2. 该槽**演出前缀区**（上一条 `14` 之后 → 本槽 `14` 之前）内**除 KEEP_OPS 外**的
         全部指令——即该行自己的语音/显示/BGM/图层/特效，删之无状态与流程副作用；
      3. 邻接 `15`（守卫：试删后任何存活格生效名字框不得改变）。
    """
    slot_of = {}
    k = 0
    for off, op, size, ops in instrs:
        if op == 0x14:
            slot_of[off] = k
            k += 1
    kill = {off for off, op, size, ops in instrs
            if op == 0x14 and slot_of.get(off) in drop_slots}
    # 演出前缀区：从被删 `14` 往前扫到上一条 `14`（不含），删掉其中的非 KEEP_OPS 指令
    idx = {ins[0]: j for j, ins in enumerate(instrs)}
    for o in sorted(kill):
        i = idx[o] - 1
        while i >= 0 and instrs[i][1] != 0x14:
            if not _keep_in_perf_zone(instrs[i][1], instrs[i][3]):
                kill.add(instrs[i][0])
            i -= 1
    # 邻接 15（守卫：试删后任何存活格生效名字框不得改变）
    cand = set()
    for o in sorted(kill):
        j = idx[o]
        if instrs[j][1] != 0x14:
            continue
        for d in (j - 1, j + 1):
            if 0 <= d < len(instrs) and instrs[d][1] == 0x15:
                cand.add(instrs[d][0])
    if not cand:
        return kill
    base = eff_names(instrs, kill)
    keep = {o for o in cand if eff_names(instrs, kill | {o}) != base}
    return kill | (cand - keep)


def norm_op46_flag(ops):
    """`0x46` 子层槽绑定标志的跨引擎归一：原版工具链 `0x80` → Steam 工具链 `0xf0`。

    `0x46` 第一条（把 PNA 子层绑到引擎层槽，操作数含 4 个层槽 id 浮点）带 1 字节标志，
    原版工具链写 `0x80`、Steam 工具链写 `0xf0`（两侧全库 ~7.6k 处零交叉；`0x00`＝纯
    坐标定位，两侧一致）。原版块带着 `0x80` 进 Steam 引擎会欠绑定子层槽——未重绑的槽
    保留上一次显示的子图 ⇒ 上一处的立绘残留在屏、压在后续 CG 上，直到清槽指令
    （实机定案见 doc/lessons-learned.md「0x46 子层槽标志」条目）。幂等；产出端
    （`build_patch.prep_orig`，供整脚本转换路径）与本函数（`_conv`，供移植/期望序列）
    共用，两侧必须一致。
    """
    i = ops.find(b'\x00')
    if 0 <= i and len(ops) > i + 3 and ops[i + 3] == 0x80:
        return ops[:i + 3] + b'\xf0' + ops[i + 4:]
    return ops


def _conv(op, ops, names=None):
    rule = CONV.get(op)
    if rule is None:
        ops2 = ops
    else:
        kind, tail = rule
        if kind == 'mid1':
            assert len(ops) >= tail
            ops2 = ops[:-tail] + b'\x00' + ops[-tail:]
        elif kind == 'end1':
            ops2 = ops + b'\x00'
        else:
            ops2 = ops + b'\x00\x00\x00\x00'
    if op == 0x46:
        ops2 = norm_op46_flag(ops2)
    if names:
        ops2 = apply_names(ops2, names)
    return ops2


def apply_names(dec, names):
    """在解码流内做资源名替换（NUL 定界精确匹配）。

    names = {旧名bytes(任意大小写): 新名bytes}——改名资源的脚本引用同步。
    **允许长度变化**（本作 `%LC` 名 / 脚本跳转目标改名会变长：日文名 → 罗马字键）。
    ⚠️ 调用方须保证：携带「解码流内绝对偏移」的操作码（`REBASE_OPS`）的操作数内
    不含被替换串——否则字段偏移会移位。本作 `0x01`/`0x02`/`0x06` 均无字符串字段。
    """
    for old, new in names.items():
        dec = dec.replace(b'\x00' + old + b'\x00', b'\x00' + new + b'\x00')
        dec = dec.replace(b'\x00' + old.upper() + b'\x00', b'\x00' + new + b'\x00')
        dec = dec.replace(b'\x00' + old.lower() + b'\x00', b'\x00' + new + b'\x00')
    return dec


def rewrite_lc_name(ops, key):
    """`0x15` 操作数里的 `%LC<名>` 换成 `%LC<key>`（窄字节 cp932，允许变长）。

    `0x15` 格式 = `[6,8]`（Steam `[6,8,0]`）⇒ 操作数 = `<cstr 含 NUL>` + 占位字节。
    仅改第一个 NUL 定界串，其后字节原样保留。
    """
    q = ops.find(b'\x00')
    if q < 0 or not ops.startswith(b'%LC'):
        return ops
    return b'%LC' + key.encode('cp932') + ops[q:]


def rename_07(instr_bytes, mapping):
    """`0x07` NextFile 指令字节 → 目标名按 `mapping` 改名（变长安全）。

    `0x07` 格式 = `[10,8]` ⇒ 指令字节 = `07 <cstr 含 NUL>`。目标名不在 `mapping` 里时原样返回。
    """
    q = instr_bytes.find(b'\x00', 1)
    if q < 0:
        return instr_bytes
    try:
        s = instr_bytes[1:q].decode('ascii')
    except UnicodeDecodeError:
        return instr_bytes
    if s in mapping:
        return bytes([instr_bytes[0]]) + mapping[s].encode('ascii') + instr_bytes[q:]
    return instr_bytes


def rebuild_host(steam_dec, orig_dec, plan, orig_fmts):
    """重建宿主脚本。

    plan = {
      'drops':   [steam 槽位(14 序)]                       # 删该行的文本与名字框指令
      'inserts': [(after_slot, r0, r1)],                  # 原版行闭区间；after_slot=-1 脚本头
      'external': {orig_off: steam_slot},                 # 跨块跳转解析（缺省空）
      'perf_sync': {steam 槽位: {'mode','orig_row'|'channels'}},   # 演出同步（删/换显示块）
      'restore_frame': True,                              # 插入后恢复名字框（缺省开）
      'skip_orig': [原版指令序号…],                        # 不搬入宿主的原版指令（回想出口三连等）
      'orig_choices': {0x0f 的原版偏移: [条目 strid…]},      # 选项条目占文本槽位（lng 等式）
    }
    返回 {'raw', 'slot_sources', 'ok', 'n14', 'n_slots', 'pool', 'fixups', 'fix_bad',
          'perf_kill'}。
    """
    ext = plan.get('external', {})
    restore_frame = plan.get('restore_frame', True)
    perf_sync = plan.get('perf_sync') or {}
    perf_noop = sorted({int(x) for x in (plan.get('perf_sync_noop') or ())})
    # 动画离场→CG 转换点的显式清屏兜底（人工定案入库，见 resource/anim_exit_clears.json）：
    # 搬入块的 09/45/47/48/57 动画组在 Steam 引擎上的终点与原版不一致（实测 AFT_007_3
    # 槽 226 的离场动画把 st02 移到屏内 (178,297) 而非退场 ⇒ 小鳥压在后续 CG 上）。
    # 凡「动画后紧接 CG 显示、且 CG 块不显式清该通道」的点，在**该原版行的第一条
    # 33/34 显示指令前**补 `37 <通道>`（与第三方补丁同型解法：动画照放，视觉由清屏保证）。
    anim_exit_clears = {int(k): list(v) for k, v in (plan.get('anim_exit_clears') or {}).items()}
    anim_clear_log = []

    def _pending_clears(row, seen):
        """该行的清屏通道（每行只发一次）。"""
        if row in anim_exit_clears and row not in seen:
            seen.add(row)
            return anim_exit_clears[row]
        return []
    skip_o = {int(x) for x in (plan.get('skip_orig') or ())}
    names = {k.encode('ascii'): v.encode('ascii') for k, v in plan.get('names', {}).items()}

    sinstrs, ok = ws2dis.disassemble(steam_dec)
    assert ok, 'host steam-table parse not self-consistent: %s' % plan.get('script', '?')
    if plan.get('orig_instrs') is not None:
        # 调用方已把原版指令表**预处理**过（`%LC` 名改键 / `0x07` 目标改名 / 成就注入），
        # 直接用它，避免二次解析把插入的指令丢掉。
        oinstrs, otail = plan['orig_instrs']
    else:
        oinstrs, otail = conv_parse(orig_dec, orig_fmts)
    if plan.get('orig_offs') is not None:
        # 插过指令后累计偏移不再等于原始解码流偏移 ⇒ 由调用方提供每条的原始偏移
        # （插入指令给唯一负哨兵值，永不与真实目标碰撞）。
        ooff = list(plan['orig_offs'])
        assert len(ooff) == len(oinstrs), 'orig_offs 长度 %d != 指令数 %d' % (len(ooff), len(oinstrs))
    else:
        ooff, p = [], 0
        for op, ops in oinstrs:
            ooff.append(p)
            p += 1 + len(ops)
    o14 = [j for j, (op, ops) in enumerate(oinstrs) if op == 0x14]   # 行 r ↔ o14[r]
    for j in sorted(skip_o):
        assert 0 <= j < len(oinstrs), 'skip_orig 越界: %r' % (j,)
        assert oinstrs[j][0] != 0x14, \
            'skip_orig 不得删台词格（槽位口径会错位）: %r' % (j,)
    jump_rename = dict(plan.get('jump_rename') or {})

    s14off = [off for off, op, size, ops in sinstrs if op == 0x14]
    # 演出同步（见 doc/restoration-route.md §7 V-10）：与删格同形——删该槽前缀区内
    # 的**显示块**（`drop` 模式删指定通道、`replace` 模式删全部图像通道再补原版行的），
    # 不碰状态写入与流程控制。`replace` 的补块在**前缀区开头**发出（排在语音/名字框之前，
    # 与 doc/file-formats.md「格内指令的归属次序」一致），资源名照抄原版（依赖 copy 补素材）。
    perf_kill, perf_add, perf_report = perf_sync_apply(sinstrs, s14off, oinstrs, o14, perf_sync,
                                                      noop=perf_noop)
    perf_missed = {k: v['missed'] for k, v in perf_report.items() if v['missed']}
    assert not perf_missed, \
        'perf_sync 通道在槽前缀区内找不到显示指令: %s' % perf_missed
    kill = drop_units(sinstrs, set(plan['drops'])) | perf_kill

    # 宿主结尾起点：最后一个保留 14 之后的第一条流程控制指令
    kept_slots = [s for s in range(len(s14off)) if s not in plan['drops']]
    tail_end_off = None
    if kept_slots:
        koff = s14off[kept_slots[-1]]
        for off2, op2, size2, ops2 in sinstrs:
            if off2 > koff and op2 in (0x01, 0x02, 0x06, 0x07, 0xFF):
                tail_end_off = off2
                break
    by_anchor = {}
    for a, r0, r1 in plan['inserts']:
        assert a == -1 or 0 <= a < len(s14off), '插入锚非法: %r' % (a,)
        assert a == -1 or a not in plan['drops'], '插入锚落在被删格: %d' % a
        by_anchor.setdefault(a, []).append((r0, r1))
    for a, ranges in by_anchor.items():
        if a >= 0:
            ranges.sort()
            assert all(r1 < r2 for (_, r1), (r2, _) in zip(ranges, ranges[1:])), \
                '锚 %d 的插入区间须按原版行序排列' % a
    ins_rows = set()
    for _a, r0, r1 in plan['inserts']:
        ins_rows.update(range(r0, r1 + 1))
    del ins_rows   # 保留计算仅为可读性；块跨度已不再依赖它（见 block_span 注释）

    def block_span(r0, r1):
        """块 = 行 r0..r1 各自的**演出前缀 ＋ 正文**。

        右端收到 r1 的 `14` **之后**即止（`o14[r1]+1`），**不再携带 r1+1 的演出前缀**：
        那一段在宿主侧由对应槽自带、或由承载 r1+1 的那一块自带，本块再带一遍就会让
        同一语音/显示触发连发两次（产物出现「同格重复语音」，见 doc/lessons-learned.md §16）。
        """
        i0 = o14[r0 - 1] + 1 if r0 > 0 else 0
        i1 = o14[r1] + 1
        n14 = sum(1 for j in range(i0, i1) if oinstrs[j][0] == 0x14)
        assert n14 == r1 - r0 + 1, '块 14 数 %d != 行数 %d（r%d-%d）' % (n14, r1 - r0 + 1, r0, r1)
        # `0x0f`（选项菜单）**允许**出现在块内：本作 ORIG `BEF_004` 的 H 场景有一处
        # 二选一（Steam 已删），还原后必须保留；其条目内嵌的 `0x5e` 尾部目标与随后的
        # `0x06` 都由重定基处理（见 TAIL4_REBASE / REBASE_OPS）。
        return i0, i1

    out = bytearray()
    remap_s, remap_o = {}, {}
    block_start = {}                # 插入锚 -> 该块在 out 内的起点（跨块回落的落点）
    slot_sources = []
    fixes = []                      # (out 内绝对写位, 's'|'o'|'x', key)
    pool = 0
    si = 0                          # 14 序（= 台账槽位口径）

    # ── 状态对齐（写盘器的「状态规范化」；移植自姊妹作 V-11）──
    # 逐槽 drop/replace 只为「指令块」负责，不为「净状态」负责：一旦承载某个「清」的
    # 指令被删/被换（或该状态由未入表的保留槽自带），那张图就一路留在屏上，直到很晚
    # 才被别的清屏指令带走（实机表现＝上一处的立绘/CG 压在还原内容上，见
    # doc/lessons-learned.md「0x46 子层槽标志」条目）。因此：在**插入块开头**（进块前，
    # 对齐原版第 r0-1 行态）与 **`replace` 补块之后**（对齐原版行态）各对齐一次——
    # 块内演出以原版同一行为准，只要进块之前状态与原版一致，块内每一行就自动一致。
    # **只发「清」是刻意的**（姊妹作 V-11 定案）：清屏不向格子添加演出 token，对按
    # 「每格 direct token」校验的闸天然不可见；需要**补/换**的情形（产物缺某图、同
    # 通道取值不同）必须能被入库表看见（perf_sync / perf_sync_manual），不在构建期
    # 静默补——那类差异由 `script/checks/insert_boundary_check.py` 按 HARD 报出。
    ostates, _osetters = perfsync.row_setters(oinstrs)
    cur_state = {}                  # 已发出指令流的在屏状态（族级清屏展开，与 perfsync 同口径）
    state_fix_log = []              # [{anchor, row, chan, action, value}]

    def _track(op, ops):
        """记录已发出指令对在屏状态的影响。"""
        if op in (0x33, 0x34):
            s = perfsync._strs(ops)
            if len(s) >= 2 and perfsync._is_img_chan(s[0]):
                cur_state[s[0]] = perfsync.norm_sprite(s[1])
        elif op == 0x37:
            s = perfsync._strs(ops)
            if s:
                perfsync.pop_clear(cur_state, s[0])

    def align_state(anchor, r_src):
        """对齐到「原版第 `r_src` 行 `14` 落笔时」的在屏状态；`r_src < 0` ⇒ 脚本头（全空）。

        调用点两处（姊妹作 V-11 全量）：插入块开头（`r_src = r0 - 1`，进块前）与
        `replace` 补块发完之后（`r_src = orig_row`，补块＝原版行演出，发完即该行态）。
        只对「原版该点无图、产物在屏有图」的通道发 `37 <通道>`；原版该点**有图**而
        产物取值不同/缺失的情形不发指令（那要补演出，须走入库表），由闸报 HARD。
        """
        target = ostates[r_src] if 0 <= r_src < len(ostates) else {}
        for c in sorted(c for c in set(target) | set(cur_state)
                        if perfsync._is_img_chan(c)):
            t, have = target.get(c), cur_state.get(c)
            if t is not None or not have:
                continue
            out.extend(b'\x37' + c.encode('cp932') + b'\x00')
            cur_state.pop(c, None)
            state_fix_log.append({'anchor': anchor, 'row': r_src, 'chan': c,
                                  'action': 'clear', 'value': have})
    buf15 = None
    buf15_off = None
    cur_pfx = b''

    def flush15():
        nonlocal buf15, buf15_off
        if buf15 is not None:
            remap_s[buf15_off] = len(out)
            out.extend(buf15)
            buf15 = None
            buf15_off = None

    def emit_block(r0, r1, after_off, anchor):
        nonlocal pool
        align_state(anchor, r0 - 1)         # 进块前：状态对齐到原版第 r0-1 行（在 block_start 之前，
        block_start.setdefault(anchor, len(out))   # 回落跳转也能先经过清屏）
        i0, i1 = block_span(r0, r1)
        base = len(out)
        rel = {}
        q = 0
        cur_row, cleared = r0, set()
        for j in range(i0, i1):
            if j in skip_o:                 # 剥离块内的原版指令（如回想出口三连）
                continue
            op, ops = oinstrs[j]
            for _c in _pending_clears(cur_row, cleared):   # 清屏长度计入块内偏移预计算
                q += 2 + len(_c)
            prev_op = oinstrs[j - 1][0] if j > i0 and (j - 1) not in skip_o else None
            extra = CHOICE_HDR_LEN if (op == 0x0F and prev_op != 0x0E) else 0  # 选项头
            rel[ooff[j]] = q + extra
            q += extra + 1 + len(_conv(op, ops, names))
            if op == 0x14:
                cur_row += 1
        cur_row, cleared = r0, set()
        for j in range(i0, i1):
            if j in skip_o:
                continue
            op, ops = oinstrs[j]
            for _c in _pending_clears(cur_row, cleared):   # 行首条显示指令前发清屏
                out.extend(b'\x37' + _c.encode('cp932') + b'\x00')
                cur_state.pop(_c, None)
                anim_clear_log.append({'anchor': anchor, 'row': cur_row, 'chan': _c})
            ops2 = _conv(op, ops, names)
            if op == 0x14:
                # 池序号全量重算：插入行的 `14.id` 必须改写为新槽序。原版行号与
                # 新槽序只在"插入块紧邻其原位置、且其前无删格"时才恰好相等；一旦
                # 其前有删格，沿用原号就会与宿主侧已重排的号位撞号，而引擎按 id
                # 索引 zh-CN 覆盖层 ⇒ 撞号处及其后的中文整段错位
                # （2026-10-06 复验 D2：9 脚本 / 1,435 槽）。长度不变，不影响 rel/q。
                ops2 = struct.pack('<H', pool) + ops2[2:]
            fields = list(REBASE_OPS.get(op, ()))
            if op in TAIL4_REBASE and len(ops2) >= 4:
                fields.append(len(ops2) - 4)
            for k in fields:
                v = struct.unpack_from('<I', ops2, k)[0] if len(ops2) >= k + 4 else 0
                if not v:
                    continue
                if v in rel:                                    # 块内：立即重定基
                    ops2 = ops2[:k] + struct.pack('<I', base + rel[v]) + ops2[k + 4:]
                elif ext.get(v) == 'tail_end':                  # 原版结尾 ⇒ 宿主结尾
                    fixes.append((len(out) + 1 + k, 't', v))
                elif v in ext:                                  # 跨块：末端经宿主映射
                    fixes.append((len(out) + 1 + k, 'x', v))
                else:
                    raise AssertionError('跨块跳转目标 %#x（op %#x @%#x）无承载'
                                         % (v, op, ooff[j]))
            # `0x0f` 选项表：条目内联在操作数里（见 ws2dis._choice_parse）。必须在
            # `out.extend` **之前**处理：条目自带 `06 <u32>` 跳转要按 rel/ext 重定基，
            # strid 先占位（收尾还会由 ws2.repool_text_ids 统一重号）。
            choice_ents = None
            if op == 0x0F:
                buf = bytearray(bytes([op]) + ops2)
                choice_ents = ws2.choice_entries(bytes(buf), 0)
                assert len(choice_ents) == ops2[0], \
                    '0x0f 条目数 %d != count %d @0x%x' % (len(choice_ents), ops2[0], ooff[j])
                for _so, _to, _lo, jo, kind, val in choice_ents:
                    # strid 不在这里写：收尾的 ws2.repool_text_ids() 会按文件顺序统一重号
                    # （0x14 id 与条目 strid 共用同一计数器），这里只负责跳转重定基。
                    if kind != 'abs' or not val:
                        continue
                    if val in rel:
                        struct.pack_into('<I', buf, jo, base + rel[val])
                    elif ext.get(val) == 'tail_end':
                        fixes.append((len(out) + jo, 't', val))
                    elif val in ext:
                        fixes.append((len(out) + jo, 'x', val))
                    else:
                        raise AssertionError('0x0f 跳转目标 %#x（@0x%x）无承载' % (val, ooff[j]))
                ops2 = bytes(buf[1:])
            if op == 0x0F and not _ends_with_choice_hdr(out):
                out.extend(choice_hdr(ops2[0]))
            out.extend(bytes([op]) + ops2)
            _track(op, ops2)
            remap_o[ooff[j]] = base + (len(out) - base - (1 + len(ops2)))
            if op == 0x14:
                row = o14.index(j)
                slot_sources.append(('orig', row))
                pool += 1
                cur_row = row + 1
            elif op == 0x0F:
                # 每个条目各占一个文本槽位（与 0x14 共用计数器）：登记来源并推进 pool。
                for _so, _to, _lo, jo, kind, val in choice_ents:
                    slot_sources.append(('choice', struct.unpack_from('<H', ops, _so - 1)[0]))
                    pool += 1
        if restore_frame:
            # 仅在"块尾没自带名字帧、且宿主下一句也不设帧"时才合成一条 15，把宿主帧接回去。
            # 之前无条件合成，会在原版块自带 `15 00`（旁白）时再补一条 `15 <宿主上一句的名>`，
            # 形成"块内 15 00 + 合成 %LCxxx"的双 15（语义上被后者覆盖，属冗余但危险的写法）。
            # 判据：`0x15` 是**流状态**，若块内最后一条 15 已经是原版此刻的生效帧，
            # 就不该再合成；见 doc/file-formats.md「选项编写规范」A7 与闸门 9e。
            nxt = next((ins for ins in sinstrs if ins[0] > after_off), None)
            if nxt is not None and nxt[1] != 0x15:
                if not _ends_with_15_frame(out):
                    out.extend(_mk15(cur_pfx))

    # 演出同步 `replace` 的补块：落在**被删显示块原位**（见 `_perf_add_anchor`），
    # 也就是宿主原来画那张图的位置 ⇒ 前缀区里的复位/清屏（`f0`/`16`/`64`/`37 *`）
    # 仍然排在补块之前执行，不会被「先画后清」抹成黑屏。多个槽落到同一偏移时按槽序拼接。
    add_at = {}
    for _slot, (anchor, seq) in sorted(perf_add.items(), key=lambda kv: int(kv[0])):
        add_at.setdefault(anchor, []).append((_slot, seq))

    def emit_perf_add(anchor):
        """把落在 `anchor`（宿主某条指令的绝对偏移）之前的补块按槽序发出。

        每个 `replace` 槽的补块发完后再按「原版该行 `14` 落笔时」的净状态对齐一次
        （只发清，姊妹作 V-11）：`replace` 连删带补只补原版行**自带**的演出，原版行
        没有对应清时会净丢一次「清」——被删 Steam 槽承担的清就此消失，那张图会一直
        留在屏上直到很晚的清屏（`emit_block` 开头的对齐管进块前，这里管补块后）。
        """
        for slot, seq in add_at.pop(anchor, ()):
            for op, ops in seq:
                ops2 = _conv(op, ops, names)
                out.extend(bytes([op]) + ops2)
                _track(op, ops2)
            _spec = None
            for _k in (slot, str(slot)):
                if _k in perf_sync:
                    _spec = perf_sync[_k]
                    break
            if _spec and _spec.get('mode') == 'replace' and _spec.get('orig_row') is not None:
                align_state(anchor, int(_spec['orig_row']))

    # 脚本头插入
    for r0, r1 in by_anchor.get(-1, []):
        emit_block(r0, r1, -1, -1)

    pos = 0
    for off, op, size, ops in sinstrs:
        pos = off + size
        if off in add_at:
            flush15()
            emit_perf_add(off)
        if off in kill:
            if op == 0x14:
                si += 1
            continue
        if op == 0x15:
            if buf15 is not None:
                remap_s[buf15_off] = len(out)
                out.extend(buf15)
            buf15 = steam_dec[off:off + size]
            buf15_off = off
            cur_pfx = _pfx(ops)
            continue
        flush15()
        if op == 0x0F and not _ends_with_choice_hdr(out):
            out.extend(choice_hdr(ops[0]))
        remap_s[off] = len(out)
        body = bytearray(steam_dec[off:off + size])   # 全指令（含操作码）
        if op == 0x07 and jump_rename:
            body = bytearray(rename_07(bytes(body), jump_rename))
        if op == 0x14:
            old = struct.unpack_from('<H', body, 1)[0]
            struct.pack_into('<H', body, 1, pool)
            slot_sources.append(('steam', old))
            pool += 1
        elif op == 0x0F:
            # 选项表（条目内联在操作数里，见 ws2dis._choice_parse）：每个条目占一个文本槽位，
            # strid 由收尾的 repool 统一重排，条目自带的 `06` 跳转由下面的 `fixes` 机制重定基。
            for _e in ws2.choice_entries(bytes([op]) + ops, 0):
                slot_sources.append(('choice', struct.unpack_from('<H', ops, _e[0] - 1)[0]))
                pool += 1
                if _e[4] == 'abs' and _e[5]:
                    fixes.append((len(out) + 1 + _e[3], 's', _e[5]))
        elif op in (0x01, 0x02, 0x06) or op in TAIL4_REBASE:
            ks = list(REBASE_OPS.get(op, ()))
            if op in TAIL4_REBASE and len(ops) >= 4:
                ks.append(len(ops) - 4)
            for k in ks:
                v = struct.unpack_from('<I', ops, k)[0] if len(ops) >= k + 4 else 0
                if v:
                    fixes.append((len(out) + 1 + k, 's', v))
        out.extend(body)
        _track(op, bytes(body[1:]))
        if op == 0x14:
            si += 1
            for r0, r1 in by_anchor.get(si - 1, []):
                emit_block(r0, r1, off, si - 1)
    flush15()
    assert not add_at, '演出同步补块落点不在宿主指令起点: %s' % sorted(add_at)
    # ⚠️ 末尾 8 字节 = **明文尾表** `[u32 消息数][u32 选项条目数]`（不参与 rotate-6）。
    # 引擎按它给「已读位图」（`MessageFlag.dat`）分配容量，写位**不查边界** ⇒ 尾表若小于
    # 真实消息数，高位下标越界写坏堆 ⇒ 概率性闪退。inserts/drops 都会改变 0x14 条数，
    # 所以这里**不抄宿主尾部**，由 ws2.tail_counts() 重算后写明文（在 encode 之后写）。
    # 解码流里的这 8 字节是「明文的 rotate-6」，抄回来等于抄旧计数（见 lessons-learned §47）。

    # 跳转目标落在**被删区间**内 ⇒ 回落到「承载该区间的那一段插入块的起点」。
    # 本作实测：Steam 脚本头有存档续玩分支（`01` 条件 → 落到 `06` 跳到场景中段某
    # 检查点，如 `BEF_003_E` 的 `06 -> 0xa820`）。该检查点在还原后已不存在，
    # 语义上最接近的位置就是同一叙事位置的**还原块起点**（从场景开头续播）。
    _anchors = sorted({ins[0] for ins in plan['inserts']})
    drop_anchor = {}
    for s in plan['drops']:
        cand = [a for a in _anchors if a < s]
        if cand:
            drop_anchor[s] = max(cand)

    def drop_fallback(target):
        slot = None
        for s, o in enumerate(s14off):
            if o <= target:
                slot = s
            else:
                break
        if slot is None or slot not in plan['drops']:
            return None
        a = drop_anchor.get(slot)
        return block_start.get(a) if a is not None else None

    fix_bad = 0
    fix_fallback = 0
    bad_detail = []
    for pos, kind, key in fixes:
        if kind == 's':
            nt = remap_s.get(key)
            if nt is None:
                nt = drop_fallback(key)
                if nt is not None:
                    fix_fallback += 1
        elif kind == 'o':
            nt = remap_o.get(key)
        elif kind == 't':
            nt = remap_s.get(tail_end_off)
        else:
            slot = ext[key]
            nt = remap_s.get(s14off[slot]) if slot < len(s14off) else None
        if nt is None and kind == 's':
            # 目标落在被演出同步删掉的显示块内（如 `04 LAYER_ORDER`）⇒ 回落到
            # 其后最近一条存活指令（语义：跳过被删的那段演出）。
            cand = [k for k in remap_s if k >= key]
            if cand:
                nt = remap_s[min(cand)]
                fix_fallback += 1
        if nt is None:
            fix_bad += 1
            bad_detail.append({'kind': kind, 'target': key})
            continue
        struct.pack_into('<I', out, pos, nt)

    body_all = ws2.repool_text_ids(bytes(out))          # 0x14 id 与 0x0f strid 统一重编号
    tail_counts = ws2.tail_counts(body_all)             # (0x14 条数, 0x0f 条目数)
    body = bytes(body_all[:-ws2.TAIL_LEN])              # 去掉解码流里的 8 字节旧尾
    assert body[-1] == 0xFF, '宿主产物未以 0xff 收尾（尾表位置异常）'
    enc = ws2.encode(body) + struct.pack('<II', tail_counts[0], tail_counts[1])
    ins2, ok2 = ws2dis.disassemble(ws2.decode(enc))
    n14 = sum(1 for _, op, _, _ in ins2 if op == 0x14)
    n_choice = sum(1 for k, _v in slot_sources if k == 'choice')
    return {
        'raw': enc,
        'slot_sources': slot_sources,
        'ok': ok2,
        'n14': n14,
        'n_choice': n_choice,
        'n_slots': len(slot_sources),
        'pool': pool,
        'fixups': len(fixes),
        'fix_bad': fix_bad,
        'fix_fallback': fix_fallback,
        'fix_bad_detail': bad_detail,
        'perf_kill': {k: v for k, v in sorted(perf_report.items())},
        'perf_add': {k: len(v) for k, v in sorted(perf_add.items())},
        'perf_noop': perf_noop,
        'state_fix': state_fix_log,
        'anim_clear': anim_clear_log,
    }
