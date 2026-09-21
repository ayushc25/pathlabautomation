# HORIBA Yumizen H500/H500E ASTM Decoder

A FastAPI service that decodes raw ASTM host-connection captures from HORIBA
Yumizen H500/H500E hematology analyzers (per the *Output Format for Host
Connection*, RAA085BEN spec) into structured JSON: patient demographics,
order info, numeric results, alarm comments, histograms, and matrix
scattergrams — plus rendered PNG graphs.

## Project structure

```
app/
  main.py                 FastAPI app instance
  routers/
    decode.py             POST /decode endpoint
  services/
    checksum.py            ASTM frame checksum compute/verify
    frame_reassembler.py    Extracts HEX/ASCII frames from the capture log, verifies
                            checksums, reassembles ETB-continued frames
    astm_parser.py          Splits reassembled messages into records, dispatches by
                            record type (H/P/O/R/C/M/L), aggregates into ParsedASTM
    record_parser.py        Generic field/component/repeat tokenising + H/P/O/C/L parsers
    result_decoder.py       R record -> {"PARAM": {"value","unit",...}}
    histogram_decoder.py    base64 -> zlib inflate -> float32 stream -> HISTOGRAM decode
    matrix_decoder.py       Same pipeline -> (x,y) point-pair MATRIX decode
    graph_generator.py      Matplotlib PNG rendering, saved under artifacts/
    report_generator.py     Orchestrates the full pipeline into the API response
  models/
    schemas.py              Pydantic response models
  utils/
    logger.py               Shared logger factory
artifacts/                  Generated PNG graphs (created at runtime)
tests/                       Unit + integration tests
examples/                    Synthetic sample capture + generated response/graphs
```

## Setup

```bash
python -m venv .venv
source .venv/Scripts/activate   # Windows Git Bash; use .venv/bin/activate on Linux/Mac
pip install -r requirements.txt
```

## Running the API

```bash
uvicorn app.main:app --reload
```

The service listens on `http://127.0.0.1:8000` by default. Interactive docs
are available at `/docs` (Swagger UI) and `/redoc`.

## Windows Service Deployment

For a customer install on Windows, the app can run as a background service so
the dashboard, API, and socket listener stay up together.

The `PackageInstaller/` folder is a self-contained copy of this project set
up for exactly that: copy the whole folder to the target machine and run
`.\install.ps1` from an elevated PowerShell prompt. See
[PackageInstaller/README.md](PackageInstaller/README.md) for full steps,
service management (`manage_service.ps1`), and uninstall instructions.

To install directly from this working copy instead (e.g. for local testing):

```powershell
pip install -r requirements.txt
.venv\Scripts\python.exe service_installer.py install
.venv\Scripts\python.exe service_installer.py start
.venv\Scripts\python.exe service_installer.py stop
.venv\Scripts\python.exe service_installer.py remove
```

Whichever copy you install from, set `SESSION_SECRET_KEY` and
`ADMIN_PASSWORD` in its `.env` file before exposing it beyond local testing —
see the warning logged at startup if `SESSION_SECRET_KEY` is left unset.

### Health

The `/health` endpoint reports app status and whether the socket listener is
running.

## API

### `POST /decode`

`multipart/form-data` with a single field `file` containing the raw ASTM
capture `.txt` (the exact logger output, including `Received:` / `HEX :` /
`RAW :` / `ASCII:` bookkeeping lines — those are stripped automatically).

```bash
curl -X POST http://127.0.0.1:8000/decode \
  -F "file=@examples/sample_capture.txt"
```

Response shape:

