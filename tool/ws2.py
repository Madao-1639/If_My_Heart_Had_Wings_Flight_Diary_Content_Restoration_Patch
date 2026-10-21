"""WS2 剧本脚本编解码 + 成就调用注入。

混淆方式是逐字节 rotate-left-6（已验证可逆，解码后暴露出 ASCII 操作码/操作数，
如脚本名、CG 文件名、LAYER_ORDER 等关键字——详见 doc/file-formats.md）。

已确认的相关操作码（基于对 Steam 版全部 159 个 Rio.arc 脚本的实测）：

    0x33  <slot>\0 <FILE.PNG>\0 0x01 0x01     在背景/CG 槏位显示一张 PNG
    0x0b  <u16 var> 0x01                      设置变量（推测为图库编号/差分编号）
    0x04  <NAME>\0                            调用另一个脚本

每次 CG 显示后必定紧跟两个 0x0b 变量设置操作，这两个操作在 Steam 版与原版脚本中
都存在——它们是显示 CG 本身固有的部分，与成就系统无关。逐字节 diff 同一场景在
两个版本的脚本，Steam 版精确多出 16 字节：

    ...0101  0b <u16 A> 01  0b <u16 B> 01  [04 "CG_ACHIEVEMENT" 00]  ...
             |<---- 两版本共有 ---->|      |<----- 仅 Steam 版 ----->|

已对 Steam 版全部脚本验证：每一处 0x33 CG 显示指令之后都跟着这条成就调用
（920 处显示，920 处调用，覆盖率 100%）。因此注入逻辑只需在既有变量对之后
插入这 16 字节调用，绝不重新生成/计算变量对本身的数值——那两个值是显示 CG
的固有数据，应直接复用脚本中已经写好的值。
"""
import re
import struct

ACH_NAME = b'CG_ACHIEVEMENT'
ACH_CALL = b'\x04' + ACH_NAME + b'\x00'

# 0x33 <slot> 00 <STEM>.PNG 00 01 01 后紧跟固有的 id 变量对。
DISPLAY = re.compile(
    rb'\x33([A-Za-z0-9_]{2,12})\x00([A-Za-z0-9_]+)\.PNG\x00\x01\x01'
    rb'\x0b(..)\x01\x0b(..)\x01', re.S)


def decode(raw):
    """反混淆一个 .ws2 成员（rotate left 6）。"""
    return bytes(((c << 6) | (c >> 2)) & 0xff for c in raw)


def encode(data):
    """重新混淆一个 .ws2 成员（逆操作：rotate right 6，等价于 rotate left 2）。"""
    return bytes(((c << 2) | (c >> 6)) & 0xff for c in data)


def find_display_sites(data):
    """遍历每一处 CG 显示操作，产出 (end_offset, cg_stem, has_call)。

    end_offset 指向固有 id 变量对结束处，正是插入成就调用的位置。
    """
    for m in DISPLAY.finditer(data):
        has_call = data[m.end():m.end() + len(ACH_CALL)] == ACH_CALL
        yield m.end(), m.group(2).decode('ascii'), has_call


def inject(raw):
    """在每一处缺少成就调用的 CG 显示后插入该调用。

    返回 (new_raw, injected_count)。只拼接 16 字节调用，脚本中已有的固有 id
    变量对保持字节不变，复用其中已有的 CG id，不重新计算。
    """
    data = decode(raw)
    out = bytearray()
    cursor = 0
    injected = 0
    for end, _stem, has_call in find_display_sites(data):
        if has_call:
            continue
        out += data[cursor:end]
        out += ACH_CALL
        cursor = end
        injected += 1
    out += data[cursor:]
    return encode(bytes(out)), injected


# ── 末尾 8 字节明文「尾表」──────────────────────────────────────────────────────
# 成员最后 8 字节 = `[u32 消息数][u32 选项条目数]`，**不参与 rotate-6 混淆**（明文）。
# 引擎**加载脚本时**读它（`data[size-8]` / `data[size-4]`），据此给「已读消息位图」
# （存档目录 `MessageFlag.dat`）分配 `(消息数 + 选项条目数 + 7) / 8` 字节；写位函数
# `bitmap[idx>>3] |= 1 << (idx & 7)` **不做边界检查** ⇒ 尾表小于脚本真实消息数时，高位
# 下标直接写到相邻堆块上，延迟到某次 `free` 被堆校验抓到 ⇒ `0xc0000374` **概率性闪退**
# （不是崩在写位处；也可能先在 Lua/UI 上表现出随机的 nil 错误）。实机指纹：
# `MessageFlag.dat` 记录的位图容量明显小于脚本消息数、且该记录 `B`（已标记次数）持续
# 增大而位图仍为 0。
# ⇒ **任何改变 `0x14` / `0x0f` 条数的改写都必须同步重写这 8 字节**，写成明文、且在
#   `encode()` **之后**写（先写会被旋转成垃圾）。落地点：`tool/writer.py::rebuild_host`、
#   `script/build/build_patch.py` 的 whole 路径；闸：`script/checks/ws2_tail_check.py`。
# （机制通识见 GalRev `docs/engines/advhd/file-formats.md`「末尾 8 字节」与 `save-system.md`
#   「MessageFlag.dat」；姊妹作《在这苍穹展翅》同一套结论。）
TAIL_LEN = 8


