# Output formats

Measured on the winged-eye (1086×362, 15 s, 94 frames incl. 41 wing-flap frames):
WebP q80 3.3 MB · GIF 5.1 MB. Test at 800 px, 6 s, whole-image motion every frame: APNG 33 MB · WebM 0.67 MB · MOV 1.0 MB · MP4 0.68 MB · GIF 9.9 MB.
Rule: size is driven by how many pixels change per frame. Holds are free; whole-wing/whole-image motion is expensive.

| format | alpha | edges | size | where it plays | encode |
|---|---|---|---|---|---|
| APNG `.png` (default) | 8-bit | perfect, lossless | largest | all modern browsers, `<img>` | `encode.apng` |
| WebP | 8-bit | smooth (lossy RGB) | ~10× smaller than APNG | all modern browsers, `<img>` | `encode.webp` (q 85–92) |
| WebM VP9 | 8-bit | smooth | tiny | Chrome/Firefox/Edge (Safari: no alpha) | `encode.webm` |
| MOV HEVC | 8-bit | smooth | tiny | Safari (macOS/iOS) | `encode.mov` |
| MP4 H.264 | none | smooth on given bg | tiny | everywhere | `encode.mp4 --bg '#hex'` |
| GIF | 1-bit | jagged | large | everywhere | `encode.gif` |

Reduce size without losing quality: lower `--width` (2× the CSS display width is enough for retina), fewer moving pixels, step 50–60 ms for slow motions.

## Embedding
```html
<!-- APNG / WebP -->
<img src="anim.png" width="540" alt="" decoding="async">

<!-- transparent video: Safari needs HEVC, others VP9 -->
<video id="a" autoplay loop muted playsinline width="540"></video>
<script>
  const v = document.getElementById('a');
  const safari = /^((?!chrome|android).)*safari/i.test(navigator.userAgent);
  v.src = safari ? 'anim.mov' : 'anim.webm';
</script>
```
Respect reduced motion: `@media (prefers-reduced-motion: reduce)` → show a static `source.png` instead.
