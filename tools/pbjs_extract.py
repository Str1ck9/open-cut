#!/usr/bin/env python3
"""
pbjs_extract.py — recover protobuf field tags/types/enums from protobuf.js
STATIC generated code (as in canvas-webw-cricanvas.js). Parses each message's
decode() switch (case N => field number N, m.Name = reader) and enum literals.
Pure stdlib; does not execute the bundle. Emits a .proto + a flat schema table.

Usage: pbjs_extract.py <bundle.js> <out.proto> <out_table.tsv>
"""
import sys, re

READER = {  # protobuf.js Reader method -> proto type
    'string':'string','bool':'bool','int32':'int32','uint32':'uint32',
    'int64':'int64','uint64':'uint64','sint32':'sint32','sint64':'sint64',
    'fixed32':'fixed32','fixed64':'fixed64','sfixed32':'sfixed32',
    'sfixed64':'sfixed64','float':'float','double':'double','bytes':'bytes',
}

def main():
    import glob as _glob
    inputs = sys.argv[1].split(',')
    srcs = []
    for p in inputs:
        srcs += sorted(_glob.glob(p))
    src = "\n".join(open(p, encoding='utf-8', errors='replace').read() for p in srcs)
    messages = {}   # name -> list of (num, fname, type, repeated)
    # find each decode function and the message it constructs
    for dm in re.finditer(r'\.decode\s*=\s*function\(([a-z]),([a-z])\)\{', src):
        rdr = dm.group(1)                     # reader var (e)
        start = dm.end()
        # message name: first `new <ns>.<Name>` after start
        nm = re.search(r'new\s+[\w.]*\.(\w+)', src[start:start+200])
        if not nm: continue
        name = nm.group(1)
        # find the switch(<v>>>>3){  — the tag dispatch — within this decode
        sw = re.search(r'switch\([a-z]+>>>3\)\{', src[start:start+600])
        if not sw: continue
        open_brace = start + sw.end() - 1      # position of the '{'
        # balance-match braces to get exactly the switch body
        depth = 0; j = open_brace
        while j < len(src):
            c = src[j]
            if c == '{': depth += 1
            elif c == '}':
                depth -= 1
                if depth == 0: break
            j += 1
        body = src[open_brace+1:j]
        mv = re.search(r'(\w+)\s*=\s*new\s+[\w.]*\.' + re.escape(name), src[start:open_brace])
        msgvar = mv.group(1) if mv else None
        # split into TOP-LEVEL cases (depth 0 within the switch body)
        labels = []   # (num_or_default, start_idx)
        depth = 0; k = 0
        while k < len(body):
            c = body[k]
            if c == '{': depth += 1
            elif c == '}': depth -= 1
            elif depth == 0:
                lm = re.match(r'case (\d+):', body[k:]) or re.match(r'(default):', body[k:])
                if lm:
                    labels.append((lm.group(1), k + lm.end()))
                    k += lm.end(); continue
            k += 1
        labels.append(('END', len(body)))
        fields = []
        for idx in range(len(labels) - 1):
            lab, s0 = labels[idx]; s1 = labels[idx+1][1]
            if lab in ('default', 'END'): continue
            num = int(lab)
            if num < 1 or num > 536870911: continue
            blk = body[s0:s1]
            # map field: protobuf.js uses the emptyObject sentinel for map entries
            if 'emptyObject' in blk:
                kv = re.findall(r'case [12]:[^;]*?[a-z]\.(\w+)\(\)', blk)
                kt = kv[0] if len(kv) > 0 and kv[0] in READER else 'string'
                sub = re.search(r'([\w.]+)\.decode\(', blk)
                vt = (sub.group(1).split('.')[-1] if sub else (kv[1] if len(kv) > 1 and kv[1] in READER else 'string'))
                fn = re.search((re.escape(msgvar) if msgvar else r'[a-z]') + r'\.(\w+)', blk)
                fields.append((num, fn.group(1) if fn else f'field{num}', f'map<{kt},{vt}>', False, True))
                continue
            sub = re.search(r'([\w.]+)\.decode\(' + rdr, blk)
            rd = re.search(rdr + r'\.(\w+)\(\)', blk)
            fn = re.search((re.escape(msgvar) if msgvar else r'[a-z]') + r'\.(\w+)', blk)
            repeated = '.push' in blk or 'length)' in blk
            fname = fn.group(1) if fn else f'field{num}'
            if sub: typ = sub.group(1).split('.')[-1]
            elif rd and rd.group(1) in READER: typ = READER[rd.group(1)]
            else: typ = 'int32'
            fields.append((num, fname, typ, repeated, False))
        if fields and name not in messages:
            messages[name] = fields

    # enums: l.Name=function(){var e={},..., e[e.FOO=N]="FOO" ...}  or  r[t[K]="FOO"]=N
    enums = {}
    for em in re.finditer(r'(\w+)\s*=\s*function\(\)\{\s*var\s+\w+=\{\}[^}]*?\}\(\)', src):
        pass  # enum shapes vary; handle with targeted literal scan below
    # targeted: capture `<v>[<n>="NAME"]=NUM` and `[e.NAME=NUM]="NAME"`
    enum_vals = {}
    for m in re.finditer(r'\[\w+\.(\w+)=(-?\d+)\]="\1"', src):
        enum_vals.setdefault('_mixed', []).append((m.group(1), int(m.group(2))))

    # write proto
    # referenced-but-undefined types -> stubs (google wrappers imported)
    SCALARS = set(READER.values())
    GWRAP = {'BoolValue','StringValue','Int32Value','Int64Value','UInt32Value',
             'UInt64Value','FloatValue','DoubleValue','BytesValue'}
    refs = set()
    for flds in messages.values():
        for num, fname, typ, rep, ismap in flds:
            if typ.startswith('map<'):
                for t in re.findall(r'map<([^,]+),([^>]+)>', typ)[0]:
                    if t not in SCALARS: refs.add(t)
            elif typ not in SCALARS:
                refs.add(typ)
    undefined = sorted(r for r in refs if r not in messages)
    gimports = sorted(f'google/protobuf/wrappers.proto' for r in undefined if r in GWRAP)
    stubs = [r for r in undefined if r not in GWRAP]
    with open(sys.argv[2], 'w') as f:
        f.write('// Recovered from protobuf.js static code in canvas-webw-*.js (Gap-1 Route B)\n')
        f.write('// Method: decode() switch(tag>>>3) -> field numbers + reader types. [C for tags]\n')
        f.write('// Enum-typed fields decode as int32 (wire-identical); scalar-vs-enum is ambiguous\n')
        f.write('// and rendered as int32. Enum value sets: see analysis/canvas-protobuf-schema.txt.\n')
        f.write('syntax = "proto3";\n')
        for imp in sorted(set(gimports)): f.write(f'import "{imp}";\n')
        f.write('\n')
        for r in stubs:
            f.write(f'message {r} {{}}  // referenced; decode not recovered in these workers\n')
        if stubs: f.write('\n')
        # google wrapper refs need fully-qualified names; rewrite in-place
        for flds in messages.values():
            for idx in range(len(flds)):
                num, fname, typ, rep, ismap = flds[idx]
                if typ in GWRAP:
                    flds[idx] = (num, fname, 'google.protobuf.'+typ, rep, ismap)
        for name in sorted(messages):
            f.write(f'message {name} {{\n')
            for num, fname, typ, rep, ismap in sorted(messages[name]):
                lbl = '' if ismap else ('repeated ' if rep else '')
                f.write(f'  {lbl}{typ} {fname} = {num};\n')
            f.write('}\n\n')
    # write table
    with open(sys.argv[3], 'w') as f:
        f.write('message\tfield_number\tfield_name\ttype\trepeated\n')
        for name in sorted(messages):
            for num, fname, typ, rep, ismap in sorted(messages[name]):
                f.write(f'{name}\t{num}\t{fname}\t{typ}\t{rep}\n')
    nfields = sum(len(v) for v in messages.values())
    print(f'messages: {len(messages)}  fields: {nfields}')
    # quick spot list
    for n in ('CanvasBody','Graphic','LayerFill','TextGraphic'):
        if n in messages:
            print(f'  {n}: {len(messages[n])} fields; sample '
                  + ', '.join(f'{t[1]}={t[0]}' for t in sorted(messages[n])[:6]))

if __name__ == '__main__':
    main()
