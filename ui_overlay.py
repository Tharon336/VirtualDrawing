import cv2
import numpy as np
from typing import Optional, Tuple

# -- Palette --
PALETTE = [
    ("White",   (255, 255, 255)),
    ("Red",     (  0,   0, 220)),
    ("Orange",  (  0, 140, 255)),
    ("Yellow",  (  0, 220, 220)),
    ("Green",   ( 50, 200,  50)),
    ("Cyan",    (220, 200,   0)),
    ("Blue",    (220,  80,   0)),
    ("Violet",  (200,   0, 180)),
    ("Pink",    (180,  80, 220)),
]

BRUSH_SIZES = [3, 6, 10, 16, 24, 36]

GESTURE_COLORS = {
    "DRAW":               (  0, 220, 100),
    "HOVER":              (200, 200,   0),
    "ERASE":              (  0, 100, 255),
    "CLEAR":              (  0,   0, 220),
    "COLOR":              (220, 100, 220),
    "THICKNESS":          (100, 220, 220),
    "THICKNESS_COOLDOWN": (  0, 140, 255),
    "UNKNOWN":            (120, 120, 120),
}

class UIOverlay:
    TOOLBAR_H   = 70
    SWATCH_R    = 18
    SWATCH_PAD  = 10
    FONT        = cv2.FONT_HERSHEY_SIMPLEX

    def __init__(self, frame_w: int, frame_h: int):
        self.w = frame_w
        self.h = frame_h
        self._flash_msg: Optional[str] = None
        self._flash_timer = 0

    def render(
        self,
        frame:          np.ndarray,
        color_idx:      int,
        size_idx:       int,
        gesture_name:   str,
        index_tip:      Optional[Tuple[int, int]],
        is_drawing:     bool,
        is_erasing:     bool,
        is_pinching:    bool,
        size_cooldown:  float,
    ) -> np.ndarray:
        out = frame.copy()

        self._draw_toolbar(out, color_idx, size_idx)
        self._draw_cooldown_indicator(out, size_cooldown)
        self._draw_gesture_label(out, gesture_name, size_cooldown)
        self._draw_cursor(out, index_tip, is_drawing, is_erasing, is_pinching,
                          PALETTE[color_idx][1], BRUSH_SIZES[size_idx])
        self._draw_flash(out)
        self._draw_help(out)

        return out

    def draw_lock_zone(self, img, is_locked: bool):
        zone_w, zone_h = 320, 220
        x1, y1 = self.w - zone_w, self.h - zone_h
        x2, y2 = self.w, self.h
        
        color = (0, 255, 0) if is_locked else (0, 0, 255)
        cv2.rectangle(img, (x1, y1), (x2, y2), color, 3)
        
        status = "LOCK: ACTIVE" if is_locked else "LOCK: OFF (FIST HERE)"
        cv2.putText(img, status, (x1 + 15, y1 + 40), self.FONT, 0.55, color, 2, cv2.LINE_AA)
        
        overlay = img.copy()
        cv2.rectangle(overlay, (x1, y1), (x2, y2), color, -1)
        cv2.addWeighted(overlay, 0.1, img, 0.9, 0, img)

    def _draw_toolbar(self, img, color_idx: int, size_idx: int):
        overlay = img.copy()
        cv2.rectangle(overlay, (0, 0), (self.w, self.TOOLBAR_H), (20, 20, 20), -1)
        cv2.addWeighted(overlay, 0.65, img, 0.35, 0, img)

        x, y = self.SWATCH_PAD + self.SWATCH_R, self.TOOLBAR_H // 2
        for i, (name, bgr) in enumerate(PALETTE):
            if i == color_idx:
                cv2.circle(img, (x, y), self.SWATCH_R + 4, (255, 255, 255), 2)
            cv2.circle(img, (x, y), self.SWATCH_R, bgr, -1)
            x += 2 * self.SWATCH_R + self.SWATCH_PAD

        bx = x + 30
        for i, sz in enumerate(BRUSH_SIZES):
            selected = (i == size_idx)
            col = (255, 255, 255) if selected else (140, 140, 140)
            cv2.circle(img, (bx, y), max(2, sz // 2), col, -1)
            bx += sz + 12

    def _draw_cooldown_indicator(self, img, cooldown: float):
        """Draws a persistent timer in the toolbar when size is on cooldown."""
        if cooldown <= 0: return
        
        text = f"SIZE LOCK: {cooldown:.1f}s"
        # Position it to the right of the brush sizes
        cv2.putText(img, text, (self.w - 220, self.TOOLBAR_H // 2 + 7), 
                    self.FONT, 0.6, (0, 140, 255), 2, cv2.LINE_AA)

    def _draw_gesture_label(self, img, gesture_name: str, size_cooldown: float):
        col = GESTURE_COLORS.get(gesture_name, (200, 200, 200))
        
        label_text = {
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

    def _draw_cursor(self, img, tip, is_drawing, is_erasing, is_pinching, color_bgr, brush_size):
        if tip is None: return
        x, y = tip
        if y < self.TOOLBAR_H: return

        if is_erasing:
            cv2.circle(img, (x, y), 30, (0, 100, 255), 2)
        elif is_drawing:
            cv2.circle(img, (x, y), brush_size // 2 + 2, color_bgr, 2)
            cv2.circle(img, (x, y), 3, color_bgr, -1)
        else:
            cv2.circle(img, (x, y), 14, (200, 200, 200), 1)

    def _draw_flash(self, img):
        if self._flash_timer <= 0 or self._flash_msg is None: return
        (tw, th), _ = cv2.getTextSize(self._flash_msg, self.FONT, 0.8, 2)
        cv2.putText(img, self._flash_msg, ((self.w - tw) // 2, self.h // 2),
                    self.FONT, 0.8, (80, 220, 120), 2, cv2.LINE_AA)
        self._flash_timer -= 1

    def _draw_help(self, img):
        lines = [
            "Index Only: Draw",
            "Index+Mid: Hover",
            "Open Palm: Erase",
            "Pinch: Color",
            "Fist: Size / Lock",
        ]
        x, y = self.w - 180, self.TOOLBAR_H + 20
        for line in lines:
            cv2.putText(img, line, (x, y), self.FONT, 0.4, (160, 160, 160), 1, cv2.LINE_AA)
            y += 18

    def flash(self, msg: str, frames: int = 45):
        self._flash_msg = msg
        self._flash_timer = frames