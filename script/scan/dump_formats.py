"""从 IDA 导出本作 AdvHD.exe 的 WS2 操作数格式表。

表基址 0x57ada8（.rdata），按 **原始 opcode 字节**索引，每项是 4 字节指针，
指向 .data 里一段以 0xff 结尾的类型码字节串；0 表示该 opcode 未实现。
"""
import json
import struct
import sys

import mcp

BASE = 0x57ADA8
N = 256


def get(addr, size):
    r = mcp.call('get_bytes', {'regions': [{'addr': hex(addr), 'size': size}]})
    return bytes(int(x, 16) for x in r['result'][0]['data'].split())


def main():
    tbl = get(BASE, N * 4)
    ptrs = [struct.unpack_from('<I', tbl, i * 4)[0] for i in range(N)]
    # 批量取所有格式串：先取所有非零指针的最小/最大范围，再切片
    nz = [p for p in ptrs if p]
    lo, hi = min(nz), max(nz) + 16
    blob = get(lo, hi - lo)
    out = {}
    for i, p in enumerate(ptrs):
        if not p:
            continue
        off = p - lo
        end = blob.index(0xff, off)
        out['0x%02x' % i] = list(blob[off:end])
    print('opcodes defined: %d / %d' % (len(out), N))
    print('0x82 ->', out.get('0x82'))
    print('0x14 ->', out.get('0x14'))
    with open(sys.argv[1] if len(sys.argv) > 1 else 'ws2_formats_fd.json', 'w', encoding='utf-8') as fh:
        json.dump({'base': hex(BASE), 'module': 'AdvHD.exe.unpacked.exe',
                   'note': 'opcode -> 类型码字节串（不含 0xff 终止符）',
                   'formats': out}, fh, ensure_ascii=False, indent=1)
    print('written')


if __name__ == '__main__':
    main()
