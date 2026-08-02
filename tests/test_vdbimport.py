"""Tests for vdbimport.py — offline, no Max and no Houdini."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

import vdbimport  # noqa: E402


def _seq(root, stem="smoke", lo=1373, hi=1380, digits=4, skip=(), empty=()):
    root.mkdir(parents=True, exist_ok=True)
    for f in range(lo, hi + 1):
        if f in skip:
            continue
        p = root / f"{stem}.{f:0{digits}d}.vdb"
        p.write_bytes(b"" if f in empty else b"x" * 100)
    return root


# ── the axis change ───────────────────────────────────────────────────────────

def test_up_maps_to_up():
    """Houdini +Y is up; Atlas +Z is up."""
    assert vdbimport.houdini_to_atlas((0, 1, 0)) == pytest.approx((0, 0, 1))


def test_round_trip_with_the_emitter_is_the_identity():
    """
    The emitter converts Atlas -> Houdini; this converts back. If the pair is
    not the identity the smoke is mirrored, which a still image will not show.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))
    import tyresmoke

    for p in [(1, 2, 3), (-4.5, 0.0, 9.25), (480.7, 279.3, 8.877)]:
        assert vdbimport.houdini_to_atlas(tyresmoke.to_houdini(p)) == \
            pytest.approx(p)


def test_conversion_is_not_mirrored():
    ex = vdbimport.houdini_to_atlas((1, 0, 0))
    ey = vdbimport.houdini_to_atlas((0, 1, 0))
    ez = vdbimport.houdini_to_atlas((0, 0, 1))
    cross = (ex[1] * ey[2] - ex[2] * ey[1],
             ex[2] * ey[0] - ex[0] * ey[2],
             ex[0] * ey[1] - ex[1] * ey[0])
    assert sum(c * e for c, e in zip(cross, ez)) == pytest.approx(1.0)


def test_rotation_matches_the_conversion():
    """
    +90 degrees about X must reproduce houdini_to_atlas exactly, since that
    rotation is what gets typed into the host.
    """
    import math
    t = math.radians(vdbimport.X_ROTATION_DEG)
    for p in [(1, 2, 3), (-4.5, 7.0, 9.25)]:
        x, y, z = p
        rotated = (x, y * math.cos(t) - z * math.sin(t),
                   y * math.sin(t) + z * math.cos(t))
        assert rotated == pytest.approx(vdbimport.houdini_to_atlas(p))


# ── scanning what was written ─────────────────────────────────────────────────

def test_scan_reports_the_range(tmp_path):
    got = vdbimport.scan_sequence(_seq(tmp_path / "vdb"))
    assert got["stem"] == "smoke"
    assert (got["first_frame"], got["last_frame"]) == (1373, 1380)
    assert got["frames"] == 8
    assert got["digits"] == 4
    assert got["bytes_total"] == 800


def test_a_hole_in_the_sequence_is_refused(tmp_path):
    """Smoke that blinks out for a frame reads as a render glitch, not a gap."""
    with pytest.raises(vdbimport.SequenceError, match="missing 1 frame"):
        vdbimport.scan_sequence(_seq(tmp_path / "vdb", skip=(1376,)))


def test_a_zero_byte_frame_is_refused(tmp_path):
    with pytest.raises(vdbimport.SequenceError, match="zero-byte"):
        vdbimport.scan_sequence(_seq(tmp_path / "vdb", empty=(1377,)))


def test_an_empty_folder_is_refused(tmp_path):
    (tmp_path / "vdb").mkdir()
    with pytest.raises(vdbimport.SequenceError, match="no numbered"):
        vdbimport.scan_sequence(tmp_path / "vdb")


def test_a_missing_folder_is_refused(tmp_path):
    with pytest.raises(vdbimport.SequenceError, match="not a directory"):
        vdbimport.scan_sequence(tmp_path / "nope")


def test_two_sequences_must_be_disambiguated(tmp_path):
    root = tmp_path / "vdb"
    _seq(root, stem="smoke")
    _seq(root, stem="debris")
    with pytest.raises(vdbimport.SequenceError, match="more than one sequence"):
        vdbimport.scan_sequence(root)
    assert vdbimport.scan_sequence(root, stem="debris")["stem"] == "debris"


def test_digit_count_is_reported(tmp_path):
    """A host told to expect four digits will not find three-digit files."""
    got = vdbimport.scan_sequence(_seq(tmp_path / "vdb", lo=1, hi=3, digits=3))
    assert got["digits"] == 3


def test_the_real_cache_is_sound():
    """The actual written sequence, if it is present on this machine."""
    root_env = os.environ.get("ATLAS_VDB_CACHE")
    if not root_env:
        pytest.skip("ATLAS_VDB_CACHE not set")
    root = Path(root_env)
    if not root.is_dir():
        pytest.skip("no cache on this machine")
    got = vdbimport.scan_sequence(root)
    assert got["first_frame"] == 1373
    assert got["last_frame"] == 1475
    assert got["frames"] == 103
    assert got["bytes_min"] > 0
