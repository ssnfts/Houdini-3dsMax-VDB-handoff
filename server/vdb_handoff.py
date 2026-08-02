"""A deterministic VDB-cache handoff without pretending to configure V-Ray."""

from __future__ import annotations

import json
from pathlib import Path

import raceanim

DEFAULT_SEQUENCE = "out/vdb/yas_crash_smoke.$F4.vdb"
VDB_TO_ATLAS = {
    "axis_mapping": {
        "atlas_x": "vdb_x",
        "atlas_y": "-vdb_z",
        "atlas_z": "vdb_y",
    },
    "matrix_4x4": [
        [1.0, 0.0, 0.0, 0.0],
        [0.0, 0.0, -1.0, 0.0],
        [0.0, 1.0, 0.0, 0.0],
        [0.0, 0.0, 0.0, 1.0],
    ],
}


def vdb_y_up_to_atlas(point: tuple[float, float, float]) -> tuple[float, float, float]:
    """Convert the Pyro cache's world-space Houdini Y-up coordinates to Atlas."""

    x, y, z = point
    return (x, -z, y)


def build_handoff(
    spine,
    profile,
    *,
    site_z: float,
    fps: int = 24,
    sequence: str = DEFAULT_SEQUENCE,
) -> dict:
    """Describe the crash cache's coordinate frame for a host-side importer."""
    if fps <= 0:
        raise ValueError("fps must be positive")
    x, y, heading = raceanim.point_at(spine, raceanim.CRASH.at_distance_m)
    contact_s = raceanim.time_at_distance(spine, raceanim.CRASH.at_distance_m)
    contact_frame = int(round(contact_s * fps))
    height = float(profile.height_at_distance(raceanim.CRASH.at_distance_m))
    return {
        "schema": "atlas.yas.crash-vdb-handoff/v2",
        "sequence": str(sequence),
        "frame_token": "$F4",
        "space": "world_space_houdini_y_up",
        "vdb_to_atlas": VDB_TO_ATLAS,
        "contact_position_atlas_m": [round(x, 3), round(y, 3), round(site_z + height, 3)],
        "contact_distance_m": raceanim.CRASH.at_distance_m,
        "contact_heading_deg": round(heading, 3),
        "contact_frame": contact_frame,
        "contact_seconds": round(contact_s, 6),
        "fps": int(fps),
        "z_rule": "site_z + elevation_profile.height_at_distance(3650.0)",
        "volume_grid": {
            "status": "not_created",
            "reason": "discover live host parameters before loading the cache",
        },
    }


def write_handoff(path: str | Path, handoff: dict) -> Path:
    """Write deterministic, human-reviewable JSON for the Houdini/Max boundary."""
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(handoff, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output
