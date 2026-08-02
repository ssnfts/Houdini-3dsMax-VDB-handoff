"""
Handing the Houdini cache to Max, and checking it before the host sees it.

The volume itself is the easy part. What goes wrong is the frame either side of
it: a sequence with a hole in it, a naming pattern the host reads differently
from the way it was written, and — the one that actually bit here — disagreement
about whether the cache is in world space or local to some anchor.

**These caches are world space.** Every voxel carries its absolute position on
the circuit, because the sim was built from world-space car poses and never
recentred. Measured on the written files, converted back to Atlas axes, they
span x 473-490, y 258-353, z 8.25-13.5, which brackets the car's own path of
x 474.1-488.7, y 242.2-351.5, z 8.11-10.20. So the correct placement in Max is
the identity transform plus the axis change, and **nothing else**. Loading them
relative to a crash anchor at x 476.9 would move the smoke most of half a
kilometre and still look like a plausible cloud in a viewport.

The axis change is the only transform needed. Houdini is Y-up, Max and Atlas are
Z-up, and Atlas = ``(hx, -hz, hy)``, which is a rotation of +90 degrees about X.
The negated term keeps the frame right-handed; dropping the sign mirrors the
scene, which is invisible in a still and puts the smoke on the wrong side of the
car.

Nothing here names a V-Ray parameter. Those must be read off the live host —
this module refuses to guess them, and the demo script discovers them before it
writes anything.
"""

from __future__ import annotations

import re
from pathlib import Path

__all__ = [
    "X_ROTATION_DEG",
    "houdini_to_atlas",
    "scan_sequence",
    "SequenceError",
]

# Houdini Y-up to Atlas/Max Z-up. Read off the sim's own frame, not recalled.
X_ROTATION_DEG = 90.0

_FRAME = re.compile(r"^(?P<stem>.+?)\.(?P<frame>\d{2,6})\.vdb$", re.IGNORECASE)


class SequenceError(RuntimeError):
    """The cache on disk is not something that should be handed to a renderer."""


def houdini_to_atlas(p):
    """
    ``(x, y, z)`` in Houdini's Y-up frame to Atlas/Max Z-up: ``(x, -z, y)``.

    The inverse of the conversion the emitter applied on the way in, so a round
    trip through the pair must be the identity — which is what the tests check,
    because a mirrored frame is not visible in a still image.
    """
    x, y, z = p
    return (x, -z, y)


def scan_sequence(folder, *, stem: str | None = None) -> dict:
    """
    Inspect a written ``.vdb`` sequence and refuse it if it is not sound.

    Returns the stem, the frame range, the file count and the byte range.

    Raises :class:`SequenceError` for the three ways a cache lies about itself:
    no files at all, a gap in the numbering, or a frame of zero bytes. A hole in
    the middle of a sequence renders as smoke that blinks out for a frame and
    back in, which reads as a glitch in the render rather than as a missing
    file, and by then the render has been paid for.

    Empty *volumes* are fine and expected — the frames before the crash contain
    no density. An empty *file* is not.
    """
    root = Path(folder)
    if not root.is_dir():
        raise SequenceError(f"{root} is not a directory")

    found = {}
    for path in sorted(root.glob("*.vdb")):
        m = _FRAME.match(path.name)
        if not m:
            continue
        if stem is not None and m.group("stem") != stem:
            continue
        found.setdefault(m.group("stem"), {})[int(m.group("frame"))] = path

    if not found:
        raise SequenceError(f"no numbered .vdb files in {root}")

    if len(found) > 1 and stem is None:
        raise SequenceError(
            f"{root} holds more than one sequence ({', '.join(sorted(found))}); "
            f"pass stem= to say which one"
        )

    picked = stem if stem is not None else next(iter(found))
    frames = found[picked]
    lo, hi = min(frames), max(frames)

    missing = [f for f in range(lo, hi + 1) if f not in frames]
    if missing:
        raise SequenceError(
            f"{picked} is missing {len(missing)} frame(s) between {lo} and {hi}: "
            f"{missing[:8]}{'...' if len(missing) > 8 else ''}"
        )

    sizes = {f: p.stat().st_size for f, p in frames.items()}
    empty = sorted(f for f, n in sizes.items() if n == 0)
    if empty:
        raise SequenceError(f"{picked} has zero-byte frames: {empty[:8]}")

    # The digit count matters: a host told to expect four digits will not find
    # files written with three.
    digits = len(_FRAME.match(frames[lo].name).group("frame"))

    return {
        "stem": picked,
        "folder": str(root),
        "first_frame": lo,
        "last_frame": hi,
        "frames": len(frames),
        "digits": digits,
        "example": str(frames[lo]),
        "bytes_total": sum(sizes.values()),
        "bytes_min": min(sizes.values()),
        "bytes_max": max(sizes.values()),
    }
