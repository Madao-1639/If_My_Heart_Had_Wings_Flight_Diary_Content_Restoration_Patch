"""格式表驱动的 WS2 线性反汇编器（本作 Flight Diary 专用）。

**表来源**：本作 `AdvHD.exe` 的操作数格式表 —— IDA 实测基址 `0x57ada8`（.rdata），
由 `sub_4D40B0` 以 `*(&off_57ADA8 + opcode)` 直接索引；每项指向 .data 中一段
以 **高位置 1 的字节**（本作全部为 `0xff`）结尾的类型码串；指针为 0 表示该 opcode 未实现。
导出脚本见 `script/scan/dump_formats.py`，落盘 `resource/ws2_formats.json`。

**类型码 → 字节**（由 `sub_4D45E0` 的 switch 与全语料 100% 平铺实证）：
  0 u8(1) | 1 i16(2) | 2 u16(2) | 3 i32(4) | 4 u32(4) | 5 f32(4)
  6/9/10 NUL 终止串（**含结尾 NUL**，共 len+1 字节；10 读后大写化）
  8 占位标记，**0 字节**（串的 NUL 已由类型 6/9/10 一并消费）
  7 计数标记：**先读一个 u8 作为 count**，其后类型重复 count 次

**特例**（不在格式表内，引擎另行处理）：
  * `0xff` FileEnd —— 表中无此项（指针 0），但脚本以它收尾；实测定长 9 字节（`ff <u32> <u32>`）。
  * `0x01` Condition —— `mode == 0` 时 5 字节，否则 16 字节。
"""
import json
import os
import struct

_DEFAULT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'resource', 'ws2_formats.json')

# 引擎另行处理的 opcode（不在格式表里）
OP_FF = 0xff
OP_COND = 0x01


class Bad(Exception):
    pass


class Table:
    def __init__(self, path=None):
        with open(path or _DEFAULT, encoding='utf-8') as fh:
            raw = json.load(fh)['formats']
        self.fmt = {int(k, 16): [t for t in v if t < 0x80] for k, v in raw.items()}

    def defined(self, op):
        return op in self.fmt


_T = None


def table():
    global _T
    if _T is None:
        _T = Table()
    return _T


def _str_end(data, p):
    q = data.find(b'\0', p)
    if q < 0:
        raise Bad('unterminated string')
    return q + 1          # 含 NUL


def read_operands(data, pos, tab=None):
    """解析 pos 处一条指令，返回 (size, fields)。fields 保留原始字节与解出的值。"""
    tab = tab or table()
    op = data[pos]
    if op == OP_FF:
        if pos + 9 > len(data):
            raise Bad('truncated 0xff')
        a, b = struct.unpack_from('<II', data, pos + 1)
        return 9, {'a': a, 'b': b}
    if op == OP_COND:
        mode = data[pos + 1]
        if mode == 0:
            return 5, {'mode': mode}
        if pos + 16 > len(data):
            raise Bad('truncated 0x01')
        vid = struct.unpack_from('<H', data, pos + 2)[0]
        val = struct.unpack_from('<f', data, pos + 4)[0]
        a, b = struct.unpack_from('<II', data, pos + 8)
        return 16, {'mode': mode, 'id': vid, 'value': round(val, 4), 'a': a, 'b': b}
    if op == 0x0F:
        # 选项表：count + count × (<strid:u16><text>\0<u16 标签><u8 0><jump>)；jump = 06 u32 | 07 name
        # 条目内联在 0x0f 操作数里（见 ws2dis._choice_parse），不能按普通指令切分。
        count = data[pos + 1]
        p = pos + 2
        entries = []
        for _ in range(count):
            strid = struct.unpack_from('<H', data, p)[0]
            p += 2
            q = _str_end(data, p)
            text = data[p:q - 1]
            p = q
            label = struct.unpack_from('<H', data, p)[0]
            p += 2
            p += 1
            kind = data[p]
            if kind == 0x06:
                val = struct.unpack_from('<I', data, p + 1)[0]
                p += 5
                jmp = ('abs', val)
            elif kind == 0x07:
                q = _str_end(data, p + 1)
                jmp = ('name', data[p + 1:q - 1].decode('cp932', 'replace'))
                p = q
            else:
                raise Bad('unknown choice jump 0x%02x @0x%x' % (kind, p))
            try:
                t = text.decode('ascii')
            except UnicodeDecodeError:
                t = text.decode('cp932', 'replace')
            entries.append({'strid': strid, 'text': t, 'label': label, 'jump': jmp})
        return p - pos, {'count': count, 'entries': entries}
    toks = tab.fmt.get(op)
    if toks is None:
        raise Bad('opcode 0x%02x undefined in FD format table' % op)
    p = pos + 1
    vals = []
    last_u8 = [None]

    def one(t):
        nonlocal p
        if t == 0:
            if p >= len(data):
                raise Bad('truncated u8')
            v = data[p]
            last_u8[0] = v
            p += 1
            return v
        if t == 1:
            v = struct.unpack_from('<h', data, p)[0]
            p += 2
            return v
        if t == 2:
            v = struct.unpack_from('<H', data, p)[0]
            p += 2
            return v
        if t == 3:
            v = struct.unpack_from('<i', data, p)[0]
            p += 4
            return v
        if t == 4:
            v = struct.unpack_from('<I', data, p)[0]
            p += 4
            return v
        if t == 5:
            v = struct.unpack_from('<f', data, p)[0]
            p += 4
            return round(v, 4)
        if t == 8:
            return None                      # 占位标记，0 字节
        if t in (6, 9, 10):
            q = _str_end(data, p)
            raw = data[p:q - 1]
            p = q
            try:
                s = raw.decode('ascii')
            except UnicodeDecodeError:
                s = raw.decode('cp932', 'replace')
            return s.upper() if t == 10 else s
        raise Bad('unknown type code %d' % t)

    i = 0
    while i < len(toks):
        t = toks[i]
        i += 1
        if t == 7:
            tt = toks[i]
            i += 1
            if p >= len(data):
                raise Bad('truncated count u8')
            cnt = data[p]
            p += 1
            vals.append(('x%d' % cnt))
            for _ in range(cnt):
                vals.append(one(tt))
        else:
            vals.append(one(t))
    return p - pos, {'args': vals}


def disassemble(data, tab=None):
    """返回 [(offset, opcode, size, fields)]；任一位置无法解析即抛 Bad。"""
    tab = tab or table()
    out = []
    pos, n = 0, len(data)
    while pos < n:
        sz, f = read_operands(data, pos, tab)
        if sz <= 0 or pos + sz > n:
            raise Bad('bad size %d at 0x%x' % (sz, pos))
        out.append((pos, data[pos], sz, f))
        pos += sz
    return out


def cover(data, tab=None):
    try:
        ins = disassemble(data, tab)
    except Bad as e:
        return None, str(e)
    if not ins:
        return ins, 'empty'
    return ins, ('ok' if ins[-1][1] == OP_FF else 'last-op 0x%02x' % ins[-1][1])
