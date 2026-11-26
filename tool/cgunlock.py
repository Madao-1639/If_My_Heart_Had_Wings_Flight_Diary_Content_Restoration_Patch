"""CG 解锁组的保存方式（ASF 版口径，用户 2026-10-28 定案）。

## 数据模型（实测，见 `doc/file-formats.md`「CG 显示的固有 id 对」）

画廊 CG 的显示指令后跟一对 `0b A 01 0b B 01`：

* `A ∈ 1080..1141`：CG 组号（同一张 CG 的 B/S 变体共用一个 A）；
* `B ∈ 1170..1443`：画廊缩略图**条目号**。`CG_PAGE01..09` 逐条 `0x01 Condition` 读 B
  （== 1.0）决定缩略图是否点亮；`CG_ACHIEVEMENT` 顺序读同一批 B，把已点亮条数累加进
  旗标 55，再按阈值 1/55/110/165/220/274 发 6 个 CG 收集成就。

## 三条纪律

1. **删格**：不得连 Steam 的解锁组一起删掉。做法是把被删格里承载的组**提前到该删格之前
   的存活格入口**（`tool/writer.py` 的 `slot_payload` / `payload_carrier`）——`0b` 在那里
   仍无条件执行，时机只会早不会晚。
2. **被替换的区间**：**抛弃原版独有的解锁组**。原版编号在 Steam 的 `CG_PAGE*` /
   `CG_ACHIEVEMENT` 里不存在，按原版 id 置位是空操作；但原版 B 值（1180..1922）与
   Steam 画廊条目号（1170..1488）**有重叠**，会凭空点亮**没看过的**缩略图并虚增 CG 完成度
   （实测 249 处，涉及 8 个画廊页、81 个条目）。
3. **同名反查**：原版显示的那张 CG 在 Steam 里**也有同名显示点**时，把它的解锁对改写为
   Steam 那一对（`cg_unlock_repoint`）——同一张画面在两版里各有一套编号，直用原版编号就是
   纪律 2 里的碰撞源。Steam 侧同名显示点恒有唯一解锁对（实测 375 个名字，一名多对 0 个），
   映射无歧义。

## 本模块提供

* `steam_index(scripts)`：Steam 全库「显示名 → (A, B)」+ 原生对集合；
* `plan(scripts, index)`：逐脚本算出「要抛弃的 ORIG 编号对」与「要改写的同名映射」；
* `apply(raw, drop, repoint)`：在**解码流**上执行（等长替换 + 整对删除 + 重定基）。
"""
import struct

from . import ws2, ws2dis

REBASE_FIELDS = {0x01: (7, 11), 0x02: (0,), 0x06: (0,)}   # 与 tool/ws2.py 同源


def pair_instances(ins):
    """相邻 `0b A 01` + `0b B 01` 实例 → [(首条下标, A, B, 所属显示名 | None)]。

    显示名取「首条 `0b` 之前最近的一次 `0x33`/`0x34`」，遇到 `0x14` 即视为换格
    （`None` = 该对不归属于任何显示点，属场景旗标，不得当解锁组处置）。
    """
    out = []
    owner = None
    for k, (off, op, size, ops) in enumerate(ins):
        if op in (0x33, 0x34):
            parts = [x for x in ops.split(b'\x00') if x]
            owner = parts[1].decode('ascii', 'replace').upper() if len(parts) > 1 else None
        elif op == 0x14:
            owner = None
        if op != 0x0B or k + 1 >= len(ins):
            continue
        nxt = ins[k + 1]
        if nxt[1] != 0x0B or len(ops) < 3 or len(nxt[3]) < 3:
            continue
        if ops[2] != 0x01 or nxt[3][2] != 0x01:
            continue
        out.append((k, int.from_bytes(ops[:2], 'little'),
                    int.from_bytes(nxt[3][:2], 'little'), owner))
    return out


def steam_index(scripts):
    """→ (name → (A, B), {(A, B)})。`scripts` = {成员名大写: 原始字节}。"""
    index, native = {}, set()
    for raw in scripts.values():
        ins, ok = ws2dis.disassemble(ws2.decode(raw))
        if not ok:
            raise AssertionError('Steam 脚本线性解析失步（CG 索引不可靠）')
        for _k, a, b, owner in pair_instances(ins):
            native.add((a, b))
            if owner is None:
                continue
            prev = index.get(owner)
            if prev is not None and prev != (a, b):
                raise AssertionError('Steam 同名 CG 出现多个解锁对：%s %s %s'
                                     % (owner, prev, (a, b)))
            index[owner] = (a, b)
    return index, native


