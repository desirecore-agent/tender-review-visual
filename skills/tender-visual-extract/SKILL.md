---
name: tender-visual-extract
description: "Technical image/document extraction review skill: secure DOCX extraction (text/tables/embedded images/relationships, with path traversal and ZIP bomb protection), PDF capability check and page-image inspection discipline (only counted as viewed after actual Read). Used for structured extraction and image evidence recording in tender document review. Includes bounded local pixel-region measurements."
---

# Technical Image / Document Extraction Review

## Receiving a delegated business task

For a received business delegation or delegated correction, actually load this installed Skill and inspect the complete original request and TaskSpec in the current verified file-backed delegation body, with their file identities. This supplied content does not require a redundant tool Read. If it is absent, actually Read the explicitly authorized original files; missing content or identities blocks business. Never report a tool Read that did not occur. Actual business documents/images must still be read using real tools. Verify their supplied full hashes, task/revision, applicable constraints, output ownership and the actual current preflight receipt. A summary or previous installation check is insufficient. Missing, unavailable, mismatched or unsatisfied bindings mean blocked/unverified before business work; request correction without widening scope. Use only the task-required reviewed helpers and this role's verified environment; do not install substitutes, write runtimes under Agent source, or borrow another role's interpreter. Report real Read/Skill and execution evidence, including failures. Direct non-delegated user requests follow the existing authorized workflow; this TaskSpec reception condition applies only to delegations. The published finite metadata-preflight bootstrap remains nonrecursive and does not authorize business work.

Runtime location (conditional): apply the following discovery and receipt checks only when the current task explicitly depends on an initialized and verified role-owned environment. A text-only task with no such dependency does not require a runtime receipt and must not be blocked solely because none exists. This does not waive any applicable installed Skill requirement to use its formal helper or validator in a verified environment; resolve a missing required binding before that execution. When this condition applies, confirm the current ToolCatalog parameters, then use read-only `ManageWorkDirs({"action":"list","scope":"current"})`; do not switch cwd, add grants or query other Agents/global scope. The list may include merged team/global directories: do not select those, or infer private ownership from primary/cwd/parent paths. If no unambiguous own private workspace is identifiable, stop. Team cwd is not the role's private workspace, and Managed runtimes base Python is not its existing venv. In an unambiguously role-owned registered private workspace, read `.runtime/<skill-name>/runtime-receipt.md` (substitute this Skill's name) or an exact current initialization receipt authorized by this task. Its real initialization owner records non-secret actual interpreter/prefix, helper/lock hashes, versions and verification evidence; existing environments are not moved. The Markdown receipt is immutable after creation; a later initialization uses a new explicitly supplied path/hash rather than overwriting it. The member provides the exact receipt binding through actual authorized delivery; no caller guesses it or silently scans alternatives. Verify these against current task bindings; a receipt grants no access and is not proof of readiness. Missing directory/receipt/identity means blocked pending exact bindings, never old-case/history search or a substitute pip install.

## Use Cases

- Safely extract paragraph text, tables (with row/column positioning), embedded images and their relationship references from DOCX files
- Perform PDF capability checks and page-image inspection (unknown installations must verify with ToolCatalog + a real non-sensitive smoke PDF first)
- Actually inspect extracted images and record evidence

## Core Principles

1. **Images only prove visible content**: Record what you see; record "not visible" when you can't see.
2. **Blurry / missing page / read failure ≠ "not provided" or "check passed"**: Always record as incomplete with the reason.
3. **No seal/signature authenticity verification**: Visual inspection reports visibility (present/absent/illegible), never authenticity.
4. **Image-text contradictions preserved side by side**: Never choose "which one to trust" on your own.
5. **An image is only counted as viewed after actual Read**: Never claim to have inspected a file not opened with the `Read` tool.
6. **Partial extraction never claims full success**: When `status` is `partial`/`rejected`, incomplete items must be truthfully reported.
7. **DOCX extraction ≠ full Office rendering**: `extract_docx.py` only extracts body paragraphs, tables, and images referenced via drawing elements; headers, footers, footnotes, endnotes, comments, embedded OLE objects are not covered.
8. **Cloud model channel disclosure**: When using a user-selected cloud model, text and images sent for processing are handled by that model's channel; fully local processing cannot be promised.
9. **No unauthorized external transmission**: By default, tender content (including extracted images, personnel info, pricing) is not sent to OCR services, email, or unfamiliar URLs; this must be distinguished from the user-selected cloud model's normal text/image processing channel.