def read_tail_counts(raw):
    """读原始成员末尾 8 字节（明文）→ (消息数, 选项条目数)。"""
    if len(raw) < TAIL_LEN:
        raise ValueError('ws2 too short for a tail table (%d)' % len(raw))
    return struct.unpack('<II', raw[-TAIL_LEN:])


def tail_counts(decoded):
    """数解码流里的 (0x14 条数, 0x0f 的条目数之和)。"""
    from tool import ws2dis
    msgs = choices = 0
    for _off, op, _sz, ops in ws2dis.disassemble(decoded)[0]:
        if op == 0x14:
            msgs += 1
        elif op == 0x0F and ops:
            choices += ops[0]          # 变长块首字节 = 条目数
    return msgs, choices


def set_tail_counts(raw, counts):
    """重写明文尾表；**必须在 `encode()` 之后调用**。"""
    return raw[:-TAIL_LEN] + struct.pack('<II', int(counts[0]), int(counts[1]))


def check_tails(members, base=None):
    """逐成员核对尾表；返回 (ok, bad)，bad 项 = (名, 实算, 尾表)。

    判据：`read_tail_counts(raw) == tail_counts(decode(raw))`（尾表**不得小于**实算值；
    写成相等即可，引擎只按尾表分配容量）。`base` 给基线成员表时，额外区分「基线自己就
    偏离」的成员（历史遗留，不算本项目新增破坏）。
    """
    ok, bad = [], []
    for name, raw in sorted(members.items()):
        if not name.lower().endswith('.ws2'):
            continue
        try:
            cnt = tail_counts(decode(raw))
        except Exception as ex:
            bad.append((name, 'decode-fail:%s' % ex, None))
            continue
        try:
            tail = read_tail_counts(raw)
        except Exception as ex:
            bad.append((name, 'tail-fail:%s' % ex, None))
            continue
        if tail != cnt:
            bad.append((name, cnt, tail))
        else:
            ok.append(name)
    return ok, bad


# ── `0x0f` 选项表：条目形态与「文本槽号」重排 ────────────────────────────────────
# 本作（FD）的条目不是 CC 那种「内联在 0x0f 操作数里」，而是 0x0f 之后紧跟的**独立指令**，
# 但字节布局与 CC/GalRev 的文档一致（差别只在 `0x0f` 只带 count）：
#
#     0f <count:u8>
#     count × ( <strid:u16> <text:cp932>\0 <u16 标签> <u8 0> <jump> )
#     jump = 06 <u32 文件内绝对偏移> | 07 <脚本名>\0
#
# 关键规则（GalRev `ws2-opcodes.md`、CC `localization.md`）：
#   `0x14` 的 `id` 与 `0x0f` 各条目的 `strid` **共用一个按文件顺序递增的槽位计数器**，
#   选项文本**也占 `.lng` 槽位** ⇒ 严格等式 `lng 条数 == 0x14 条数 + Σ(0f count)`。
#   反例（本项目踩过）：只给 `0x14` 编号、条目沿用原版 strid ⇒ 条目会指到相邻的正文槽，
#   选项显示成「上一句正文 / 空白」且不可选（见 doc/lessons-learned.md §48）。
def choice_entries(dec, off):
    """`off` 处 `0x0f` 的条目 → [(strid_off, text_off, label_off, jump_off, kind, val)]。

    布局见 `ws2dis._choice_parse`（本作是**内联**在 0x0f 操作数里的）：
        <strid:u16> <text:cp932>\0 <u16 标签> <u8 0> <jump>
        jump = 06 <u32 文件内绝对偏移> | 07 <脚本名>\0
    每个条目占一个文本槽位（与 0x14 共用计数器）⇒ `lng 条数 == 0x14 + Σ(0f count)`。
    """
    from tool import ws2dis
    return ws2dis.choice_entries(dec, off)


