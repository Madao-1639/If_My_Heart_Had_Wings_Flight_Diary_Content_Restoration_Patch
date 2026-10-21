# -*- coding: utf-8 -*-
"""存档状态速查（只读）：把 `SaveNNN` 的**第 0 块**（当前状态）解成「脚本 / 台词 / 语音 / CG / 落到哪一格」。

用途：处理「某处剧情丢失 / 卡死 / 回主菜单」类反馈时，先定位玩家到底停在哪一格，再回原版同名脚本比结构。
格式（本作实测，MoeNovel AdvHD 系；与姊妹作的 `CCST` 同族，块魔数为 `IMHF`）：

    +0x00  char[4]  "IMHF"
    +0x04  u16 lo, u16 hi        （tick = hi<<16|lo，单调递增）
    +0x08  8 字节 0
    +0x10  u32 0
    +0x14  u32 台词长度（UTF-16 码元数）
    +0x18  UTF-16LE 台词正文
    之后   引擎对象图（脚本名 / %LC 说话人 / 语音名 / CG 名 / 图层名，均为 [u32 len][UTF-16LE] 串）

文件本身是**环形快照链**：第 0 块 = 最新，第 1..N-1 块 = 回溯历史（按环序 1,2,…,N-1,0 排才是时间序）。
因此第 0 块的台词就是「存档瞬间那一句」，用 语音 / CG / 台词 三锚点即可唯一定位到某一格。

⚠️ 存档**不跨补丁/跨版本可续**：本项目重写脚本后旧游标落在新脚本指令中部 ⇒ 快照能画出上一句、
点一下翻页就卡死。这不是脚本缺陷（见 doc/lessons-learned.md §46）。

用法：
    python tool/savestate.py                       # 列存档目录里全部 Save*
    python tool/savestate.py Save001               # 只看这一档（可给前缀或完整路径）
    python tool/savestate.py Save001 --history 20  # 顺带打印最近 20 块的时间序台词
"""
import glob
import os
import re
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

from tool import arcbuild, ws2, ws2dis  # noqa: E402

MAGIC = b'IMHF'
SAVE_ROOT = os.path.join(os.path.expanduser('~'), 'Saved Games', 'MoeNovel')
TEXT_OFF = 0x14
TEXT_DATA = 0x18
MAX_SCAN = 400                      # 对象串长度上限（防御性）
SCRIPT_RE = re.compile(r'^[A-Z]{3}_[0-9A-Z_]{1,12}(_E)?$')


def save_dirs():
    """只认**本引擎**的存档目录（Save* 首 4 字节 == IMHF；别的游戏目录静默跳过）。"""
    out = []
    for d in glob.glob(os.path.join(SAVE_ROOT, '*')):
        for f in glob.glob(os.path.join(d, 'Save*')):
            if not os.path.isfile(f) or re.search(r'(Favorite|GS)$', f):
                continue
            with open(f, 'rb') as fh:
                if fh.read(4) == MAGIC:
                    out.append(d)
                    break
    return out


def strings(blob, lo, hi):
    """扫描 `[u32 len][UTF-16LE]` 串（逐字节滑窗，与姊妹作 saveadv 同法）。"""
    out, off = [], lo
    while off < hi - 4:
        n = struct.unpack_from('<I', blob, off)[0]
        if 0 < n <= MAX_SCAN and off + 4 + n * 2 <= len(blob):
            try:
                t = blob[off + 4:off + 4 + n * 2].decode('utf-16-le')
            except UnicodeDecodeError:
                t = None
            if t and all(ord(c) >= 0x20 for c in t) and any(c.isalnum() or ord(c) > 0x2000 for c in t):
                out.append(t)
                off += 4 + n * 2
                continue
        off += 1
    return out


def blocks(blob):
    offs = [m.start() for m in re.finditer(re.escape(MAGIC), blob)]
    recs = []
    for i, o in enumerate(offs):
        end = offs[i + 1] if i + 1 < len(offs) else len(blob)
        n = struct.unpack_from('<I', blob, o + TEXT_OFF)[0]
        text = ''
        if 0 < n < 4000 and o + TEXT_DATA + n * 2 <= len(blob):
            text = blob[o + TEXT_DATA:o + TEXT_DATA + n * 2].decode('utf-16-le', 'replace')
        recs.append({'idx': i, 'text': text, 'tokens': strings(blob, o, end)})
    return recs