## DOCX Extraction Usage

Script path (relative to this skill directory): `scripts/extract_docx.py`

### Basic Command

```bash
python3 <skill_dir>/scripts/extract_docx.py INPUT.docx --out-dir OUTPUT_DIR
```

**Use a fresh output directory for each run**. The script never overwrites: if any file or symlink already exists at the target output path, it refuses (exit code 5); unrelated existing files in the directory are unaffected (only same-name collisions are rejected).

### Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--out-dir` | (required) | Output directory for extracted images. The directory **itself** being a symlink is rejected; a parent directory being a symlink is accepted via the caller-provided realpath (symlinked parent is not rejected). Non-empty directories are accepted: only same-name file/symlink collisions with this batch's output are rejected; unrelated existing files are untouched (use a fresh empty directory for clean isolation) |
| `--json` | `OUT_DIR/extraction.json` | JSON result output path (must not point to the input file) |
| `--max-total-bytes` | 200000000 | ZIP decompression total limit (anti-ZIP-bomb) |
| `--max-entry-bytes` | 50000000 | Single entry decompression limit |
| `--max-entries` | 2000 | ZIP entry count limit |
| `--max-image-bytes` | 100000000 | Image extraction budget |
| `--strict` | off | Abort entirely on any dangerous entry (safety rules always execute; this parameter only controls "reject that entry and continue" vs "abort immediately") |
| `--min-image-side` | 10 | Size gate (**must be greater than** semantics): images with width or height ≤ this value are marked `readability=too_small`. Default 10 = minimum acceptable size is 11, aligned with confirmed model boundary (width and height must be >10). Parameter must be ≥1; 0 or negative is rejected (exit code 64) |

### Output Structure (JSON)

- `status`: `complete` (all body-referenced images resolved or no references, and no uncovered containers) / `partial` (some resolved, some incomplete, or uncovered containers / depth exceeded) / `rejected` (has references but none resolved, with no external links or uncovered containers)
- `paragraphs[]`: `paragraph_index` + `text` + `location` (logical path) + `drawing_relationship_ids` (rid list, compatibility field) + `drawing_references` (contains `rid` and `kind`: embed / link / none)
- `tables[]`: `table_index` + `location` + `rows[][]` (only direct-row/direct-cell text; nested tables are separate entries linked via parent cell path)
- `images[]`: Authoritative image list, using **actual body drawing/blip references** as the denominator; both **embed and link** reference kinds are counted (a blip missing both is recorded as `none`; the denominator does not shrink due to missing attributes). Each entry contains `relationship_id`, `reference_kind`, `status` (resolved / missing-part / rejected / external-not-fetched / budget-exceeded / unsupported), `location` (reference logical path), `note` (incomplete reason); only `resolved` entries include `extracted_to`, `sha256`, `dimensions`, `readability`. External-link images are always `external-not-fetched`: recorded only, never fetched, never sent a request
- `uncovered_containers[]`: Unsupported visible containers or depth-exceeded wrapper structures in the body (uncovered, not "no content"), each containing `tag`, `location`, `note`; when non-empty, result must be `partial` with non-zero exit code
- `uncovered_parts[]`: Parts that exist in the package but are not extracted by this tool (e.g., headers/footers/footnotes/endnotes/comments)
- `security.external_relationships`: External relationships are recorded only, not followed
- `security.rejected_entries`: Rejected dangerous ZIP entries (with reason)

### Location Semantics (Important)

- All locations are **logical positions**, not Word page numbers. DOCX has no fixed pagination; **do not fabricate page numbers**.
- `location` path grammar: `body:N` (Nth direct child of body), `body:N/sdt:M` (inside content control), `body:N/row:R/cell:C/para` (paragraph inside table cell). Rows/cells wrapped by `w:sdt` have a `/sdt` segment in the path (e.g., `.../row:R/sdt/cell:C`, `.../cell:C/sdt`), indicating the wrapper node.
- `cell_index` is the **logical ordinal** of direct cells within a row, not a visible column number (does not interpret gridSpan/vMerge merged cells). `row:R`'s R is a logical row number, not a Word physical page number or visible column position.

### Coverage Declaration (No Broad DOCX Review Claims)

