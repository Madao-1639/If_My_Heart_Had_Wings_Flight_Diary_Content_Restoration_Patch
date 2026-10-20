# -*- coding: utf-8 -*-
"""全量验收（FD 移植版）——route §5 的验收项。

1  归档完整性        ：asset/ 的交付归档全部过 arcbuild.verify()，且集合 == 交付名单
2  调用链完整性      ：产物 Rio 的 07/02 目标可达（Rio ∪ Rio1 ∪ TITLE/EVRET ∪ 数字/十六进制 label；
                       `SL_*` 后日谈脚本与 `DEBG01` 调试脚本为 Steam 未交付项，豁免）
3  成就触发点完整性  ：CG_ACHIEVEMENT 723 处 + 0xF0 触发 33 处，逐脚本与 backup 相同
4  资源配对正确性    ：0x33/0x34/0x28/0x1E 引用可解析（交付归档取 asset，未交付者取 backup）
5  零破坏性          ：同名成员替换只允许落在「计划脚本 / lng / L4 交付 / censor 覆盖名单」内；
                      覆盖名单条数 == 实际替换数
6  可复现性          ：asset 哈希 == payload/METADATA.json（`--stage build` 时 payload 未按
                      本次产物重建 ⇒ 明确 SKIP；`--stage release` 时强制）
7  实机测试          ：人工（打印清单）
8  交付项完整性      ：AGS_001（脚本+lng）、24 个宿主 lng 条数 == 槽数、L4 两处 pna、
                      Script.arc Lua、orig 来源槽的语音成员全部在位
9  WS2 线性自洽      ：产物全部 ws2 恰好在 0xff 收尾（本作无尾表）
10 语音重指          ：`resource/voice_repoint_manual.json` 存在时逐条验 token/字节；本作无表 ⇒ 跳过

任一 FAIL ⇒ 退出码 1。明细写 tmp/final_verification.md。
"""
import argparse
import collections
import hashlib
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tool import arcbuild, ws2, ws2dis, lng, paths, pna  # noqa: E402

ASSET = os.path.join(ROOT, 'asset')
BACKUP = os.path.join(ROOT, 'backup')
SHIPPED_ARCHIVES = ['Chip1.arc', 'Chip2.arc', 'Chip7.arc', 'Chip8.arc', 'Chip9.arc',
                    'Graphic.arc', 'Rio.arc', 'Script.arc', 'Se.arc', 'SysGraphic.arc',
                    'Voice.arc', 'zh-CN/Rio.arc', 'zh-CN/SysGraphic.arc']
# 未交付归档（与 backup 无差异，玩家原档即 Steam 自带）：只用于资源解析
UNDELIVERED = ['Bgm.arc', 'Chip3.arc', 'Chip4.arc', 'Chip5.arc', 'Chip6.arc', 'Chip10.arc',
               'Effect.arc', 'Rio1.arc', 'SysVoice.arc']
EXPECT_HOOKS = 723
EXPECT_F0 = 33
TARGET_EXEMPT = {'DEBG01'}          # 调试脚本，两版都不交付
TARGET_EXEMPT_PREFIX = ('SL_',)     # Steam 未交付的后日谈脚本（mainmenu 仍留调用）

fails = []
skips = []
lines = []


def check(name, ok, detail=''):
    lines.append('[%s] %s %s' % ('PASS' if ok else 'FAIL', name, detail))
    if not ok:
        fails.append(name)
    return ok


def skip(name, detail=''):
    lines.append('[SKIP] %s %s' % (name, detail))
    skips.append(name)


def read_members(path):
    return {nb.decode('utf-16le', 'replace'): d for nb, d in arcbuild.read_raw(path)}


