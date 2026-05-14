# VirtualDrawing — How It Works

> A complete guide written for beginners. No prior programming knowledge required.

---

## What This Is

A drawing app controlled entirely by your hands in front of a webcam — no mouse, no touchscreen, no special hardware beyond the camera built into your laptop.

- Your webcam feed plays in the background.
- An invisible digital canvas floats on top of it, like a sheet of transparent glass.
- You hold your hands up and make shapes with your fingers to draw, erase, and change settings.
- One hand draws; the other acts as a safety switch to prevent accidental marks.

---

## How to Run It

**1. Set up the environment (first time only)**

```bash
# Create a virtual environment — an isolated sandbox for this project's packages
python -m venv venv

# Activate it (Mac/Linux)
source venv/bin/activate

# Install the required libraries
pip install -r requirements
```

**2. Download the AI model (first time only)**

The hand-tracking model is not included in the repo because it is a large binary file.
Download it and place it in the project folder:

```bash
curl -o hand_landmarker.task \
  https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/latest/hand_landmarker.task
```

Or visit the official page: [developers.google.com/mediapipe/solutions/vision/hand_landmarker](https://developers.google.com/mediapipe/solutions/vision/hand_landmarker)

**3. Run**

```bash
python main.py
```

**4. Quit**

Press `q` while the window is focused.

---

## Gesture Quick Reference

| What your left hand does | Gesture name | Lock required? |
|---|---|---|
| Point index finger only | **DRAW** — leaves ink on canvas | YES — right-hand fist in lock zone |
| Point index + middle finger | **HOVER** — moves cursor, no ink | No |
| Open all 4 fingers flat | **ERASE** — wipes a circle of paint | YES — right-hand fist in lock zone |
| Touch thumb tip to index tip | **COLOR** — cycles to next color | No |
| Make a fist | **SIZE** — cycles to next brush size | No (5 s cooldown applies) |

**Right hand (lock zone — far right of screen):**
Make a fist → the lock zone box turns green → drawing and erasing are now enabled.

**Edge-triggering:** COLOR and SIZE only fire once when the gesture first appears. Holding the gesture does nothing extra — you must release and re-form it to trigger again.

### Available Colors (cycle with pinch)

White → Red → Orange → Yellow → Green → Cyan → Blue → Violet → Pink → *(loops back)*

### Available Brush Sizes (cycle with fist)

3 px → 6 px → 10 px → 16 px → 24 px → 36 px → *(loops back)*

---

## How the App Sees Your Hand

Your webcam captures roughly 30 images per second, called **frames**. Each frame is passed to a pre-built AI model called **MediaPipe HandLandmarker**.

The model locates your hand and returns **21 tracking points** called **landmarks** — one for each key joint:

```
 0 = Wrist
 4 = Thumb tip
 8 = Index finger tip       6 = Index finger middle joint (PIP)
12 = Middle finger tip      10 = Middle finger middle joint (PIP)
16 = Ring finger tip        14 = Ring finger middle joint (PIP)
20 = Pinky tip              18 = Pinky middle joint (PIP)
```

Each point has an `x` (left/right) and `y` (up/down) value between `0.0` and `1.0`, where `(0,0)` is the top-left corner of the frame.

**How a finger is detected as "up":**
The tip must be higher on screen than the middle joint. "Higher" means a *smaller* `y` value because `y = 0` is the top of the screen.

```
If landmark[8].y  <  landmark[6].y  →  index finger is UP
```

The app checks all four outer fingers and counts how many are extended. That count, plus whether the thumb and index are touching, maps directly to the gestures in the table above.

---

## The Two-Zone System

**Problem:** If drawing activated the moment a finger pointed up, the canvas would fill with unwanted marks every time a hand entered the frame.

**Solution:** The 1280 px wide screen is divided into two zones:

```
|←————————— Painter Zone (0–900 px) ————————————→|←— Lock Zone (900–1280 px) —→|
|                  Left 70%                        |        Right 30%            |
|  Color, Size, Draw, Erase, Hover all happen here | Fist here = safety switch   |
```

- **Painter zone** (left 70%, wrist x ≤ 900): reads your drawing gestures.
- **Lock zone** (right 30%, wrist x > 900): only watches for a fist. Anything else is ignored.

Gestures that *change settings* (color, size) work from the painter zone with no lock needed.
Gestures that *modify the canvas* (draw, erase) require the right-hand lock to be active simultaneously — like a dead man's switch on heavy machinery.

---

## The 5-Second Size Cooldown

A fist is a natural transition shape — your hand briefly passes through it every time you open or close your fingers. Without protection, size would change accidentally dozens of times per session.

**Fix:** After each size change, a 5-second lockout activates. Any fist detected during that window is ignored and the status label changes to `STATUS: SIZE LOCKED (WAIT)`. A countdown (`SIZE LOCK: 3.4s`) ticks in the toolbar until it clears.

---

## The Anti-Flicker System

Computer vision occasionally loses track of a hand for one or two frames due to fast motion or changes in lighting. Without mitigation, this causes the lock to blink off and on, creating jittery, broken strokes.

**Fix:** A grace-period counter called `lock_smoothing_frames` is set to `10` whenever a valid lock fist is detected. If the model misses the fist for a frame, the counter drops by 1 but the lock *stays active*. The lock only disengages after 10 consecutive frames with no fist detected — smoothly absorbing brief tracking drops.

---

## The Drawing Canvas

File: `canvas.py`

The canvas is an invisible **grid of pixel values** stored in memory as a NumPy array — a fast, maths-friendly table of numbers. Its size matches the video feed exactly:

```
1280 columns × 720 rows = 921,600 pixels
```

Each pixel stores four numbers: **B**lue, **G**reen, **R**ed, **A**lpha. This is called **BGRA format** (OpenCV uses BGR instead of the more common RGB — just a different ordering convention).

- `Alpha = 0` → pixel is fully transparent → camera feed shows through
- `Alpha = 255` → pixel is fully opaque → only paint is visible

**Drawing a stroke:** OpenCV draws a line from the last known finger position to the current one (`cv2.line`, anti-aliased). A small filled circle is painted at each new tip to give strokes smooth, rounded caps instead of flat cut-offs.

**Erasing:** A circle of 30 px radius around the fingertip is filled with `(0, 0, 0, 0)` — transparent black — effectively cutting a hole in the paint layer.

### Undo

Every time a new stroke begins, the canvas saves a full copy of itself into a stack list (`_history`, max depth 20). Calling `undo()` pops the most recent copy off the stack and replaces the live canvas with it.

### Saving

`canvas.save()` writes the current layer as a transparent PNG file (e.g. `drawing_20260423_170820.png`). The transparency is preserved so the image can be used over any background.

---

## Blending the Canvas onto the Camera Feed

At the end of every frame, the transparent paint layer must be merged with the live camera image. This is called **alpha blending**:

```
Final pixel = (Paint pixel × opacity) + (Camera pixel × (1 − opacity))
```

- Where `opacity` is the alpha value of that pixel, converted from 0–255 → 0.0–1.0.
- `opacity = 1.0` → only paint is visible (solid brushstroke).
- `opacity = 0.0` → only camera is visible (empty canvas area).

This is computed in floating-point for accuracy, then clamped back to 0–255 integers for display.

---

## The UI Overlay

File: `ui_overlay.py`

Everything drawn on top of the blended image — none of it is part of the canvas or the camera feed:

| Element | Location | What it shows |
|---|---|---|
| **Toolbar** | Top strip (70 px tall) | Color swatches + brush size dots; selected ones are highlighted |
| **Size cooldown timer** | Top-right of toolbar | `SIZE LOCK: 3.4s` — orange countdown when size changes are blocked |
| **Status label** | Bottom-left | Current gesture name in a matching color |
| **Lock zone box** | Bottom-right corner | Green (`LOCK: ACTIVE`) or red (`LOCK: OFF`) with a faint fill |
| **Cursor ring** | Around index fingertip | Sized brush ring when drawing; large orange ring when erasing; grey ring otherwise |
| **Flash banner** | Screen center | Big text for ~1.5 s (45 frames) after a color or size change fires |
| **Help cheat-sheet** | Top-right | Small static text listing each gesture |

---

## The Main Loop

File: `main.py`

Everything runs inside a single loop that repeats ~30 times per second:

```
1.  Read a frame from the webcam.
2.  Mirror it horizontally (so left/right feel natural, like a mirror).
3.  Convert BGR → RGB and wrap it for MediaPipe.
4.  Build a monotonically increasing timestamp (MediaPipe VIDEO mode requires this).
5.  Run hand detection → get up to 2 sets of 21 landmarks.
6.  Sort each detected hand by wrist X position:
      wrist.x > 900  →  right/lock zone  →  check for fist  →  update lock state
      wrist.x ≤ 900  →  painter zone     →  classify gesture
7.  Update lock state (apply anti-flicker grace counter).
8.  Calculate remaining size cooldown.
9.  Act on the painter gesture (priority order):
      COLOR  →  advance color index (edge-triggered)
      SIZE   →  advance size index if cooldown = 0 (edge-triggered)
      DRAW   →  if lock active: draw stroke
      ERASE  →  if lock active: erase circle
10. Alpha-blend canvas onto camera frame.
11. Draw the lock zone box.
12. Render all UI overlay elements on top.
13. Display the final frame in the window.
14. If 'q' pressed → release camera, close window, exit.
```

---

## File Map

```
main.py              — Orchestrator. Loop, state, gesture routing, compositing.
gesture_detector.py  — Reads 21 landmarks, returns a Gesture enum value.
canvas.py            — BGRA NumPy layer: strokes, erase, undo, save, alpha-blend.
ui_overlay.py        — Toolbar, cursors, labels, flash banners, help text.
hand_landmarker.task — Pre-built Google AI model binary. Do not modify.
requirements         — pip dependency list (opencv, mediapipe, numpy).
```

---

## Libraries

| Library | What it does in this project |
|---|---|
| `opencv-python` (`cv2`) | Webcam capture, image drawing primitives, font rendering, display window |
| `mediapipe` | Runs the hand landmark AI model, returns 21 joint positions per hand |
| `numpy` | Stores the canvas as a fast pixel array; used for alpha-blend maths |

---

## About `hand_landmarker.task`

This is a pre-trained AI model from Google's **MediaPipe Solutions** library. You don't write it — you download it once and drop it in the project folder.

- **Official page:** [developers.google.com/mediapipe/solutions/vision/hand_landmarker](https://developers.google.com/mediapipe/solutions/vision/hand_landmarker)
- **Direct download:**

```bash
curl -o hand_landmarker.task \
  https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/latest/hand_landmarker.task
```
