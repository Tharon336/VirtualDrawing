---

# What This Project Is and How It Works

## (Explained for Someone Who Barely Knows Programming)

---

## The Big Picture

This is a **drawing app that uses your webcam and your hands** — no mouse, no touchscreen. You hold your hands up in front of the camera to change configurations and paint on screen. It's like drawing in the air.

Here's what it looks like in action:

* Your webcam shows your face/room in the background.
* A digital canvas (like a transparent sheet of glass) sits on top of the camera feed.
* The app uses a **Two-Handed System**: one hand changes settings or draws, while the other hand acts as a safety valve.
* **Global Actions vs. Drawing Actions:** You can change your brush color or size at absolutely any time. However, to actually leave ink on the canvas or erase it, your other hand must grant permission.

---

## The Files — What Each One Does

Think of each `.py` file as a "department" in a company. Each department has one job.

```
main.py              — The Boss. Runs everything, tracks timers, and connects all departments.
gesture_detector.py  — The Eye. Looks at your hand and interprets its physical shape.
canvas.py            — The Painter. Manages the hidden drawing grid and stroke paths.
ui_overlay.py        — The Designer. Draws the toolbar, text labels, and tracking cursors.
hand_landmarker.task — The Brain (pre-built). A ready-made AI model that finds hands.
requirements         — The Shopping List. Tells Python what extra tools it needs to install.

```

### Where `hand_landmarker.task` Comes From

This file is a pre-trained AI model provided by Google as part of their **MediaPipe Solutions** library. It is not something you write yourself — you simply download it and place it next to your code.

