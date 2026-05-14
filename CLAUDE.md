# VirtualDrawing — Claude Code Context

## What This Is

A real-time webcam drawing app controlled entirely by hand gestures. No mouse or touchscreen. MediaPipe tracks 21 hand landmarks per frame; gesture logic routes actions to a BGRA canvas layer that is alpha-blended over the live camera feed.

Run with: `python main.py` (requires webcam, venv active)
Quit: press `q` in the window.

## File Map

| File | Role |
|---|---|
| `main.py` | Main loop: webcam capture → landmark detection → gesture routing → compositing → display |
| `gesture_detector.py` | Converts raw MediaPipe landmarks into `Gesture` enum values |
| `canvas.py` | 1280×720 BGRA NumPy canvas — stroke drawing, erase, undo (max 20), save, alpha-blend |
| `ui_overlay.py` | Toolbar, cursors, flash messages, lock zone box, help text overlay |
| `hand_landmarker.task` | Pre-built MediaPipe binary model — do not modify |
| `requirements` | `opencv-python>=4.8.0`, `mediapipe>=0.10.0`, `numpy>=1.24.0` |

## Core Architecture

### Two-Zone Layout (1280px wide)
- **Painter zone** (`wrist.x ≤ 900px`, left 70%): reading gestures for draw/erase/color/size
- **Lock zone** (`wrist.x > 900px`, right 30%): right-hand fist here activates the dead-man's switch

### Gesture Table

| Fingers Up | Gesture | Lock Required? |
|---|---|---|
| Index only | DRAW | YES |
| Index + Middle | HOVER | NO |
| All 4 | ERASE | YES |
| Thumb pinches Index | COLOR | NO |
| Fist (0 fingers) | THICKNESS (left) / LOCK (right) | NO |

Detection logic in `gesture_detector.py`: finger "up" = `tip.y < pip.y - 0.02` (normalized coords).

### Key State Variables (`main.py`)
- `color_idx`, `size_idx` — index into `PALETTE` and `BRUSH_SIZES` in `ui_overlay.py`
- `lock_active` + `lock_smoothing_frames` — anti-flicker: lock stays on for 10 frames after last fist detection
- `last_size_change_time` + `COOLDOWN_DURATION = 5.0s` — prevents accidental size triggers; shown as `SIZE LOCK: Xs` in toolbar
- `prev_gesture` — edge-trigger: COLOR and THICKNESS only fire on gesture *transition*, not hold

### Canvas (`canvas.py`)
- BGRA NumPy array, `alpha=0` = transparent, `alpha=255` = solid
- `draw_stroke()` → `cv2.line()` + capped dot at tip (LINE_AA)
- `erase()` → `cv2.circle()` radius 30, sets pixels to `(0,0,0,0)`
- `begin_stroke()` saves a snapshot to `_history` (capped at 20); `undo()` pops it
- `composite_onto(frame_bgr)` → per-channel float32 alpha blend → returns BGR

### UI (`ui_overlay.py`)
- `PALETTE` — 9 colors as `(name, BGR_tuple)`
- `BRUSH_SIZES = [3, 6, 10, 16, 24, 36]`
- `flash(msg, frames=45)` — center-screen banner lasting ~1.5s
- `draw_lock_zone()` — green/red box bottom-right, called *before* `render()` in main loop
- `_draw_help()` — static gesture cheat-sheet top-right corner

## Environment
- Python 3.14, venv at `./venv/`
- Webcam must support 1280×720; MediaPipe runs in `VIDEO` mode (monotonic timestamps required — handled by `current_time_ms` logic in `main.py`)
