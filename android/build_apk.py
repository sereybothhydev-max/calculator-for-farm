#!/usr/bin/env python3
"""Build a tiny offline WebView APK for Calculator for Farm without the Android SDK.

Writes classes.dex, binary AndroidManifest.xml and resources.arsc by hand,
zips them with the web app in assets/, and signs with APK Signature Scheme v2.
"""
import hashlib, io, os, struct, sys, zipfile, zlib, datetime

PKG = "farm.calc"
ACTIVITY = "farm.calc.MainActivity"
LABEL = "Calculator for Farm"
VERSION_CODE = int(os.environ.get("VERSION_CODE", "1"))
VERSION_NAME = os.environ.get("VERSION_NAME", "1.0")
MIN_SDK, TARGET_SDK = 24, 34
ICON_RES_ID = 0x7F010000
URL = "file:///android_asset/index.html"

def uleb(n):
    out = bytearray()
    while True:
        b = n & 0x7F; n >>= 7
        if n: out.append(b | 0x80)
        else: out.append(b); return bytes(out)

def align(buf, a):
    while len(buf) % a: buf.append(0)

# ---------------------------------------------------------------- DEX
def build_dex():
    T = dict(main="Lfarm/calc/MainActivity;", act="Landroid/app/Activity;", bundle="Landroid/os/Bundle;",
             wv="Landroid/webkit/WebView;", ws="Landroid/webkit/WebSettings;", ctx="Landroid/content/Context;",
             view="Landroid/view/View;", str="Ljava/lang/String;", V="V", Z="Z", I="I")
    # protos: key -> (shorty, return, params)
    P = {"V": ("V", "V", ()), "V_bundle": ("VL", "V", ("bundle",)), "V_ctx": ("VL", "V", ("ctx",)),
         "V_view": ("VL", "V", ("view",)), "V_str": ("VL", "V", ("str",)), "Z_I": ("ZI", "Z", ("I",)),
         "ws": ("L", "ws", ()), "V_Z": ("VZ", "V", ("Z",))}
    M = {"act_init": ("act", "<init>", "V"), "act_onCreate": ("act", "onCreate", "V_bundle"),
         "act_rwf": ("act", "requestWindowFeature", "Z_I"), "act_scv": ("act", "setContentView", "V_view"),
         "main_init": ("main", "<init>", "V"), "main_onCreate": ("main", "onCreate", "V_bundle"),
         "ws_js": ("ws", "setJavaScriptEnabled", "V_Z"), "ws_dom": ("ws", "setDomStorageEnabled", "V_Z"),
         "wv_init": ("wv", "<init>", "V_ctx"), "wv_gs": ("wv", "getSettings", "ws"),
         "wv_load": ("wv", "loadUrl", "V_str")}
    strings = set(T.values()) | {p[0] for p in P.values()} | {m[1] for m in M.values()} | {URL}
    strings = sorted(strings)
    sidx = {s: i for i, s in enumerate(strings)}
    types = sorted(T.values(), key=lambda s: sidx[s])
    tidx = {s: i for i, s in enumerate(types)}
    ti = lambda k: tidx[T[k]]
    proto_keys = sorted(P, key=lambda k: (ti(P[k][1]), tuple(ti(a) for a in P[k][2])))
    pidx = {k: i for i, k in enumerate(proto_keys)}
    meth_keys = sorted(M, key=lambda k: (ti(M[k][0]), sidx[M[k][1]], pidx[M[k][2]]))
    midx = {k: i for i, k in enumerate(meth_keys)}

    def i35c(op, method, regs):
        regs = list(regs) + [0] * (5 - len(regs))
        return [(len([r for r in regs if r is not None]) and 0) or 0]  # placeholder (unused)

    def invoke(op, mkey, regs):
        n = len(regs); r = list(regs) + [0] * (5 - n)
        return [(n << 12) | (r[4] << 8) | op, midx[mkey], (r[3] << 12) | (r[2] << 8) | (r[1] << 4) | r[0]]

    # onCreate: v0..v3 locals, v4 = this, v5 = bundle
    oncreate = []
    oncreate += invoke(0x6F, "act_onCreate", [4, 5])          # invoke-super
    oncreate += [(1 << 12) | (0 << 8) | 0x12]                 # const/4 v0, 1
    oncreate += invoke(0x6E, "act_rwf", [4, 0])               # requestWindowFeature(FEATURE_NO_TITLE)
    oncreate += [(1 << 8) | 0x22, ti("wv")]                   # new-instance v1, WebView
    oncreate += invoke(0x70, "wv_init", [1, 4])               # invoke-direct WebView(this)
    oncreate += invoke(0x6E, "wv_gs", [1])                    # getSettings
    oncreate += [(2 << 8) | 0x0C]                             # move-result-object v2
    oncreate += invoke(0x6E, "ws_js", [2, 0])
    oncreate += invoke(0x6E, "ws_dom", [2, 0])
    oncreate += invoke(0x6E, "act_scv", [4, 1])               # setContentView(webview)
    oncreate += [(3 << 8) | 0x1A, sidx[URL]]                  # const-string v3, URL
    oncreate += invoke(0x6E, "wv_load", [1, 3])
    oncreate += [0x000E]                                      # return-void
    init = invoke(0x70, "act_init", [0]) + [0x000E]
    codes = [("init", 1, 1, 1, init), ("onCreate", 6, 2, 2, oncreate)]

    HDR = 0x70
    n_s, n_t, n_p, n_m = len(strings), len(types), len(P), len(M)
    off = HDR
    string_ids_off = off; off += 4 * n_s
    type_ids_off = off; off += 4 * n_t
    proto_ids_off = off; off += 12 * n_p
    method_ids_off = off; off += 8 * n_m
    class_defs_off = off; off += 32
    data_off = off

    data = bytearray()
    def pos(): return data_off + len(data)
    # code items
    code_offs = {}
    code_start = pos()
    for name, regs, ins, outs, insns in codes:
        align(data, 4)
        code_offs[name] = pos()
        data += struct.pack("<HHHHII", regs, ins, outs, 0, 0, len(insns))
        data += struct.pack("<%dH" % len(insns), *insns)
    # type lists (params)
    align(data, 4)
    tl_start = pos(); tl_offs = {}; tl_count = 0
    for k in proto_keys:
        params = P[k][2]
        if not params: continue
        key = tuple(ti(a) for a in params)
        if key in tl_offs: continue
        align(data, 4)
        tl_offs[key] = pos(); tl_count += 1
        data += struct.pack("<I", len(key)) + struct.pack("<%dH" % len(key), *key)
    # string data
    sd_start = pos(); sd_offs = []
    for s in strings:
        sd_offs.append(pos())
        data += uleb(len(s)) + s.encode("utf-8") + b"\0"
    # class data
    cd_off = pos()
    data += uleb(0) + uleb(0) + uleb(1) + uleb(1)
    data += uleb(midx["main_init"]) + uleb(0x10001) + uleb(code_offs["init"])
    data += uleb(midx["main_onCreate"]) + uleb(0x4) + uleb(code_offs["onCreate"])
    # map list
    align(data, 4)
    map_off = pos()
    items = [(0x0000, 1, 0), (0x0001, n_s, string_ids_off), (0x0002, n_t, type_ids_off),
             (0x0003, n_p, proto_ids_off), (0x0005, n_m, method_ids_off), (0x0006, 1, class_defs_off),
             (0x2001, len(codes), code_start), (0x1001, tl_count, tl_start), (0x2002, n_s, sd_start),
             (0x2000, 1, cd_off), (0x1000, 1, map_off)]
    data += struct.pack("<I", len(items))
    for t, n, o in items: data += struct.pack("<HHII", t, 0, n, o)

    body = bytearray()
    for o in sd_offs: body += struct.pack("<I", o)
    for t in types: body += struct.pack("<I", sidx[t])
    for k in proto_keys:
        sh, ret, params = P[k]
        body += struct.pack("<III", sidx[sh], ti(ret), tl_offs[tuple(ti(a) for a in params)] if params else 0)
    for k in meth_keys:
        c, name, p = M[k]
        body += struct.pack("<HHI", ti(c), pidx[p], sidx[name])
    body += struct.pack("<IIIIIIII", ti("main"), 0x1, ti("act"), 0, 0xFFFFFFFF, 0, cd_off, 0)
    assert HDR + len(body) == data_off
    file_size = data_off + len(data)
    hdr = bytearray(b"dex\n035\0" + b"\0" * 24)
    hdr += struct.pack("<IIIIII", file_size, HDR, 0x12345678, 0, 0, map_off)
    for n, o in ((n_s, string_ids_off), (n_t, type_ids_off), (n_p, proto_ids_off), (0, 0),
                 (n_m, method_ids_off), (1, class_defs_off), (len(data), data_off)):
        hdr += struct.pack("<II", n, o)
    dex = hdr + body + data
    dex[12:32] = hashlib.sha1(dex[32:]).digest()
    dex[8:12] = struct.pack("<I", zlib.adler32(bytes(dex[12:])))
    return bytes(dex)

