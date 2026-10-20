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
  * `0xff` FileEnd —— 定长 9 字节（`ff <u32> <u32>`），**即脚本最后一个字节**（本作无尾部
    追加字节；姊妹作那 8 字节尾在本作不存在，实测 119+107 脚本全为 0 字节尾）。
  * `0x01` Condition —— 首字节 `mode == 0` 时 5 字节，否则 16 字节（本作语料中 mode 恒非 0）。

**实测不变式**（119 Steam + 107 ORIG 脚本全量核验）：
  * `0x01.a`/`0x01.b`/`0x02`/`0x06` 的非零目标**全部落在指令起点** ⇒ 它们是「解码流内绝对
    字节偏移」，改写脚本时必须重定位（见 `tool/ws2conv.REBASE_OPS`）。
  * 两版语料的 `0x0f` 出现次数**为 0** ⇒ 本作对白槽位等式退化为 `lng 条数 == 0x14 条数`。
"""
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
FMT_JSON = os.path.normpath(os.path.join(_HERE, '..', 'resource', 'ws2_formats.json'))
FMT_JSON_ORIG = os.path.normpath(os.path.join(_HERE, '..', 'resource', 'ws2_formats_orig.json'))

TYPE_SIZE = {0: 1, 1: 2, 2: 2, 3: 4, 4: 4, 5: 4, 8: 0}
STR_TYPES = (6, 9, 10)

OP_END = 0xFF
OP_COND = 0x01
TAIL_LEN = 0               # 本作脚本以 0xff（9 字节）收尾，其后无追加字节
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


def instruction_size(data, pos, formats=None):
    """返回 (size, opcode)；size 含操作码本身。"""
    fmts = FORMATS if formats is None else formats
    op = data[pos]
    if op == OP_END:
        return 9, op
    if op == OP_COND:
        mode = data[pos + 1]
        return COND_LEN.get(mode, 16), op
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
