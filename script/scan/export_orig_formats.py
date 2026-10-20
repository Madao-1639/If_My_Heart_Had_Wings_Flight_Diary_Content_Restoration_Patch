"""导出原版 AdvHD.exe 的 WS2 操作数格式表 → resource/ws2_formats_orig.json（+ tmp/verify 副本）。

表位置：.data RVA 0x12DAD8，256 个 u32 **绝对地址**指针（ImageBase=0x400000），
每个非零指针指向一段以 0xff 结尾的「类型码」字节串（类型码同本作：0..10）。
发现方法：对 .rdata/.data 全窗口滚动打分（非零且指向合法格式串的条目数），取最高分候选，
再用 HOT_002/004/HUS_001 三脚本 100% 平铺验证（base 偏移 ±4 均失败，唯 0x12DAD8 通过）。
"""
import json
import struct
import sys

sys.path.insert(0, 'tmp')
from an_pe import parse_pe

EXE = ('D:/My_Code/tmp/GamePatch/If_My_Heart_Had_Wings_Flight_Diary/'
       'If_My_Heart_Had_Wings_Flight_Diary_Original/AdvHD.exe')
TABLE_RVA = 0x12DAD8
IMG = 0x400000

b = open(EXE, 'rb').read()
info = parse_pe(EXE)
secs = info['sections']


def r2o(rva):
    for n, va, vs, ra, rs in secs:
        if va <= rva < va + max(vs, rs):
            return ra + (rva - va)
    return None


o = r2o(TABLE_RVA)
fmt = {}
for i in range(256):
    p = struct.unpack_from('<I', b, o + i * 4)[0]
    if not p:
        continue
    rva = p - IMG if p >= IMG else p
    po = r2o(rva)
    if po is None:
        continue
    e = b.index(b'\xff', po, po + 40)
    fmt['0x%02x' % i] = list(b[po:e])

doc = {
    'module': 'AdvHD.exe (原版发行版)',
    'table_rva': hex(TABLE_RVA),
    'image_base': hex(IMG),
    'note': 'opcode -> 类型码字节串（不含 0xff 终止符）；指针为绝对地址。'
            '已用 HOT_002/HOT_004/HUS_001 三脚本 100% 平铺验证。',
    'defined': len(fmt),
    'formats': fmt,
}

for path in ('resource/ws2_formats_orig.json', 'tmp/verify/ws2_formats_orig.json'):
    with open(path, 'w', encoding='utf-8') as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=1)
    print('written', path, 'defined=%d' % len(fmt))
