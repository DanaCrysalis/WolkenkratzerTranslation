#!/usr/bin/env python3
"""
patch_levelup.py  --  "elegant" fix for the broken level-up / learn-magic messages.

The game stamps the stat number (and the learned-magic name) into the message
buffer at a HARDCODED byte offset -- the offset where the placeholder sat in the
ORIGINAL Japanese string.  Our English keeps its "XX" (full-width 0x82 0x77 x2)
at the end of the sentence, so the number lands mid-word and the literal XX is
left stranded.

Instead of contorting the English, this patch repoints each stat's digit-writer
to the byte offset where the ENGLISH "XX" actually is, so the natural sentences
("Your strength raised by 4", "Flare magic learned.") render correctly.

Complication: the compiler SHARES two digit-writers:
    W1 @0x80097c50  = STR (via j) + INT (fall-through)   -> stores off 8..11
    W2 @0x80097da4  = magic (via j) + SPD (fall-through)  -> stores off 10..13
    HP has its own inline writer @0x80097948               -> stores off 6..9
    "learn magic" copies a 10-byte name (offsets 2..11)
Each pair needs a DIFFERENT English offset, so we:
  * point every in-place writer at its fall-through stat's offset,
  * re-route each j-entered stat to a writer that already has the right offset
    if one exists (STR usually == HP), otherwise to a private copy placed in
    project free space.

No text/TSV changes; pure code patch.  Run on the BUILT English MAIN.EXE.
VA<->file:  file = VA - 0x80010000 + 0x800
"""
import struct, sys, os, json

BASE = 0x80010000
FB   = 0x800

# ---- pointer table: file offset of the 32-bit string pointer -> stat key ----
PTR = {'HP':0x100968, 'magic':0x10096c, 'STR':0x100970,
       'INT':0x100974, 'SPD':0x100978, 'learn':0x10097c}

# ---- the four digit-store sites of each in-place writer (VA), original imm ----
HP_STORES = [0x800979ac,0x800979b0,0x800979e0,0x800979e4]   # orig 6,7,8,9
W1_STORES = [0x80097cb4,0x80097cb8,0x80097ce8,0x80097cec]   # orig 8,9,10,11  (INT fall-through)
W2_STORES = [0x80097e08,0x80097e0c,0x80097e3c,0x80097e40]   # orig 10,11,12,13 (SPD fall-through)
HP_ORIG=[6,7,8,9]; W1_ORIG=[8,9,10,11]; W2_ORIG=[10,11,12,13]

# in-place writer "ori" entry points (a j-entered stat lands here; its delay-slot
# lui $v0,0x6666 supplies the high half the ori expects)
ENTRY = {'HP':0x80097948, 'INT':0x80097c50, 'SPD':0x80097da4}

# j sites of the two j-entered stats
J_SITE = {'STR':0x80097b9c, 'magic':0x80097aec}      # orig targets W1 / W2

# learn: 6 store sites; dest byte = name_base + delta
LEARN = [(0x8009804c,3),(0x80098050,0),(0x80098054,7),
         (0x80098058,4),(0x8009805c,8),(0x80098060,9)]   # (VA, delta from base)
LEARN_ORIG=[5,2,9,6,10,11]

# self-contained writer template to copy into free space (already ends with
# `j 0x80097e48 ; sll $v0,$t1,0x10`): W1 body 0x80097c50..0x80097cf8
TEMPLATE_VA=(0x80097c50,0x80097cf8)   # [start,end)  == 0xa8 bytes, 42 instrs
TAIL=0x80097e48

def enc_j(t):  return (0x02<<26)|((t>>2)&0x03ffffff)

class Exe:
    def __init__(s,data): s.d=bytearray(data)
    def fo(s,va): return va-BASE+FB
    def r32(s,va): return struct.unpack('<I',s.d[s.fo(va):s.fo(va)+4])[0]
    def w32(s,va,w): s.d[s.fo(va):s.fo(va)+4]=struct.pack('<I',w)
    def rbytes(s,va,n): return bytes(s.d[s.fo(va):s.fo(va)+n])
    def wbytes(s,va,b): s.d[s.fo(va):s.fo(va)+len(b)]=b
    def set_imm(s,va,imm): s.w32(va,(s.r32(va)&0xffff0000)|(imm&0xffff))
    def get_imm(s,va): return s.r32(va)&0xffff
    # file-offset variants (for the pointer table, which we index by file off)
    def r32f(s,off): return struct.unpack('<I',s.d[off:off+4])[0]

def find_xx(e, str_va, want_run):
    """Return byte offset of the first run of >=want_run full-width X (82 77)."""
    seg=e.rbytes(str_va, 96)
    i=0; best=None
    while i < len(seg)-1:
        if seg[i]==0x82 and seg[i+1]==0x77:
            run=0; j=i
            while j<len(seg)-1 and seg[j]==0x82 and seg[j+1]==0x77:
                run+=1; j+=2
            if run>=want_run:
                return i, run
        i+=1
    raise RuntimeError(f"no XX placeholder (>= {want_run}) found at {str_va:#x}")