# ---------------------------------------------------------------- string pool (UTF-16)
def string_pool(strings):
    offs, blob = [], bytearray()
    for s in strings:
        offs.append(len(blob))
        u = s.encode("utf-16-le")
        blob += struct.pack("<H", len(s)) + u + b"\0\0"
    align(blob, 4)
    hsize = 28
    start = hsize + 4 * len(strings)
    body = b"".join(struct.pack("<I", o) for o in offs) + blob
    return struct.pack("<HHIIIIII", 0x0001, hsize, hsize + len(body), len(strings), 0, 0, start, 0) + body

# ---------------------------------------------------------------- binary manifest
def build_manifest():
    attr_ids = [("label", 0x01010001), ("icon", 0x01010002), ("name", 0x01010003), ("exported", 0x01010010),
                ("configChanges", 0x0101001F), ("minSdkVersion", 0x0101020C), ("versionCode", 0x0101021B),
                ("versionName", 0x0101021C), ("windowSoftInputMode", 0x0101022B), ("targetSdkVersion", 0x01010270)]
    rid = dict(attr_ids)
    strings = [a for a, _ in attr_ids]
    def S(s):
        if s not in strings: strings.append(s)
        return strings.index(s)
    NS_URI = "http://schemas.android.com/apk/res/android"
    S("android"); S(NS_URI)
    TSTR, TREF, TDEC, THEX, TBOOL = 0x03, 0x01, 0x10, 0x11, 0x12
    def A(name, typ, val, android=True):
        return (android, name, typ, val)
    tree = ("manifest", [A("versionCode", TDEC, VERSION_CODE), A("versionName", TSTR, VERSION_NAME),
                         A("package", TSTR, PKG, False)], [
        ("uses-sdk", [A("minSdkVersion", TDEC, MIN_SDK), A("targetSdkVersion", TDEC, TARGET_SDK)], []),
        ("application", [A("label", TSTR, LABEL), A("icon", TREF, ICON_RES_ID)], [
            ("activity", [A("name", TSTR, ACTIVITY), A("exported", TBOOL, 0xFFFFFFFF),
                          A("configChanges", THEX, 0xDA0), A("windowSoftInputMode", THEX, 0x30)], [
                ("intent-filter", [], [
                    ("action", [A("name", TSTR, "android.intent.action.MAIN")], []),
                    ("category", [A("name", TSTR, "android.intent.category.LAUNCHER")], [])])])])])
    nodes = bytearray(); line = [1]
    def node(typ, ext):
        n = struct.pack("<HHIII", typ, 16, 16 + len(ext), line[0], 0xFFFFFFFF) + ext
        line[0] += 1
        return n
    def emit(el):
        name, attrs, kids = el
        ns_idx = S(NS_URI)
        attrs = sorted(attrs, key=lambda a: (0, rid[a[1]]) if a[0] else (1, 0))
        ab = bytearray()
        for android, an, typ, val in attrs:
            ai = S(an)
            if typ == TSTR:
                v = S(val); raw = v
            else:
                v = val; raw = 0xFFFFFFFF
            ab += struct.pack("<IIIHBBI", ns_idx if android else 0xFFFFFFFF, ai, raw, 8, 0, typ, v)
        ext = struct.pack("<IIHHHHHH", 0xFFFFFFFF, S(name), 20, 20, len(attrs), 0, 0, 0) + ab
        out = node(0x0102, ext)
        for k in kids: out += emit(k)
        out += node(0x0103, struct.pack("<II", 0xFFFFFFFF, S(name)))
        return out
    ns = struct.pack("<II", S("android"), S(NS_URI))
    body = node(0x0100, ns) + emit(tree) + node(0x0101, ns)
    pool = string_pool(strings)
    resmap = struct.pack("<HHI", 0x0180, 8, 8 + 4 * len(attr_ids)) + b"".join(struct.pack("<I", i) for _, i in attr_ids)
    content = pool + resmap + body
    return struct.pack("<HHI", 0x0003, 8, 8 + len(content)) + content

