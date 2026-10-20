"""本作定制 Lua 5.3 字节码的**读 + 写**（`galrev.advhd.luac53` 只读，本模块补上序列化）。

定制点（与上游 5.3 的差异，见 `galrev/advhd/luac53.py` 模块 docstring）：
字符串长度是 **1 字节**（不是 `sizeof(size_t)`），其余字段与上游 5.3 相同。

用法：
    from tool import lua53
    top = lua53.load(blob)          # 返回 galrev.advhd.luac53.Proto 树
    blob2 = lua53.dump(top)         # 序列化

第一道闸：`dump(load(blob)) == blob` 逐字节往返。工具脚本改完 Proto 树后必须
先过这道闸，再做语义校验。

定位原型的辅助函数 `find(top, path)`：`path` 形如 `[142, 8]`，表示顶层 protos 的第
142 个子原型的第 8 个子原型（`luadis53.dump` 打印的 `LegacyGame/142/8` 即此路径）。
"""
import struct

import sys
import os

# galrev 以路径引用（与项目其余 tool 相同的用法）
_GALREV = os.environ.get('GALREV_DIR', r'D:\My_Code\tmp\GamePatch\GalRevserse\GalRev')
if _GALREV not in sys.path:
    sys.path.insert(0, _GALREV)
from galrev.advhd import luac53  # noqa: E402

Proto = luac53.Proto
T_NIL, T_BOOLEAN, T_NUMFLT, T_SHORT_STR = 0, 1, 3, 4
T_NUMINT, T_LONG_STR = 19, 20

SIGNATURE = b'\x1bLua'
VERSION = 0x53
FORMAT = 0
LUAC_DATA = b'\x19\x93\r\n\x1a\n'
SIZES = bytes([4, 4, 4, 8, 8])   # int, size_t, Instruction, lua_Integer, lua_Number
LUAC_INT = 0x5678
LUAC_NUM = 370.5


def load(blob):
    return luac53.load(blob)


def find(top, path):
    p = top
    for i in path:
        p = p.protos[i]
    return p


def _str(b):
    if b is None:
        return b'\x00'
    if len(b) + 1 > 255:
        raise ValueError('string too long for 1-byte length: %d' % len(b))
    # 长度字节 = len+1，载荷只有 len 字节（**不带 NUL**）；读取端按 `size-1` 消费。
    return bytes([len(b) + 1]) + b


def _u32(v):
    return struct.pack('<I', v & 0xFFFFFFFF)


def _dump_function(f, out):
    out += _str(f.source)
    out += _u32(f.line_defined)
    out += _u32(f.last_line_defined)
    out += bytes([f.num_params & 0xFF, f.is_vararg & 0xFF, f.max_stack_size & 0xFF])
    out += _u32(len(f.code))
    for w in f.code:
        out += struct.pack('<I', w & 0xFFFFFFFF)
    out += _u32(len(f.constants))
    for tag, val in f.constants:
        out += bytes([tag])
        if tag == T_NIL:
            pass
        elif tag == T_BOOLEAN:
            out += bytes([1 if val else 0])
        elif tag == T_NUMFLT:
            out += struct.pack('<d', val)
        elif tag == T_NUMINT:
            out += struct.pack('<q', val)
        elif tag in (T_SHORT_STR, T_LONG_STR):
            out += _str(val)
        else:
            raise ValueError('unsupported constant tag %d' % tag)
    out += _u32(len(f.upvalues))
    for instack, idx in f.upvalues:
        out += bytes([instack & 0xFF, idx & 0xFF])
    out += _u32(len(f.protos))
    for sub in f.protos:
        _dump_function(sub, out)
    out += _u32(len(f.lineinfo))
    out += bytes(f.lineinfo)
    out += _u32(len(f.locvars))
    for name, startpc, endpc in f.locvars:
        out += _str(name)
        out += _u32(startpc)
        out += _u32(endpc)
    out += _u32(len(f.upvalue_names))
    for name in f.upvalue_names:
        out += _str(name)


def dump(top):
    out = bytearray()
    out += SIGNATURE
    out += bytes([VERSION, FORMAT])
    out += LUAC_DATA
    out += SIZES
    out += struct.pack('<q', LUAC_INT)
    out += struct.pack('<d', LUAC_NUM)
    out += b'\x01'                       # 主 chunk 的 sizeupvalues
    _dump_function(top, out)
    return bytes(out)
