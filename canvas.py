"""
canvas.py
---------
Manages the drawing canvas: strokes, undo history, erasing, saving.
The canvas lives as a transparent BGRA NumPy array that is blended
on top of the camera feed each frame.
"""

import time
import cv2
import numpy as np
from pathlib import Path
from typing import Optional, Tuple, List


class Canvas:
    MAX_UNDO = 20   # max history depth

    def __init__(self, width: int, height: int):
        self.width  = width
        self.height = height

        # BGRA canvas — drawn strokes go here
        self._layer  = np.zeros((height, width, 4), dtype=np.uint8)
        self._history: List[np.ndarray] = []   # undo stack

        self._last_pos: Optional[Tuple[int, int]] = None
        self._drawing = False

    # ------------------------------------------------------------------ canvas ops

    def begin_stroke(self):
        """Call when the user starts a new stroke (finger went down)."""
        self._save_snapshot()
        self._last_pos = None
        self._drawing  = True

    def end_stroke(self):
        self._last_pos = None
        self._drawing  = False

    def draw_stroke(
        self,
        pos: Tuple[int, int],
        color_bgr: Tuple[int, int, int],
        thickness: int,
    ):
        """Draw a smooth line from the last position to `pos`."""
        if not self._drawing:
            self.begin_stroke()

        if self._last_pos is not None:
            cv2.line(
                self._layer,
                self._last_pos,
                pos,
                (*color_bgr, 255),   # full alpha
                thickness,
                lineType=cv2.LINE_AA,
            )
            # Draw a filled circle at the tip for smooth caps
            cv2.circle(self._layer, pos, thickness // 2, (*color_bgr, 255), -1, cv2.LINE_AA)
        else:
            # First point of a stroke — just a dot
            cv2.circle(self._layer, pos, thickness // 2, (*color_bgr, 255), -1, cv2.LINE_AA)

        self._last_pos = pos

    def erase(self, pos: Tuple[int, int], radius: int = 30):
        """Erase a circular area around `pos`."""
        cv2.circle(self._layer, pos, radius, (0, 0, 0, 0), -1)

    def clear(self):
        self._save_snapshot()
        self._layer[:] = 0

    def undo(self):
        if self._history:
            self._layer = self._history.pop()

    def save(self, directory: str = ".") -> str:
        """Save the canvas (transparent PNG) and a flat composite (PNG)."""
        ts   = time.strftime("%Y%m%d_%H%M%S")
        path = Path(directory) / f"drawing_{ts}.png"
        cv2.imwrite(str(path), self._layer)
        return str(path)

    # ------------------------------------------------------------------ blending

    def composite_onto(self, frame_bgr: np.ndarray) -> np.ndarray:
        """Alpha-blend the canvas layer on top of `frame_bgr`. Returns BGR."""
        # Split canvas into BGR + alpha mask
        b, g, r, a = cv2.split(self._layer)
        alpha = a.astype(np.float32) / 255.0

        result = frame_bgr.copy().astype(np.float32)
        for c_idx, channel in enumerate([b, g, r]):
            result[:, :, c_idx] = (
                channel.astype(np.float32) * alpha
                + result[:, :, c_idx] * (1.0 - alpha)
            )
        return np.clip(result, 0, 255).astype(np.uint8)

    # ------------------------------------------------------------------ internal

    def _save_snapshot(self):
        self._history.append(self._layer.copy())
        if len(self._history) > self.MAX_UNDO:
            self._history.pop(0)