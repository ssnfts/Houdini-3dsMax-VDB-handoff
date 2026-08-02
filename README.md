# Houdini to 3ds Max VDB handoff

Verified Houdini saves, VDB sequence validation that refuses gaps and zero-byte frames, and the axis conversion between Houdini's Y-up and a Z-up scene.

Part of Atlas. Extracted as a standalone tool; nothing here imports anything
outside this folder.

## Layout

```
server/   the modules
tests/    run these first
```

## Run the tests

```
python -m pytest tests -q
```

3 test files ship with this product.

Not shipped: `test_vdb_handoff` (imports the Houdina Houdini project tree)

## Requirements

Python 3.11+. The tests are offline and need no 3ds Max, no Houdini and no
network.

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