- **Covered**: `word/document.xml` body (paragraphs, tables, bounded-depth nesting of `w:sdt` content controls — including multi-level sdt, nested sdt in cells, sdt-wrapping-table-in-cells, sdt-wrapping-rows/cells, nested tables, drawing references) + `word/_rels/document.xml.rels`. Exceeding supported depth (default 8 wrapper layers) or encountering unsupported visible containers triggers `uncovered_containers` and a partial/non-zero exit; never silently omitted.
- **Not covered**: Headers, footers, footnotes, endnotes, comments, and other story parts. When present in the package, recorded in `uncovered_parts` — not extracted, not treated as "no content".

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Full success (all referenced images resolved or no image references, and no uncovered containers) |
| 1 | Partial extraction (`status=partial`/`rejected`, no budget factor); JSON written, incomplete items truthfully listed |
| 2 | Invalid ZIP/DOCX |
| 3 | Security violation (path traversal / symlink / entity attack / duplicate part / duplicate relationship Id / bomb limit) |
| 4 | Missing required document part |
| 5 | Budget exceeded, output conflict (target exists / points to input), or write error |
| 64 | Usage/parameter error (including illegal `--min-image-side` value) |

### No-Silent-Overwrite Policy

- The script **never overwrites** any existing file: images and JSON are created with `O_CREAT|O_EXCL` exclusive creation.
- Pre-validation of input and all output identities and collisions: canonical paths (realpath) + device/inode dual comparison, not just string comparison.
- Path policy matches actual behavior: accepts the caller-provided realpath as the write target; **does not reject symlinks in parent directories** (output directory **itself** being a symlink is rejected); non-empty output directories are accepted, **only same-name file/symlink collisions are rejected**; unrelated existing files are untouched, not deleted, not overwritten.
- Rejection: JSON path points to the input file (same path or same inode), output directory itself is a symlink, output directory already contains same-name file/symlink, image path and JSON path collide.
- Re-running on the same output directory with same-name collision is rejected (exit code 5); use a fresh directory for each batch.

### Security Checklist

- ZIP path traversal (`..`, absolute paths, backslashes) → rejected
- Symlink entries → rejected (default mode: entry goes to `rejected_entries` and its content is **never read/output**; if a required part is rejected, the entire run fails)
- External relationships (TargetMode=External) → recorded only, not followed
- XML entity expansion attacks (DOCTYPE/ENTITY) → rejected at the parse layer, **encoding-aware**: identified and decoded via BOM / NUL byte heuristic / XML declaration (supports UTF-8, UTF-16LE/BE); inconsistent or unsupported encoding declarations are rejected. All document/rels parts share the same policy
- Duplicate canonical part names (e.g., two `word/document.xml`) → rejected before parsing; duplicate relationship Ids → rejected
- ZIP bombs (total / single file / entry count) → parameterizable limits
- Read-only input + isolated output: script never writes to the input file; output exclusively created

## PDF Reading & Capability Reference

See `pdf-capability-check.md` (relative to this skill directory).

> **Note**: The capabilities below are based on a development environment smoke test. Unknown installations must first use ToolCatalog to read tool parameters + run a real non-sensitive smoke PDF verification; do not claim "all previous releases support this."

### Two Read Modes

| Mode | Invocation | Returns | Use When |
|------|-----------|---------|----------|
| **Default (auto)** | `Read(file_path, pages="1")` or omit `pages` for sequential reads | Text pages → plain text; scanned/image pages → auto-rendered as page images; omitting `pages` reads by budget from page 1 | Quick text extraction, outline scanning, sequential reading |
| **Explicit page image (render)** | `Read(file_path, pages="1", pdf_mode="render")` | All selected pages rendered as bitmaps | Inspecting figures, seals, charts, layout, embedded pixel badges |

### Behavioral Notes

- `render` **requires** explicit valid `pages`; cannot be combined with `outline=true`.
- The model must support **vision** capability; **on a fixed non-vision or unknown-capability model, `render` will fail** (not "skip images and return text"), behavior confirmed from the actual tool response.
- **Auto without `pages`** reads from page 1 by document budget; same session and version allows continuation; file version change resets the cursor.
- **After `render`**, subsequent reads should stay in render mode and use the tool's precise remaining page range; a single `render` does not cover the entire document.
- **Auto mode returning a page image that is actually viewed counts as viewed** — explicit `render` is not the only valid path.
- Single-batch page images are subject to gateway request body size limits; split with `pages` for smaller batches (e.g., 1–3 pages per call).

