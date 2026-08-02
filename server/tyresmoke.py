"""
Where the smoke comes from: the tyres, and only when they are actually sliding.

A pyro simulation is only as good as what feeds it, and the tempting shortcut is
to emit smoke wherever the crashing car is. That produces a cloud that follows a
car around, which is not what a spin looks like. What a spin looks like is smoke
pouring off four contact patches whose *sideways* speed has gone from nothing to
tens of metres per second, each one tracing its own arc.

So the emission here is driven by lateral slip: the component of a tyre's world
velocity that runs across the tread rather than along it. That single quantity
does the whole job, because it is near zero for a car tracking straight — a
rolling tyre's velocity is parallel to its own rolling direction — and it is
enormous the moment the car is pointing somewhere other than where it is going.
No flags, no hand-tuned envelope, no "start smoking at frame N".

Tyre positions and velocities are not derived analytically. Each contact patch is
placed in the world from the car's state, and its velocity is taken by finite
difference of that world position. The rotational term that a spinning car adds
to its outboard wheels — the reason the outside front smokes hardest — falls out
of the differencing for free, and cannot be got wrong separately from the
positions it came from.

**Deliberately not modelled:** longitudinal lock-up smoke under braking. That
needs brake state, and the motion model in :mod:`raceanim` does not carry any.
Claiming it would mean inventing a brake input and then dressing the output up as
physics.

Units are metres and seconds throughout, in the Atlas scene frame: +X east,
+Y north, +Z up, heading clockwise from +Y.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import raceanim
from cars import F1_2022, CarSpec

__all__ = [
    "SLIP_FLOOR_MS",
    "SLIP_SATURATION_MS",
    "to_houdini",
    "to_atlas",
    "tyre_offsets",
    "car_state_at",
    "tyre_world",
    "smoke_rate",
    "sample_window",
    "write_source",
]

# Below this the tread is gripping and a real tyre leaves no visible smoke.
SLIP_FLOOR_MS = 2.0

# The slip speed by which emission is effectively saturated. A tyre sliding at
# 40 m/s does not make twice the smoke of one at 20 — it is already producing all
# the rubber vapour it can — so the response saturates rather than running away.
SLIP_SATURATION_MS = 18.0


def to_houdini(p):
    """
    Atlas (Z-up) to Houdini (Y-up): ``(x, y, z) -> (x, z, -y)``.

    Houdini's pyro defaults — buoyancy, gravity, wind — all assume Y is up.
    Simulating in Atlas's Z-up frame instead means overriding each of those, and
    every override is a chance to leave one pointing sideways and produce smoke
    that falls over. One conversion at the boundary is cheaper to get right and
    far cheaper to check.

    The negated Y keeps the frame right-handed. Dropping the sign gives a mirror
    image, which looks entirely normal in a viewport and puts the smoke on the
    wrong side of the car.
    """
    x, y, z = p
    return (x, z, -y)


def to_atlas(p):
    """Houdini (Y-up) back to Atlas (Z-up). The exact inverse of :func:`to_houdini`."""
    x, y, z = p
    return (x, -z, y)


def tyre_offsets(car: CarSpec = F1_2022):
    """
    The four contact patches in body coordinates, as ``(name, right, forward)``.

    Right and forward are metres from the car's centre. The offsets are read from
    :class:`cars.CarSpec` rather than restated, so a change to the car is a change
    to the smoke.
    """
    half_track = car.track / 2.0
    half_base = car.wheelbase / 2.0
    return (
        ("front_left", -half_track, half_base),
        ("front_right", half_track, half_base),
        ("rear_left", -half_track, -half_base),
        ("rear_right", half_track, -half_base),
    )


def _axes(heading_deg: float):
    """Forward and right unit vectors for a heading clockwise from +Y."""
    h = math.radians(heading_deg)
    forward = (math.sin(h), math.cos(h))
    right = (math.cos(h), -math.sin(h))
    return forward, right


# How far either side of a point the clean-line heading is measured over.
# See :func:`base_heading` for why this is not zero.
HEADING_BASELINE_M = 6.0


def base_heading(spine, distance: float,
                 baseline_m: float = HEADING_BASELINE_M) -> float:
    """
    The racing line's heading at ``distance``, measured over an arc baseline.

    :func:`raceanim.point_at` reports the heading of the *segment* a point falls
    in, which is piecewise constant: it steps at every OSM vertex, and the ways
    here have vertices anywhere from 2 to 266 m apart. Placing a car sideways of
    the line by ``lateral * right(heading)`` then teleports it several
    centimetres each time a step is crossed, and differencing across that step
    reports a tyre doing 217 m/s. Nothing about that is physics — it is the
    polyline's resolution being mistaken for motion.

    Measuring the heading between two points either side of the sample removes
    the steps, because position along the line is continuous even where its
    derivative is not. The baseline is in metres rather than seconds so the
    result depends on the circuit's shape and not on how fast a car happens to
    be going through it.
    """
    total = raceanim.lap_length(spine)
    half = max(baseline_m, 1e-6) / 2.0
    ax, ay, _ = raceanim.point_at(spine, (distance - half) % total)
    bx, by, _ = raceanim.point_at(spine, (distance + half) % total)
    dx, dy = bx - ax, by - ay
    if abs(dx) < 1e-12 and abs(dy) < 1e-12:
        return raceanim.point_at(spine, distance % total)[2]
    return math.degrees(math.atan2(dx, dy)) % 360.0


def car_state_at(spine, spec, t_since_contact: float, *, contact_time: float,
                 site_z: float, track_height=None):
    """
    The spinning car's world state at a moment.

    This delegates to :func:`raceanim.crash_pose_at_time`, which is the same
    function that writes the car's keys in Max. That is the whole point: an
    earlier version of this module built its own pose from the racing line plus
    the crash offsets, which is a second motion model, and two motion models
    disagree. This one did — by exactly 3.000 m at contact, the field's
    ``stagger_m``, because the spinner is a numbered car on the grid and not an
    abstraction sitting on the centre line.

    The divergence got worse after contact rather than better. ``crash_pose``
    deliberately detaches from the lap on impact and slides along the *contact
    tangent* before coming to rest, while a racing-line model obediently
    continues round the corner. Smoke built the old way would have started one
    car-width out and ended in a different part of the circuit.

    ``track_height`` is a callable ``(x, y) -> metres`` giving the circuit's
    local rise above the graded site. Pass the same one the car keys use —
    ``demo_yas_animate.py`` calls ``profile.height_at_point(x, y)``. Without it
    the smoke sits on a flat plane at ``site_z`` while the car climbs: measured
    at this crash the gap ran from 2.8 m at the tell to 6.9 m by the end of the
    settle, because the incident is on rising ground. It is sampled by position
    rather than by lap distance on purpose, since after contact the car has left
    the racing line and its distance along the lap no longer says where it is.

    Returns ``(x, y, z, heading, clearance)``. ``clearance`` is height above the
    *local* track, which is what decides whether a tyre is touching anything.
    Deriving it as ``z - site_z`` instead would fold the circuit's rise into it
    and report the car as flying three metres up while it sits on the road —
    and since emission is gated on contact, that produces no smoke at all, from
    a run that raises no error.
    """
    x, y, heading, _roll, _pitch, height = raceanim.crash_pose_at_time(
        spine, contact_time + t_since_contact, spec)
    rise = float(track_height(x, y)) if track_height is not None else 0.0
    return (x, y, site_z + rise + height, heading, height)


def tyre_world(state, car: CarSpec = F1_2022):
    """
    Contact-patch world positions for a car state, in body order.

    The z returned is the car's floor height; a contact patch sits on the ground
    unless the car has been launched, and when it has been launched it is no
    longer making smoke anyway.
    """
    x, y, z, heading = state[:4]
    forward, right = _axes(heading)
    out = []
    for name, r, f in tyre_offsets(car):
        out.append((
            name,
            x + r * right[0] + f * forward[0],
            y + r * right[1] + f * forward[1],
            z,
        ))
    return out


def smoke_rate(slip_ms: float, height_m: float = 0.0,
               car: CarSpec = F1_2022) -> float:
    """
    Emission strength in 0..1 for a lateral slip speed and a ride height.

    Zero below :data:`SLIP_FLOOR_MS`, then saturating — a tyre already producing
    all the smoke it can does not produce more for sliding faster. The curve is
    ``1 - exp(-s)``, which is the shape of any process approaching a ceiling.

    ``height_m`` is how far the car has been pitched up off the road. Slip alone
    is not enough to make smoke: rubber has to be dragged across tarmac, and a
    car in the air is not touching any. The crash launches the spinner most of a
    metre, so without this the plume kept pouring out of four wheels that were
    nowhere near the ground. Contact fades out over the tyre's radius rather
    than switching off, because the outside of a leaning car lifts first.
    """
    excess = slip_ms - SLIP_FLOOR_MS
    if excess <= 0.0:
        return 0.0

    radius = max(car.tyre_diameter / 2.0, 1e-6)
    contact = 1.0 - max(0.0, min(height_m, radius)) / radius
    if contact <= 0.0:
        return 0.0

    return contact * (1.0 - math.exp(-excess / SLIP_SATURATION_MS))


def sample_window(spine, spec=None, *, site_z: float, fps: int = 24,
                  substeps: int = 2, car: CarSpec = F1_2022,
                  contact_time: float | None = None, track_height=None):
    """
    Sample the whole crash window, one record per sub-frame.

    The window runs from the anticipation (``-tell_s``) to the end of the
    follow-through (``settle_s``), because that is the span over which the car is
    doing anything a tyre would object to.

    Each record carries every tyre's world position, world velocity and lateral
    slip. Velocities come from a central difference of the tyre's own world
    position, so the rotational contribution of the spin is included without
    being computed separately.
    """
    spec = spec or raceanim.CRASH
    if contact_time is None:
        contact_time = _contact_time(spine, spec)

    step = 1.0 / (fps * max(1, substeps))

    # One pose per sample, differenced against its neighbours, rather than three
    # poses per sample from a separate epsilon probe. crash_pose_at_time costs
    # about 4.6 ms -- it profiles the whole lap twice through field_at_time -- so
    # the probe form spent two thirds of its work recomputing poses that the
    # neighbouring samples had already paid for.
    times = []
    t = -spec.tell_s
    while t <= spec.settle_s + 1e-9:
        times.append(t)
        t += step

    states = [car_state_at(spine, spec, ts, contact_time=contact_time,
                           site_z=site_z, track_height=track_height)
              for ts in times]
    patches = [tyre_world(s, car) for s in states]

    records = []
    end = spec.settle_s
    # The racing line's heading is reported in [0, 360), so a car crossing north
    # would show a 360-degree step. Nothing in the world turns like that, and a
    # consumer keying rotation from this would snap the car through a full turn
    # in one frame, so the series is unwrapped as it is built.
    unwrapped = None
    for i, t in enumerate(times):
        here = states[i]
        # Central where there are neighbours, one-sided at the ends.
        lo, hi = max(i - 1, 0), min(i + 1, len(times) - 1)
        span = max((times[hi] - times[lo]), 1e-9)
        before, after = patches[lo], patches[hi]
        _forward, right = _axes(here[3])

        tyres = []
        for (name, px, py, pz), (_n0, bx, by, _bz), (_n1, ax, ay, _az) in zip(
                patches[i], before, after):
            vx = (ax - bx) / span
            vy = (ay - by) / span
            # Slip is the across-the-tread component. A rolling tyre's velocity
            # is parallel to its rolling direction, so this is ~0 when gripping.
            slip = abs(vx * right[0] + vy * right[1])
            tyres.append({
                "name": name,
                "P": [px, py, pz],
                "v": [vx, vy, 0.0],
                "slip": slip,
                # Clearance above the *local* track, not above the graded site.
                "rate": smoke_rate(slip, max(here[4], 0.0), car),
            })

        if unwrapped is None:
            unwrapped = here[3]
        else:
            unwrapped += (here[3] - unwrapped + 180.0) % 360.0 - 180.0

        records.append({
            "t": t,
            "frame": contact_time * fps + t * fps,
            "centre": [here[0], here[1], here[2]],
            "heading": unwrapped,
            "tyres": tyres,
        })

    return records


def _contact_time(spine, spec, *, gap_s: float = 0.9) -> float:
    """
    When the spinner reaches ``spec.at_distance_m``, in seconds.

    Must match :func:`raceanim.crash_pose_at_time`'s own ``contact_s`` exactly,
    since that is what the car in Max is keyed from. ``gap_s`` therefore carries
    the same default.
    """
    lap_m = raceanim.lap_length(spine)
    if spec.at_distance_m > lap_m:
        raise ValueError(
            f"the crash is pinned at {spec.at_distance_m} m but the lap is only "
            f"{lap_m:.1f} m long. Walking off the end and returning the lap time "
            f"would put the smoke somewhere plausible and wrong."
        )

    # The slot offset is not decoration: the spinner is a numbered car in the
    # field, and each slot behind the leader is another gap_s of elapsed time.
    # Omitting it put the smoke 2.7 s from the car when the spinner was slot 3.
    return (raceanim.time_at_distance(spine, spec.at_distance_m)
            + spec.spinner_slot * gap_s)


def write_source(path, records, *, meta: dict) -> dict:
    """
    Write the emitter cache Houdini reads, and report what went into it.

    JSON rather than a Houdini format on purpose: it can be diffed, inspected and
    checked by tests that never open Houdini, and the numbers in it are the same
    numbers the animation uses.
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)

    smoking = [r for r in records
               if any(t["rate"] > 0.0 for t in r["tyres"])]
    peak = max((t["slip"] for r in records for t in r["tyres"]), default=0.0)

    summary = {
        "samples": len(records),
        "smoking_samples": len(smoking),
        "peak_slip_ms": peak,
        "t_first_smoke": smoking[0]["t"] if smoking else None,
        "t_last_smoke": smoking[-1]["t"] if smoking else None,
    }

    target.write_text(json.dumps(
        {"meta": {**meta, **summary}, "records": records}, indent=1))
    return {"path": str(target), "bytes": target.stat().st_size, **summary}