# ---------------------------------------------------------------- resources.arsc
def build_arsc():
    gpool = string_pool(["res/drawable/icon.png"])
    tpool = string_pool(["drawable"])
    kpool = string_pool(["icon"])
    spec = struct.pack("<HHIBBHI", 0x0202, 16, 20, 1, 0, 0, 1) + struct.pack("<I", 0)
    config = struct.pack("<I", 64) + b"\0" * 60
    hsize = 8 + 1 + 1 + 2 + 4 + 4 + 64
    entries = struct.pack("<I", 0)
    entry = struct.pack("<HHI", 8, 0, 0) + struct.pack("<HBBI", 8, 0, 0x03, 0)
    tbody = struct.pack("<BBHII", 1, 0, 0, 1, hsize + 4) + config + entries + entry
    tchunk = struct.pack("<HHI", 0x0201, hsize, 8 + len(tbody)) + tbody
    name = PKG.encode("utf-16-le").ljust(256, b"\0")
    phsize = 288
    type_off = phsize; key_off = phsize + len(tpool)
    pbody = struct.pack("<I", 0x7F) + name + struct.pack("<IIIII", type_off, 1, key_off, 1, 0)
    pcontent = pbody + tpool + kpool + spec + tchunk
    pchunk = struct.pack("<HHI", 0x0200, phsize, 8 + len(pcontent)) + pcontent
    content = struct.pack("<I", 1) + gpool + pchunk
    return struct.pack("<HHI", 0x0002, 12, 8 + len(content)) + content