### Key Constraints

- No returned and viewed page image = **unviewed** (page images actually returned and viewed via auto or render both count); never claim inspection without it.
- Render failure → record as **partial** (incomplete item + failure reason); never pass, never fabricate success.
- Remote/third-party OCR services must not be installed; unauthorized OCR, email, or unfamiliar URL transmission outside the user-selected model channel is prohibited; the selected model still processes text/images under its disclosed authorization.
- Hyperlinks and QR codes in documents are not followed by default; no extra upload to OCR services.
- Page-image resolution is determined by the upstream renderer, currently baseline approximately 180 DPI, subject to downsampling.

## Image Inspection Discipline

1. Every image requiring review must be actually opened with the `Read` tool
2. Recording format: `[Viewed] <file path> — <observation summary>`
3. When illegible: `[Illegible] <file path> — <reason>` (readability tagged `illegible`, counted as incomplete)
4. Not yet inspected: `[Not inspected] <file path>`
5. Never infer image visual content from filename, metadata, or OCR text

## Very Small / Illegible Image Rules (No Default Pass)

1. **Size gate (too_small)**: When extracted image width or height **≤ threshold** (default 10 pixels, i.e., minimum acceptable size is 11, aligned with confirmed model boundary "width and height must be >10"; script parameter `--min-image-side` adjustable, must be ≥1), JSON tags `readability=too_small`. Such images **must not be sent to vision models** (model vision APIs generally require width/height >~10 pixels; a 1×1 image triggers 400), **must not count as "effectively viewed"**, must remain in the planned/reference and acceptance denominator, and must not count in the effectively viewed/completed numerator; always record as unchecked/incomplete with reason. The same denominator rule applies to illegible and unviewed images. Any legitimate scope exclusion needs a separate, explicit and evidenced reason; small dimensions alone cannot justify exclusion.
2. **Illegible**: When content is unreadable after Read (blurry, too dark, render artifacts, etc.), tag `illegible`, count as incomplete; do not mask as "pending confirmation" or treat as "not provided" or "check passed".
3. **Unknown dimensions**: When format is unrecognized or dimensions cannot be probed, tag `unknown_dimensions`, also not passing; requires manual/other confirmation or records as incomplete.
4. **Passing the size gate only means Read may be attempted, not visual acceptance**: Images that pass the size gate still require actual Read with human confirmation of legibility to count as inspected; header parsing alone does not constitute visual acceptance.
5. **Do not create details via enlargement**: For low-resolution images, do not upscale, sharpen, or speculate to produce non-existent text, numbers, seals, or graphic details; record only what is actually visible.
6. **No default external transmission**: Extracted images are used only within the local review chain by default; without user/delegator authorization, images are not sent to external services or written into external deliverables.
7. **No authenticity checks**: Size and readability checks only prove "can/cannot see" and "what is seen," not that seals, signatures, or certificates are genuinely valid.

## Visual Self-Check Rules (Post-Review Verification)

These rules apply after initial observation to catch common visual misreadings. They are **generalized** — not tied to any specific test case, pattern, or known correct answer.

1. **Direction / rotation verification**: For rotated text or shapes, determine orientation by comparing the **pointed end or distinctive tip** of the object relative to its **main body or baseline** — do not infer rotation solely from overall image layout or surrounding page text. Verify the reading direction of characters/glyphs by checking stroke order and glyph upright orientation independently.

2. **Chart / bar sequence ordering**: When ranking items by height or length in a chart:
   - Step A: Walk items **left to right** (or along their natural axis) one by one.
   - Step B: For each pair, compare the **top edge** (for vertical bars) or **rightmost edge** (for horizontal bars) against the **shared baseline**, not relative positions on the page.
   - Step C: Only after all pairwise comparisons are complete, produce the ordered ranking.
   - Never skip the comparison step or assume rankings from a quick glance.

3. **Uncertain items**: If a detail cannot be reliably determined (too small, partially obscured, ambiguous glyph), mark it **`[未验证]` / `[unverified]`** — do not fabricate a ranking, direction, or count. The absence of certainty is itself a finding that must be reported.

4. **File metadata accuracy**: Byte counts and SHA-256 hashes in reports **must** be computed by actual file-system tools (e.g., `shasum`, `stat`) during the current run. Never quote metadata from memory, prior reports, or other agents' outputs.

