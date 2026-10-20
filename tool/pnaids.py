"""`0x39` 子图层记录号的解析/改写与 PNA 记录映射加载。

口径（见 `doc/pna-resources.md`）：
`0x39` 操作数 = `<通道名 cstr>` + 3 字节头 + `条数 u8` + 条数 × `u16 记录号`；
记录号是 **PNA 记录下标（0 基，含哨兵/空记录）**。两侧同名 PNA 的记录表可能
不同（Steam 删哨兵、加层、重排）⇒ 原版来源块的记录号必须按
`resource/pna_id_map.json` 换算成 Steam 记录号。
"""
import json
import os
import struct

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAP_PATH = os.path.join(ROOT, 'resource', 'pna_id_map.json')


def load_map(path=MAP_PATH):
    """→ {成员名大写: {原版记录号(int): Steam 记录号(int)}}。"""
    if not os.path.exists(path):
        raise SystemExit('缺 %s（先跑 script/build/build_pna_id_map.py --write）' % path)
    d = json.load(open(path, encoding='utf-8'))
    out = {}
    for nm, rec in (d.get('members') or {}).items():
        out[nm.upper()] = {int(k): int(v) for k, v in (rec.get('map') or {}).items()}
    return out


def parse_039(ops):
    """`0x39` 操作数 → (chan, head3, ids)；布局不合法返回 None。"""
    q = ops.find(b'\x00')
    if q < 0:
        return None
    try:
        chan = ops[:q].decode('cp932')
    except UnicodeDecodeError:
        return None
    rest = ops[q + 1:]
    if len(rest) < 3:
        return None
    n = rest[2]
    if 3 + 2 * n > len(rest):
        return None
    ids = [struct.unpack_from('<H', rest, 3 + 2 * k)[0] for k in range(n)]
    return chan, rest[:3], ids


def rebuild_039(chan, head3, ids):
    out = bytearray(chan.encode('cp932') + b'\x00' + head3)
    for i in ids:
        out += struct.pack('<H', i)
    return bytes(out)


def rewrite_039(ops, rec_map):
    """按 rec_map 改写一条 `0x39` 操作数。

    返回 `(new_ops, n_rewritten, unmapped)`；布局不合法时 `(ops, 0, [])`。
    `unmapped` 列出在 rec_map 里找不到的原版记录号（调用方必须视为错误）。
    """
    p = parse_039(ops)
    if p is None:
        return ops, 0, []
    chan, head3, ids = p
    new, changed, miss = [], 0, []
    for i in ids:
        j = rec_map.get(i)
        if j is None:
            new.append(i)
            miss.append(i)
        else:
            new.append(j)
            if j != i:
                changed += 1
    if not changed and not miss:
        return ops, 0, []
    return rebuild_039(chan, head3, new), changed, miss
