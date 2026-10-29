#!/usr/bin/env python3
"""
pbscan.py — locate and decode embedded google.protobuf.FileDescriptorProto blobs
in a (thinned) C++ protobuf Mach-O binary, and render .proto schemas.

Pure stdlib (no protobuf runtime needed). Interface recovery only: emits message/
enum/field structure (names, numbers, types, labels). Does not execute the target.

Usage: pbscan.py <binary> <out_dir> [--redact substr,substr]
  --redact: message names containing any of these substrings have their fields
            omitted from emitted .proto (replaced with a marker) — used to keep
            protected (crypto/DRM) message internals out of the deliverable.
"""
import sys, os, re, subprocess

# ---- wire-format primitives -------------------------------------------------
def read_varint(b, i):
    r = s = 0
    while True:
        if i >= len(b): raise ValueError("varint eof")
        x = b[i]; i += 1
        r |= (x & 0x7f) << s
        if not (x & 0x80): return r, i
        s += 7
        if s > 70: raise ValueError("varint too long")

def parse_message(b, start, end):
    """Generic parse of a length-delimited protobuf message region [start,end).
    Returns dict field_num -> list of (wire, payload) where payload is int (wire0)
    or bytes (wire2) or raw int (wire1/5). Raises on malformed."""
    i = start; out = {}
    while i < end:
        tag, i = read_varint(b, i)
        fn, wt = tag >> 3, tag & 7
        if fn == 0: raise ValueError("field 0")
        if wt == 0:
            v, i = read_varint(b, i)
        elif wt == 2:
            ln, i = read_varint(b, i)
            if i + ln > end: raise ValueError("len overflow")
            v = b[i:i+ln]; i += ln
        elif wt == 5:
            v = b[i:i+4]; i += 4
        elif wt == 1:
            v = b[i:i+8]; i += 8
        else:
            raise ValueError("bad wire %d" % wt)
        out.setdefault(fn, []).append((wt, v))
    return out

def s(x):  # bytes->str
    return x.decode('utf-8', 'replace')

# ---- FileDescriptorProto model ----------------------------------------------
PROTO_TYPE = {1:'double',2:'float',3:'int64',4:'uint64',5:'int32',6:'fixed64',
    7:'fixed32',8:'bool',9:'string',10:'group',11:'message',12:'bytes',
    13:'uint32',14:'enum',15:'sfixed32',16:'sfixed64',17:'sint32',18:'sint64'}
LABEL = {1:'optional',2:'required',3:'repeated'}

def parse_field(b):
    m = parse_message(b, 0, len(b))
    name = s(m[1][0][1]) if 1 in m else '?'
    number = m[3][0][1] if 3 in m else 0
    label = m[4][0][1] if 4 in m else 0
    typ = m[5][0][1] if 5 in m else 0
    type_name = s(m[6][0][1]).lstrip('.') if 6 in m else ''
    oneof = m[9][0][1] if 9 in m else None
    return dict(name=name, number=number, label=label, typ=typ,
                type_name=type_name, oneof=oneof)

def signed32(v):  # enum values are int32, sign-extended into a 64-bit varint
    v &= (1 << 64) - 1
    if v >= (1 << 63): v -= (1 << 64)
    return v

def parse_enum(b):
    m = parse_message(b, 0, len(b))
    name = s(m[1][0][1]) if 1 in m else '?'
    vals = []
    for _, vb in m.get(2, []):
        vm = parse_message(vb, 0, len(vb))
        vals.append((s(vm[1][0][1]) if 1 in vm else '?',
                     signed32(vm[2][0][1]) if 2 in vm else 0))
    return dict(name=name, values=vals)

def parse_descriptor(b):
    m = parse_message(b, 0, len(b))
    name = s(m[1][0][1]) if 1 in m else '?'
    fields = [parse_field(fb) for _, fb in m.get(2, [])]
    nested = [parse_descriptor(nb) for _, nb in m.get(3, [])]
    enums = [parse_enum(eb) for _, eb in m.get(4, [])]
    oneofs = [s(parse_message(ob,0,len(ob)).get(1,[(0,b'?')])[0][1]) for _, ob in m.get(8, [])]
    return dict(name=name, fields=fields, nested=nested, enums=enums, oneofs=oneofs)

