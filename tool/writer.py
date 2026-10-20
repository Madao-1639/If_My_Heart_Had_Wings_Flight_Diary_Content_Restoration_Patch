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
KEEP_OPS = {0x01, 0x02, 0x05, 0x06, 0x07, 0x09, 0x0B, 0x0F, 0x15, 0xF0, 0xFF}

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


def _perf_block_kill(instrs, j_cur, zone_lo, chans, with_clear=False):
    """某槽演出前缀区内、`chans` 各通道的显示块 → 要删的指令偏移集。

    `chans=None` ⇒ 命中所有**立绘／背景**通道（`st*`／`bg*`；`ev` 交 CG 序列专管，不动）。
    `with_clear` 为真时连同这些通道的 `37` 清屏指令一起删（`replace` 模式用；
    `drop` 模式不动清屏）。只删**显示块**：显示指令及其图层伴生；`0b` 状态写入一律保留。
    返回 (kill_offsets, hit_chans)。
    """
    kill, hit = set(), set()

    def _match(chan, name):
        if not chan:
            return False
        if chans is None:
            # `replace`：该槽**全部图像通道**（ev + st*/bg*）。删掉的层由原版行自己的块
            # 补回；CG 也在内（FD 的 CG 显示点没有独立改写表，随 replace 一并还原）。
            return perfsync._is_img_chan(chan)
        return chan in chans

    for j in range(zone_lo, j_cur):
        op, ops = instrs[j][1], instrs[j][3]
        if op == 0x37 and with_clear:
            chan = _chan_of(ops)
            if _match(chan, None):
                hit.add(chan)
                kill.add(instrs[j][0])
            continue
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