# ---------------------------------------------------------------- zip with 4-byte alignment for stored entries
def build_zip(files):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, data, stored in files:
            zi = zipfile.ZipInfo(name, date_time=(2026, 10, 6, 0, 0, 0))
            zi.compress_type = zipfile.ZIP_STORED if stored else zipfile.ZIP_DEFLATED
            zi.external_attr = 0o644 << 16
            if stored:
                hdr_end = buf.tell() + 30 + len(name.encode())
                pad = (-hdr_end) % 4
                if pad:
                    pad = pad + 4 if pad < 4 else pad
                    zi.extra = struct.pack("<HH", 0xD935, pad - 4) + b"\0" * (pad - 4)
            z.writestr(zi, data)
    return buf.getvalue()

# ---------------------------------------------------------------- APK Signature Scheme v2
def sign_v2(apk, key, cert_der, pub_der):
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding
    eocd = apk.rfind(b"PK\x05\x06")
    cd_off = struct.unpack("<I", apk[eocd + 16:eocd + 20])[0]
    sections = [apk[:cd_off], apk[cd_off:eocd], apk[eocd:]]
    chunks = []
    for sec in sections:
        for i in range(0, len(sec), 1 << 20):
            c = sec[i:i + (1 << 20)]
            chunks.append(hashlib.sha256(b"\xa5" + struct.pack("<I", len(c)) + c).digest())
    digest = hashlib.sha256(b"\x5a" + struct.pack("<I", len(chunks)) + b"".join(chunks)).digest()
    lp = lambda b: struct.pack("<I", len(b)) + b
    ALGO = 0x0103
    digests = lp(lp(struct.pack("<I", ALGO) + lp(digest)))
    certs = lp(lp(cert_der))
    signed_data = digests + certs + lp(b"")
    sig = key.sign(signed_data, padding.PKCS1v15(), hashes.SHA256())
    signer = lp(signed_data) + lp(lp(struct.pack("<I", ALGO) + lp(sig))) + lp(pub_der)
    value = lp(lp(signer))
    pair = struct.pack("<Q", 4 + len(value)) + struct.pack("<I", 0x7109871A) + value
    size = len(pair) + 8 + 16
    block = struct.pack("<Q", size) + pair + struct.pack("<Q", size) + b"APK Sig Block 42"
    new_eocd = bytearray(apk[eocd:])
    new_eocd[16:20] = struct.pack("<I", cd_off + len(block))
    return apk[:cd_off] + block + apk[cd_off:eocd] + bytes(new_eocd)

def load_or_make_key(path):
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    kp, cp = path + ".key.pem", path + ".cert.pem"
    if os.path.exists(kp):
        key = serialization.load_pem_private_key(open(kp, "rb").read(), None)
        cert = x509.load_pem_x509_certificate(open(cp, "rb").read())
    else:
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Calculator for Farm")])
        now = datetime.datetime(2026, 1, 1)
        cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
                .serial_number(x509.random_serial_number()).not_valid_before(now)
                .not_valid_after(now + datetime.timedelta(days=365 * 30)).sign(key, hashes.SHA256()))
        open(kp, "wb").write(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                               serialization.NoEncryption()))
        open(cp, "wb").write(cert.public_bytes(serialization.Encoding.PEM))
    pub = key.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    return key, cert.public_bytes(serialization.Encoding.DER), pub

def main(web_dir, icon_png, out, keybase):
    files = [("AndroidManifest.xml", build_manifest(), False), ("classes.dex", build_dex(), False),
             ("resources.arsc", build_arsc(), True), ("res/drawable/icon.png", open(icon_png, "rb").read(), True)]
    for fn in sorted(os.listdir(web_dir)):
        if fn in ("sw.js",): continue
        files.append(("assets/" + fn, open(os.path.join(web_dir, fn), "rb").read(), False))
    apk = build_zip(files)
    key, cert, pub = load_or_make_key(keybase)
    open(out, "wb").write(sign_v2(apk, key, cert, pub))
    print("wrote", out, os.path.getsize(out), "bytes")

if __name__ == "__main__":
    main(*sys.argv[1:5])
