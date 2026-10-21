# -*- coding: utf-8 -*-
"""演练工具：往一个**未改动**的 Steam 脚本里**新增**一张两选项，验证规则可复用。

不碰 asset/、不碰游戏目录：只读 `backup/Rio.arc` 的成员，把新选项插到脚本开头，
产物写到 `tmp/rehearsal/<member>`，再用生产同款校验器自检：

  1. 线性反汇编自洽（恰好在 0xff 收尾、其后仅尾表 8 字节）；
  2. 所有绝对偏移（`01` 字段 7/11、`02`/`06` 字段 0、`0f` 条目 `06`）落在指令起点；
  3. 选项头存在、形态与 count 一致；
  4. 标记规范：提示句尾 `%K`、落点 `0b…` + 纯 `%P`；
  5. 槽位：`0x14` 数与选项条目数各自增加应增加的量。

插入内容（与原版 BEF_004 同形）：

    14 提示句（尾 %K）
    0e 0b 00 02 00 01
    0f 02
      条目A → 0b 65 00 00 → 14 "%P" → 14 "分岐1" → 06 → 汇合点
      条目B → 0b 65 00 01 → 14 "%P" → 14 "分岐2" → 落到汇合点
    汇合点 = 原脚本第一句（整体后移）
"""
import os
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

from tool import arcbuild, ws2, ws2dis          # noqa: E402
from tool.ws2conv import REBASE_OPS             # noqa: E402

TARGET = os.environ.get('REHEARSE_MEMBER', 'BEF_003_E.ws2')
OUTDIR = os.path.join(ROOT, 'tmp', 'rehearsal')
Z = b'\x00'
TWO_Z = b'\x00\x00'


def line(text, cid=0):
    """`14 <u16 id> 00 00 "char" 00 <text> 00 00`（Steam 形态：正文后再多一个 0）"""
    return (bytes([0x14]) + struct.pack('<H', cid) + TWO_Z + b'char' + Z
            + text.encode('cp932') + Z + Z)


def build_block():
    """→ 新块字节。整块插在偏移 0，所以块内偏移 == 流内绝对偏移。"""
    body = bytearray()

    def put(b):
        body.extend(b)

    put(line('選んでください%K'))
    put(bytes([0x0E, 0x0B, 0x00, 0x02, 0x00, 0x01]))
    put(bytes([0x0F, 0x02]))

    def entry(text, label):
        put(struct.pack('<H', 0))                    # strid 占位（收尾统一 repool）
        put(text.encode('cp932') + Z)
        put(struct.pack('<H', label) + Z)            # label u16 + 一个 0
        put(bytes([0x06]))
        at = len(body)
        put(b'\x00\x00\x00\x00')
        return at

    j1 = entry('選択肢A', 0x0180)
    j2 = entry('選択肢B', 0x0180)

    t1 = len(body)
    put(bytes([0x0B]) + struct.pack('<H', 101) + Z)
    put(line('%P'))
    put(line('分岐1です。%K%P'))
    put(bytes([0x06]))
    exit_at = len(body)
    put(b'\x00\x00\x00\x00')

    t2 = len(body)
    put(bytes([0x0B]) + struct.pack('<H', 101) + bytes([0x01]))
    put(line('%P'))
    put(line('分岐2です。%K%P'))

    merge = len(body)                                 # = 原脚本起点
    struct.pack_into('<I', body, j1, t1)
    struct.pack_into('<I', body, j2, t2)
    struct.pack_into('<I', body, exit_at, merge)
    return bytes(body)


