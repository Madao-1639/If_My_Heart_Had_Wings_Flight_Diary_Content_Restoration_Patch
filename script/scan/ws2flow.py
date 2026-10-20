"""列出 ws2 的调用/跳转目标（0x04 CALL / 0x07 JUMP）+ 显示资源引用。"""
import re
import sys

sys.path.insert(0, 'D:/My_Code/tmp/GamePatch/GalRevserse/GalRev')
from galrev.advhd import arc, ws2

ORIG = 'D:/My_Code/tmp/GamePatch/If_My_Heart_Had_Wings_Flight_Diary/If_My_Heart_Had_Wings_Flight_Diary_Original'
STEAM = 'E:/SteamLibrary/steamapps/common/IF MY HEART HAD WINGS FLIGHT DIARY'
PATCH = 'D:/My_Code/tmp/GamePatch/If_My_Heart_Had_Wings_Flight_Diary/If_My_Heart_Had_Wings_Flight_Diary_Restoration Patch'

CALL = re.compile(rb'\x04([A-Za-z0-9_]+)\x00')
JUMP = re.compile(rb'\x07([A-Za-z0-9_]+)\x00')


def members(path):
    return {nb.decode('utf-16le'): d for nb, d in arc.read_raw(path)}


if __name__ == '__main__':
    which, arcname, target = sys.argv[1], sys.argv[2], sys.argv[3]
    paths = {'orig': ORIG, 'steam': STEAM, 'patch': PATCH}
    ms = members(paths[which] + '/' + arcname)
    key = [k for k in ms if k.lower() == target.lower()][0]
    dec = ws2.decode(ms[key])
    calls = [m.group(1).decode('ascii') for m in CALL.finditer(dec)]
    jumps = [m.group(1).decode('ascii') for m in JUMP.finditer(dec)]
    print('%s/%s  %d bytes' % (which, key, len(ms[key])))
    print('CALL (%d): %s' % (len(calls), ' '.join(calls)))
    print('JUMP (%d): %s' % (len(jumps), ' '.join(jumps)))