def parse_fdp(b):
    m = parse_message(b, 0, len(b))
    name = s(m[1][0][1]) if 1 in m else '?'
    package = s(m[2][0][1]) if 2 in m else ''
    deps = [s(d) for _, d in m.get(3, [])]
    messages = [parse_descriptor(mb) for _, mb in m.get(4, [])]
    enums = [parse_enum(eb) for _, eb in m.get(5, [])]
    syntax = s(m[12][0][1]) if 12 in m else 'proto2'
    return dict(name=name, package=package, deps=deps, messages=messages,
                enums=enums, syntax=syntax)

# ---- blob location ----------------------------------------------------------
def find_fdp_blobs(b):
    """Find candidate FileDescriptorProto starts: 0x0A <varint len> <name...proto>
    then greedily parse the message to get its exact end."""
    blobs = []
    for mo in re.finditer(rb'\.proto\b', b):
        # name ends at mo.end(); find the 0x0A len tag that introduces this string
        name_end = mo.end()
        for lead in range(1, 4):           # length varint is 1-2 bytes typically
            # try name length L so that start = name_end - L, tag at start-?
            pass
        # brute: the string field is `0A <len> <name>`; scan back up to 160 bytes
        found = None
        for ln_pos in range(name_end-1, max(0, name_end-170), -1):
            # candidate: b[ln_pos] is low tag 0x0A, b[ln_pos+1..] length varint, then name
            if b[ln_pos] != 0x0A: continue
            try:
                L, after = read_varint(b, ln_pos+1)
            except ValueError:
                continue
            if after + L == name_end and 3 <= L <= 160:
                found = ln_pos
                break
        if found is None: continue
        start = found
        # greedily find end of the FDP message
        end = greedy_end(b, start)
        if end - start < 16: continue
        blobs.append((start, end))
    # dedupe by start
    seen = {}
    for st, en in blobs:
        if st not in seen or en > seen[st]:
            seen[st] = en
    return sorted((st, en) for st, en in seen.items())

def greedy_end(b, start):
    """Walk wire fields from start; stop at first implausible top-level tag.
    FileDescriptorProto field numbers are small (1..14)."""
    i = start; n = len(b)
    while i < n:
        save = i
        try:
            tag, j = read_varint(b, i)
        except ValueError:
            break
        fn, wt = tag >> 3, tag & 7
        if fn == 0 or fn > 14 or wt in (3,4,6,7):
            break
        i = j
        try:
            if wt == 0:
                _, i = read_varint(b, i)
            elif wt == 2:
                ln, i = read_varint(b, i)
                if i + ln > n: i = save; break
                i += ln
            elif wt == 5: i += 4
            elif wt == 1: i += 8
        except ValueError:
            i = save; break
    return i

# ---- .proto rendering -------------------------------------------------------
# field names that are the crypto/DRM surface (§0.3) — layout redacted
REDACT_FIELD = ('hello_key', 'devices_key', 'key_response', 'session_key',
                'handshake', 'aes_', 'cipher', 'nonce', 'auth_tag', 'enc_data')

def render_field(f, proto3):
    if any(r in f['name'].lower() for r in REDACT_FIELD):
        return f"  // [REDACTED field {f['number']} '{f['name']}' — protected surface, SPEC §0.3]"
    lbl = LABEL.get(f['label'], '')
    if f['typ'] in (11, 14):
        tname = f['type_name'] or ('message' if f['typ']==11 else 'enum')
    else:
        tname = PROTO_TYPE.get(f['typ'], 'bytes')
    # proto3: singular (label optional) fields carry no label keyword; keep repeated.
    if proto3:
        pre = 'repeated ' if lbl == 'repeated' else ''
    else:
        pre = (lbl + ' ') if lbl else ''
    return f"  {pre}{tname} {f['name']} = {f['number']};"

def render_message(d, redact, proto3, indent=0):
    pad = '  ' * indent
    out = [f"{pad}message {d['name']} {{"]
    is_redacted = any(r in d['name'] for r in redact)
    if is_redacted:
        nf = len(d['fields'])
        out.append(f"{pad}  // [REDACTED — protected surface, SPEC §0.3] {nf} field(s) present; layout omitted")
    else:
        for e in d['enums']:
            out += [pad+'  '+l for l in render_enum(e).splitlines()]
        for nd in d['nested']:
            out += render_message(nd, redact, proto3, indent+1).splitlines()
        for f in d['fields']:
            out.append(pad + render_field(f, proto3))
    out.append(f"{pad}}}")
    return '\n'.join(out)

