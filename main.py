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
    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

    detector = GestureDetector()
    ui = UIOverlay(1280, 720)
    canvas = Canvas(1280, 720)

    base_options = python.BaseOptions(model_asset_path='hand_landmarker.task')
    options = vision.HandLandmarkerOptions(
        base_options=base_options,
        num_hands=2, 
        min_hand_detection_confidence=0.5,
        min_hand_presence_confidence=0.5,
        running_mode=vision.RunningMode.VIDEO
    )
    landmarker = vision.HandLandmarker.create_from_options(options)

    # State Variables
    color_idx, size_idx = 0, 2
    prev_gesture = Gesture.UNKNOWN
    
    # --- COOLDOWN VARIABLES ---
    last_size_change_time = 0.0
    COOLDOWN_DURATION = 5.0 # seconds
    
    # --- ANTI-FLICKER VARIABLES ---
    lock_active = False
    lock_smoothing_frames = 0
    LOCK_TIMEOUT = 10 
    
    start_time_ms = int(time.time() * 1000)
    last_timestamp_ms = -1

    while cap.isOpened():
        success, frame = cap.read()
        if not success: break

        frame = cv2.flip(frame, 1)
        h, w, _ = frame.shape
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
        
        current_time_ms = int(time.time() * 1000) - start_time_ms
        if current_time_ms <= last_timestamp_ms: current_time_ms = last_timestamp_ms + 1
        last_timestamp_ms = current_time_ms
        
        result = landmarker.detect_for_video(mp_image, current_time_ms)
        
        current_frame_lock_detected = False
        painter_res = None

        if result.hand_landmarks:
            for landmarks in result.hand_landmarks:
                wrist = landmarks[0]
                px_x = int(wrist.x * w)
                
                if px_x > 900: 
                    res = detector.detect_tasks(landmarks, w, h)
                    if res.gesture == Gesture.THICKNESS: 
                        current_frame_lock_detected = True
                else:
                    if painter_res is None:
                        painter_res = detector.detect_tasks(landmarks, w, h)

        if current_frame_lock_detected:
            lock_active = True
            lock_smoothing_frames = LOCK_TIMEOUT
        else:
            if lock_smoothing_frames > 0:
                lock_smoothing_frames -= 1
            else:
                lock_active = False

        # --- GESTURE ACTIONS ---
        current_gesture_name = "IDLE"
        index_tip = None
        
        # Calculate remaining thickness cooldown
        time_since_change = time.time() - last_size_change_time
        cooldown_rem = max(0.0, COOLDOWN_DURATION - time_since_change)

        if painter_res:
            current_gesture = painter_res.gesture
            current_gesture_name = current_gesture.name
            index_tip = painter_res.index_tip

            if current_gesture == Gesture.COLOR and prev_gesture != Gesture.COLOR:
                color_idx = (color_idx + 1) % len(PALETTE)
                ui.flash(f"COLOR: {PALETTE[color_idx][0]}")
            elif current_gesture == Gesture.THICKNESS and prev_gesture != Gesture.THICKNESS:
                if cooldown_rem == 0.0:
                    size_idx = (size_idx + 1) % len(BRUSH_SIZES)
                    ui.flash(f"SIZE: {BRUSH_SIZES[size_idx]}px")
                    last_size_change_time = time.time()
                    cooldown_rem = COOLDOWN_DURATION 
                else:
                    current_gesture_name = "THICKNESS_COOLDOWN"
            
            elif lock_active:
                if current_gesture == Gesture.DRAW:
                    canvas.draw_stroke(index_tip, PALETTE[color_idx][1], BRUSH_SIZES[size_idx])
                elif current_gesture == Gesture.ERASE:
                    canvas.erase(index_tip)
            
            if not lock_active or current_gesture != Gesture.DRAW:
                canvas.end_stroke()
            prev_gesture = current_gesture
        else:
            canvas.end_stroke()

        combined = canvas.composite_onto(frame)
        ui.draw_lock_zone(combined, lock_active)
        
        output = ui.render(combined, color_idx, size_idx, current_gesture_name, 
                           index_tip, (lock_active and painter_res and painter_res.gesture == Gesture.DRAW), 
                           (lock_active and painter_res and painter_res.gesture == Gesture.ERASE), 
                           (painter_res and painter_res.gesture == Gesture.COLOR),
                           cooldown_rem) 

        cv2.imshow("AI Painter - Rock Solid Mode", output)
        if cv2.waitKey(1) & 0xFF == ord('q'): break

    cap.release()
    cv2.destroyAllWindows()
    landmarker.close()

if __name__ == "__main__":
    main()