5. **Evidence grounding**: Every visual conclusion (short code, shape count, chart trend, rotation) must be traceable to a specific `Read` tool invocation that returned an `ImageContent` result. When a previous observation is disputed or suspect, **re-render the specific page** with `pdf_mode="render"` and re-inspect the fresh image — do not defer to the original observation.

## Dependencies

- DOCX extraction: Python 3.9+ (standard library only: zipfile, xml.etree.ElementTree, json, hashlib, argparse, codecs, re, stat, struct)
- DOCX extraction uses only the standard library; optional geometry requires Python >=3.10 and locked Pillow 12.3.0. See [dependencies](DEPENDENCIES.md). Measurement is offline; explicitly authorized dependency installation accesses official package infrastructure.

## Optional local raster geometry measurements

When an actually viewed chart or diagram has an ambiguous component count, relative pixel extent, or tip orientation, use `scripts/measure_regions.py` for bounded, objective supplementary measurements. This tool does not read PDF files, OCR text, classify objects, identify seal authenticity, or decide tender compliance. Keep the actual `Read` observation and this measurement distinct; geometry alone does not count as viewing an image.

First read `DEPENDENCIES.md`; install the locked dependency into this Agent's own private workspace runtime. Use its interpreter, never a developer tree or another Agent's environment. Read `schemas/measurement-input.schema.json` and `schemas/measurement-output.schema.json` before constructing the request. All seven input fields are mandatory. Supply JSON on stdin to the interpreter running `scripts/measure_regions.py`; stdout is the sole result. Use the execution tool's timeout of 30 seconds. If it terminates before valid output, mark measurement incomplete; do not use partial stdout.

1. Select a local PNG/JPEG path already authorized for this task and actually viewed. For a PDF page, first obtain a page image through an available, verified platform export capability. Do not scrape unrelated run caches or assume that a rendered tool image has an accessible file path. If unavailable, report the capability gap. Before accepting any measurement, match `source.sha256` to the immutable SHA-256 recorded for the PNG/JPEG version actually viewed. For a derived PDF page image, match it to the verified export receipt's image SHA-256 and preserve the separately verified original-PDF SHA-256 and Read-to-physical-page mapping. A matching path alone is insufficient. If identity is missing or mismatched, do not combine the measurement with the old visual observation: re-establish authorization and version identity, actually view that exact version, and repeat measurement as needed.
2. Choose an explicit ROI and decoded RGB channel bounds plus minimum HSV saturation from the visible region. Preserve the submitted configuration and full JSON as evidence. The coordinate origin is the top-left; x increases rightward, y downward. Pixel centers have integer coordinates; ROI and bounding box right/bottom edges are exclusive. Nonidentity EXIF orientation is rejected. No rotation, scaling or color transformation is applied. ICC profile presence is reported but color management is not performed.
3. Prefer separated, solid-color shapes. If axes, labels or background are selected, tighten the explicitly documented ROI/threshold and explain why. Do not repeatedly tune thresholds to reach a desired answer. If meaningful threshold changes alter the result, retain both and mark the interpretation uncertain. Never silently change `min_area` to remove inconvenient items.
4. `retained_components` is the count of connected threshold-mask regions after filtering, **not the count of depicted semantic items**. Touching shapes merge; fragmented shapes split. Check the actual image for both. The result separately reports all small discarded regions/pixels, border contact and matched-pixel total.
5. Compare bounding extents and areas only as pixel geometry at the same image scale. X/Y sections give each component's selected pixel population along up to nine columns/rows, including both extrema. A narrower end may support a visual tip interpretation for an isolated suitable shape, but holes, arrow shafts, overlaps and labels can defeat that interpretation. There is no automatic arrow-direction decision. Never translate pixel dimensions into chart data values or physical dimensions without independently evidenced calibration.
6. Empty mask, cropped/border-touching shapes, touching/fragmented objects, mixed colors, anti-aliasing, JPEG noise, unsupported mode/orientation, transparent ROI, budgets or timeout mean the question may remain unresolved. `status=measured` means statistics computed, not interpretation confirmed. `status=rejected` and exit 2 mean incomplete; never interpret them as absence or pass. Exit 0 only means a valid measurement JSON was produced.