def render_enum(e):
    out = [f"enum {e['name']} {{"]
    seen = [v for _, v in e['values']]
    if len(seen) != len(set(seen)):
        out.append("  option allow_alias = true;")
    for n, v in e['values']:
        out.append(f"  {n} = {v};")
    out.append("}")
    return '\n'.join(out)

def collect_types(fdp):
    """Return {fully.qualified.Name: filename} for every message/enum defined."""
    pkg = fdp['package']
    out = {}
    def walk(d, prefix):
        full = (prefix + '.' + d['name']) if prefix else d['name']
        out[full] = fdp['name']
        for e in d['enums']:
            out[full + '.' + e['name']] = fdp['name']
        for nd in d['nested']:
            walk(nd, full)
    base = pkg
    for m in fdp['messages']: walk(m, base)
    for e in fdp['enums']:
        out[(base + '.' + e['name']) if base else e['name']] = fdp['name']
    return out

def collect_refs(fdp):
    refs = set()
    def walk(d):
        for f in d['fields']:
            if f['typ'] in (11, 14) and f['type_name']:
                refs.add(f['type_name'])
        for nd in d['nested']: walk(nd)
    for m in fdp['messages']: walk(m)
    return refs

def render_proto(fdp, redact, imports):
    proto3 = fdp['syntax'] in ('proto3', 'editions')
    out = [f"// recovered FileDescriptorProto: {fdp['name']}"]
    if fdp['syntax'] == 'editions':
        out.append('edition = "2023";')
    else:
        out.append(f'syntax = "{fdp["syntax"]}";')
    if fdp['package']:
        out.append(f"package {fdp['package']};")
    for imp in sorted(imports):
        out.append(f'import "{imp}";')
    out.append("")
    for e in fdp['enums']:
        out.append(render_enum(e)); out.append("")
    for m in fdp['messages']:
        out.append(render_message(m, redact, proto3)); out.append("")
    return '\n'.join(out)

def count(fdp):
    nm = ne = nf = 0
    def walk(d):
        nonlocal nm, nf, ne
        nm += 1; nf += len(d['fields']); ne += len(d['enums'])
        for nd in d['nested']: walk(nd)
    for m in fdp['messages']: walk(m)
    ne += len(fdp['enums'])
    return nm, ne, nf

def main():
    binp, outd = sys.argv[1], sys.argv[2]
    redact = []
    if '--redact' in sys.argv:
        redact = sys.argv[sys.argv.index('--redact')+1].split(',')
    b = open(binp, 'rb').read()
    os.makedirs(outd, exist_ok=True)
    blobs = find_fdp_blobs(b)
    fdps = []
    for st, en in blobs:
        try:
            fdp = parse_fdp(b[st:en])
        except Exception:
            continue
        if not fdp['messages'] and not fdp['enums']: continue
        if (fdp['package'] or '').startswith('google.protobuf'):
            print(f"(skipped bundled {fdp['name']})"); continue
        fdp['_st'], fdp['_len'] = st, en - st
        fdps.append(fdp)
    # global type index across this binary's descriptors
    index = {}
    for fdp in fdps:
        index.update(collect_types(fdp))
    results = []
    for fdp in fdps:
        imports = set()
        for ref in collect_refs(fdp):
            if ref in index and index[ref] != fdp['name']:
                imports.add(index[ref])
            elif ref.startswith('google.protobuf.'):
                imports.add('google/protobuf/' +
                    re.sub(r'(?<!^)(?=[A-Z])', '_', ref.split('.')[-1]).lower() + '.proto')
        name = fdp['name'] or ('blob_%x.proto' % fdp['_st'])
        if not name.endswith('.proto'): name += '.proto'
        dest = os.path.join(outd, name)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, 'w') as f:
            f.write(render_proto(fdp, redact, imports) + '\n')
        nm, ne, nf = count(fdp)
        results.append((name, fdp['package'], nm, ne, nf, fdp['_st'], fdp['_len']))
    for name, pkg, nm, ne, nf, st, ln in results:
        print(f"{name:42s} pkg={pkg:26s} msgs={nm:4d} enums={ne:3d} fields={nf:5d} len={ln}")
    print(f"TOTAL file-descriptors: {len(results)}")

if __name__ == '__main__':
    main()