def build(member=None):
    """→ (成员名, 编码后的新成员字节（含对齐的尾表）, 统计 dict)。"""
    member = member or TARGET
    ms = {nb.decode('utf-16le', 'replace'): d for nb, d in arcbuild.read_raw('backup/Rio.arc')}
    if member not in ms:
        raise SystemExit('目标成员不存在: %s' % member)
    old = ws2.decode(ms[member])
    ins, ok = ws2dis.disassemble(old)
    if not ok:
        print('原脚本线性解析不自洽，换目标')
        return 1
    starts = {x[0] for x in ins}
    n14 = sum(1 for x in ins if x[1] == 0x14)
    nch = sum(x[3][0] for x in ins if x[1] == 0x0F)

    blk = build_block()
    delta = len(blk)
    new = bytearray(blk) + bytearray(old)

    for off, op, size, ops in ins:
        base = off + delta + 1
        for k in REBASE_OPS.get(op, ()):
            if len(ops) < k + 4:
                continue
            v = struct.unpack_from('<I', ops, k)[0]
            if not v:
                continue
            assert v in starts, '原脚本 op %#x 目标 %#x 不在指令起点' % (op, v)
            struct.pack_into('<I', new, base + k, v + delta)
        if op == 0x0F:
            for e in ws2.choice_entries(old, off):
                if e[4] == 'abs' and e[5]:
                    struct.pack_into('<I', new, e[3] + delta, e[5] + delta)

    new = ws2.repool_text_ids(bytes(new))
    # 尾表：末尾 8 字节明文 [消息数][选项条目数] 必须等于实算（§47：偏小 ⇒ 写位越界 ⇒ 闪退）
    counts = ws2.tail_counts(new)
    raw = ws2.set_tail_counts(ws2.encode(new), counts)
    ok_tail, bad_tail = ws2.check_tails({member: raw})
    assert ok_tail, '尾表未对齐（%s）：%s' % (member, bad_tail)

    # ── 自检（生产同款判据）──
    ins2, ok2 = ws2dis.disassemble(new)
    starts2 = {x[0] for x in ins2}
    fails = []
    if not ok2:
        fails.append('线性解析未在 0xff 收尾 / 尾表异常')
    n14b = sum(1 for x in ins2 if x[1] == 0x14)
    nchb = sum(x[3][0] for x in ins2 if x[1] == 0x0F)
    for off, op, size, ops in ins2:
        for k in REBASE_OPS.get(op, ()):
            if len(ops) < k + 4:
                continue
            v = struct.unpack_from('<I', ops, k)[0]
            if v and v not in starts2:
                fails.append('op %#x @0x%x 字段 %d → %#x 不在指令起点' % (op, off, k, v))
        if op != 0x0F:
            continue
        ents = ws2.choice_entries(new, off)
        if len(ents) != ops[0]:
            fails.append('0f @0x%x 条目数 %d != count %d' % (off, len(ents), ops[0]))
        for e in ents:
            if e[4] == 'abs' and e[5] and e[5] not in starts2:
                fails.append('0f @0x%x 条目 → %#x 不在指令起点' % (off, e[5]))
    for i, (off, op, size, ops) in enumerate(ins2):
        if op != 0x0F:
            continue
        if i == 0 or ins2[i - 1][1] != 0x0E:
            fails.append('0f @0x%x 缺选项头' % off)
            continue
        h = ins2[i - 1][3]
        if h[0] != 0x0B or h[1] != 0 or h[3] != 0 or h[4] != 1 or h[2] != ops[0]:
            fails.append('0f @0x%x 头形态/count 不对 %s' % (off, h.hex(' ')))
        k = i - 1
        while k >= 0 and ins2[k][1] != 0x14:
            k -= 1
        if k < 0:
            fails.append('0f @0x%x 无提示句' % off)

    expect14, expect_ch = n14 + 5, nch + 2
    if n14b != expect14:
        fails.append('0x14 数 %d != 期望 %d' % (n14b, expect14))
    if nchb != expect_ch:
        fails.append('选项条目数 %d != 期望 %d' % (nchb, expect_ch))

    # 复用两个独立闸的判据（提示句 %K / 落点 0b+%P / 帧内无语音 / 跳转自洽 / 槽位等式），
    # 避免"演练自称通过"与实际闸门脱节。
    import importlib.util
    _here = os.path.dirname(os.path.abspath(__file__))

    def _load(_name, _file):
        _sp = importlib.util.spec_from_file_location(_name, os.path.join(_here, _file))
        _m = importlib.util.module_from_spec(_sp)
        _sp.loader.exec_module(_m)
        return _m

    _csc = _load('csc', 'choice_spec_check.py')
    _cjc = _load('cjc', 'choice_jump_check.py')
    _n_sp, _f_sp, _ins_sp = _csc._check_script(member, ws2.decode(raw))
    fails += ['[规范闸] ' + x for x in _f_sp]
    _f_jp, _n14c, _nchc = _cjc.check_script(member, raw)
    fails += ['[跳转/槽位闸] ' + x for x in _f_jp]
    if _n_sp != 1:
        fails.append('规范闸：选项表数 %d != 1' % _n_sp)

    if fails:
        raise SystemExit('演练自检失败（%d 项）：%s' % (len(fails), ' | '.join(fails[:6])))
    print('目标 %s：原 %d B / %d 条 0x14 / %d 个选项条目' % (member, len(old), n14, nch))
    print('插入 %d B → 新脚本 %d B；0x14=%d，选项条目=%d，槽位总数=%d'
          % (delta, len(new), n14b, nchb, n14b + nchb))
    print('演练: PASS（头/count、跳转全落点、提示句 %%K、落点 0b+%%P、槽位等式、帧内无 0x16、尾表对齐）'
          .replace('%%', '%'))
    return member, raw, {'old_len': len(old), 'delta': delta, 'n14': n14b,
                         'nch': nchb, 'tail': counts, 'inspected': _ins_sp}


def main():
    member, raw, st = build()
    os.makedirs(OUTDIR, exist_ok=True)
    outp = os.path.join(OUTDIR, member)
    open(outp, 'wb').write(raw)
    print('产物 → %s（%d B；尾表 %s）' % (outp, len(raw), st['tail']))
    return 0


if __name__ == '__main__':
    sys.exit(main())