def scan(scripts, index, native):
    """逐脚本 → {脚本: {'drop': [(偏移, A, B)], 'repoint': [(偏移, A, B, A2, B2)]}}。

    只针对**不属于 Steam 原生对**的实例；`owner` 为 `None`（无显示归属）的一律跳过
    ——那是场景旗标，删了会改剧情分支。
    """
    out = {}
    for name in sorted(scripts):
        dec = ws2.decode(scripts[name])
        ins, ok = ws2dis.disassemble(dec)
        if not ok:
            raise AssertionError('%s 产物线性解析失步' % name)
        drop, repoint = [], []
        for k, a, b, owner in pair_instances(ins):
            if (a, b) in native or owner is None:
                continue
            want = index.get(owner)
            if want is None:
                drop.append((ins[k][0], a, b))
            elif want != (a, b):
                repoint.append((ins[k][0], a, b, want[0], want[1]))
        out[name] = {'drop': drop, 'repoint': repoint}
    return out


def _rebase(dec, ins, removed, changes):
    """按删除区间重定基全部流内绝对偏移。`removed` = [(lo, hi)] 降序区间。

    重定基面必须**与 `ws2`/`ws2conv` 的 `REBASE_OPS` 同口径**，并额外覆盖
    **`0f` 条目内联的 `06 <u32>` 跳转**（条目跳转不在 `REBASE_FIELDS` 里，是
    `0x0f` 操作数内部的结构）。

    ⚠️ **v0.0.6 引入、已在 v0.0.6 二次推送修掉**：本函数原先只重定基
    `0x01`/`0x02`/`0x06`，漏了 `0f` 条目。这是 v0.0.6「删 CG 解锁组」功能附带的缺陷：
    后果只在**同时含 `0f` 与可删解锁对**的脚本上显现：条目跳转停在旧坐标 ⇒ 落在指令中部
    （引擎行为未定义）。7 个 choice 变体脚本（`AFT_003`/`AFT_007_3`/`BEF_003`/`BEF_004`/
    `HOT_002`/`HUS_001`/`KAN_2001`）全中。修法：条目跳转按 `move()` 同口径平移。

    ℹ️ **归因注意**：修复 commit（`8229040`）在 v0.0.6 tag 之后（tag 钉在 `ae0c146`），
    但修复本身属于 **v0.0.6 的第二次推送**，不算 v0.1.0 的改动。按 commit 时间归纳版本会误判
    —— tag 不会因二次推送前移。
    """
    from . import ws2dis
    starts = {x[0]: x for x in ins}

    def move(v):
        return v - sum(hi - lo for lo, hi in removed if v >= hi)

    new = bytearray(dec)
    for lo, hi in sorted(removed, reverse=True):
        del new[lo:hi]
    for off, op, size, ops in ins:
        if any(lo <= off < hi for lo, hi in removed):
            continue
        base = move(off) + 1
        if off in changes:
            # 同名反查：等长替换整条操作数
            assert len(changes[off]) == len(ops)
            new[move(off) + 1:move(off) + 1 + len(ops)] = changes[off]
            ops = changes[off]
        for k in REBASE_FIELDS.get(op, ()):
            if len(ops) < k + 4:
                continue
            v = struct.unpack_from('<I', ops, k)[0]
            if not v:
                continue
            assert v in starts, 'op %#x 目标 %#x 不在指令起点' % (op, v)
            if any(lo <= v < hi for lo, hi in removed):
                raise AssertionError('跳转目标 %#x 落在被删的解锁组内（须先改流程）' % v)
            new[base + k:base + k + 4] = struct.pack('<I', move(v))
        if op == 0x0F:
            # `0f` 条目**内联**在操作数里（条目 = strid + text + label + 0 + `06 <u32>`）。
            # 条目跳转是流内绝对偏移，必须与普通跳转**同口径**平移；它不在
            # `REBASE_FIELDS` 里（那是操作数字段的算法），漏掉就会停在旧坐标。
            for _so, _to, _lo, _jo, _kind, _val in ws2dis.choice_entries(dec, off):
                if _kind != 'abs' or not _val:
                    continue
                assert _val in starts, '0f 条目跳转 %#x 不在指令起点' % _val
                if any(lo <= _val < hi for lo, hi in removed):
                    raise AssertionError(
                        '0f 条目跳转 %#x 落在被删的解锁组内（须先改流程）' % _val)
                _no = move(off) + (_jo - off)       # 条目跳转字段在删除后的绝对位置
                new[_no:_no + 4] = struct.pack('<I', move(_val))
    return bytes(new)