def perf_sync_apply(instrs, s14off, oinstrs, o14, perf_sync):
    """演出同步 → (kill_offsets, add_blocks, report)。

    `perf_sync = {steam 槽位: spec}`，`spec` 三种：

    * `{'mode': 'drop', 'channels': [通道]}`：删该槽前缀区内这些通道的显示块；
    * `{'mode': 'keep', 'channels': [通道]}`：**只删**这些通道的清屏，保留在屏延续；
    * `{'mode': 'replace', 'orig_row': r}`：删该槽前缀区内**全部立绘/背景**显示块与清屏，
      再把原版行 r 的图像演出块（含塞在 st*/bg* 的 CG 名图，排除 `ev`）补回；
    * `keep` 可与任一 mode 正交（`spec['keep'] = [通道]`）。

    `add_blocks = {槽位: [(op, ops), ...]}`（原版格式，调用方经 `_conv` 转换后发出）。
    """
    if not perf_sync:
        return set(), {}, {}
    idx = {ins[0]: j for j, ins in enumerate(instrs)}
    kill, add_blocks, report = set(), {}, {}
    for slot, spec in sorted(perf_sync.items()):
        slot = int(slot)
        if not isinstance(spec, dict):
            spec = {'mode': 'drop', 'channels': list(spec)}
        zone = _perf_zone(instrs, idx, s14off, slot)
        mode = spec.get('mode', 'drop')
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
        added = []
        if mode == 'replace':
            # 目标：该槽在屏状态 = 原版行 r。搬 **全部图像通道**（ev/st/bg）的显示块
            # 与清屏（按原版顺序）——CG 也在内（FD 的 CG 显示点没有独立改写表，
            # 由本模式一并还原；`0b` 解锁对是状态写入，仍原样保留）。
            r = spec['orig_row']
            i0 = o14[r - 1] + 1 if r > 0 else 0
            i1 = o14[r]
            events = []
            for b in perfsync.image_blocks([(op, ops) for op, ops in oinstrs[i0:i1]]):
                if not b['idx']:
                    continue
                is_cg = perfsync.is_cg_name(b.get('name'))
                ops_seq = []
                for i in b['idx']:
                    op, ops = oinstrs[i0 + i]
                    # 状态写入默认不搬；但 **CG 显示块内的 `0x0b` 解锁对**必须搬
                    # （新增的 CG 显示点在 Steam 侧没有对可保留 ⇒ 用原版自己的）。
                    if op in _PERF_PRESERVE and not (is_cg and op == 0x0b):
                        continue
                    ops_seq.append((op, ops))
                if is_cg and not any(op == 0x0b for op, _ in ops_seq):
                    got = 0
                    for j in range(max(b['idx']) + 1, i1 - i0):
                        op, ops = oinstrs[i0 + j]
                        if op == 0x0b:
                            ops_seq.append((op, ops))
                            got += 1
                            if got == 2:
                                break
                        elif op in (0x14, 0x33):
                            break
                if ops_seq:
                    events.append((min(b['idx']), ops_seq))
            for j in range(i0, i1):
                op, ops = oinstrs[j]
                if op == 0x37:
                    chan = _chan_of(ops)
                    if perfsync.is_sb_channel(chan) or chan == 'ev':
                        events.append((j - i0, [(op, ops)]))
            events.sort(key=lambda x: x[0])
            for _pos, seq in events:
                added.extend(seq)
        k, hit = _perf_block_kill(instrs, zone[1], zone[0], chans,
                                  with_clear=(mode == 'replace'))
        kill |= k
        if added:
            add_blocks[slot] = added
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
    }
    返回 {'raw', 'slot_sources', 'ok', 'n14', 'n_slots', 'pool', 'fixups', 'fix_bad',
          'perf_kill'}。
    """
    ext = plan.get('external', {})
    restore_frame = plan.get('restore_frame', True)
    perf_sync = plan.get('perf_sync') or {}
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
    jump_rename = dict(plan.get('jump_rename') or {})

    s14off = [off for off, op, size, ops in sinstrs if op == 0x14]
    # 演出同步（见 doc/restoration-route.md §7 V-10）：与删格同形——删该槽前缀区内
    # 的**显示块**（`drop` 模式删指定通道、`replace` 模式删全部图像通道再补原版行的），
    # 不碰状态写入与流程控制。`replace` 的补块在**前缀区开头**发出（排在语音/名字框之前，
    # 与 doc/file-formats.md「格内指令的归属次序」一致），资源名照抄原版（依赖 copy 补素材）。
    perf_kill, perf_add, perf_report = perf_sync_apply(sinstrs, s14off, oinstrs, o14, perf_sync)
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
        block_start.setdefault(anchor, len(out))
        i0, i1 = block_span(r0, r1)
        base = len(out)
        rel = {}
        q = 0
        for j in range(i0, i1):
            op, ops = oinstrs[j]
            rel[ooff[j]] = q
            q += 1 + len(_conv(op, ops, names))
        for j in range(i0, i1):
            op, ops = oinstrs[j]
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
            out.extend(bytes([op]) + ops2)
            remap_o[ooff[j]] = base + (len(out) - base - (1 + len(ops2)))
            if op == 0x14:
                row = o14.index(j)
                slot_sources.append(('orig', row))
                pool += 1
        if restore_frame:
            nxt = next((ins for ins in sinstrs if ins[0] > after_off), None)
            if nxt is not None and nxt[1] != 0x15:
                out.extend(_mk15(cur_pfx))

    def emit_perf_add(slot):
        """演出同步 `replace` 的补块：原版行 r 的图像演出，按原顺序发出。

        排在**该槽前缀区开头**（即上一条 `14`／其锚定插入块之后），因此先于该槽自带的
        语音（`2e`+`28`）与名字框（`15`）执行——与 doc/file-formats.md「格内指令的归属
        次序」（演出 → 语音 → 名字框 → `14`）一致。资源名照抄原版脚本里的名字。
        """
        for op, ops in perf_add.get(slot, ()):
            out.extend(bytes([op]) + _conv(op, ops, names))

    # 脚本头插入
    for r0, r1 in by_anchor.get(-1, []):
        emit_block(r0, r1, -1, -1)
    emit_perf_add(0)

    pos = 0
    for off, op, size, ops in sinstrs:
        pos = off + size
        if off in kill:
            if op == 0x14:
                si += 1
                # 被删槽不发出正文，但**演出同步的补块仍要挂到下一个槽**（否则「前一个槽
                # 被删」的槽永远补不上——补块锚在「上一条 `14` 之后」）。
                flush15()
                emit_perf_add(si)
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
            n = body[1]
            pp = 3                                    # body[0]=0f, [1]=count, 条目自 3 起
            for _ in range(n):
                old_strid = struct.unpack_from('<H', body, pp)[0]
                struct.pack_into('<H', body, pp, pool)
                slot_sources.append(('steam', old_strid))
                pool += 1
                e1 = body.index(b'\x00', pp + 2) + 1
                jmp = body[e1 + 3]
                if jmp == 0x06:
                    tgt = struct.unpack_from('<I', body, e1 + 4)[0]
                    if tgt:
                        fixes.append((len(out) + e1 + 4, 's', tgt))
                pp = (body.index(b'\x00', e1 + 4) + 1) if jmp == 0x07 else (e1 + 3 + 5)
            body = bytes(body)
        elif op in (0x01, 0x02, 0x06) or op in TAIL4_REBASE:
            ks = list(REBASE_OPS.get(op, ()))
            if op in TAIL4_REBASE and len(ops) >= 4:
                ks.append(len(ops) - 4)
            for k in ks:
                v = struct.unpack_from('<I', ops, k)[0] if len(ops) >= k + 4 else 0
                if v:
                    fixes.append((len(out) + 1 + k, 's', v))
        out.extend(body)
        if op == 0x14:
            si += 1
            for r0, r1 in by_anchor.get(si - 1, []):
                emit_block(r0, r1, off, si - 1)
            emit_perf_add(si)
    flush15()
    out.extend(steam_dec[pos:])                       # 0xff 后的 8 字节尾

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

    enc = ws2.encode(bytes(out))
    ins2, ok2 = ws2dis.disassemble(ws2.decode(enc))
    n14 = sum(1 for _, op, _, _ in ins2 if op == 0x14)
    return {
        'raw': enc,
        'slot_sources': slot_sources,
        'ok': ok2,
        'n14': n14,
        'n_slots': len(slot_sources),
        'pool': pool,
        'fixups': len(fixes),
        'fix_bad': fix_bad,
        'fix_fallback': fix_fallback,
        'fix_bad_detail': bad_detail,
        'perf_kill': {k: v for k, v in sorted(perf_report.items())},
        'perf_add': {k: len(v) for k, v in sorted(perf_add.items())},
    }