```jsonc
{
  "patient": { "patient_id": "...", "name": {...}, "dob": "...", "sex": "...", "physician": "..." },
  "order": { "sample_id": "...", "tests": ["WBC", "RBC", ...], "priority": "...", ... },
  "results": {
    "WBC": { "value": 6.42, "unit": "10^3/uL", "reference_range": {"low": 4.0, "high": 10.0}, "flags": ["N"], "status": "F", "timestamp": "..." },
    "RBC": { "value": 4.81, "unit": "10^6/uL", ... }
  },
  "comments": [ { "source": "I", "alarm_type": "G", "description": "...", "measurement": "EOS%" } ],
  "histograms": {
    "RBCVolHist": { "type": "RBC", "name": "RBCVolHist", "x": [0, 1, ...], "y": [40.0, 39.2, ...] }
  },
  "matrices": {
    "LmneScatter": { "type": "LMNE", "name": "LmneScatter", "points": [ {"x": 0.0, "y": 0.0}, ... ] }
  },
  "images": {
    "RBC_histogram": "artifacts/<session>_histogram_RBCVolHist.png",
    "PLT_histogram": "artifacts/<session>_histogram_PltVolHist.png",
    "WBC_histogram": "artifacts/<session>_histogram_WbcVolHist.png",
    "LMNE_scattergram": "artifacts/<session>_scattergram_LmneScatter.png",
    "EOS_scattergram": "artifacts/<session>_scattergram_EosScatter.png"
  },
  "meta": {
    "header": {"sender_name": "HORIBA^Yumizen_H500", "version": "1", ...},
    "frames_parsed": 14,
    "records_parsed": 14,
    "records_skipped": 0,
    "checksum_failures": 0,
    "warnings": []
  }
}
```

A full worked example (input + generated output + PNGs) lives in
`examples/sample_capture.txt` and `examples/sample_response.json`. Regenerate
them with:

```bash
python -m examples.generate_example
```

### Error handling

| Condition | Status |
|---|---|
| File isn't `.txt` | 415 |
| File is empty | 400 |
| No ASTM frames could be extracted at all | 400 |
| Unexpected internal failure | 500 |

Individual malformed records (bad checksum, unparsable R/M record, unknown
record type, etc.) never abort the whole decode — they're logged as
warnings and surfaced in `meta.warnings` / `meta.records_skipped`, while the
rest of the capture continues to decode normally.

## ASTM parsing details

- **Checksum**: modulo-256 sum of every byte from the frame number through
  the ETX/ETB terminator (inclusive), rendered as 2 uppercase hex digits.
  Verified per-frame whenever the raw `HEX :` bytes are available in the
  capture log; frames with only an `ASCII:` line (no hex) skip verification.
- **Multi-frame messages**: frames terminated with ETB are concatenated
  (via their text bodies, sans frame-number byte) until a frame terminated
  with ETX completes the logical message.
- **Records supported**: H (header), P (patient), O (order), R (result), C
  (comment/alarm), M (manufacturer: HISTOGRAM/MATRIX), L (terminator).
- **R records**: parameter name is read from the universal test ID's last
  non-empty component (e.g. `^^^WBC` -> `WBC`) — never hardcoded, so any
  analyte the instrument reports round-trips.
- **M records**: `HISTOGRAM`/`MATRIX` payloads use the
  `FLOATLE-stream/deflate:base64` pipeline: base64 decode -> zlib inflate ->
  little-endian float32 unpack -> NumPy array. Histograms become
  `{type, name, x, y}`; matrices are interpreted as interleaved (x, y) pairs
  -> `{type, name, points: [{x, y}, ...]}`.
- **Graphs**: RBC/PLT/WBC histograms and LMNE/EOS matrices are auto-detected
  (by substring match against each record's type/name) and rendered to PNG
  under `artifacts/`; paths are returned in `images`.

## Tests

```bash
pytest -q
```

Covers: checksum compute/verify (valid, corrupted, malformed frame), frame
reassembly (single-frame, multi-record, ETB continuation, checksum failure,
ASCII-only fallback), result decoding (value/unit/reference-range/flags,
unresolvable-parameter skip), histogram/matrix decoding (round-trip via the
real base64/deflate/float32 pipeline, malformed-payload handling), end-to-end
ASTM parsing, and the `/decode` HTTP endpoint (success, wrong content type,
empty file, unparsable file).
