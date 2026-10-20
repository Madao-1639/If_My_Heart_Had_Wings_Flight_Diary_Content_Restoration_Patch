"""极简 IDA-MCP 客户端：`python mcp.py <tool> '<json-args>'`，也支持交互式批量。"""
import json
import sys
import urllib.request

URL = 'http://127.0.0.1:13337/mcp'


def call(tool, args=None, timeout=120):
    payload = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
               "params": {"name": tool, "arguments": args or {}}}
    req = urllib.request.Request(URL, data=json.dumps(payload).encode(),
                                 headers={'Content-Type': 'application/json',
                                          'Accept': 'application/json, text/event-stream'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read().decode('utf-8', 'replace')
    # 可能是 SSE（data: {...}）或纯 JSON
    txt = raw
    if 'data:' in raw:
        txt = '\n'.join(l[5:].strip() for l in raw.split('\n') if l.startswith('data:'))
    d = json.loads(txt)
    if 'error' in d:
        return {'error': d['error']}
    res = d.get('result', {})
    if 'structuredContent' in res:
        return res['structuredContent']
    cont = res.get('content', [])
    if cont and cont[0].get('type') == 'text':
        try:
            return json.loads(cont[0]['text'])
        except Exception:
            return cont[0]['text']
    return res


if __name__ == '__main__':
    tool = sys.argv[1]
    args = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
    out = call(tool, args)
    print(json.dumps(out, ensure_ascii=False, indent=1)[:6000])
