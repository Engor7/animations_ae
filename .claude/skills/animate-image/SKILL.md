---
name: animate-image
description: Animate a flat PNG illustration into a smooth looping animation (APNG by default; WebP/WebM/MOV/MP4/GIF on request) — eyes that look around and blink, flapping wings, floating, breathing, swaying, glowing. Use whenever the user gives an image and says what should move.
---

# Animate an image

Budget: aim for ≤ 3 image Reads and one render-fix loop. Reuse `animkit`; never hand-scan pixels in loops.

## 1. Intake (no questions unless something essential is missing)
- `Read` the source once. Note what moves (from the user) and what must stay still.
- Defaults if unspecified: APNG at source resolution, 8–15 s seamless loop, 25 fps (step 40 ms), subtle UI-friendly motion.
- Work inside the user's composition folder (see CLAUDE.md); copy `.claude/skills/animate-image/template_anim.py` there only if a Python render is really needed.

## 2. Measure parts (fast)
- Programmatic first: OpenCV on alpha/colors — `cv2.connectedComponentsWithStats`, `cv2.findContours`, `cv2.inRange`,
  `cv2.HoughCircles` / `cv2.fitEllipse`, `np.polyfit` on edge points for lids/curves.
- If a coordinate is easier to eyeball: `animkit grid source.png grid.png --box … --zoom 2` and Read that one image.
- Print numbers, don't render overlays unless a fit looks wrong.

## 3. Build layers (see reference/techniques.md for recipes)
- Everything premultiplied float32 (`core.load`). Masks are soft coverage 0..1.
- Split moving parts from static ones with masks; reconstruct what a moving part uncovers
  (`core.inpaint`, `core.radial_fill_from_reflection`, flat fill + `core.high_pass_texture` grain).
- Prefer motions that never uncover unknown pixels (rotation about a round body's center, eyelid covering, iris under lids).
- **Identity check**: `render(neutral_state)` vs source → mean abs diff should be < 0.1; fix before animating.

## 4. Motion
- `state(t)` returns a dict of floats; build with `timeline` helpers: `Moves` (saccades/looks), `blink`, `oscillation`
  (flaps/wags from keyframed extremes), `Track`, `breathe` (seamless sines), `pulse`.
- Alive = irregular: vary hold lengths (0.6–2.5 s), add micro-moves, blink during gaze shifts, occasional double blink,
  secondary actions (lid droops when looking down, eye glances up during a flap).
- Event times multiples of 40 ms; loop end state == start state.

## 5. Render → check → encode
- `render.render_frames(tl.schedule(state, LOOP_MS), render_frame, out/frames)` (parallel).
- One contact sheet of key moments (`preview.contact_sheet(..., times=[…])`, optionally `crop=` a detail). Read it once.
- Encode requested format(s); encoders verify duration + per-frame alpha and print OK/FAIL. FAIL → fix, don't hand-inspect.
- Real-browser look only if needed: `preview.html` + `python3 -m http.server 8765 --directory <folder>` (background)
  → Playwright `browser_navigate` → `browser_take_screenshot`.

## 6. Deliver
Short Russian summary: file paths, size, resolution, loop length, what moves. Mention size trade-offs only if the file is heavy
(> ~10 MB) with one concrete option (width, WebP, video). See reference/formats.md for embedding snippets.