def cells_of(member):
    """{语音名: [格号…]}、{CG/背景名: [格号…]}（格号 1 起，= 该格 `0x14` 的槽序）。"""
    ms = {nb.decode('utf-16le', 'replace'): d for nb, d in arcbuild.read_raw(os.path.join(ROOT, 'asset', 'Rio.arc'))}
    key = [k for k in ms if k.lower() == member.lower()]
    if not key:
        return {}, {}
    ins, _ok = ws2dis.disassemble(ws2.decode(ms[key[0]]))
    voice, img = {}, {}
    try:
        vfmt = __import__('tool.ws2fmt', fromlist=['Table']).Table(
            os.path.join(ROOT, 'resource', 'ws2_formats.json'))
        ins = __import__('tool.ws2fmt', fromlist=['disassemble']).disassemble(ws2.decode(ms[key[0]]), vfmt)
    except Exception:
        return voice, img
    cell = 0
    pend_v = pend_i = None
    for _off, op, _sz, f in ins:
        args = f.get('args') or []
        if op == 0x28:
            ogg = [x for x in args if isinstance(x, str) and x.upper().endswith('.OGG')]
            pend_v = ogg[0] if ogg else pend_v
        elif op == 0x33:
            s = [x for x in args if isinstance(x, str) and x.upper().endswith('.PNG')]
            pend_i = s[-1] if s else pend_i
        elif op == 0x14:
            cell += 1
            if pend_v:
                voice.setdefault(pend_v.upper(), []).append(cell)
                pend_v = None
            if pend_i:
                img.setdefault(pend_i.upper(), []).append(cell)
    return voice, img


def describe(path, history=0):
    blob = open(path, 'rb').read()
    recs = blocks(blob)
    if not recs:
        print('%s: 找不到 IMHF 块' % os.path.basename(path))
        return
    cur = recs[0]
    toks = cur['tokens']
    scripts = [t for t in toks if SCRIPT_RE.match(t)]
    ogg = sorted({t for t in toks if t.upper().endswith('.OGG')})
    png = sorted({t for t in toks if t.upper().endswith('.PNG')})
    lc = [t for t in toks if t.startswith('%LC')]
    print('== %s（%d 块，%d B）' % (os.path.basename(path), len(recs), len(blob)))
    print('   脚本   : %s' % (' / '.join(dict.fromkeys(scripts)) or '?'))
    print('   台词   : %r' % cur['text'])
    print('   说话人 : %s' % (' / '.join(dict.fromkeys(lc)) or '-'))
    print('   语音   : %s' % (', '.join(ogg) or '-'))
    print('   CG/BG  : %s' % (', '.join(png[:6]) or '-'))
    guessed = []
    for sc in dict.fromkeys(scripts):
        voice, img = cells_of(sc + '.ws2')
        if not voice and not img:
            continue
        hits = []
        for v in ogg:
            hits += [('voice ' + v, c) for c in voice.get(v.upper(), [])]
        for p in png:
            hits += [('cg ' + p, c) for c in img.get(p.upper(), [])]
        if hits:
            cols = [c for _n, c in hits]
            guess = max(set(cols), key=cols.count)
            span = sorted({c for _n, c in hits})
            guessed.append('%s 第 %d 格（命中 %s；近邻 %s…%s）'
                           % (sc, guess, ', '.join(sorted({n for n, _c in hits})[:4]),
                              span[0], span[-1]))
    print('   定位   : %s' % ('；'.join(guessed) or '（未命中 asset 脚本，可能是别的版本/补丁的存档）'))
    if history:
        chron = recs[1:] + recs[:1]
        print('   历史（最近 %d 句，旧→新）:' % min(history, len(chron)))
        for r in chron[-history:]:
            print('     [%3d] %r' % (r['idx'], r['text']))


def main(argv):
    history, args, i = 0, [], 0
    while i < len(argv):
        if argv[i] == '--history':
            history = int(argv[i + 1]) if i + 1 < len(argv) else 20
            i += 2
            continue
        args.append(argv[i])
        i += 1
    dirs = save_dirs()
    if not dirs:
        print('存档目录未找到：%s' % SAVE_ROOT)
        return 2
    pats = []
    for d in dirs:
        files = sorted(glob.glob(os.path.join(d, 'Save*')))
        files = [f for f in files if not re.search(r'(Favorite|GS)$', f) and os.path.isfile(f)
                 and open(f, 'rb').read(4) == MAGIC]
        pats += files
    if args:
        pats = [p for p in pats if args[0].lower() in os.path.basename(p).lower()] or \
               [p for p in args if os.path.isfile(p)]
    if not pats:
        print('没有匹配的存档')
        return 1
    for p in pats:
        describe(p, history)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
