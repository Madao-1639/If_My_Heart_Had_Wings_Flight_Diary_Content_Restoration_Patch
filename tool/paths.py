"""路径解析：定位 Steam backup 目录与原版发行目录，并按不区分大小写匹配归档文件名。

路径全部相对本文件推导（本文件在 `tool/` 下），不含任何硬编码绝对路径：
  PATCH = 本仓库根目录（`tool/` 的父目录）
  ROOT  = PATCH 的父目录（原版发行目录与 PATCH 同级）
  STEAM = PATCH/backup（Steam 原始基线，只读）

第三方补丁（国外还原补丁 / 中文汉化补丁）只作**改动面线索**，不作依据，故不纳入本模块的常规解析；
需要时用 `third_party_dir()` 显式取。
"""
import os

PATCH = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(PATCH)
STEAM = os.path.join(PATCH, 'backup')

_ORIG = None
_THIRD = None


def orig_dir():
    """原版发行版目录（日文）。优先环境变量 IMHFD_ORIG_DIR，否则在 ROOT 下按目录名发现。"""
    global _ORIG
    if _ORIG is None:
        env = os.environ.get('IMHFD_ORIG_DIR')
        if env:
            _ORIG = env
        else:
            for d in os.listdir(ROOT):
                if d == 'If_My_Heart_Had_Wings_Flight_Diary_Original' or d.startswith(u'\u3053\u306e\u5927\u7a7a'):
                    _ORIG = os.path.join(ROOT, d)
                    break
    if _ORIG is None:
        raise RuntimeError('original release dir not found under %s' % ROOT)
    return _ORIG


def third_party_dir():
    """第三方还原补丁目录（只作线索，不作依据）。"""
    global _THIRD
    if _THIRD is None:
        env = os.environ.get('IMHFD_THIRD_DIR')
        if env:
            _THIRD = env
        else:
            for d in os.listdir(ROOT):
                if 'Restoration Patch' in d:
                    _THIRD = os.path.join(ROOT, d)
                    break
    return _THIRD


def listing(dirpath):
    """返回 {小写文件名: 绝对路径}"""
    out = {}
    for fn in os.listdir(dirpath):
        p = os.path.join(dirpath, fn)
        if os.path.isfile(p):
            out[fn.lower()] = p
    return out


# 本作（Flight Diary）归档清单。与原版的差别：
#   * Steam 独有：chip10.arc（朱莉线 DLC CG）、rio1.arc（朱莉线剧本）
#   * 两版同名：其余全部
TARGETS = [
    'bgm.arc',
    'chip1.arc', 'chip2.arc', 'chip3.arc', 'chip4.arc', 'chip5.arc',
    'chip6.arc', 'chip7.arc', 'chip8.arc', 'chip9.arc', 'chip10.arc',
    'effect.arc', 'graphic.arc',
    'rio.arc', 'rio1.arc',
    'script.arc', 'se.arc', 'sysgraphic.arc', 'sysvoice.arc', 'voice.arc',
]

# 朱莉线专属归档：还原工作**不得触碰**
JULIE_ARCHIVES = ['chip10.arc', 'rio1.arc']


def match_archives(targets=None):
    """返回 {canonical_key: (orig_path, steam_path)}，只含两边都存在的目标归档。"""
    targets = targets or TARGETS
    o = listing(orig_dir())
    s = listing(STEAM)
    out = {}
    for t in targets:
        if t in o and t in s:
            out[t] = (o[t], s[t])
    return out


def display_name(path):
    return os.path.basename(path)
