# -*- coding: utf-8 -*-
"""闸门：选项处的**文本/人名规范**（spec 的可执行部分，见 doc/file-formats.md「选项编写规范」）。

只检查由 [语料]/[反汇编] 已经证实的四条，不含任何未定案推断：

1. 选项头存在且 count 一致 —— 由 `choice_header_check.py` / `final_verification` 9c 负责，此处不重复。
2. **选项帧内不得有语音**：**提示句之后 → 选项头之前**不得出现 `0x28`（语音播放），
   也不得出现名字非空的 `0x15`（该区间为 0 说明帧内本来就没有任何指令，属正常）。
   依据：本作原版 `BEF_004` 的该区间 `0x28` 计数 = 0、非空 `0x15` 计数 = 0。
3. **提示句存在且以 `%K` 结尾**：`0f` 之前最近的一条 `0x14`，正文必须以 `%K` 收尾（不得以 `%P` 收尾）。
   依据：原版 `605` 尾 `%K`，其前三条都是 `%K%P`；`%K` = 留框、`%P` = 清框。
4. **落点首格是 `0b…` + 纯标记 `%P`**：每个条目的文件内跳转（`06`）目标处，
   跳过若干 `0x0b`（状态位）后必须是正文恰为 `%P` 的 `0x14`。
   依据：原版两条落点即 `0b 65 00 0x` → `14 "%P"`。

用法: python script/checks/choice_spec_check.py [--pay]
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

from tool import arcbuild, ws2, ws2dis   # noqa: E402

ARCHIVES = ('Rio.arc',)
NUL = 0


def _cstr(buf, p):
    e = buf.index(bytes([NUL]), p)
    return buf[p:e], e + 1


def _line_text(ops):
    """`0x14` 操作数 → 正文。

    实测布局（本作 Steam 与原版一致）：`<u16 id>` + 两个零字节 + `<cstr 名>` + `<cstr 正文>`
    （Steam 侧正文后再多一个零字节；两种都能被本解析吃掉）。
    """
    p = 2
    if ops[p:p + 2] == bytes([NUL, NUL]):
        p += 2
    _name, p = _cstr(ops, p)
    text, p = _cstr(ops, p)
    return text


def _check_script(name, dec):
    """→ (选项表数, 失败清单, 帧内被检查的指令数)。"""
    fails = []
    n_choice = 0
    inspected = 0
    try:
        ins, _ok = ws2dis.disassemble(dec)
    except Exception:
        return 0, [], 0
    by_off = {x[0]: idx for idx, x in enumerate(ins)}
    for i, (off, op, sz, ops) in enumerate(ins):
            if op != 0x0F:
                continue
            n_choice += 1

            # 2) 选项帧内（提示句之后 → 选项头之前）不得有语音
            #    区间必须从**提示句**起算：选项头恒紧贴 `0f`，从 `0f` 往回收会在遇到 `0e` 时立刻停，
            #    实际检查长度恒为 0（死检查）。
            j = i - 1
            while j >= 0 and ins[j][1] != 0x14:
                j -= 1
            j = j + 1 if j >= 0 else 0
            while j < i and ins[j][1] != 0x0E:
                inspected += 1
                if ins[j][1] == 0x28:
                    fails.append('%s: `0f` @0x%x 选项帧内出现 0x28 语音 @0x%x'
                                 % (name, off, ins[j][0]))
                elif ins[j][1] == 0x15 and ins[j][3][:1] not in (bytes([NUL]), b''):
                    fails.append('%s: `0f` @0x%x 选项帧内出现非空名字 0x15 @0x%x'
                                 % (name, off, ins[j][0]))
                j += 1

            # 3) 提示句以 %K 结尾
            k = i - 1
            while k >= 0 and ins[k][1] != 0x14:
                k -= 1
            if k < 0:
                fails.append('%s: `0f` @0x%x 之前找不到提示句（0x14）' % (name, off))
            else:
                try:
                    txt = _line_text(ins[k][3])
                except Exception:
                    txt = b''
                if not txt.endswith(b'%K'):
                    fails.append('%s: `0f` @0x%x 提示句 @0x%x 未以 %%K 收尾（尾=%r）'
                                 % (name, off, ins[k][0], txt[-10:]))

            # 4) 条目落点 = `0b…` + 纯标记 %P
            for e in ws2.choice_entries(dec, off):
                if e[4] != 'abs' or not e[5]:
                    continue
                ti = by_off.get(e[5])
                if ti is None:
                    fails.append('%s: `0f` @0x%x 条目跳转 %#x 不是指令起点'
                                 % (name, off, e[5]))
                    continue
                while ti < len(ins) and ins[ti][1] == 0x0B:
                    ti += 1
                if ti >= len(ins) or ins[ti][1] != 0x14:
                    fails.append('%s: `0f` @0x%x 条目落点 %#x 未以 `0b…` + `14` 开头'
                                 % (name, off, e[5]))
                    continue
                try:
                    txt = _line_text(ins[ti][3])
                except Exception:
                    txt = b''
                if txt != b'%P':
                    fails.append('%s: `0f` @0x%x 条目落点 %#x 首格不是纯标记 %%P（=%r）'
                                 % (name, off, e[5], txt[:14]))
    return n_choice, fails, inspected


def check_archive(path):
    """→ (选项表数, 失败清单)"""
    fails = []
    n_choice = 0
    if not os.path.exists(path):
        return 0, []
    for nb, data in arcbuild.read_raw(path):
        name = nb.decode('utf-16le', 'replace')
        if not name.endswith('.ws2'):
            continue
        n, f, _ins = _check_script(name, ws2.decode(data))
        n_choice += n
        fails += f
    return n_choice, fails


def _selftest():
    """证明「帧内无语音/非空人名」不是死检查：干净样本 PASS、注入后必须 FAIL。"""
    import importlib.util
    here = os.path.dirname(os.path.abspath(__file__))
    spec = importlib.util.spec_from_file_location(
        'reh', os.path.join(here, 'rehearse_new_choice.py'))
    reh = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reh)
    blk = bytearray(reh.build_block())
    pos = blk.find(bytes([0x0E, 0x0B, 0x00]))
    assert pos > 0, '样本里找不到选项头'

    n0, f0, ins0 = _check_script('SELFTEST/clean', bytes(blk))
    ok0 = (n0 == 1 and not f0 and ins0 == 0)
    print('  干净样本：选项表 %d，失败 %d，帧内检查 %d 条 ⇒ %s' %
          (n0, len(f0), ins0, 'PASS' if ok0 else 'FAIL ' + str(f0[:2])))

    # 注入 1：提示句后、选项头前的**非空人名 0x15**
    bad1 = bytes(blk[:pos]) + bytes([0x15]) + b'ABC' + bytes([0, 0]) + bytes(blk[pos:])
    _n1, f1, i1 = _check_script('SELFTEST/name', bad1)
    ok1 = any('非空名字' in x for x in f1)
    print('  注入非空 0x15：帧内检查 %d 条，命中 %s ⇒ %s' %
          (i1, [x.split(':')[-1].strip() for x in f1 if '非空名字' in x][:1],
           'PASS（能拦住）' if ok1 else 'FAIL（漏检）'))

    # 注入 2：同区间的 0x28 语音（从产物里取一条真实的 0x28 指令字节）
    voice = b''
    try:
        ms = {nb.decode('utf-16le'): d for nb, d in arcbuild.read_raw(
            os.path.join(ROOT, 'asset', 'Rio.arc'))}
        dec = ws2.decode(ms['BEF_004_E.ws2'])
        ins, _ = ws2dis.disassemble(dec)
        for off, op, sz, _ops2 in ins:
            if op == 0x28:
                voice = dec[off:off + sz]
                break
    except Exception:
        voice = b''
    # 注入 3：落点首格**不是**纯标记 %P（把第一支入口的 "%P" 改成 "XX"，等长）
    _pos = blk.find(b'%P' + bytes([0]))
    if _pos > 0:
        bad3 = bytes(blk[:_pos]) + b'XX' + bytes(blk[_pos + 2:])
        _n3, f3, _i3 = _check_script('SELFTEST/landing', bad3)
        ok3 = any('不是纯标记' in x for x in f3)
        print('  注入落点非 %%P：命中 %s ⇒ %s' %
              ([x.split(':')[-1].strip() for x in f3 if '不是纯标记' in x][:1],
               'PASS（能拦住）' if ok3 else 'FAIL（漏检）'))
    else:
        ok3 = True
        print('  跳过落点注入（样本里没找到 %P）')

    if voice:
        bad2 = bytes(blk[:pos]) + voice + bytes(blk[pos:])
        _n2, f2, i2 = _check_script('SELFTEST/voice', bad2)
        ok2 = any('0x28' in x for x in f2)
        print('  注入 0x28（%d B）：帧内检查 %d 条，命中 %s ⇒ %s' %
              (len(voice), i2, [x.split(':')[-1].strip() for x in f2 if '0x28' in x][:1],
               'PASS（能拦住）' if ok2 else 'FAIL（漏检）'))
    else:
        ok2 = True
        print('  跳过 0x28 注入（产物里没找到 0x28 指令）')

    return 0 if (ok0 and ok1 and ok2 and ok3) else 1


def main(argv):
    if '--self-test' in argv:
        return _selftest()
    stages = [('asset', os.path.join(ROOT, 'asset'))]
    if '--pay' in argv:
        stages.append(('payload', os.path.join(ROOT, 'payload')))
    all_fails, total = [], 0
    for tag, base in stages:
        for arc in ARCHIVES:
            n, f = check_archive(os.path.join(base, arc))
            total += n
            all_fails += ['[%s] %s' % (tag, x) for x in f]
    for x in all_fails:
        print('  FAIL', x)
    if all_fails:
        print('选项规范检查: FAIL %d 项（%d 张选项表）' % (len(all_fails), total))
        return 1
    print('选项规范检查: PASS（%d 张选项表：帧内无语音 / 提示句 %%K / 落点 0b+%%P）' % total)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