def plan_bytes(raw, spec):
    """按 `spec`（`scan` 的一行）改写单个脚本 → (新原始字节, 统计)。

    同名反查是**等长**替换（`0b <u16> 01`），删除是整对 6+6=12 字节；删除后统一重定基。
    """
    if not spec['drop'] and not spec['repoint']:
        return raw, {'drop': 0, 'repoint': 0}
    dec = ws2.decode(raw)
    ins, ok = ws2dis.disassemble(dec)
    assert ok
    starts = {x[0]: x for x in ins}
    removed = []
    for off, _a, _b in spec['drop']:
        a = starts[off]
        b = ins[ins.index(a) + 1]
        removed.append((off, off + 1 + len(a[3]) + 1 + len(b[3])))
    changes = {}
    for off, _a, _b, a2, b2 in spec['repoint']:
        a = starts[off]
        b = ins[ins.index(a) + 1]
        changes[off] = struct.pack('<H', a2) + a[3][2:]
        changes[b[0]] = struct.pack('<H', b2) + b[3][2:]
    out = _rebase(dec, ins, removed, changes)
    # 回读：**全部**流内绝对偏移（含 `0f` 条目跳转）必须落到指令起点。
    # ⚠️ 旧版回读只查 `REBASE_FIELDS`，与 `_rebase` 漏 `0f` 是同一个盲点——
    # 写入端与闸同时漏，所以 9d/9f 的 7 处错误直到独立闸才暴露。两者必须同口径。
    ins2, ok2 = ws2dis.disassemble(out)
    assert ok2, '改写后线性解析失步'
    st2 = {x[0] for x in ins2}
    for off, op, _sz, ops in ins2:
        for k in REBASE_FIELDS.get(op, ()):
            if len(ops) < k + 4:
                continue
            v = struct.unpack_from('<I', ops, k)[0]
            if v:
                assert v in st2, '回读：op %#x 目标 %#x 不在指令起点' % (op, v)
        if op == 0x0F:
            for _e in ws2dis.choice_entries(out, off):
                if _e[4] == 'abs' and _e[5]:
                    assert _e[5] in st2, \
                        '回读：0f@%#x 条目跳转 %#x 不在指令起点' % (off, _e[5])
    return ws2.encode(out), {'drop': len(removed),
                             'repoint': len(spec['repoint']),
                             'removed': list(removed)}


def shift_targets(stat, targets):
    """按 `plan_bytes` 的删除区间平移一组「解码流内绝对偏移」→ 新坐标。

    `stat` = `plan_bytes` 返回的统计字典（需含 `removed` = 真实删除区间 [lo,hi)）；
    `targets` = {名: 偏移}（如 `slot_sources[sc]['variant']['targets']` 的 brA/brB/conf）。

    **为什么需要**：`variants.apply` 先把 brA/brB/conf 的绝对偏移写进 `slot_sources`，
    `plan_bytes` 之后才删解锁组并整体前移 ⇒ 那些偏移全部作废。不重算会发生
    「落盘布局（targets）与产物字节脱钩」，闸按 targets 回读时一律报「不在指令起点」
    （`variant_route_check` 35 项 FAIL 即此）。

    ⚠️ **删除区间必须从 `stat` 取、不得按「每对固定 N 字节」推算**：一对解锁组是
    `0b <u16 A> 01` + `0b <u16 B> 01` = 4+4 = **8 B**（不是 12——早期按 12 算会让
    平移量偏大 50%，与「`removed` 的 hi-lo」互相矛盾而静默算错）。
    ⚠️ 落点若**落在被删区间内**，说明该落点本身要被删掉——那是结构错误（分支起点/
    汇合点不可能在解锁组里），直接断言失败，不做静默吸附。
    """
    spans = [(lo, hi) for lo, hi in (stat or {}).get('removed') or []]
    if not spans:
        return dict(targets)
    out = {}
    for k, v in targets.items():
        cut = sum(hi - lo for lo, hi in spans if v >= hi)
        assert not any(lo <= v < hi for lo, hi in spans), \
            '变体落点 %s=%#x 落在被删的解锁组内 %r（结构错误）' % (k, v, spans)
        out[k] = v - cut
    return out