* **Official download page:** [https://developers.google.com/mediapipe/solutions/vision/hand_landmarker](https://developers.google.com/mediapipe/solutions/vision/hand_landmarker)
* **Direct download link (float16, latest):** `https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/latest/hand_landmarker.task`

To re-download it from the terminal:
```bash
curl -o hand_landmarker.task https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/latest/hand_landmarker.task
```

---

## How a Computer "Sees" Your Hand

Your webcam captures about 30 images per second (called **frames**). For each frame, the app uses a pre-built AI model called **MediaPipe HandLandmarker** to find your hands.

The model returns **21 points** called **landmarks** — imagine 21 tiny tracking dots placed on key joints of your hand:

```
Tip of index finger = point 8
Tip of middle finger = point 12
Tip of ring finger = point 16
Tip of pinky = point 20
Tip of thumb = point 4
Wrist = point 0

```

Each point has an `x` (how far left/right) and `y` (how far up/down) position, represented as a decimal between 0.0 and 1.0. For example, `x=0.5, y=0.5` means a joint is sitting in the exact center of the video frame.

---

## The "Lock Zone" System & Gesture Separation

**Problem:** If drawing activated just by pointing your finger, the app would start sketching lines the moment your hand appeared on screen — even if you were just adjusting your posture or moving your hand out of the way.

**Solution:** The screen is split into two distinct functional zones:

* **Left 70%** = "Painter Zone" — this hand controls configurations, drawing, and erasing.
* **Right 30%** = "Lock Zone" — this hand acts as a safety switch.

To keep the user experience as fluid as possible, the application handles gestures using two different execution pathways:

1. **Global Configuration (Unlocked):** Changing your brush **Color** (pinching) or brush **Size** (making a fist) works instantly. You do not need your opposite hand to engage the lock to change your preferences.
2. **Canvas Modification (Locked):** **Drawing** and **Erasing** actually modify the picture. Because of this, they are strictly locked. They will only work if your right hand is inside the Lock Zone making a tight fist. Think of it like a "dead man's switch" on heavy machinery — you must actively hold the switch open to paint.

---

## Gesture Recognition — How the App Reads Hand Shapes

File: `gesture_detector.py`

After the AI hands over the 21 tracking points, this file figures out **what shape your hand is making**.

The trick is simple: **is each finger pointing up or curled down?**
A finger is considered "up" if its **tip** is higher on screen than its **middle joint** (called the PIP joint). In computer graphics, "higher" means a smaller `y` value because `y=0` sits at the very top of the screen.

```
Index finger tip  = point 8
Index finger PIP  = point 6

If point8.y < point6.y → index finger is UP

```

By checking all four outer fingers, we count how many are extended. Because a **Fist** is incredibly distinct and reliable for an AI to track, we repurposed it to act as both our Lock trigger and our Thickness modifier!

| Fingers Up | Gesture Detected | What It Does | Lock Required? |
| --- | --- | --- | --- |
| **Index only** | DRAW | Draws a line at your fingertip | **YES** |
| **All 4 fingers** | ERASE | Wipes away nearby drawings | **YES** |
| **Thumb touching Index** | COLOR | Cycles to the next toolbar color | NO |
| **0 fingers (Fist)** | THICKNESS | Cycles brush size (Left) / Engages Lock (Right) | NO |
| **Index + Middle** | HOVER | Moves cursor smoothly without drawing | NO |

### The 5-Second Size Cooldown

Because a fist is a "middle-ground" gesture — meaning your hand naturally forms a fist for a split second whenever you open or close your fingers — it is easy to accidentally trigger a brush size change.

To solve this, a **5-second time delay** is built into the engine. The moment you make a fist in the Painter zone, your brush size changes, and a safety lockout timer activates. For the next 5 seconds, any accidental fists are ignored.

---

## The Drawing Canvas — How Strokes Are Stored

File: `canvas.py`

The "canvas" is a **grid of numbers in memory** called a **NumPy array**. Think of it as a giant spreadsheet where each cell represents one single pixel on your screen.

The canvas matches your video feed at **1280 pixels wide × 720 pixels tall** = 921,600 individual cells. Each cell stores 4 distinct values: Blue, Green, Red, and Alpha (transparency). This is known as **BGRA format**.

* `Alpha = 0` means completely transparent (the cell is empty, revealing the webcam feed behind it).
* `Alpha = 255` means completely solid color (you see only the digital paint).

When drawing a line, the app uses **OpenCV** to track your previous finger coordinate and draw a continuous path to your current coordinate. It applies anti-aliasing (`cv2.LINE_AA`) to ensure lines stay perfectly smooth and crisp rather than jagged. It also plants a tiny solid circle at the tip of each line segment to give your curves clean, rounded caps.

### Undo History

Every time your finger touches down to begin a new stroke, the canvas **saves a snapshop copy of itself** into an internal stack list called `_history`. The system holds onto your last 20 actions. If you invoke an undo command, it discards the broken top layer and restores the last saved spreadsheet state.

---

## Blending the Drawing onto the Camera Feed

At the tail end of every single frame frame calculation, the transparent canvas must merge seamlessly with your raw incoming webcam footage. This mathematical process is called **alpha blending**:

$$\text{Final Pixel Color} = (\text{Drawing Pixel} \times \text{Opacity}) + (\text{Camera Pixel} \times (1 - \text{Opacity}))$$

* If `Opacity = 1.0` (solid paint), the camera pixel is completely covered.
* If `Opacity = 0.0` (empty canvas), the math drops the drawing completely and passes the raw camera feed straight through.

---

## The UI Overlay — Indicators and Timers

File: `ui_overlay.py`

This department handles rendering all visual assets that are not the drawing or the background video:

* **Top Toolbar:** Renders your interactive color palette swatches and brush thickness circles. These act as passive feedback indicators displaying your current brush attributes.
* **Lock Zone Status Box:** A structural bounding box rendered in the bottom right corner. It glows **Green** (`LOCK: ACTIVE`) when a fist is registered on the right side of the screen, and **Red** (`LOCK: OFF`) when drawing is unauthorized.
* **Persistent Cooldown Timer:** If your brush size configuration is locked inside its 5-second safety window, an orange countdown indicator dynamically materializes in the top right of your toolbar (e.g., `SIZE LOCK: 3.4s`).
* **Dynamic Status Label:** Tucked into the bottom-left corner, this displays what gesture is actively processing. If you make a fist while the size picker is locked out, it updates to an orange alert: `STATUS: SIZE LOCKED (WAIT)`.
* **System Feedback Flashes:** When a settings swap successfully fires, a bold text banner flashes in the center of your view for roughly 1.5 seconds (45 frames) to call out the change.

---

## The Main Loop — How It All Runs

File: `main.py`

The core script executes a tight **system loop**, repeating these steps roughly 30 times per second until a user terminates the program:

```
1. Capture an image frame from your attached webcam.
2. Mirror the frame horizontally so your movements feel intuitive.
3. Feed the image array into the MediaPipe AI HandLandmarker engine.
4. Separate hand landmarks by their physical coordinates:
     - Is the hand coordinate X > 900 (Right 30%)? → Check for fist → If found, flag Lock Detected.
     - Is the hand coordinate X <= 900 (Left 70%)? → Check shape → Identify Painter Gesture.
5. Cooldown Management: Calculate exact time elapsed since the last brush size modification.
6. Process Gestures based on Priority:
     - Is it a COLOR pinch? → Advance selected color palette index.
     - Is it a THICKNESS fist? → Is Cooldown at 0.0s? 
          ↳ YES: Increment brush size, save time stamp, reset 5s window.
          ↳ NO: Override status name to "THICKNESS_COOLDOWN".
     - Is the right-hand Safety Lock engaged?
          ↳ DRAW gesture → Draw smooth line paths at index fingertip location.
          ↳ ERASE gesture → Clear transparent pixel values surrounding the index tip.
7. Perform alpha blending calculations to fuse your canvas layer onto the video frame.
8. Layer the UI artwork, bounding boxes, text strings, and countdown values on top.
9. Render the final composite image into a display window.
10. Check keyboard state: If 'q' is pressed, break loop, release camera, and terminate.

```

---

## The "Anti-Flicker" System

Computer vision engines occasionally drop track or **miss a hand for an isolated frame or two** due to rapid motion or lighting changes. Without built-in mitigation, this causes drawing tools to stutter or drop out entirely.

To prevent this, the engine employs an internal grace period counter called `lock_smoothing_frames`. When a lock gesture is validated, this counter is instantly set to `10`. If the tracking engine drops your hand for a frame, the counter drops by 1 but keeps the drawing engine active. The lock only disengages if the gesture is completely missing for 10 sequential frames, smoothly absorbing momentary tracking drops.

---

## Libraries Used

| Library | Functional Responsibility |
| --- | --- |
| `opencv-python` (`cv2`) | Handles webcam hardware access, drawing geometries, font rendering, and window output. |
| `mediapipe` | Utilizes localized machine learning models to track 21 skeletal hand coordinates in real time. |
| `numpy` | Manages the high-speed multi-channel matrix math arrays required to process pixel layouts. |

---

