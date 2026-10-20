"""反汇编一个 ws2 并打印可读清单。用法：
    python ws2listing.py <orig|steam|patch> <归档> <脚本名> [> out.txt]
"""
import sys

sys.path.insert(0, 'D:/My_Code/tmp/GamePatch/GalRevserse/GalRev')
sys.path.insert(0, 'D:/My_Code/tmp/GamePatch/If_My_Heart_Had_Wings_Flight_Diary/'
                   'If_My_Heart_Had_Wings_Flight_Diary_Content_Restoration_Patch/tool')
from galrev.advhd import arc, ws2
import ws2fmt

NAMES = {
    0x01: 'Condition', 0x02: 'Jump2', 0x04: 'RunFile', 0x05: 'StopAll?', 0x06: 'Jump',
    0x07: 'NextFile', 0x09: 'LayerConfig', 0x0b: 'SetFlag', 0x0e: 'Unk0E', 0x0f: 'ShowChoice',
    0x11: 'SetTimer', 0x12: 'StartTimer', 0x14: 'DisplayMessage', 0x15: 'SetDisplayName',
    0x16: 'LayerCmdBlock', 0x18: 'AddLog', 0x1a: 'OpenTitle', 0x1c: 'ExecuteFunction',
    0x1d: 'Unk1D', 0x1e: 'PlayMusic', 0x1f: 'StopMusic', 0x28: 'SoundEffect',
    0x2e: 'CharMessageStart', 0x33: 'SetBackground', 0x34: 'UsePnaPackage', 0x35: 'PlayMovie',
    0x37: 'ClearLayer', 0x39: 'DisplayCharImage', 0x3f: 'LayersList', 0x40: 'SetMask',
    0x45: 'DragBackground', 0x46: 'MoveBackground', 0x47: 'Effect1', 0x48: 'Effect2',
    0x57: 'UnkBackground1', 0x58: 'Effect3', 0x65: 'C65', 0x66: 'ShowGraphic',
    0x6e: 'SetVariable', 0x73: 'SetPnaFile', 0x80: 'Unk80', 0x82: 'Unk82',
    0xf0: 'UnkScreen', 0xff: 'FileEnd',
}

ROOTS = {
    'orig': 'D:/My_Code/tmp/GamePatch/If_My_Heart_Had_Wings_Flight_Diary/If_My_Heart_Had_Wings_Flight_Diary_Original',
    'steam': 'E:/SteamLibrary/steamapps/common/IF MY HEART HAD WINGS FLIGHT DIARY',
    'patch': 'D:/My_Code/tmp/GamePatch/If_My_Heart_Had_Wings_Flight_Diary/If_My_Heart_Had_Wings_Flight_Diary_Restoration Patch',
}


def main():
    which, arcname, target = sys.argv[1], sys.argv[2], sys.argv[3]
    ms = {nb.decode('utf-16le'): d for nb, d in arc.read_raw(ROOTS[which] + '/' + arcname)}
    key = [k for k in ms if k.lower() == target.lower()][0]
    dec = ws2.decode(ms[key])
    ins = ws2fmt.disassemble(dec)
    print('# %s/%s  %d bytes  %d instructions' % (which, key, len(dec), len(ins)))
    for off, op, sz, f in ins:
        nm = NAMES.get(op, '')
        args = f.get('args')
        if args is not None:
            a = ' '.join(str(x) for x in args if x is not None)
        else:
            a = ' '.join('%s=%s' % (k, v) for k, v in f.items())
        print('%05x  %02x %-18s %s' % (off, op, nm, a))


if __name__ == '__main__':
    main()
