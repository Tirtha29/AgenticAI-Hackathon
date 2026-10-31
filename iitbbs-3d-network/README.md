# IIT Bhubaneswar 3D network map

Low-poly 3D campus (three.js) with a Flask backend that feeds live network status
for 23 buildings, including 9 hostel blocks.

## Run (VS Code)
1. Open this folder in VS Code, open a terminal.
2. Windows: `run.bat`   |   Mac/Linux: `./run.sh`
   (or manually: `pip install -r requirements.txt` then `python app.py`)
3. Open http://127.0.0.1:5000

First run needs internet once: three.js is downloaded automatically into
`static/vendor/` and cached, so later runs work offline.

## Use
- Orbit: drag to rotate, scroll to zoom, right-drag to pan.
- Walk: click "Walk", then W A S D / arrows, drag to look, Shift to run, Esc to exit.
- Click a building (or the left list) for latency, loss, speed, clients, access points,
  and "Run diagnostics".
- Every building carries a status emoji on top (see below). Hostels also show pulsing Wi-Fi rings. Lines from the NOC carry moving packets; colour
  and speed follow status (green healthy, amber degraded, red down).
- "Open diagnostics" goes to /diagnostics, the starting page of your diagnostic site.

## Connect PyDAC
Edit `pydac_adapter.py` -> `read_block()`. Until then the backend SIMULATES data
(shown as "Data: simulated" in the legend).

## Edit buildings
`data/buildings.json`: x/z position in metres (north is -z), w/d/h size, name, description.
Positions are stylised from your satellite views and master plan, not surveyed.
Hostels are named Boys Hostel 1 to 9 (rename in the JSON).

## API
GET /api/buildings, GET /api/network, POST /api/diagnose/<id>

## Detailed buildings (one module per building)
Detailed models live in `static/js/buildings/<name>.js` and are called from the matching
`shape` branch in `static/js/main.js`. Each module has a CONFIG block at the top and is
built from the reference photos.

| Building | Module | Notes |
|---|---|---|
| Auditorium | `buildings/auditorium.js` | ~68k triangles. Stone-block fins round both ends, glass foyer, floating canopy with tension struts, curved steps, fountain forecourt, palms, cars, people. |
| Main Gate | `buildings/gate.js` | Built from the two gate photos: cream beam with 5 gold stripes and lettering, 3-column clusters, central emblem pillar, 4 black iron leaves with gold wheels (open/close with **G** or the header button), end blocks, wings, boundary wall, guard cabins, palms, paver aprons, road markings. Walk mode now starts on the road outside, looking at it. |
| Lalitgiri / Ratnagiri / Pushpagiri halls + amphitheatre | `buildings/lecturehall.js` | One module, three buildings (`variant`: `hall` or `pushpagiri`, `rot` in buildings.json turns the front to face the amphitheatre). Tan stone drum, ribbon glazing, silver seamed lens roof, solar ring, steel pergola, pilaster or glass-curtain front, forecourt, terraced amphitheatre with stage. |

Adding the next building: copy `auditorium.js`, change the shape, add a
`else if (b.shape === '...')` branch in `main.js` that calls it. Footprint (`x, z, w, d, h`)
still comes from `data/buildings.json`. The auditorium footprint was enlarged to 48 x 32 m
and moved to x=-78 to fit its forecourt without touching the library.

## Status emoji
`static/js/status.js` draws the five faces from your sketch on a canvas and floats one above every building (map-pin style, always faces the camera, scales with distance, pops when the mood changes; the sad and angry ones pulse and shake).

| Face | Colour | Meaning (see `moodOf()` in status.js) |
|---|---|---|
| Grin | green | status ok, latency < 20 ms, loss < 0.5 %, all APs online |
| Smile | green | status ok |
| Neutral | yellow | status warn (degraded) |
| Sad | red | status down |
| Angry | red | down and (no APs online, or loss > 12 %, or latency > 220 ms) |

The same faces appear in the building list, the info panel and the legend. Change the thresholds in `moodOf()`.

## People and cycles
`static/js/life.js`: ~40 walkers (some in pairs, backpacks, long hair) and 11 cyclists move along the road network, keep to the left, pedal, and turn at the ends. Security guards and small groups stand at the gate. Edit the `routes` list and the `walkers` / `cyclists` counts in `main.js` (search for "campus life").
