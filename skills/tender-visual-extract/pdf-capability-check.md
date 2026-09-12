# PDF Capability Reference

## Current Status (2026-08-31)

Use the available tools directly for the assigned material. If a concrete reading or rendering failure needs diagnosis, inspect tool parameters and optionally use a small non-sensitive sample. A smoke test is not a first-use or task-admission requirement; report actual capability limits.

The platform PDF reading tool (Read) supports two modes:

| Mode | Parameter | Behavior |
|------|-----------|----------|
| Default (auto) | No `pdf_mode` or `pdf_mode="auto"` | Text pages extract plain text; scanned/image pages auto-render as page images; without `pages`, reads by budget from page 1 |
| Explicit page image (render) | `pdf_mode="render"` + explicit `pages` | All selected pages rendered as bitmaps, for inspecting figures, seals, charts, layout |

## Capability Boundary

| Capability | Status | Notes |
|------------|--------|-------|
| Text-layer extraction | ✅ Verified | Default Read mode reads text layer directly |
| Page-image rendering | ✅ Verified | `pdf_mode="render"` + explicit `pages`; model must support vision |

> OCR differs from text-layer extraction; establish its availability from actual tools and results. Ordinary visual tasks require no prior OCR smoke test.

## Usage Constraints

### Model Requirements

- Page-image mode requires a **vision-capable model**.
- On a **fixed non-vision or unknown-capability model, `render` fails** — it does not "skip images and return text." Behavior must be confirmed from the actual tool response; Smart-routed vision selection must also be verified from real responses.
- A single-page diagnostic may help after a concrete rendering failure; otherwise work directly on assigned material.

### Page & Budget Limits

- `render` must include a valid `pages` parameter (e.g., `"1"`, `"1-3"`, `"1,3,5"`).
- **Auto without `pages`** reads by budget from page 1. Same session + same file version = continuation; file version change resets the cursor.
- **After `render`**, continue in render mode using the tool's precise remaining-page range. A single `render` does not cover the entire document.
- **Auto returning a page image + actual viewing = inspected.** Explicit `render` is not the only valid path.
- Single-batch page images are bounded by the upstream gateway's request body limit. Split into smaller batches when exceeded.

### Resolution

- Page-image resolution is determined by the upstream renderer. Current baseline is approximately **180 DPI**, subject to downsampling.
- Very small embedded images (≤ 10×10 px) may remain illegible even in page images; check the DOCX-extracted original when available.

## Failure Recording Strategy

When PDF page-image rendering fails:

1. **Record as incomplete (partial)**: `[Render failed] <file> page N — <error>`
2. **Do not mark as passed**: Unrendered ≠ no issue
3. **Do not fabricate success**: Never infer "not provided" from "not read"
4. **Do not draw conclusions from unrendered results**: Make no assertions about unviewed image content
5. **Record the failure reason**: Preserve error information for troubleshooting

## Correct Practices

- Text pages: Extract text normally, tag as `[Text layer read]`
- Text pages with figures/seals/charts: Use `pdf_mode="render"` for explicit rendering before actual inspection
- Image pages render success: Record observations after actual viewing
- Image pages render failure: Tag `[Incomplete-render failed]`, add to incomplete list
- Scanned pages unreadable: Tag `[Incomplete-unrenderable]`, do not skip
- Auto mode returns page image and actually seen: Also counts as viewed; record observations

## Prohibitions

- Do not install remote OCR services
- Prohibited: unauthorized OCR, email, or unfamiliar URL transmission outside the user-selected model channel; the selected model still processes text/images under its disclosed authorization
- Do not announce "this page has no issues" or "check passed" due to render failure
- Do not substitute OCR text for actual visual inspection of images
- No seal/signature/certificate authenticity verification: visual inspection only reports visibility (present/absent/illegible), not authenticity
- Do not send tender content (including extracted images, personnel info, pricing) to OCR services, email, or unfamiliar URLs
- Distinguish from the user-selected cloud model's normal text/image processing channel; do not claim fully local processing

## DOCX Extraction Distinction

- The DOCX extraction script (`extract_docx.py`) processes ZIP-internal XML structures and embedded resources — **independent of PDF rendering capability**.
- Limited DOCX extraction ≠ full Office rendering: headers, footers, footnotes, endnotes, comments, embedded OLE objects are not in scope.
- PDF page-image mode is for viewing PDF document visual presentation, independent from DOCX extraction.

## Cloud Model Channel Disclosure

When using a user-selected cloud model, text and images sent for processing are handled by that model's channel. Fully local processing cannot be promised.


## Export a viewed PDF page for local geometry

Check the current ToolCatalog for `ExportMedia` with exactly `media_ref` and `file_path`; availability is installation-specific. The tool is a medium-risk, reversible **mutation**, separate from read-only Read and subject to the platform's real approval policy. Its file writes require an authorized workspace destination with an existing parent and a new filename; existing targets are rejected, never overwritten. Do not infer availability from a version number or a rendered image alone.

Use a `dc-media://` reference actually supplied by the current Read page-image result or authorized attachment. Bind each reference to the current original PDF SHA-256, physical page number and actual viewed image invocation. Do not guess references, inspect media caches/tokens or recover bytes from diagnostic logs. For a multi-page render, preserve the returned reference-to-page mapping; if ambiguous, render one explicit page and verify its mapping.

Invoke `ExportMedia(media_ref=<actual reference>, file_path=<new path in registered private workspace>)`. Success returns a JSON text payload with `path`, `media_ref`, `mime_type`, `bytes`, and `sha256`; it exports original bytes without re-rendering or recompression, at most 32 MiB. It does **not** return a PDF hash or page number: those must come from the separately verified original-file manifest and Read mapping, and must not be invented as export fields. Preserve the actual payload, approval outcome and error if any. A failed write, rejected authorization or missing capability remains incomplete.

The geometry helper accepts only PNG/JPEG even though ExportMedia supports additional media formats. Pass the returned authorized `path`, and require helper `source.sha256` and `source.bytes` to equal the export `sha256` and `bytes`; require format/dimensions to match the actual image under the declared unrotated coordinate convention. Match the export `media_ref` back to the exact viewed Read image and original PDF hash/page chain. A missing or conflicting identity requires re-establishing the exact version and actually viewing it again, never merging stale observations. The export alone is not a successful measurement or visual acceptance.

Follow the complete [skill](SKILL.md) and [dependency setup](DEPENDENCIES.md). Only the current registered private workspace may hold exported pages, temporary data and runtime environments. Quantified geometric findings require actual pixel measurements mapped to the visible semantic objects; component counts are not automatically object counts. Preserve unresolved contradictions and report unknown when segmentation is unsuitable.
