# main.py — Entry point. Runs the webcam loop, feeds frames into MediaPipe,
# routes detected gestures to the canvas and UI, and displays the result.

import cv2
import numpy as np
import mediapipe as mp
import time
from mediapipe.tasks import python
from mediapipe.tasks.python import vision

from gesture_detector import GestureDetector, Gesture
from canvas import Canvas
from ui_overlay import UIOverlay, PALETTE, BRUSH_SIZES


def main():
    # Open the default webcam (index 0) and request 1280x720 resolution
    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

    # Create our three helper objects — one per "department"
    detector = GestureDetector()          # reads hand shapes
    ui       = UIOverlay(1280, 720)       # draws the toolbar and indicators
    canvas   = Canvas(1280, 720)          # holds the drawing layer

    # Load the pre-built MediaPipe AI model from disk
    base_options = python.BaseOptions(model_asset_path='hand_landmarker.task')
    options = vision.HandLandmarkerOptions(
        base_options=base_options,
        num_hands=2,                              # track up to 2 hands at once
        min_hand_detection_confidence=0.5,        # how sure it must be before reporting a hand
        min_hand_presence_confidence=0.5,
        running_mode=vision.RunningMode.VIDEO     # VIDEO mode requires a timestamp each frame
    )
    landmarker = vision.HandLandmarker.create_from_options(options)

    # --- Persistent state across frames ---
    color_idx, size_idx = 0, 2          # which color and brush size are selected
    prev_gesture = Gesture.UNKNOWN      # tracks last frame's gesture for edge-triggering

    # Cooldown: prevents accidental brush-size changes for 5 s after each change
    last_size_change_time = 0.0
    COOLDOWN_DURATION     = 5.0         # seconds

    # Anti-flicker: keeps the lock active for up to 10 frames after the fist disappears
    lock_active           = False
    lock_smoothing_frames = 0
    LOCK_TIMEOUT          = 10          # frames of grace period

    # MediaPipe VIDEO mode needs monotonically increasing timestamps in milliseconds
    start_time_ms    = int(time.time() * 1000)
    last_timestamp_ms = -1

    # --- Main loop: runs ~30 times per second until 'q' is pressed ---
    while cap.isOpened():
        success, frame = cap.read()
        if not success:
            break                       # camera disconnected — stop

        # Mirror the image so movements feel natural (like a mirror)
        frame = cv2.flip(frame, 1)
        h, w, _ = frame.shape

        # Convert BGR (OpenCV default) → RGB (MediaPipe expects RGB)
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image  = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)

        # Build a safe monotonic timestamp for MediaPipe
        current_time_ms = int(time.time() * 1000) - start_time_ms
        if current_time_ms <= last_timestamp_ms:
            current_time_ms = last_timestamp_ms + 1
        last_timestamp_ms = current_time_ms

        # Run hand detection on this frame
        result = landmarker.detect_for_video(mp_image, current_time_ms)

        # Reset per-frame detection results
        current_frame_lock_detected = False
        painter_res = None

        # Loop through every hand found in this frame
        if result.hand_landmarks:
            for landmarks in result.hand_landmarks:
                wrist = landmarks[0]
                px_x  = int(wrist.x * w)  # convert normalized x (0-1) to pixel x

                if px_x > 900:
                    # RIGHT zone (x > 900): check for a fist to activate the lock
                    res = detector.detect_tasks(landmarks, w, h)
                    if res.gesture == Gesture.THICKNESS:
                        current_frame_lock_detected = True
                else:
                    # LEFT zone (x ≤ 900): this hand does the actual drawing
                    if painter_res is None:
                        painter_res = detector.detect_tasks(landmarks, w, h)

        # Update lock state with anti-flicker smoothing
        if current_frame_lock_detected:
            lock_active           = True
            lock_smoothing_frames = LOCK_TIMEOUT
        else:
            if lock_smoothing_frames > 0:
                lock_smoothing_frames -= 1  # grace period: count down before disabling
            else:
                lock_active = False         # grace period expired — lock is off

        # --- Process gestures ---
        current_gesture_name = "IDLE"
        index_tip = None

        # How many seconds of cooldown are still left for brush size changes
        time_since_change = time.time() - last_size_change_time
        cooldown_rem = max(0.0, COOLDOWN_DURATION - time_since_change)

        if painter_res:
            current_gesture      = painter_res.gesture
            current_gesture_name = current_gesture.name
            index_tip            = painter_res.index_tip

            # COLOR: pinch — only fires on the frame the gesture first appears
            if current_gesture == Gesture.COLOR and prev_gesture != Gesture.COLOR:
                color_idx = (color_idx + 1) % len(PALETTE)
                ui.flash(f"COLOR: {PALETTE[color_idx][0]}")

            # THICKNESS (fist in painter zone): cycle brush size, start cooldown
            elif current_gesture == Gesture.THICKNESS and prev_gesture != Gesture.THICKNESS:
                if cooldown_rem == 0.0:
                    size_idx = (size_idx + 1) % len(BRUSH_SIZES)
                    ui.flash(f"SIZE: {BRUSH_SIZES[size_idx]}px")
                    last_size_change_time = time.time()
                    cooldown_rem = COOLDOWN_DURATION
                else:
                    current_gesture_name = "THICKNESS_COOLDOWN"  # blocked — show warning

            # DRAW / ERASE: only allowed while the right-hand lock is active
            elif lock_active:
                if current_gesture == Gesture.DRAW:
                    canvas.draw_stroke(index_tip, PALETTE[color_idx][1], BRUSH_SIZES[size_idx])
                elif current_gesture == Gesture.ERASE:
                    canvas.erase(index_tip)

            # End the current stroke if we stopped drawing
            if not lock_active or current_gesture != Gesture.DRAW:
                canvas.end_stroke()

            prev_gesture = current_gesture

        else:
            # No hand in the painter zone — stop any active stroke
            canvas.end_stroke()

        # --- Compose the final frame ---

        # Blend the transparent drawing layer on top of the camera image
        combined = canvas.composite_onto(frame)

        # Draw the lock-zone bounding box (green = active, red = off)
        ui.draw_lock_zone(combined, lock_active)

        # Layer all other UI elements (toolbar, cursor, labels, flash) on top
        output = ui.render(
            combined, color_idx, size_idx, current_gesture_name,
            index_tip,
            (lock_active and painter_res and painter_res.gesture == Gesture.DRAW),
            (lock_active and painter_res and painter_res.gesture == Gesture.ERASE),
            (painter_res and painter_res.gesture == Gesture.COLOR),
            cooldown_rem
        )

        # Show the final image in a window
        cv2.imshow("AI Painter - Rock Solid Mode", output)

        # Exit when 'q' is pressed
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    # Clean up hardware and model resources
    cap.release()
    cv2.destroyAllWindows()
    landmarker.close()


if __name__ == "__main__":
    main()
