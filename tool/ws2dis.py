# -*- coding: utf-8 -*-
"""WS2 线性反汇编器（本作 Flight Diary）。

操作数格式表取自**引擎自身**：
  * `resource/ws2_formats.json`      —— Steam 版 `AdvHD.exe` 的 `0x57ada8` 表（160/256 项有定义）
  * `resource/ws2_formats_orig.json` —— 原版 `AdvHD.exe` 的 `.data RVA 0x12dad8` 表（102 项）

表项 = 类型码字节串（不含终止符 `0xff`）。类型码语义（`tool/ws2fmt.py` 有完整说明）：
  0 u8(1) | 1 i16(2) | 2 u16(2) | 3 i32(4) | 4 u32(4) | 5 f32(4)
  6/9/10 NUL 终止串（**含结尾 NUL**；10 读后大写化）| 8 占位标记，**0 字节**
  7 计数标记：**先读一个 u8 作为 count**，其后类型重复 count 次

本模块只做「线性定长切分」，返回 `(off, op, size, operand_bytes)`；数值语义的解码见
`tool/ws2fmt.py`。

**特例**（不在格式表内，引擎另行处理）：
  * `0xff` FileEnd —— 解码流里定长 9 字节（`ff` + 8 字节）。⚠️ 这 8 字节**不是** FileEnd 的
    操作数，而是成员末尾的**明文尾表** `[u32 消息数][u32 选项条目数]`（**不参与** rotate-6）：
    解码后读到的是「明文的 rotate-6」（垃圾值），写盘时必须按新指令流重算并以明文附回。
    格式与崩溃机制见 `doc/file-formats.md`「尾部 8 字节」、`tool/ws2.py` 尾表段、
    `doc/lessons-learned.md` §47。
  * `0x01` Condition —— 首字节 `mode == 0` 时 5 字节，否则 16 字节（本作语料中 mode 恒非 0）。

**实测不变式**（119 Steam + 107 ORIG 脚本全量核验）：
  * `0x01.a`/`0x01.b`/`0x02`/`0x06` 的非零目标**全部落在指令起点** ⇒ 它们是「解码流内绝对
    字节偏移」，改写脚本时必须重定位（见 `tool/ws2conv.REBASE_OPS`）。
  * 两版语料的 `0x0f` 出现次数**为 0** ⇒ 本作对白槽位等式退化为 `lng 条数 == 0x14 条数`。
"""
import json
import os
import struct
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
FMT_JSON = os.path.normpath(os.path.join(_HERE, '..', 'resource', 'ws2_formats.json'))
FMT_JSON_ORIG = os.path.normpath(os.path.join(_HERE, '..', 'resource', 'ws2_formats_orig.json'))

TYPE_SIZE = {0: 1, 1: 2, 2: 2, 3: 4, 4: 4, 5: 4, 8: 0}
STR_TYPES = (6, 9, 10)

OP_END = 0xFF
OP_COND = 0x01
OP_CHOICE = 0x0F           # ShowChoice：操作数为 count(u8) + count 个条目（条目见 choice_entries）
TAIL_LEN = 0               # 解析约定：0xff 已按 9 字节消费（含 8 字节明文尾表），其后无字节。
                           # ⚠️ 这不代表成员没有尾表——写入端必须用 ws2.tail_counts() 重算并明文附回。
COND_LEN = {0: 5}          # mode -> 总长度；未列出的 mode 一律 16 字节


def load_formats(path=FMT_JSON):
    """表项 -> {op: [类型码…]}（剔除终止符等 >= 0x80 的字节）。"""
    with open(path, encoding='utf-8') as fh:
        raw = json.load(fh)['formats']
    return {int(k, 16): [t for t in v if t < 0x80] for k, v in raw.items()}


FORMATS = load_formats()
FORMATS_ORIG = load_formats(FMT_JSON_ORIG)

# 原版 exe 格式表的**经验修补**：原版表只定义 102 个 opcode，但 `BEF_004.ws2` 用到
# `0x5f`/`0x80`（各 1 次，位于脚本中部）——该脚本疑为原版的更新构建。两者在 Steam 表里
# 有定义且与「串 + 占位」同型（不产生语音槽），故借用其形状。修补后 `BEF_004.ws2` 线性
# 解析 100% 自洽（收尾恰在 `0xff`、无残余字节）。
ORIG_TABLE_PATCH = {0x5f: [10, 8], 0x80: [6, 8]}
FORMATS_ORIG.update({op: list(f) for op, f in ORIG_TABLE_PATCH.items() if op not in FORMATS_ORIG})


def _strlen(data, pos):
    """NUL 终止串的字节数（**含**结尾 NUL）。"""
    end = data.find(b'\x00', pos)
    if end < 0:
        raise ValueError('unterminated string at 0x%x' % pos)
    return end - pos + 1


def choice_block_end(data, off):
    """`0x0f` 整块（含所有条目）的结束偏移。"""
    _ents, end = _choice_parse(data, off)
    return end


