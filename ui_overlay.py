# ui_overlay.py — Draws everything the user sees on screen that is NOT the drawing itself:
# the color/size toolbar, cursor ring, lock-zone box, status labels, flash banners, and help text.

import cv2
import numpy as np
from typing import Optional, Tuple

# --- Color palette ---
# Each entry is (display name, BGR color tuple).
# BGR = Blue-Green-Red (OpenCV stores colors in this order, not RGB).
PALETTE = [                              # list[ tuple[str, tuple[int, int, int]] ]
    ("White",   (255, 255, 255)),         # tuple: (name, BGR tuple)
    ("Red",     (  0,   0, 220)),
    ("Orange",  (  0, 140, 255)),
    ("Yellow",  (  0, 220, 220)),
    ("Green",   ( 50, 200,  50)),
    ("Cyan",    (220, 200,   0)),
    ("Blue",    (220,  80,   0)),
    ("Violet",  (200,   0, 180)),
    ("Pink",    (180,  80, 220)),
]

# Available brush sizes in pixels (diameter)
BRUSH_SIZES = [3, 6, 10, 16, 24, 36]     # list[int]

# What color each gesture name gets in the status label at the bottom of the screen
GESTURE_COLORS = {                       # dict[str, tuple[int, int, int]]
    "DRAW":               (  0, 220, 100),   # green
    "HOVER":              (200, 200,   0),   # yellow
    "ERASE":              (  0, 100, 255),   # orange
    "CLEAR":              (  0,   0, 220),   # red
    "COLOR":              (220, 100, 220),   # purple
    "THICKNESS":          (100, 220, 220),   # teal
    "THICKNESS_COOLDOWN": (  0, 140, 255),   # orange (warning)
    "UNKNOWN":            (120, 120, 120),   # grey
}


