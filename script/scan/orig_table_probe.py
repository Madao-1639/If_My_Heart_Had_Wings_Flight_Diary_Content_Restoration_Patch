"""纯 Python 在原版 AdvHD.exe 中定位 WS2 操作数格式表。

表结构（参照本作）：.rdata 中 256 个 u32 指针，按 opcode 索引；非零指针指向 .data/.rdata 中
一段「类型码(0..10) 后接 0xff 终止」的字节串；0 表示未实现。
用滚动计数找「有效指针占比最高」的 1024 字节窗口。
"""
import struct
import sys

sys.path.insert(0, 'tmp')
from an_pe import parse_pe

EXE = sys.argv[1] if len(sys.argv) > 1 else \
    'D:/My_Code/tmp/GamePatch/If_My_Heart_Had_Wings_Flight_Diary/' \
    'If_My_Heart_Had_Wings_Flight_Diary_Original/AdvHD.exe'

b = open(EXE, 'rb').read()
info = parse_pe(EXE)
secs = info['sections']


def rva2off(rva):
    for name, vaddr, vsize, raddr, rsize in secs:
        if vaddr <= rva < vaddr + max(vsize, rsize):
            return raddr + (rva - vaddr)
    return None


# 全镜像有效 RVA 范围
ranges = [(v, v + max(vs, rs)) for _, v, vs, _, rs in secs]


def valid(v):
    return any(a <= v < b for a, b in ranges)


IMG = 0x400000


def ok(v):
    if v == 0:
        return False
    if valid(v) and v in good:
        return True
    if v >= IMG and valid(v - IMG) and (v - IMG) in good:
        return True
    return False


def good_fmt(rva):
    """rva 处是否为合法格式串：0..10 的类型码后接 0xff（<=24 字节）。"""
    o = rva2off(rva)
    if o is None:
        return False
    n = 0
    while n < 24 and o + n < len(b):
        c = b[o + n]
        if c == 0xff:
            return True
        if c > 10:
            return False
        n += 1
    return False


# 预计算 good 集合（.data/.rdata 内 4 字节对齐的 RVA）
good = set()
for name, vaddr, vsize, raddr, rsize in secs:
    if name.lower() not in ('.rdata', '.data', '_rdata'):
        continue
    for rva in range(vaddr, vaddr + max(vsize, rsize), 1):
        if good_fmt(rva):
            good.add(rva)
print('good format RVAs:', len(good))

# 扫描指针表
def score_at(o):
    return sum(1 for i in range(256) if ok(struct.unpack_from('<I', b, o + i * 4)[0]))


best = []
for name, vaddr, vsize, raddr, rsize in secs:
    if name.lower() not in ('.rdata', '.data', '_rdata'):
        continue
    end = raddr + max(vsize, rsize) - 1024
    o = raddr
    # 滚动
    cur = score_at(o)
    best.append((cur, vaddr, o))
    while o + 4 <= end:
        v_out = struct.unpack_from('<I', b, o)[0]
        v_in = struct.unpack_from('<I', b, o + 1024)[0]
        cur += (1 if ok(v_in) else 0) - (1 if ok(v_out) else 0)
        o += 4
        if cur > best[-1][0]:
            best.append((cur, vaddr + (o - raddr), o))

best.sort(reverse=True)
print('top candidates (score, RVA, fileoff):')
for s, rva, o in best[:12]:
    ptrs = [struct.unpack_from('<I', b, o + i * 4)[0] for i in range(256)]
    nz = [p for p in ptrs if p]
    span = (max(nz) - min(nz)) if nz else 0
    print('  score=%d RVA=%#x fileoff=%#x  nonzero=%d span=%#x' % (s, rva, o, len(nz), span))