def choice_entries(data, off):
    """条目列表（见下）。"""
    return _choice_parse(data, off)[0]


def _choice_parse(data, off):
    """解析 `off` 处 `0x0f` 的条目 → [(strid_off, text_off, label_off, jump_off, kind, val)]。

    本作（FD）的条目是紧跟 `0x0f` 的**内联字节**（引擎在 `0x0f` 处理器里按此布局读，
    格式表的 `0x0f = [0]` 只声明 count）：
        <strid:u16> <text:cp932>\0 <u16 标签> <u8 0> <jump>
        jump = 06 <u32 文件内绝对偏移> | 07 <脚本名>\0
    ⚠️ 必须**整体当作 0x0f 的操作数**来切分：条目首字节恰好是 `0x5e`/`0x5f` 等合法
    opcode，若按普通指令解析就会把条目当成独立指令，且重编 strid 后会立刻失步
    （见 doc/lessons-learned.md §48）。
    """
    if data[off] != OP_CHOICE:
        raise ValueError('not a 0x0f @0x%x' % off)
    count = data[off + 1]
    p = off + 2
    out = []
    for _ in range(count):
        strid_off = p
        p += 2
        text_off = p
        p += _strlen(data, p)
        label_off = p
        p += 2
        p += 1                          # u8 0
        kind = data[p]
        if kind == 0x06:
            out.append((strid_off, text_off, label_off, p + 1, 'abs',
                        struct.unpack_from('<I', data, p + 1)[0]))
            p += 5
        elif kind == 0x07:
            out.append((strid_off, text_off, label_off, p, 'name', None))
            p += _strlen(data, p + 1)
        else:
            raise ValueError('unknown choice jump 0x%02x @0x%x' % (kind, p))
    return out, p


def instruction_size(data, pos, formats=None):
    """返回 (size, opcode)；size 含操作码本身。"""
    fmts = FORMATS if formats is None else formats
    op = data[pos]
    if op == OP_END:
        return 9, op
    if op == OP_COND:
        mode = data[pos + 1]
        return COND_LEN.get(mode, 16), op
    if op == OP_CHOICE:
        return choice_block_end(data, pos) - pos, op
    fmt = fmts.get(op)
    if fmt is None:
        raise ValueError('opcode 0x%02x undefined in format table @0x%x' % (op, pos))
    p = pos + 1
    i, n = 0, len(fmt)
    while i < n:
        c = fmt[i]
        if c >= 0x80:
            break
        if c == 7:
            if p >= len(data):
                raise ValueError('truncated var block at 0x%x' % pos)
            cnt = data[p]
            p += 1
            rep = fmt[i + 1] if i + 1 < n else 0
            i += 2
            for _ in range(cnt):
                if rep in STR_TYPES:
                    p += _strlen(data, p)
                else:
                    p += TYPE_SIZE.get(rep, 0)
            continue
        if c in STR_TYPES:
            p += _strlen(data, p)
        else:
            p += TYPE_SIZE.get(c, 0)
        i += 1
    return p - pos, op


def disassemble(data, stop_at_end=True, formats=None):
    """线性反汇编。

    返回 (instrs, ok)：instrs 为 [(off, op, size, operand_bytes)]。
    ok=True 表示「恰好在 0xff 处结束、其后无残余字节」——即线性解析自洽。
    表中未定义的 opcode 直接抛 ValueError（除非它就是收尾的 0xff）。
    """
    out = []
    pos, n = 0, len(data)
    while pos < n:
        sz, op = instruction_size(data, pos, formats)
        out.append((pos, op, sz, data[pos + 1:pos + sz]))
        pos += sz
        if stop_at_end and op == OP_END:
            return out, (n - pos == TAIL_LEN)
    return out, False


def disassemble_strict(data, formats=None):
    """只要指令列表（向后兼容）。"""
    return disassemble(data, formats=formats)[0]


def _main():
    args = sys.argv[1:]
    if args and args[0] == '--arc':
        sys.path.insert(0, _HERE)
        import arcbuild
        from ws2 import decode
        ok = bad = 0
        badlist = []
        for name, raw in arcbuild.read_raw(args[1]):
            nm = name.decode('utf-16-le', 'replace')
            if not nm.lower().endswith('.ws2'):
                continue
            try:
                _instrs, good = disassemble(decode(raw))
            except ValueError as e:
                good, nm = False, '%s (%s)' % (nm, e)
            if good:
                ok += 1
            else:
                bad += 1
                badlist.append(nm)
        print('ok=%d bad=%d' % (ok, bad))
        for nm in badlist:
            print('  FAIL', nm)
        return
    data = open(args[0], 'rb').read()
    instrs, ok = disassemble(data)
    for off, op, sz, ops in instrs:
        print('0x%04x  op=0x%02x sz=%-3d ops=%s' % (off, op, sz, ops.hex(' ')))
    print('tail ok:', ok)


if __name__ == '__main__':
    _main()