class UIOverlay:
    TOOLBAR_H = 70    # int — height of the top toolbar bar in pixels
    SWATCH_R  = 18    # int — radius of each color circle in the toolbar
    SWATCH_PAD = 10   # int — gap between color circles
    FONT      = cv2.FONT_HERSHEY_SIMPLEX  # int (OpenCV font ID constant)

    def __init__(self, frame_w: int, frame_h: int):
        self.w = frame_w                  # int
        self.h = frame_h                  # int

        # Flash message state — a large center-screen banner shown briefly after an action
        self._flash_msg:   Optional[str] = None   # str | None
        self._flash_timer: int = 0                # int — counts down in frames; 0 = hidden

    def render(
        self,
        frame:         np.ndarray,
        color_idx:     int,
        size_idx:      int,
        gesture_name:  str,
        index_tip:     Optional[Tuple[int, int]],
        is_drawing:    bool,    # True when actively drawing a stroke
        is_erasing:    bool,    # True when actively erasing
        is_pinching:   bool,    # True when doing the color-change pinch
        size_cooldown: float,   # seconds remaining on the brush-size cooldown (0 = available)
    ) -> np.ndarray:
        """Compose all UI elements onto a copy of `frame` and return the result."""
        out = frame.copy()                # np.ndarray (BGR image)

        self._draw_toolbar(out, color_idx, size_idx)
        self._draw_cooldown_indicator(out, size_cooldown)
        self._draw_gesture_label(out, gesture_name, size_cooldown)
        self._draw_cursor(out, index_tip, is_drawing, is_erasing, is_pinching,
                          PALETTE[color_idx][1], BRUSH_SIZES[size_idx])
        self._draw_flash(out)
        self._draw_help(out)

        return out

    def draw_lock_zone(self, img: np.ndarray, is_locked: bool):
        """
        Draw the lock-zone bounding box in the bottom-right corner.
        Green + "LOCK: ACTIVE" when a fist is detected there; red otherwise.
        Called separately from render() so it sits beneath the other UI layers.
        """
        zone_w, zone_h = 320, 220              # ints (tuple unpacking)
        x1, y1 = self.w - zone_w, self.h - zone_h   # ints
        x2, y2 = self.w, self.h                # ints

        color  = (0, 255, 0) if is_locked else (0, 0, 255)  # tuple[int, int, int] — BGR
        status = "LOCK: ACTIVE" if is_locked else "LOCK: OFF (FIST HERE)"   # str

        cv2.rectangle(img, (x1, y1), (x2, y2), color, 3)  # (x1,y1)/(x2,y2) are tuples (points)
        cv2.putText(img, status, (x1 + 15, y1 + 40), self.FONT, 0.55, color, 2, cv2.LINE_AA)

        # Faint semi-transparent fill so the zone is visible without being distracting
        overlay = img.copy()                   # np.ndarray
        cv2.rectangle(overlay, (x1, y1), (x2, y2), color, -1)
        cv2.addWeighted(overlay, 0.1, img, 0.9, 0, img)

    # ------------------------------------------------------------------ private helpers

    def _draw_toolbar(self, img: np.ndarray, color_idx: int, size_idx: int):
        """Draw the dark top bar with color swatches and brush-size circles."""
        # Semi-transparent dark background strip
        overlay = img.copy()
        cv2.rectangle(overlay, (0, 0), (self.w, self.TOOLBAR_H), (20, 20, 20), -1)
        cv2.addWeighted(overlay, 0.65, img, 0.35, 0, img)

        # Draw color swatches left to right; highlight the selected one with a white ring
        x, y = self.SWATCH_PAD + self.SWATCH_R, self.TOOLBAR_H // 2   # ints
        for i, (name, bgr) in enumerate(PALETTE):   # i: int, name: str, bgr: tuple[int,int,int]
            if i == color_idx:
                cv2.circle(img, (x, y), self.SWATCH_R + 4, (255, 255, 255), 2)  # selection ring
            cv2.circle(img, (x, y), self.SWATCH_R, bgr, -1)
            x += 2 * self.SWATCH_R + self.SWATCH_PAD

        # Draw brush-size preview dots; selected one is white, others are grey
        bx = x + 30
        for i, sz in enumerate(BRUSH_SIZES):
            col = (255, 255, 255) if i == size_idx else (140, 140, 140)
            cv2.circle(img, (bx, y), max(2, sz // 2), col, -1)
            bx += sz + 12

    def _draw_cooldown_indicator(self, img: np.ndarray, cooldown: float):
        """Show a countdown timer in the toolbar while brush-size changes are blocked."""
        if cooldown <= 0:
            return  # nothing to show when not on cooldown
        text = f"SIZE LOCK: {cooldown:.1f}s"    # str (f-string)
        cv2.putText(img, text, (self.w - 220, self.TOOLBAR_H // 2 + 7),
                    self.FONT, 0.6, (0, 140, 255), 2, cv2.LINE_AA)

    def _draw_gesture_label(self, img: np.ndarray, gesture_name: str, size_cooldown: float):
        """Display a human-readable status line in the bottom-left corner."""
        col = GESTURE_COLORS.get(gesture_name, (200, 200, 200))   # tuple[int,int,int] — BGR

        # Map internal gesture names to friendlier display strings
        label_text = {                            # dict[str, str] lookup → str
            "DRAW":               "STATUS: DRAWING",
            "HOVER":              "STATUS: HOVERING",
            "ERASE":              "STATUS: ERASING",
            "CLEAR":              "STATUS: READY TO CLEAR",
            "COLOR":              "STATUS: CHANGING COLOR",
            "THICKNESS":          "STATUS: CHANGING SIZE",
            "THICKNESS_COOLDOWN": "STATUS: SIZE LOCKED (WAIT)",
            "UNKNOWN":            "STATUS: IDLE",
        }.get(gesture_name, "STATUS: IDLE")

        cv2.putText(img, label_text, (12, self.h - 16), self.FONT,
                    0.65, col, 2, cv2.LINE_AA)

    def _draw_cursor(
        self,
        img:       np.ndarray,
        tip:       Optional[Tuple[int, int]],
        is_drawing: bool,
        is_erasing: bool,
        is_pinching: bool,
        color_bgr: Tuple[int, int, int],
        brush_size: int,
    ):
        """
        Draw a visual indicator around the fingertip so the user can see exactly
        where on screen their finger is and what mode is active.
        """
        if tip is None:
            return           # no hand detected — nothing to draw
        x, y = tip           # ints (unpack tuple[int, int])
        if y < self.TOOLBAR_H:
            return           # finger is inside the toolbar area — hide the cursor

        if is_erasing:
            # Large orange ring showing the erase radius
            cv2.circle(img, (x, y), 30, (0, 100, 255), 2)
        elif is_drawing:
            # Ring sized to match the current brush, plus a small center dot
            cv2.circle(img, (x, y), brush_size // 2 + 2, color_bgr, 2)
            cv2.circle(img, (x, y), 3, color_bgr, -1)
        else:
            # Neutral grey ring for hover / idle
            cv2.circle(img, (x, y), 14, (200, 200, 200), 1)

    def _draw_flash(self, img: np.ndarray):
        """Show a large center-screen message for ~1.5 seconds (45 frames) after an action."""
        if self._flash_timer <= 0 or self._flash_msg is None:
            return
        (tw, th), _ = cv2.getTextSize(self._flash_msg, self.FONT, 0.8, 2)  # tuple[tuple[int,int], int]
        # Center the text horizontally
        cv2.putText(img, self._flash_msg, ((self.w - tw) // 2, self.h // 2),
                    self.FONT, 0.8, (80, 220, 120), 2, cv2.LINE_AA)
        self._flash_timer -= 1  # count down each frame until it disappears

    def _draw_help(self, img: np.ndarray):
        """Render a small static gesture cheat-sheet in the top-right corner."""
        lines = [                       # list[str]
            "Index Only: Draw",
            "Index+Mid: Hover",
            "Open Palm: Erase",
            "Pinch: Color",
            "Fist: Size / Lock",
        ]
        x, y = self.w - 180, self.TOOLBAR_H + 20   # ints
        for line in lines:               # line: str
            cv2.putText(img, line, (x, y), self.FONT, 0.4, (160, 160, 160), 1, cv2.LINE_AA)
            y += 18

    def flash(self, msg: str, frames: int = 45):
        """Trigger a flash banner. `frames` controls how long it stays on screen."""
        self._flash_msg   = msg
        self._flash_timer = frames
