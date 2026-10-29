#!/usr/bin/env python3
"""
ipc_map.py — recover the Electron IPC surface of preload.js (Gap 2).
De-rotates the javascript-obfuscator string array, resolves each ipcBridge
forwarder to its ipcRenderer method, and (from the renderer bundle) recovers
literal channel strings passed by callers. Static only; does not execute the app.

Usage: ipc_map.py <preload.js> <renderer_glob> <out.tsv>
"""
import sys, re, glob

def js_parseint(x):
    m = re.match(r'\s*([+-]?\d+)', x)
    return int(m.group(1)) if m else float('nan')

def main():
    pre = open(sys.argv[1], encoding='utf-8', errors='replace').read()
    # 1. string array
    am = re.search(r"function (a0_0x[0-9a-f]+)\(\)\{const \w+=\[([^\]]+)\];", pre)
    arr_fn = am.group(1)
    arr = re.findall(r"'((?:[^'\\]|\\.)*)'", am.group(2))
    # 2. accessor offset
    acc = re.search(r"function (a0_0x[0-9a-f]+)\((\w+),(\w+)\)\{\2=\2-(0x[0-9a-f]+);", pre)
    acc_name, off = acc.group(1), int(acc.group(4), 16)
    # 3. rotation magic + checksum expr (indices used)
    rot = re.search(r"\}\(" + arr_fn + r",(0x[0-9a-f]+)\)\);", pre)
    magic = int(rot.group(1), 16)
    expr = re.search(r"while\(!!\[\]\)\{try\{const \w+=(.*?);if", pre).group(1)
    idxs = [int(h, 16) for h in re.findall(r'\((0x[0-9a-f]+)\)', expr)]
    # build a python-evaluable checksum over current array
    def checksum(a):
        def p(i): return js_parseint(a[i - off])
        e = expr
        e = re.sub(r'parseInt\(\w+\((0x[0-9a-f]+)\)\)', lambda m: f'p({int(m.group(1),16)})', e)
        e = e.replace('!![]', 'True')
        try:
            return eval(e, {'p': p})
        except Exception:
            return None
    # 4. rotate until checksum == magic
    a = arr[:]
    for _ in range(len(a) * 4 + 10):
        if checksum(a) == magic: break
        a.append(a.pop(0))
    def resolve(idx): return a[idx - off]
    # accessor aliases: const <alias>=<acc_name>;
    aliases = set(re.findall(r"const (a0_0x[0-9a-f]+)=" + acc_name + r";", pre)) | {acc_name}
    accgrp = "(?:" + "|".join(aliases) + r")"
    # 5. pair each ipcRenderer[ACC(midx)]( call to the nearest preceding 'api': key,
    #    capturing the first argument (literal channel or forwarded caller-arg).
    rows = []
    key_re = re.compile(r"'([A-Za-z][A-Za-z0-9]{2,45})':")
    for m in re.finditer(r"ipcRenderer\[" + accgrp + r"\((0x[0-9a-f]+)\)\]\(", pre):
        midx = int(m.group(1), 16)
        method = resolve(midx)
        # nearest api key in the ~300 chars before this call
        pre_slice = pre[max(0, m.start()-300):m.start()]
        keys = key_re.findall(pre_slice)
        if not keys: continue
        api = keys[-1]
        # first argument after the '('
        rest = pre[m.end(): m.end()+120]
        lit = re.match(r"\s*'([A-Za-z0-9_.:-]+)'", rest)
        if lit:
            chan = lit.group(1)
        else:
            chan = '(caller-arg)'
        rows.append((api, method, chan, 0))
    # dedupe by api (first/best)
    seen = {}
    for api, method, chan, n in rows:
        if api not in seen or (seen[api][1] == '(caller-arg)' and chan != '(caller-arg)'):
            seen[api] = (method, chan, n)
    rows = [(api, v[0], v[1], v[2]) for api, v in seen.items()]

    # 6. recover channels from renderer: ipcBridge.<api>(<EnumObj>.<Member>, ...)
    #    where channel-enum members map Member -> "value" (usually identity).
    rend = "\n".join(open(p, encoding='utf-8', errors='replace').read()
                     for g in sys.argv[2].split(',') for p in sorted(glob.glob(g)))
    # channel-enum member -> value  (e.g.  i.GetStatsigOverrides=`GetStatsigOverrides`)
    member_val = {}
    for m in re.finditer(r'\.([A-Z][A-Za-z0-9]+)=[`"\']([A-Za-z0-9_.:-]+)[`"\']', rend):
        member_val.setdefault(m.group(1), m.group(2))
    call_chan = {}
    # api -> enum member used as first arg
    for m in re.finditer(r'ipcBridge\.(\w+)\(\s*\w+\.([A-Z][A-Za-z0-9]+)', rend):
        api, member = m.group(1), m.group(2)
        call_chan.setdefault(api, set()).add(member_val.get(member, member))
    # also direct string-literal first args, if any
    for m in re.finditer(r'''ipcBridge\.(\w+)\(\s*[`"']([A-Za-z0-9_.:-]{3,60})[`"']''', rend):
        call_chan.setdefault(m.group(1), set()).add(m.group(2))

    def group(api):
        a = api[0].lower() + api[1:]   # normalize leading case
        for p in ('pluginCdio','pluginDeviceCommon','pluginVulcan','pluginLocalData',
                  'pluginSystemFont','pluginSystemPrinter','pluginPathOperation','plugin',
                  'machine','appConfig','appFeatureFlag','app','auth','canvasCache','canvas',
                  'login','tab','window','clipboard','dataStorage','event',
                  'log','record','update','statsig','wifi','screenSize','project',
                  'systemPreferences','menu','about','keepScreenAwake','spell','word'):
            if a.startswith(p):
                return p
        return 'misc'
    total_keys = len(set(re.findall(r"'([A-Za-z][A-Za-z0-9]{2,45})':", pre)))
    rows.sort()
    with open(sys.argv[3], 'w') as f:
        f.write("bridge_api\tipcRenderer_method\thandler_group\tchannel_confirmed\tchannel_inferred\n")
        for api, method, chan, n in rows:
            rc = ','.join(sorted(call_chan.get(api, [])))
            inferred = api[0].upper() + api[1:]
            f.write(f"{api}\t{method}\t{group(api)}\t{rc}\t{inferred}\n")
    from collections import Counter
    print(f"array rotated: checksum matched={checksum(a)==magic}  methods={dict(Counter(r[1] for r in rows))}")
    print(f"ipcBridge keys in preload: {total_keys} | ipcRenderer forwarders mapped: {len(rows)}")
    print(f"channels confirmed from renderer: {sum(1 for r in rows if call_chan.get(r[0]))} "
          f"(all follow channel == PascalCase(api); rest inferred by that rule)")
    print(f"handler groups: {dict(Counter(group(r[0]) for r in rows))}")

if __name__ == '__main__':
    main()