def text_slots(dec):
    """按文件顺序列出所有文本槽：`('14', off)` / `('choice', strid_off)`。"""
    from tool import ws2dis
    ins, _ok = ws2dis.disassemble(dec)
    out = []
    for off, op, _sz, _ops in ins:
        if op == 0x0F:
            out += [('choice', e[0]) for e in choice_entries(dec, off)]
        elif op == 0x14:
            out.append(('14', off))
    return out


def repool_text_ids(dec):
    """把 `0x14` 的 id 与 `0x0f` 条目的 strid 按文件顺序重排为 0,1,2,…（同一计数器）。"""
    out = bytearray(dec)
    for i, (kind, off) in enumerate(text_slots(dec)):
        struct.pack_into('<H', out, (off + 1) if kind == '14' else off, i)
    return bytes(out)


# ── 选项帧内的 `0x16` 必须剔除（Steam 侧）────────────────────────────────────
# 实机证据：本作 Steam 版在选项帧保留 `16 00 00` 时，`MenuInf.enabled=false` +
# `MenuInf.effect=true` 同时成立（只有 `closeMessageWindow`(/15/50) 会产生这对值），
# 输入门 `GetMenuMouseEnable`(/15/5) 永久关闭 ⇒ 选项能画、点不动、无悬停、第 2 项恒高亮。
# 删掉该 `0x16` 后：悬停/点击/两条分支全部正常，且提示句**留在框内与选项同屏**（即原版
# 的"留框提示"语义）。原版（老一代 Lua，无 enabled/effect 状态机）容忍它，Steam 版不容忍
# ⇒ 见 doc/file-formats.md「选项编写规范」与 doc/engine-mechanics.md「0x16 的副作用」。
REBASE_FIELDS = {0x01: (7, 11), 0x02: (0,), 0x06: (0,)}   # 与 tool/ws2conv.REBASE_OPS 同源


def _choice_frame_op16(ins):
    """→ 需要剔除的 `0x16` 偏移（选项帧＝提示句之后、选项头/`0f` 之前），没有则 None。"""
    for i, (off, op, _sz, _ops) in enumerate(ins):
        if op != 0x0F:
            continue
        stop = off
        if i > 0 and ins[i - 1][1] == 0x0E:
            stop = ins[i - 1][0]
        j = i - 1
        while j >= 0 and ins[j][1] != 0x14:
            j -= 1
        assert j >= 0, '0x0f @0x%x 之前找不到提示句' % off
        prompt = ins[j][0]
        hit = [o for (o, o_op, _s, _p) in ins if o_op == 0x16 and prompt < o < stop]
        if hit:
            return hit[0]
    return None


def _delete_and_rebase(dec, off, size):
    """删除解码流里 `[off, off+size)`，并把所有"流内绝对偏移"整体平移（保持跳转自洽）。"""
    from tool import ws2dis
    ins, ok = ws2dis.disassemble(dec)
    assert ok, '删除前线性解析不自洽'
    starts = {x[0] for x in ins}

    def shift(v):
        return v - size if v >= off else v

    new = bytearray(dec[:off]) + bytearray(dec[off + size:])
    for o, op, _sz, ops in ins:
        if o == off:
            continue
        base = o + 1 - (size if o > off else 0)
        for k in REBASE_FIELDS.get(op, ()):
            if len(ops) < k + 4:
                continue
            v = struct.unpack_from('<I', ops, k)[0]
            if not v:
                continue
            assert v in starts, 'op %#x 目标 %#x 不在指令起点' % (op, v)
            struct.pack_into('<I', new, base + k, shift(v))
        if op == 0x0F:
            for e in choice_entries(dec, o):
                if e[4] != 'abs' or not e[5]:
                    continue
                assert e[5] in starts
                jo = e[3] - (size if o > off else 0)
                struct.pack_into('<I', new, jo, shift(e[5]))
    return bytes(new)


def drop_choice_frame_op16(dec):
    """剔除所有选项帧内的 `0x16`（幂等）。→ (新解码流, 剔除条数)。"""
    from tool import ws2dis
    total = 0
    while True:
        ins, ok = ws2dis.disassemble(dec)
        if not ok:
            break
        off = _choice_frame_op16(ins)
        if off is None:
            break
        assert dec[off:off + 3] == bytes([0x16, 0x00, 0x00]),             '选项帧内 0x16 形态异常：%s' % dec[off:off + 3].hex(' ')
        dec = _delete_and_rebase(dec, off, 3)
        total += 1
    return dec, total