Hard limits: source 32 MiB; whole image 16 million pixels; ROI 1 million pixels; 5,000 total components including those later filtered; request 16 KiB. Cooperative elapsed processing limit 12 seconds is checked during traversal, but cannot interrupt a native decoder; the caller's 30-second execution timeout is required. Split ROIs explicitly if necessary and retain overlap/crop caveats. Inputs are opened read-only as regular files, with final symlinks rejected where the OS supports O_NOFOLLOW; parent symlinks resolve normally. The tool does not implement filesystem authorization: the caller must supply only an authorized file. It reads that file and stdin only, with no network, directory enumeration or source writes.

### Measurement evidence and version-binding requirements

1. **Full request and result preservation**: For every `measure_regions.py` invocation, persist three separate files: (a) the exact JSON request body, (b) the complete untruncated stdout (the measurement JSON), and (c) stderr and exit code. Never print only a slice, never discard stderr on success, and never omit a non-zero exit code from the record.
2. **Exported image version binding**: After `ExportMedia` produces a local JPEG/PNG, **actually `Read` that exact file** before using it as a measurement source. This binds the exported path, byte length, and SHA-256 to the version you inspected. Do not assume a cache hit, skip the Read, or match by filename alone.
3. **Per-object discrepancy investigation**: When the visual object count and `retained_components` disagree, investigate each visual object individually: (a) is it fully within the ROI? (b) was its color captured by the RGB/HSV thresholds? (c) was it filtered out by `min_area`? (d) did it merge with a neighbor via connectivity? (e) did it fragment into multiple components? Record the status of each object. Do not attribute the mismatch to a single unverified cause (e.g. "likely merged") without examining the evidence.
4. **Unresolved discrepancies are incomplete**: Any count or ranking difference that remains unexplained after the per-object check must be recorded as **incomplete** (`[未验证]`/`[unverified]`). Do not close the discrepancy by asserting "visual priority" or "measurement priority" — both are hypotheses until the per-object investigation resolves them. The incomplete item stays in the denominator.
5. **No sample-specific content**: These rules are generic. Do not embed example ROIs, thresholds, correct answers, or specific hash values into the skill documentation.

### Evidence required for geometric conclusions

Quantified conclusions about counts, relative extents, bar rankings or tip geometry require an actual measurement and an explicit mapping of ROI, thresholds, components and sections to semantic objects in the same image version. Without pixel results or a clear object mapping, report unknown; never equate connected-region count with depicted item count. When measurements contradict an earlier observation, preserve both, re-view the exact version and check threshold/segmentation suitability. Until resolved, silently retaining the old observation or automatically adopting the measurement is prohibited. Rotated text, chart values and unsuitable segmentation still require their own visual/text evidence; this helper does not invent answers.

For PDF local page images, follow the [export chain](pdf-capability-check.md) and [runtime setup](DEPENDENCIES.md).

## Full-raster coverage before whole-figure geometry

Before treating a local ROI's measurements as evidence about a whole figure, run the supervised `scripts/audit_roi_coverage.py` CLI with the same exact image identity and seven-field RGB/HSV request. Read [coverage usage](USAGE.md) and its two schemas first. Preserve request/full stdout/stderr/exit separately in the registered private workspace. Its new files are additive; the reviewed region helper and locked Pillow dependency stay unchanged.

Inspect outside-ROI matches against the actual image. Widen or explicitly tile ROIs when justified and reconcile object identities, clipping and overlap before quantifying the whole figure. Outside pixels can be objects, axes, labels or background. Outside=0 concerns only the submitted threshold, never semantic completeness. Count/ordering discrepancies stay unknown/incomplete in the denominator until explained; neither geometry nor earlier visual guesses automatically prevails.

A full-image transparency, decode, size, scan-time or worker-timeout rejection means coverage unknown. Never replace it with zero outside matches or reuse a successful result from another image/threshold. The stricter full-image alpha check does not remove the original helper's ability to measure an opaque ROI, but such local measurements cannot establish full-image coverage.

## Candidate file-backed delegation input

After the platform capability is released and verified, use the [input preparation guide](delegation-input.md). Received delegated input is the complete `tender-delegation-input/v1` JSON document. Its `original_request.text` preserves the exact original request; `task_spec.value` preserves the full parsed Spec, while its SHA binds the original file bytes, not JSON reserialization. The new structural gate does not replace the original TaskSpec checker, source comparison, actual Skill execution, or independently verified receipts. Missing or mismatched evidence still blocks affected business work. Direct human maintenance requests remain outside this delegated-input contract.
