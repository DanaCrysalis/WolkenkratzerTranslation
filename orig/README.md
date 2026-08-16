# orig/ — pristine Japanese originals (NOT in git)

Place the **untouched** files extracted from a Japanese
*Wolkenkratzer: Shinpan no Tou* (SLPS-00197) disc here:

| file | size (bytes) |
|---|---|
| `MAIN.EXE.bak`    | 1085440 |
| `SLPS_001.97.bak` |  333824 |

Extract with `dumpsxiso "game.bin" -x extracted -s rebuild.xml`, then

```
cp extracted/MAIN.EXE      orig/MAIN.EXE.bak
cp extracted/SLPS_001.97   orig/SLPS_001.97.bak
```

**Do not commit these** (`.gitignore` covers them) and never let a build write
back into this directory — every build must start from these exact bytes.
An already-patched `MAIN.EXE` is *not* a valid seed.
