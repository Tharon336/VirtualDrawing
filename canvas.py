# canvas.py — Manages the invisible drawing layer that sits on top of the camera feed.
# Handles strokes, erasing, undo history, saving, and blending onto a video frame.

import time
import cv2
import numpy as np
from pathlib import Path
from typing import Optional, Tuple, List


class Canvas:
    MAX_UNDO = 20   # how many undo steps to remember

    def __init__(self, width: int, height: int):
        self.width  = width
        self.height = height

        # The drawing surface: a grid of pixels, each with Blue, Green, Red, Alpha values.
        # Alpha=0 means fully transparent (shows camera); Alpha=255 means fully opaque (shows paint).
        self._layer: np.ndarray = np.zeros((height, width, 4), dtype=np.uint8)

        # Stack of previous canvas states for undo (most recent is at the end)
        self._history: List[np.ndarray] = []

        self._last_pos: Optional[Tuple[int, int]] = None  # where the finger was last frame
        self._drawing = False                              # whether a stroke is currently active

    # ------------------------------------------------------------------ canvas ops

    def begin_stroke(self):
        """Call when the user starts a new stroke. Saves current state for undo."""
        self._save_snapshot()
        self._last_pos = None
        self._drawing  = True

    def end_stroke(self):
        """Call when the user lifts their finger. Clears the previous-position memory."""
        self._last_pos = None
        self._drawing  = False

    def draw_stroke(
        self,
        pos:       Tuple[int, int],
        color_bgr: Tuple[int, int, int],
        thickness: int,
    ):
        """
        Draw a smooth line from the last known finger position to `pos`.
        If this is the very first point of a stroke, just paint a dot instead.
        """
        if not self._drawing:
            self.begin_stroke()  # auto-start if called without begin_stroke()

        if self._last_pos is not None:
            # Draw a line from the previous position to the current one
            cv2.line(
                self._layer,
                self._last_pos,
                pos,
                (*color_bgr, 255),     # add full opacity (Alpha=255)
                thickness,
                lineType=cv2.LINE_AA,  # anti-aliased = smooth edges, no jaggies
            )
            # Paint a filled circle at the new tip so line caps are smooth and round
            cv2.circle(self._layer, pos, thickness // 2, (*color_bgr, 255), -1, cv2.LINE_AA)
        else:
            # First point of this stroke — just a single dot
            cv2.circle(self._layer, pos, thickness // 2, (*color_bgr, 255), -1, cv2.LINE_AA)

        self._last_pos = pos  # remember this position for the next frame

    def erase(self, pos: Tuple[int, int], radius: int = 30):
        """Erase a circular area of paint around `pos` by setting pixels back to transparent."""
        cv2.circle(self._layer, pos, radius, (0, 0, 0, 0), -1)  # Alpha=0 = invisible

    def clear(self):
        """Wipe the entire canvas (saves undo first)."""
        self._save_snapshot()
        self._layer[:] = 0  # set every pixel to transparent black

    def undo(self):
        """Restore the canvas to its state before the last stroke or clear."""
        if self._history:
            self._layer = self._history.pop()  # swap in the saved copy

    def save(self, directory: str = ".") -> str:
        """Save the drawing as a transparent PNG file. Returns the file path."""
        ts   = time.strftime("%Y%m%d_%H%M%S")
        path = Path(directory) / f"drawing_{ts}.png"
        cv2.imwrite(str(path), self._layer)
        return str(path)

    # ------------------------------------------------------------------ blending

    def composite_onto(self, frame_bgr: np.ndarray) -> np.ndarray:
        """
        Merge the drawing layer on top of a camera frame using alpha blending.
        Formula per pixel:  result = (paint × opacity) + (camera × (1 − opacity))
        Returns a plain BGR image (no alpha channel) ready to display.
        """
        # Split the 4-channel canvas into colour channels and the alpha mask
        b, g, r, a = cv2.split(self._layer)
        alpha = a.astype(np.float32) / 255.0  # convert 0-255 → 0.0-1.0

        result = frame_bgr.copy().astype(np.float32)

        # Blend each colour channel separately
        for c_idx, channel in enumerate([b, g, r]):
            result[:, :, c_idx] = (
                channel.astype(np.float32) * alpha          # painted pixels
                + result[:, :, c_idx] * (1.0 - alpha)       # camera pixels showing through
            )

        return np.clip(result, 0, 255).astype(np.uint8)  # clamp values and convert back

    # ------------------------------------------------------------------ internal

    def _save_snapshot(self):
        """Push a copy of the current canvas onto the undo stack."""
        self._history.append(self._layer.copy())
        # Drop the oldest entry if we've exceeded the limit
        if len(self._history) > self.MAX_UNDO:
            self._history.pop(0)
