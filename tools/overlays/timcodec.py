"""4-bit TIM decoder/encoder for the ending overlays. Preserves CLUT, VRAM
coords, and all header fields exactly; only the pixel indices are replaced."""
import struct

def decode(path):
    d = open(path, "rb").read()
    magic, flag = struct.unpack_from("<II", d, 0)
    assert magic == 0x10, "not a TIM"
    mode = flag & 7
    assert mode == 0, f"expected 4-bit (mode 0), got mode {mode}"
    p = 8
    clen = struct.unpack_from("<I", d, p)[0]
    ccx, ccy, ccw, cch = struct.unpack_from("<HHHH", d, p+4)
    clut_raw = d[p+12:p+clen]                 # raw CLUT bytes (keep verbatim)
    p += clen
    ilen = struct.unpack_from("<I", d, p)[0]
    ix, iy, iw, ih = struct.unpack_from("<HHHH", d, p+4)
    pix = d[p+12:p+ilen]
    W, H = iw*4, ih
    # unpack 4-bit indices (low nibble = left pixel)
    idx = bytearray(W*H)
    for y in range(H):
        row = y*(iw*2)
        for xb in range(iw*2):
            b = pix[row+xb]
            idx[y*W + xb*2]   = b & 0xF
            idx[y*W + xb*2+1] = b >> 4
    clut = [struct.unpack_from("<H", clut_raw, i*2)[0] for i in range(len(clut_raw)//2)]
    return dict(flag=flag, clut_hdr=(ccx,ccy,ccw,cch), clut_raw=clut_raw, clut=clut,
                img_hdr=(ix,iy,iw,ih), W=W, H=H, idx=idx, ilen=ilen, clen=clen,
                orig_size=len(d))

def encode(meta, idx):
    """Rebuild a TIM from meta (from decode) with new index array `idx`."""
    ix, iy, iw, ih = meta["img_hdr"]
    W, H = iw*4, ih
    assert len(idx) == W*H, f"idx size {len(idx)} != {W*H}"
    pix = bytearray(iw*2*ih)
    for y in range(H):
        row = y*(iw*2)
        for xb in range(iw*2):
            lo = idx[y*W + xb*2] & 0xF
            hi = idx[y*W + xb*2+1] & 0xF
            pix[row+xb] = lo | (hi << 4)
    out = bytearray()
    out += struct.pack("<II", 0x10, meta["flag"])
    out += struct.pack("<I", meta["clen"]) + struct.pack("<HHHH", *meta["clut_hdr"]) + meta["clut_raw"]
    out += struct.pack("<I", meta["ilen"]) + struct.pack("<HHHH", ix,iy,iw,ih) + bytes(pix)
    return bytes(out)