def main(inp, outp):
    e=Exe(open(inp,'rb').read())
    assert e.d[:8]==b'PS-X EXE', "not a PS-X EXE"
    assert enc_j(0x80097da4)==e.r32(0x80097aec), \
        "magic j != expected -> binary is not the known build (already patched?)"
    # guard: writers must be un-patched (original immediates present)
    for site,orig in zip(HP_STORES,HP_ORIG): assert e.get_imm(site)==orig, f"HP writer changed @{site:#x}"
    for site,orig in zip(W1_STORES,W1_ORIG): assert e.get_imm(site)==orig, f"W1 writer changed @{site:#x}"
    for site,orig in zip(W2_STORES,W2_ORIG): assert e.get_imm(site)==orig, f"W2 writer changed @{site:#x}"
    for (site,_),orig in zip(LEARN,LEARN_ORIG): assert e.get_imm(site)==orig, f"learn copy changed @{site:#x}"

    # ---- discover the real English placeholder offsets ----
    ptr={k:e.r32f(off) for k,off in PTR.items()}
    off={}
    for k in ('HP','magic','STR','INT','SPD'):
        o,run=find_xx(e,ptr[k],2); off[k]=o
        assert run>=2, f"{k}: expected >=2 X, got {run}"
    lb,lrun=find_xx(e,ptr['learn'],5); off['learn']=lb
    print("English placeholder offsets:",{k:off[k] for k in ('HP','magic','STR','INT','SPD','learn')})

    def set_writer(stores, base):
        for site,delta in zip(stores,[0,1,2,3]): e.set_imm(site, base+delta)

    # ---- in-place writers -> their fall-through stat's offset ----
    set_writer(HP_STORES, off['HP'])   # serves HP (fall-through)  [+ maybe STR]
    set_writer(W1_STORES, off['INT'])  # serves INT (fall-through)
    set_writer(W2_STORES, off['SPD'])  # serves SPD (fall-through)

    # ---- learn: 10-byte name copy -> name slot ----
    for (site,delta) in LEARN: e.set_imm(site, off['learn']+delta)

    # ---- free-space allocator (project-vetted, currently all-zero) ----
    fs_list=[]
    _here=os.path.dirname(os.path.abspath(__file__))
    for fsjson in (os.environ.get('WK_DATA','') and
                   os.path.join(os.environ['WK_DATA'],'MAIN_freespace.json'),
                   os.path.join(_here,'..','data','MAIN_freespace.json'),
                   os.path.join(os.path.dirname(os.path.abspath(inp)),'MAIN_freespace.json'),
                   os.path.join('.','MAIN_freespace.json')):
        if fsjson and os.path.exists(fsjson):
            break
    if os.path.exists(fsjson):
        fs_list=json.load(open(fsjson))
    used_fs=[]
    def alloc(nbytes):
        need=nbytes
        # prefer freespace.json chunks that are still all-zero and 4-alignable
        for o,ln in sorted(fs_list,key=lambda x:-x[1]):
            a=(o+3)&~3
            if (o+ln)-a>=need and all(b==0 for b in e.d[a:a+need]) and a not in used_fs:
                used_fs.append(a); return a
        # fallback: scan for an all-zero run in the code image, avoiding known
        # runtime buffers (0x107184, 0x108528)
        i=FB; end=FB+0x108800
        BAD=[(0x107184,0x1081ec),(0x108528,0x10894c)]
        while i<end:
            if e.d[i]==0:
                j=i
                while j<end and e.d[j]==0: j+=1
                a=(i+3)&~3
                if j-a>=need and not any(lo<=a<hi for lo,hi in BAD) and a not in used_fs:
                    used_fs.append(a); return a
                i=j
            else: i+=1
        raise RuntimeError("no free space for relocated writer")

    def make_writer(base):
        """copy the self-contained template, patch its 4 sb offsets to base..base+3"""
        body=bytearray(e.rbytes(TEMPLATE_VA[0], TEMPLATE_VA[1]-TEMPLATE_VA[0]))
        k=0
        for i in range(0,len(body),4):
            w=struct.unpack('<I',body[i:i+4])[0]
            if (w>>26)==0x28:  # sb
                w=(w&0xffff0000)|((base+k)&0xffff); k+=1
                body[i:i+4]=struct.pack('<I',w)
        assert k==4, "template did not contain 4 sb stores"
        fva=BASE+(alloc(len(body))-FB)
        e.wbytes(fva, bytes(body))
        return fva

    # ---- route the two j-entered stats ----
    def route(stat):
        o=off[stat]
        for host,hva in ENTRY.items():
            if off[host]==o:                       # reuse an in-place writer
                e.w32(J_SITE[stat], enc_j(hva));   return f"{stat} -> reuse {host} writer @{hva:#x}"
        fva=make_writer(o)                          # private copy in free space
        e.w32(J_SITE[stat], enc_j(fva));           return f"{stat} -> new writer @{fva:#x}"
    print(route('STR'))
    print(route('magic'))

    # ---- verify ----
    bad=[]
    for k,stores in (('HP',HP_STORES),('INT',W1_STORES),('SPD',W2_STORES)):
        got=[e.get_imm(s) for s in stores]
        exp=[off[k]+d for d in (0,1,2,3)]
        if got!=exp: bad.append((k,got,exp))
    if bad: raise RuntimeError(f"verify failed: {bad}")

    open(outp,'wb').write(e.d)
    assert os.path.getsize(outp)==len(e.d)
    print(f"\nOK -> {outp}  ({len(e.d)} bytes, unchanged size)")

if __name__=='__main__':
    inp = sys.argv[1] if len(sys.argv)>1 else 'MAIN.EXE'
    outp= sys.argv[2] if len(sys.argv)>2 else 'MAIN_fixed.EXE'
    main(inp,outp)
