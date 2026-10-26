# -*- coding: utf-8 -*-
"""同名 CG 的「9XX 号段」命名隔离表（`resource/censor_map.json` 的 `isolate` 字段）。

**问题**：某个 CG 名在两版里都存在、但 Steam 版做过全年龄处理（改画）。我们的默认处置是
「同名素材整名覆盖回原版」。一旦这个 CG 同时出现在**两条演绎路径**上（原版路径要原版画、
Steam 路径要 Steam 画），单一成员名就装不下两份画 ⇒ 必须做**命名隔离**。

**方案**（用户 2026-10-27 定案）：把**原版**那张改编号到 9XX 号段（前缀与中缀不变，只把
序号首位的 0 换成 9），如 `BEF_03_001B.png → BEF_03_901B.png`；**原名保留 Steam 原画**。
于是：
  * 原名（Steam 画）——由分支 B / Steam 原生体引用，零改动；
  * 9XX 名（原版画）——由**产品侧（A 路径与共享内容）**的 `33/34` 显示引用；
  * 两个名字**同长度** ⇒ 脚本里改名不需要重定基。

消费方：`script/build/build_l3.py`（写 9XX 成员 + 原名回 Steam 字节）、
`script/build/build_patch.py`（把产品侧显示名改成 9XX）、
`script/checks/*`（比较口径用 `normalize()` 折算回原编号）。
"""
import json
import os

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TABLE = os.path.join(HERE, 'resource', 'censor_map.json')


def _upper_name(idx):
    return idx.upper()


def load():
    """→ (isolate_map, reset_map)

    * `isolate_map`: {9XX 名(大写): 原编号名(大写)}  —— 供比较口径折算；
    * `reset_map`  : {原编号名(小写): 9XX 成员名(原始大小写)} —— 供写盘/改名使用。
    """
    with open(TABLE, encoding='utf-8') as fh:
        cm = json.load(fh)
    iso, reset = {}, {}
    for m in cm.get('members') or []:
        name = m.get('name')
        target = m.get('isolate')
        if not name or not target:
            continue
        iso[_upper_name(target)] = _upper_name(name)
        reset[name.lower()] = target
    return iso, reset


ISOLATE_MAP, RESET_MAP = load()


def normalize(name):
    """9XX 名 → 原编号名（其它原样，统一大写）。用于「与两版素材比对」的闸门口径。"""
    u = name.upper()
    return ISOLATE_MAP.get(u, u)


def isolate_refs():
    """→ {原编号名(大写): 9XX 名(大写)}，供脚本改写用（引用串一律大写 + `.PNG`）。"""
    return {v: k for k, v in ISOLATE_MAP.items()}


def isolate_members():
    """→ [(原编号名(小写), 9XX 成员名(原始大小写))]。"""
    return sorted(RESET_MAP.items())