def asset_arcs():
    out = set()
    for dirpath, _dirs, files in os.walk(ASSET):
        for fn in files:
            if fn.lower().endswith('.arc'):
                out.add(os.path.relpath(os.path.join(dirpath, fn), ASSET).replace('\\', '/'))
    return out


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def main(argv=None):
    ap = argparse.ArgumentParser(description='FD 全量验收')
    ap.add_argument('--stage', choices=('build', 'release'), default='build')
    args = ap.parse_args(argv)

    plan = json.load(open(os.path.join(ROOT, 'resource', 'restore_plan.json'), encoding='utf-8'))
    slots_all = json.load(open(os.path.join(ROOT, 'resource', 'slot_sources.json'), encoding='utf-8'))
    orig_dir = paths.orig_dir()

    # ── 1. 归档完整性 ──
    for arch in SHIPPED_ARCHIVES:
        p = os.path.join(ASSET, arch)
        if not os.path.exists(p):
            check('1 交付归档存在 %s' % arch, False)
            continue
        try:
            arcbuild.verify(p)
            check('1 verify %s' % arch, True)
        except Exception as ex:
            check('1 verify %s' % arch, False, str(ex))
    surplus = asset_arcs() ^ set(SHIPPED_ARCHIVES)
    check('1 asset 归档集合 == 交付名单（无未改动文件）', not surplus, str(sorted(surplus)))

    rio = read_members(os.path.join(ASSET, 'Rio.arc'))
    zh = read_members(os.path.join(ASSET, 'zh-CN', 'Rio.arc'))
    backup_rio = read_members(os.path.join(BACKUP, 'Rio.arc'))
    rio1 = read_members(os.path.join(BACKUP, 'Rio1.arc'))

    # ── 2. 调用链完整性 ──
    known = set()
    for n in rio:
        if n.lower().endswith('.ws2'):
            b = n[:-4].upper()
            known.add(b)
            if b.endswith('_E'):
                known.add(b[:-2])
    for n in rio1:
        if n.lower().endswith('.ws2'):
            known.add(n[:-4].upper())
    known |= {'TITLE', 'EVRET'}
    missing = set()
    for n, d in rio.items():
        if not n.lower().endswith('.ws2'):
            continue
        # 按**指令**取跳转目标：直接在解码流里正则会被二进制数据里的 0x02/0x07
        # 假命中（如 AFT_006_3 的 "CEEV"）。
        for _off, op, _sz, ops in ws2dis.disassemble(ws2.decode(d), formats=ws2dis.FORMATS)[0]:
            if op not in (0x07, 0x02):
                continue
            parts = [x for x in ops.split(b'\x00') if x]
            if not parts:
                continue
            t = parts[0].decode('ascii', 'replace').upper()
            if op == 0x02:                     # 数字 label（如 7c），不是脚本名
                continue
            if t in known or t.isdigit() or t in TARGET_EXEMPT or t.startswith(TARGET_EXEMPT_PREFIX):
                continue
            missing.add((n[:-4], t))
    check('2 调用链（07/02 目标可达）', not missing, str(sorted(missing)[:6]))

    # ── 3. 成就触发点 ──
    hooks = sum(ws2.decode(d).count(b'\x04CG_ACHIEVEMENT\x00')
                for n, d in rio.items() if n.lower().endswith('.ws2'))
    f0 = 0
    for n, d in rio.items():
        if not n.lower().endswith('.ws2'):
            continue
        ins, _ok = ws2dis.disassemble(ws2.decode(d), formats=ws2dis.FORMATS)
        f0 += sum(1 for i in ins if i[1] == 0xF0)
    check('3 成就钩子 %d 处' % EXPECT_HOOKS, hooks == EXPECT_HOOKS, '实测 %d' % hooks)
    check('3 成就触发 0xF0 共 %d 处' % EXPECT_F0, f0 == EXPECT_F0, '实测 %d' % f0)
    hook_diff = []
    for n, d in rio.items():
        if not n.lower().endswith('.ws2') or n not in backup_rio:
            continue
        ca = ws2.decode(d).count(b'\x04CG_ACHIEVEMENT\x00')
        cb = ws2.decode(backup_rio[n]).count(b'\x04CG_ACHIEVEMENT\x00')
        if ca != cb:
            hook_diff.append((n, cb, ca))
    check('3 逐脚本成就钩子与 backup 相同', not hook_diff, str(hook_diff[:6]))

    # ── 4. 资源配对 ──
    arch_names = {}
    for arch in SHIPPED_ARCHIVES:
        p = os.path.join(ASSET, arch)
        if os.path.exists(p):
            arch_names[arch] = {n.lower() for n in read_members(p)}
    for arch in UNDELIVERED:
        p = os.path.join(BACKUP, arch)
        if os.path.exists(p):
            arch_names[arch] = {n.lower() for n in read_members(p)}
    all_names = set()
    for s in arch_names.values():
        all_names |= s

    def resolve(f):
        f = f.lower().lstrip('>')
        return f in all_names

    unres = set()
    for n, d in rio.items():
        if not n.lower().endswith('.ws2'):
            continue
        for _off, op, _sz, ops in ws2dis.disassemble(ws2.decode(d), formats=ws2dis.FORMATS)[0]:
            if op not in (0x33, 0x34, 0x28, 0x1E):
                continue
            parts = [x for x in ops.split(b'\x00') if x]
            if len(parts) < 2:
                continue
            fname = parts[1].decode('cp932', 'replace').strip()
            if not fname or not re.search(r'\.(PNG|PNA|OGG)$', fname, re.I):
                continue
            if fname.upper() == 'BGM_STOP.OGG':
                continue
            if not resolve(fname):
                unres.add((n[:-4], hex(op), fname))
    check('4 资源引用全部可解析', not unres, str(sorted(unres)[:6]))

    # ── 5. 零破坏性 ──
    swapped = []
    for arch in SHIPPED_ARCHIVES:
        ap, bp = os.path.join(ASSET, arch), os.path.join(BACKUP, arch)
        if not (os.path.exists(ap) and os.path.exists(bp)):
            continue
        am, bm = read_members(ap), read_members(bp)
        for n, d in bm.items():
            if n in am and am[n] != d:
                swapped.append((arch, n))
    intended = set()
    for sc, p in plan['scripts'].items():
        member = p.get('steam_file') or p.get('target_member')
        if member:
            intended.add(('Rio.arc', member))
        if p.get('steam_file'):
            intended.add(('zh-CN/Rio.arc', p['steam_file'][:-4] + '.lng'))
    intended.add(('Script.arc', 'LegacyGame.lua'))
    intended.add(('SysGraphic.arc', 'SYS_Story.pna'))
    intended.add(('zh-CN/SysGraphic.arc', 'SYS_C_Story.pna'))
    roster = set()
    censor = json.load(open(os.path.join(ROOT, 'resource', 'censor_map.json'), encoding='utf-8'))
    for m in censor.get('members', []):
        if m.get('action') == 'overwrite':
            roster.add((m['archive'], m['name']))
    # 层内修复（PNA 记录级）：允许替换，但**必须**在表里逐记录登记；成员本身不做整名覆盖。
    layer_fix = set()
    lp = os.path.join(ROOT, 'resource', 'pna_id_map.json')
    if os.path.exists(lp):
        pm = json.load(open(lp, encoding='utf-8'))
        for nm, rec in (pm.get('members') or {}).items():
            if rec.get('repair'):
                layer_fix.add(('Graphic.arc', nm))
    allowed = {(a.lower(), n.lower()) for a, n in roster} |               {(a.lower(), n.lower()) for a, n in layer_fix}
    unexpected = [x for x in swapped
                  if (x[0], x[1]) not in intended
                  and (x[0].lower(), x[1].lower()) not in allowed]
    check('5 Steam 原有成员未被意外替换（覆盖名单/层内修复名单内为方针允许）',
          not unexpected, str(unexpected[:8]))
    replaced = {(a.lower(), n.lower()) for a, n in swapped}
    roster_l = {(a.lower(), n.lower()) for a, n in roster}
    replaced_roster = replaced & roster_l
    check('5b 覆盖名单条数 = 实际替换次数（逐名对齐）',
          len(roster) > 0 and replaced_roster == roster_l,
          'roster %d / 实际命中 %d / 缺 %s' % (len(roster), len(replaced_roster),
                                          sorted(roster_l - replaced_roster)[:5]))
    # 5c 层内修复：repair 记录 == 原版、其余记录 == Steam 基线
    lp = os.path.join(ROOT, 'resource', 'pna_id_map.json')
    rep_bad, n_rep = [], 0
    if os.path.exists(lp):
        pm = json.load(open(lp, encoding='utf-8'))
        ga = {k.upper(): v for k, v in read_members(os.path.join(ASSET, 'Graphic.arc')).items()}
        gs = {k.upper(): v for k, v in read_members(os.path.join(paths.STEAM, 'Graphic.arc')).items()}
        go = {k.upper(): v for k, v in read_members(os.path.join(orig_dir, 'Graphic.arc')).items()}
        for nm, rec in (pm.get('members') or {}).items():
            reps = {int(r['steam']): int(r['orig']) for r in (rec.get('repair') or [])}
            if not reps:
                continue
            if nm.upper() not in ga or nm.upper() not in gs or nm.upper() not in go:
                rep_bad.append('%s: 缺成员' % nm)
                continue
            P, S, O = pna.load(ga[nm.upper()]), pna.load(gs[nm.upper()]), pna.load(go[nm.upper()])
            for i in range(len(P['entries'])):
                if i in reps:
                    n_rep += 1
                    oi = reps[i]
                    if P['images'][i] != O['images'][oi] or P['entries'][i][2:6] != O['entries'][oi][2:6]:
                        rep_bad.append('%s 记录 %d != 原版 %d' % (nm, i, oi))
                elif P['images'][i] != S['images'][i] or P['entries'][i][2:6] != S['entries'][i][2:6]:
                    rep_bad.append('%s 非 repair 记录 %d 被改动' % (nm, i))
    check('5c 层内修复：repair 记录 == 原版、其余 == Steam 基线', not rep_bad,
          'repair %d / 异常 %s' % (n_rep, rep_bad[:5]))

    # ── 6. 可复现性 ──
    mf_path = os.path.join(ROOT, 'payload', 'METADATA.json')
    if args.stage == 'build':
        skip('6 asset == 交付表（payload/METADATA.json）',
             '构建阶段：payload 未按本次产物重建（S6 发布步骤）；发布前用 --stage release 强制')
    elif not os.path.exists(mf_path):
        check('6 交付表存在', False, 'payload/METADATA.json 缺失（先跑步 5）')
    else:
        metadata = json.load(open(mf_path, encoding='utf-8'))
        cur = {}
        for rel in sorted(asset_arcs()):
            cur[rel] = sha256(os.path.join(ASSET, rel))
        bad = []
        for rel, h in sorted(cur.items()):
            info = metadata.get(rel)
            if not info:
                bad.append('%s 不在交付表' % rel)
            elif info.get('checksum') != h:
                bad.append('%s 哈希不同' % rel)
        for rel in metadata:
            if rel not in cur:
                bad.append('%s 在交付表但 asset 无' % rel)
        check('6 asset == 交付表（payload/METADATA.json）', not bad, str(bad[:6]))

    # ── 8. 交付项完整性 ──
    check('8 AGS_001.ws2 在 Rio.arc', 'AGS_001.ws2' in rio)
    if 'AGS_001.lng' in zh:
        n = len(lng.parse_lng(zh['AGS_001.lng'], key=lng.KEY_FD))
        check('8 AGS_001.lng 槽位 %d' % len(slots_all['AGS_001']['slots']),
              n == len(slots_all['AGS_001']['slots']), '实测 %d' % n)
    else:
        check('8 zh 含 AGS_001.lng', False)
    lng_bad = []
    for sc, v in sorted(slots_all.items()):
        if not v.get('steam_file'):
            continue
        key = v['steam_file'][:-4] + '.lng'
        if key not in zh:
            lng_bad.append('%s 缺' % key)
            continue
        n = len(lng.parse_lng(zh[key], key=lng.KEY_FD))
        if n != len(v['slots']):
            lng_bad.append('%s %d!=%d' % (key, n, len(v['slots'])))
    check('8 宿主 lng 条数 == 槽数（%d 个）' % len([1 for v in slots_all.values() if v.get('steam_file')]),
          not lng_bad, str(lng_bad[:6]))
    check('8 zh-CN/Rio.arc 成员 51', len(zh) == 51, '实测 %d' % len(zh))

    script_a = read_members(os.path.join(ASSET, 'Script.arc'))
    script_b = read_members(os.path.join(BACKUP, 'Script.arc'))
    check('8 Script.arc LegacyGame.lua 已改（L4 按钮表）',
          script_a.get('LegacyGame.lua') != script_b.get('LegacyGame.lua'))
    sg_a = read_members(os.path.join(ASSET, 'SysGraphic.arc'))
    sg_b = read_members(os.path.join(BACKUP, 'SysGraphic.arc'))
    check('8 SysGraphic.arc SYS_Story.pna 已改（按钮图层）',
          sg_a.get('SYS_Story.pna') != sg_b.get('SYS_Story.pna'))
    zsg_a = read_members(os.path.join(ASSET, 'zh-CN', 'SysGraphic.arc'))
    zsg_b = read_members(os.path.join(BACKUP, 'zh-CN', 'SysGraphic.arc'))
    check('8 zh-CN/SysGraphic.arc SYS_C_Story.pna 已改',
          zsg_a.get('SYS_C_Story.pna') != zsg_b.get('SYS_C_Story.pna'))

    # 语音在位：orig 来源槽的语音成员必须在 asset Voice.arc（或 backup）
    voice_names = {n.lower() for n in read_members(os.path.join(ASSET, 'Voice.arc'))}
    voice_names |= {n.lower() for n in read_members(os.path.join(BACKUP, 'Voice.arc'))}
    orig = read_members(os.path.join(orig_dir, 'Rio.arc'))
    miss_voice = set()
    n_voice = 0
    for sc, p in sorted(plan['scripts'].items()):
        if p.get('kind') != 'host':
            continue
        of = p.get('orig_file')
        if of not in orig:
            continue
        ins, _ok = ws2dis.disassemble(ws2.decode(orig[of]), formats=ws2dis.FORMATS_ORIG)
        cur = None
        voices = []
        for _off, op, _sz, ops in ins:
            if op == 0x28:
                parts = [x for x in ops.split(b'\x00') if x]
                if parts and parts[0].lower().startswith(b'char'):
                    ogg = [x for x in parts if x.upper().endswith(b'.OGG')]
                    if ogg:
                        cur = ogg[0].decode('ascii', 'replace')
            elif op == 0x14:
                voices.append(cur)
                cur = None
        for src, val in slots_all[sc]['slots']:
            if src != 'orig' or val >= len(voices) or not voices[val]:
                continue
            n_voice += 1
            if voices[val].lower() not in voice_names:
                miss_voice.add((sc, val, voices[val]))
    check('8 orig 来源槽语音成员在位（%d 条）' % n_voice, not miss_voice, str(sorted(miss_voice)[:6]))

    # ── 9. WS2 线性自洽 ──
    bad_parse = []
    for n, d in rio.items():
        if not n.lower().endswith('.ws2'):
            continue
        try:
            _ins, ok = ws2dis.disassemble(ws2.decode(d), formats=ws2dis.FORMATS)
        except Exception as ex:
            bad_parse.append('%s:%s' % (n, str(ex)[:40]))
            continue
        if not ok:
            bad_parse.append(n)
    check('9 产物 WS2 线性解析自洽（%d 个）' % len([1 for n in rio if n.lower().endswith('.ws2')]),
          not bad_parse, str(bad_parse[:6]))

    # ── 10. 语音重指（人工定案） ──
    vp = os.path.join(ROOT, 'resource', 'voice_repoint_manual.json')
    if not os.path.exists(vp):
        skip('10 语音重指（人工定案）', '本作无 voice_repoint_manual.json')
    else:
        reps = json.load(open(vp, encoding='utf-8')).get('repoints') or []
        for e in reps:
            key = e['script'] + '.ws2'
            dec = ws2.decode(rio[key]) if key in rio else b''
            check('10 语音重指 %s %s→%s' % (e['script'], e['from'], e['to']),
                  e['from'].encode('ascii') not in dec and e['to'].encode('ascii') in dec)

    # ── 汇总 ──
    lines.append('')
    lines.append('FAILS: %d -> %s' % (len(fails), fails))
    lines.append('SKIPS: %d -> %s' % (len(skips), skips))
    lines.append('')
    lines.append('7 实机测试清单（人工）：')
    lines.append('  - 路线入口：mainmenu 第 8 个按钮（あげは线 AGS_001）可点，进入 AGS_001')
    lines.append('  - 还原段前后各一屏：AFT_003 / BEF_006 / HOT_003 / KAN_1004 / KAN_2001 / KAN_3002_1 / KAN_3004_2')
    lines.append('  - 头插脚本开头：KAN_1004、KAN_2001 首屏文本与语音')
    lines.append('  - 成就：任一 CG 收集成就正常弹出')
    lines.append('  - 朱莉线（AKA_*）保持 Steam 原样，未受影响')
    os.makedirs(os.path.join(ROOT, 'tmp'), exist_ok=True)
    with open(os.path.join(ROOT, 'tmp', 'final_verification.md'), 'w', encoding='utf-8', newline='\n') as fh:
        fh.write('\n'.join(lines) + '\n')
    npass = sum(1 for x in lines if x.startswith('[PASS]'))
    print('final_verification: PASS %d / FAIL %d / SKIP %d' % (npass, len(fails), len(skips)))
    for name in fails:
        print('  FAIL ' + name.encode('ascii', 'replace').decode())
    for name in skips:
        print('  SKIP ' + name.encode('ascii', 'replace').decode())
    print('明细: tmp/final_verification.md')
    return 1 if fails else 0


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    sys.exit(main())
