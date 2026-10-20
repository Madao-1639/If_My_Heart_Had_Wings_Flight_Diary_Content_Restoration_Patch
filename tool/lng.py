"""AdvHD .lng localization container codec.

Layout (verified byte-exact round-trip):
    u32                 count
    u16 * count         per-string byte length (includes the trailing NUL pair)
    bytes               count strings, back-to-back, no padding

Each string is UTF-16LE XORed with a single-byte key. 密钥**不是引擎常量，按作标定**。
已知观测值：

    0x3E  《Flight Diary》(本作) —— Steam 官方 `zh-CN/Rio.arc` 的 50 个逐脚本 .lng
          与 `zh-CN/Rio1.arc` 的 8 个 .lng（2026-10-13 实测，条目与 Steam 英文脚本
          台词严格对应，零解码失败）
    0x88  姊妹作《在这苍穹展翅》Steam 官方简体中文 `zh-CN/Rio.arc`
    0xCE  姊妹作 oozora_CHSpatch 汉化补丁的 lng

读档拿不准用哪个 key 时用 detect_key()，写档必须显式传 key。
"""
import struct

KEY_FD = 0x3E          # 本作 Flight Diary
KEY_STEAM_ZHCN = 0x88  # 姊妹作《在这苍穹展翅》
KEY_OOZORA = 0xCE      # 姊妹作 oozora 汉化补丁


def _table(key):
    return bytes(c ^ key for c in range(256))


def parse_lng(raw, key=KEY_FD):
    """Return the list of decoded strings (trailing NUL stripped).

    key 必须与数据源匹配：本作 Flight Diary 用 KEY_FD（0x3E）。key 用错时
    多数条目会直接抛 UnicodeDecodeError，但也可能静默解出乱码——拿不准先
    detect_key()。
    """
    count = struct.unpack_from('<I', raw, 0)[0]
    lens = struct.unpack_from('<%dH' % count, raw, 4)
    off = 4 + 2 * count
    if off + sum(lens) != len(raw):
        raise ValueError('lng length table does not cover payload')
    tab = _table(key)
    out = []
    for length in lens:
        chunk = raw[off:off + length]
        off += length
        out.append(chunk.translate(tab).decode('utf-16le').rstrip('\0'))
    return out



def parse_lng_tolerant(raw, key=KEY_FD):
    """parse_lng 的容错版：长度表覆盖之外的**尾部残留**按 count 截断后解析。

    官方 `CO1_003.lng`/`CO2_002.lng` 的长度表外各有 20/6 字节残留（见 doc/file-formats.md），
    count 与脚本行数严格一致 ⇒ 截断即可，别把尾巴当第 count+1 条。
    """
    count = struct.unpack_from('<I', raw, 0)[0]
    lens = struct.unpack_from('<%dH' % count, raw, 4)
    off = 4 + 2 * count
    need = sum(lens)
    if off + need > len(raw):
        raise ValueError('lng length table exceeds payload')
    raw = raw[:off + need]
    return parse_lng(raw, key)

def detect_key(raw):
    """Guess the XOR key of an lng blob.

    两个候选 key 都解一遍：优先选零解码失败者；都无法区分时（两 key 均
    零失败/均失败）退回 CJK 字符占比更高者。仅用于读入未知来源的 lng，
    写档不要依赖猜测结果。
    """
    def score(key):
        bad = 0
        cjk = 0
        total = 0
        for s in parse_lng_lenient(raw, key):
            total += 1
            cjk += sum(1 for c in s if '\u4e00' <= c <= '\u9fff')
        return bad, cjk / max(total, 1)

    results = {}
    for key in (KEY_FD, KEY_STEAM_ZHCN, KEY_OOZORA):
        try:
            results[key] = score(key)
        except Exception:
            results[key] = (10 ** 9, 0.0)
    best = min(results, key=lambda k: (results[k][0], -results[k][1]))
    return best


def parse_lng_lenient(raw, key):
    """parse_lng 但对解码失败的单条字符串用 replace 容错（供检测/统计用）。"""
    count = struct.unpack_from('<I', raw, 0)[0]
    lens = struct.unpack_from('<%dH' % count, raw, 4)
    off = 4 + 2 * count
    if off + sum(lens) != len(raw):
        raise ValueError('lng length table does not cover payload')
    tab = _table(key)
    out = []
    for length in lens:
        chunk = raw[off:off + length]
        off += length
        out.append(chunk.translate(tab).decode('utf-16le', 'replace').rstrip('\0'))
    return out


def encode_lng(strings, key=KEY_FD):
    """Inverse of parse_lng."""
    tab = _table(key)
    blobs = [(s + '\0').encode('utf-16le').translate(tab) for s in strings]
    out = bytearray(struct.pack('<I', len(blobs)))
    for blob in blobs:
        if len(blob) > 0xffff:
            raise ValueError('string exceeds u16 length field')
        out += struct.pack('<H', len(blob))
    for blob in blobs:
        out += blob
    return bytes(out)


NAMETABLE = 'NameTable.txt'


def load_nametable(game_dir):
    """读官方 `NameTable.txt` → (text, archive_path)。

    **遵循原生存放方式**：不搬位、不另建副本，返回官方包实际放置该成员的那个
    归档路径。引擎的语言包是「叠加覆盖」语义 ⇒ 查找顺序＝语言包优先、基础档兜底
    （两者都有时语言包生效）：

    1. `<game_dir>/zh-CN/Rio.arc`（官方范式通常在这里）
    2. `<game_dir>/Rio.arc`（本作 Flight Diary 原生就在这里，zh-CN 只有 `.lng`）

    需要修改/生成该表时，写回**本函数返回的同一归档**，不得搬到另一侧。
    """
    import os
    from tool import arcbuild

    for rel in (os.path.join('zh-CN', 'Rio.arc'), 'Rio.arc'):
        path = os.path.join(game_dir, rel)
        if not os.path.exists(path):
            continue
        for nb, data in arcbuild.read_raw(path):
            if nb.decode('utf-16le', 'replace') == NAMETABLE:
                return data.decode('utf-16le'), path
    raise SystemExit('缺 %s：已查 %s/zh-CN/Rio.arc 与 %s/Rio.arc'
                     % (NAMETABLE, game_dir, game_dir))
