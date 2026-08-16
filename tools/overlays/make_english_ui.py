"""English MEMORY.TIM (memory-card messages) and PC_MAKE1.TIM (charset
buttons). Edits only the text pixels inside each box; borders, portraits,
cursor art untouched."""
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy.ndimage import binary_dilation
import timcodec

OUT="/mnt/user-data/outputs/english_overlays"
FONT="/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
S=4

def text_cov(text, fs, pad=2):
    f=ImageFont.truetype(FONT, fs*S)
    dr=ImageDraw.Draw(Image.new("L",(4,4)))
    tw=int(dr.textlength(text,font=f))
    img=Image.new("L",(tw+pad*2*S,(fs+pad*2)*S),0)
    ImageDraw.Draw(img).text((pad*S,pad*S),text,fill=255,font=f)
    return np.asarray(img.resize((img.width//S,img.height//S),Image.LANCZOS)).astype(np.float32)/255.

def stamp(a, cov, cx, cy, body, aa, ring_idx=None):
    h,w=cov.shape; x0=int(cx-w/2); y0=int(cy-h/2)
    bodym=cov>=0.38; aam=(cov>=0.15)&~bodym
    ringm=binary_dilation(bodym|aam,iterations=1)&~(bodym|aam) if ring_idx is not None else np.zeros_like(bodym)
    for yy in range(h):
        for xx in range(w):
            X,Y=x0+xx,y0+yy
            if not(0<=X<256 and 0<=Y<256): continue
            if bodym[yy,xx]: a[Y,X]=body
            elif aam[yy,xx]: a[Y,X]=aa
            elif ringm[yy,xx] and ring_idx is not None: a[Y,X]=ring_idx

def edit_region(a, x0,x1,y0,y1, erase, fill):
    sub=a[y0:y1, x0:x1]
    sub[np.isin(sub, list(erase))]=fill

# ---------------- MEMORY.TIM ----------------
m=timcodec.decode("/mnt/user-data/uploads/MEMORY.TIM")
a=np.array(m["idx"],dtype=np.uint8).reshape(256,256)
orig=a.copy()
TEXT={1,2,5}
# strip rects + fills + lines: (x0,x1,y0,y1,fill,[(text,cx,cy,fs)])
strips=[
 (0,224,0,32,4,[("No memory card is inserted.",112,8,10),
                ("The game cannot be saved.",112,24,10)]),
 (0,224,32,48,4,[("The memory card is not formatted.",112,40,10)]),
 (0,176,48,64,3,[("Format the memory card?",88,56,10)]),
 (0,176,64,80,3,[("Yes",50,72,10),("No",121,72,10)]),
 (0,192,80,112,4,[("There are not enough free blocks.",96,88,10),
                  ("The game cannot be saved.",96,104,10)]),
 (0,95,112,128,6,[("Data error",46,120,9)])  # erase to x95, preserve cursor arrow,
]
for (x0,x1,y0,y1,fill,lines) in strips:
    edit_region(a,x0,x1,y0,y1,TEXT,fill)
    for (t,cx,cy,fs) in lines:
        stamp(a, text_cov(t,fs), cx, cy, body=5, aa=1, ring_idx=2)
# safety: outside strip rects unchanged
delta=(a!=orig)
for (x0,x1,y0,y1,_,_l) in strips: delta[y0:y1,x0:x1]=False
assert delta.sum()==0, delta.sum()
tim=timcodec.encode(m,a.flatten())
open(f"{OUT}/MEMORY.TIM","wb").write(tim)
o=open("/mnt/user-data/uploads/MEMORY.TIM","rb").read()
print("MEMORY.TIM:", len(tim)==len(o), tim[:8+m['clen']]==o[:8+m['clen']])

# ---------------- PC_MAKE1.TIM ----------------
m2=timcodec.decode("/mnt/user-data/uploads/PC_MAKE1.TIM")
b=np.array(m2["idx"],dtype=np.uint8).reshape(256,256)
orig2=b.copy()
BTN_TEXT={15,1}
labels=["Hiragana","Katakana","ABC","abc"]
boxes=[(1,63),(65,127),(129,191),(193,255)]
for (bx0,bx1),lab in zip(boxes,labels):
    ix0,ix1 = bx0+5, bx1-5          # interior inside bevel
    edit_region(b, ix0,ix1, 182,194, BTN_TEXT, 2)
    fs = 9 if len(lab)>4 else 10
    stamp(b, text_cov(lab,fs), (bx0+bx1)//2, 188, body=15, aa=1)
delta=(b!=orig2)
for (bx0,bx1) in boxes: delta[182:194, bx0+5:bx1-5]=False
assert delta.sum()==0, delta.sum()
tim2=timcodec.encode(m2,b.flatten())
open(f"{OUT}/PC_MAKE1.TIM","wb").write(tim2)
o2=open("/mnt/user-data/uploads/PC_MAKE1.TIM","rb").read()
print("PC_MAKE1.TIM:", len(tim2)==len(o2), tim2[:8+m2['clen']]==o2[:8+m2['clen']])
