# Houdini to 3ds Max VDB handoff

Checks a Houdini smoke or fire cache before 3ds Max ever opens it, and gets
it into the scene the right way up. It verifies that Houdini really saved,
refuses VDB sequences with missing or empty frames, and converts between
Houdini's Y-up space and a Z-up 3ds Max scene.

Part of [Atlas](https://github.com/ssnfts/atlas). Extracted as a standalone
tool; nothing here imports anything outside this folder.

## What it does

- **Validates a `.vdb` sequence** (`vdbimport.scan_sequence`). It reports the
  name stem, frame range, file count and file sizes, and raises an error for
  no files, a gap in the numbering, or a zero-byte frame. A missing frame
  otherwise shows up as smoke that blinks out for one frame of a finished
  render.
- **Converts axes** between Houdini (Y-up) and 3ds Max (Z-up):
  `(x, y, z)` becomes `(x, -z, y)`, with the 4×4 matrix written into a
  handoff file so the importer does not guess.
- **Verifies Houdini saves** (`houdini.py`). It builds the Python that saves
  the scene inside Houdini and then judges the reply: the file exists, it
  was rewritten just now, and Houdini no longer reports unsaved changes. It
  also refuses a non-`.hipnc` path on an Apprentice licence before Houdini
  sees it.
- **Builds the smoke source** (`tyresmoke.py`). It works out where each tyre
  contact patch is and how fast it is sliding sideways, so smoke comes off
  the tyres only while they are actually sliding.
- **Includes generic open-wheel car proxies** (`cars.py`) and the race
  animation maths (`raceanim.py`) used to place them. The cars are generic
  shapes, not any real team's design.

## Prerequisites

- Python 3.11 or later. The modules use only the standard library.
- Houdini, to produce the cache (any licence; Apprentice writes `.hipnc`).
- 3ds Max with a volume loader such as V-Ray's VRayVolumeGrid, to render it.
- Neither program is needed for the checks themselves or for the tests.

## Install

```
git clone https://github.com/ssnfts/Houdini-3dsMax-VDB-handoff.git
```

Nothing to build. `pip install pytest` if you want to run the tests.

## How to use it

**Check a cache before importing it:**

```python
import sys
sys.path.insert(0, "server")
import vdbimport

info = vdbimport.scan_sequence(r"D:\shots\crash\vdb")
print(info["stem"], info["first_frame"], info["last_frame"], info["frames"])
# raises vdbimport.SequenceError if a frame is missing or empty
```

**Convert a Houdini position to the 3ds Max scene:**

```python
vdbimport.houdini_to_atlas((1.0, 2.0, 3.0))    # -> (1.0, -3.0, 2.0)
```

**Save the Houdini scene and prove it happened:**

```python
import houdini

path = houdini.check_save_path("D:/shots/crash/crash_v003.hipnc", apprentice=True)
code = houdini.save_script(path, label="after pyro sim")
# run `code` inside Houdini (Python Shell, hython or an MCP tool), then:
result = houdini.parse_save_reply(stdout_from_houdini, expect_label="after pyro sim")
```

**Write the handoff file** that records the axis mapping, frame rate and
sequence pattern for the 3ds Max side: `vdb_handoff.build_handoff(...)` then
`vdb_handoff.write_handoff(path, handoff)`.

## Getting the best result

- **Scan every cache before you queue a render.** It takes a second and a
  gap found afterwards costs the whole render.
- **Cache in world space** and say so in the handoff file. Most "the smoke
  is in the wrong place" problems are a disagreement about world versus
  local space, not about axes.
- **Match frame rate and frame range on both sides** before simulating.
  `houdini.align_script` builds the Houdini code to set them.
- **Keep the `$F4` four-digit frame padding.** The two programs read other
  patterns differently.
- **Empty volumes are fine; empty files are not.** Frames before the action
  legitimately hold no density.
- **On Apprentice, save as `.hipnc` only.**

## Works well with

**Graphic design.** Render a single hero frame of smoke, dust or fire with
an alpha channel and use it as an element in posters and key art in
Photoshop or Affinity.

**Product visualization.** Tyre smoke, exhaust, steam or dry-ice mist around
a vehicle or product. Pair it with
[Motorsport vehicle rig](https://github.com/ssnfts/Motorsport-lap-animation)
for the car's motion and
[V-Ray material graph builder](https://github.com/ssnfts/V-Ray-material-graph-builder)
for the road surface.

**Film.** Houdini Pyro for the simulation, 3ds Max and V-Ray for lighting
and rendering, with
[Cinematic camera moves](https://github.com/ssnfts/Cinematic-camera-moves)
for the shot and [Atlas](https://github.com/ssnfts/atlas) for a sun that
matches the plate. For particle effects that stay inside 3ds Max, see
[tyFlow script generator](https://github.com/ssnfts/tyFlow-script-generator).

**Automation.** Run `scan_sequence` as a gate in a render-farm submission
script (Deadline or similar) or a CI job, so a broken cache never reaches
the queue. The save check suits agent-driven Houdini sessions, where a
quiet failed save is otherwise invisible.

## Layout

```
server/   the modules
tests/    offline tests
```

## Tests

```
python -m pytest tests -q
```

3 test files. They are offline and need no 3ds Max, no Houdini and no
network.

Not shipped: `test_vdb_handoff`, which imports a separate Houdini project tree.


## Data licensing

This is source code, licensed however you choose. The *data* it fetches is
not:

- OpenStreetMap is ODbL 1.0 -- attribution, and share-alike on derived
  databases.
- Copernicus GLO-30 requires attribution.
- Poly Haven textures are CC0.

`attribution.py`, where included, generates the manifest for you.

## Compatibility

Every 3ds Max and V-Ray parameter name in this code was read off a live
3ds Max 2027 with V-Ray 7 update 3. Names are discovered from the host rather
than recalled, but they were discovered on *that* host. Treat other versions
as unverified until checked.
