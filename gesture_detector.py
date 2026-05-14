import math
from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional, Tuple, List

class Gesture(Enum):
    DRAW      = auto()
    HOVER     = auto()
    ERASE     = auto()
    CLEAR     = auto() 
    COLOR     = auto()
    THICKNESS = auto()
    UNKNOWN   = auto()

@dataclass
class GestureResult:
    gesture: Gesture
    index_tip: Optional[Tuple[int, int]]
    thumb_tip: Optional[Tuple[int, int]]
    confidence: float

class GestureDetector:
    WRIST = 0
    THUMB_TIP = 4;  THUMB_IP = 3
    INDEX_TIP = 8;  INDEX_PIP = 6
    MIDDLE_TIP = 12; MIDDLE_PIP = 10
    RING_TIP = 16;  RING_PIP = 14
    PINKY_TIP = 20; PINKY_PIP = 18

    PINCH_THRESHOLD = 0.08
    FINGER_UP_THRESHOLD = 0.02

    def __init__(self):
        self._prev_gesture = Gesture.UNKNOWN
        self._gesture_hold_frames = 0
        self._hold_required = 2 

    def detect_tasks(self, lm_list: List, frame_w: int, frame_h: int) -> GestureResult:
        index_tip_px = self._to_px(lm_list[self.INDEX_TIP], frame_w, frame_h)
        thumb_tip_px = self._to_px(lm_list[self.THUMB_TIP], frame_w, frame_h)

        # Detect fingers up
        index_up  = lm_list[self.INDEX_TIP].y < lm_list[self.INDEX_PIP].y - self.FINGER_UP_THRESHOLD
        middle_up = lm_list[self.MIDDLE_TIP].y < lm_list[self.MIDDLE_PIP].y - self.FINGER_UP_THRESHOLD
        ring_up   = lm_list[self.RING_TIP].y < lm_list[self.RING_PIP].y - self.FINGER_UP_THRESHOLD
        pinky_up  = lm_list[self.PINKY_TIP].y < lm_list[self.PINKY_PIP].y - self.FINGER_UP_THRESHOLD
        
        fingers_up_count = sum([index_up, middle_up, ring_up, pinky_up])
        
        pinch_dist = self._dist(lm_list[self.THUMB_TIP], lm_list[self.INDEX_TIP])
        is_pinch = pinch_dist < self.PINCH_THRESHOLD

        if is_pinch:
            raw = Gesture.COLOR
        elif fingers_up_count == 0:
            raw = Gesture.THICKNESS # Fist is now Thickness (Left hand) and Lock (Right hand)
        elif fingers_up_count == 4:
            raw = Gesture.ERASE
        elif index_up and not middle_up:
            raw = Gesture.DRAW
        elif index_up and middle_up and not ring_up:
            raw = Gesture.HOVER
        else:
            raw = Gesture.UNKNOWN

        return GestureResult(raw, index_tip_px, thumb_tip_px, 1.0)

    @staticmethod
    def _dist(a, b): return math.sqrt((a.x - b.x)**2 + (a.y - b.y)**2)
    @staticmethod
    def _to_px(lm, w, h): return (int(lm.x * w), int(lm.y * h))