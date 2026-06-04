# gesture_detector.py — Reads the 21 hand landmark points from MediaPipe and
# decides what gesture the hand is making (draw, erase, color change, etc.).

import math
from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional, Tuple, List


# All possible gestures the app understands
class Gesture(Enum):                        # Enum (each member is a Gesture value)
    DRAW      = auto()   # index finger only — draw a line
    HOVER     = auto()   # index + middle — move cursor without drawing
    ERASE     = auto()   # all 4 fingers open — erase nearby strokes
    CLEAR     = auto()   # (reserved for future use)
    COLOR     = auto()   # thumb touching index (pinch) — cycle to next color
    THICKNESS = auto()   # fist — change brush size (left hand) or activate lock (right hand)
    UNKNOWN   = auto()   # hand is visible but no recognized gesture


# A small container that bundles the gesture result with useful pixel positions
@dataclass
class GestureResult:                            # dataclass (auto-generated __init__)
    gesture:    Gesture                          # enum value
    index_tip:  Optional[Tuple[int, int]]        # tuple[int, int] | None
    thumb_tip:  Optional[Tuple[int, int]]        # tuple[int, int] | None
    confidence: float                            # float


class GestureDetector:
    # MediaPipe landmark indices — each number refers to a specific joint on the hand
    WRIST      = 0                    # int
    THUMB_TIP  = 4;  THUMB_IP   = 3   # ints — thumb tip and joint just below
    INDEX_TIP  = 8;  INDEX_PIP  = 6   # ints — index tip and middle joint
    MIDDLE_TIP = 12; MIDDLE_PIP = 10  # ints
    RING_TIP   = 16; RING_PIP   = 14  # ints
    PINKY_TIP  = 20; PINKY_PIP  = 18  # ints

    # If the distance between thumb and index tip (in normalized 0-1 coords) is
    # below this value, we consider it a pinch
    PINCH_THRESHOLD = 0.08            # float

    # A finger must be this many units higher than its middle joint to count as "up"
    # (prevents borderline half-bent fingers from triggering incorrectly)
    FINGER_UP_THRESHOLD = 0.02        # float

    def __init__(self):
        # These are kept for future gesture-smoothing logic (not yet used)
        self._prev_gesture        = Gesture.UNKNOWN   # Gesture enum
        self._gesture_hold_frames = 0                  # int
        self._hold_required       = 2                  # int

    def detect_tasks(self, lm_list: List, frame_w: int, frame_h: int) -> GestureResult:
        """
        Takes a list of 21 landmarks for one hand and returns the matching Gesture.
        lm_list entries have .x and .y as normalized floats (0.0 – 1.0).
        frame_w / frame_h are used to convert those floats into pixel coordinates.
        """

        # Convert the two fingertips we care about most into pixel coordinates
        index_tip_px = self._to_px(lm_list[self.INDEX_TIP], frame_w, frame_h)   # tuple[int, int]
        thumb_tip_px = self._to_px(lm_list[self.THUMB_TIP], frame_w, frame_h)   # tuple[int, int]

        # A finger is "up" if its tip is higher on screen than its middle joint.
        # In screen coordinates y=0 is the TOP, so "higher" = smaller y value.
        index_up  = lm_list[self.INDEX_TIP].y  < lm_list[self.INDEX_PIP].y  - self.FINGER_UP_THRESHOLD   # bool
        middle_up = lm_list[self.MIDDLE_TIP].y < lm_list[self.MIDDLE_PIP].y - self.FINGER_UP_THRESHOLD   # bool
        ring_up   = lm_list[self.RING_TIP].y   < lm_list[self.RING_PIP].y   - self.FINGER_UP_THRESHOLD   # bool
        pinky_up  = lm_list[self.PINKY_TIP].y  < lm_list[self.PINKY_PIP].y  - self.FINGER_UP_THRESHOLD   # bool

        # Count how many of the four outer fingers are extended
        fingers_up_count = sum([index_up, middle_up, ring_up, pinky_up])   # int (from list[bool])

        # Measure how close the thumb tip is to the index tip (normalized distance)
        pinch_dist = self._dist(lm_list[self.THUMB_TIP], lm_list[self.INDEX_TIP])   # float
        is_pinch   = pinch_dist < self.PINCH_THRESHOLD                              # bool

        # Map the physical hand shape to a Gesture value (priority order matters)
        if is_pinch:
            raw = Gesture.COLOR         # Gesture enum — thumb + index touching → color change
        elif fingers_up_count == 0:
            raw = Gesture.THICKNESS     # all fingers curled = fist → size / lock
        elif fingers_up_count == 4:
            raw = Gesture.ERASE         # full open palm → erase
        elif index_up and not middle_up:
            raw = Gesture.DRAW          # only index up → draw
        elif index_up and middle_up and not ring_up:
            raw = Gesture.HOVER         # index + middle up → hover (no drawing)
        else:
            raw = Gesture.UNKNOWN

        return GestureResult(raw, index_tip_px, thumb_tip_px, 1.0)   # GestureResult (dataclass)

    @staticmethod
    def _dist(a, b):
        """Euclidean distance between two landmarks in normalized (0-1) space."""
        return math.sqrt((a.x - b.x) ** 2 + (a.y - b.y) ** 2)   # float

    @staticmethod
    def _to_px(lm, w, h):
        """Convert a normalized landmark (0-1) to pixel coordinates."""
        return (int(lm.x * w), int(lm.y * h))   # tuple[int, int]
