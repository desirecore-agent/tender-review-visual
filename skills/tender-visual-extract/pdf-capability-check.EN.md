# Tender Visual Extract — PDF & Document Capability Guide

> English companion to `SKILL.md`. For full DOCX extraction reference, see `SKILL.md`.

## 1. PDF Reading: Two Modes

The `Read` tool supports two PDF reading modes:

| Mode | Invocation | Returns | Use When |
|------|-----------|---------|----------|
| **Default (auto)** | `Read(file_path, pages="1")` or omit `pages` for sequential reads | Text pages → plain text; scanned/image pages → auto-rendered as page images; omitting `pages` reads by budget from page 1 | Quick text extraction, outline scanning, sequential reading |
| **Explicit page image (render)** | `Read(file_path, pages="1", pdf_mode="render")` | All selected pages rendered as bitmaps | Inspecting figures, seals, charts, layout, embedded pixel badges |

### Key Rules

- **`render` requires explicit `pages`** — cannot be combined with `outline=true`.
- **Model must support vision** — on a **fixed non-vision or unknown-capability model, `render` will fail** (it does not silently fall back to returning text). Behavior must be confirmed from the actual tool response; Smart-routed vision selection must also be verified from real responses.
- **Gateway size limit** — large page-image batches may exceed the request body limit; split with `pages` (e.g., 1–3 pages per call).

### Read Behavior Details

- **Auto without `pages`**: reads from page 1 by document budget. Within the same session and file version, consecutive calls continue reading; the cursor resets when the file version changes.
- **After a `render` call**: subsequent reads should stay in render mode and use the exact remaining page range returned by the tool — a single `render` does not cover the entire document.
- **Auto returning a page image counts as visual inspection** — if the auto mode returns a bitmap and you actually see it, that counts. Explicit `render` is not the only valid path.

## 2. Capability Matrix

| Capability | Status | Notes |
|------------|--------|-------|
| Text-layer extraction | ✅ Verified | Default Read mode |
| Page-image rendering | ✅ Verified | `pdf_mode="render"` + explicit `pages`; requires vision-capable model |

> OCR differs from text-layer extraction; establish its availability from actual tools and results. Ordinary visual tasks require no prior OCR smoke test.

## 3. Constraints

### Model Requirements

- Page-image mode requires a **vision-capable model**.
- A single-page diagnostic may help after a concrete rendering failure; otherwise work directly on assigned material.
- Smart routing or other controlled vision selection must be confirmed from real tool responses.

### Page & Budget Limits

- `render` must include a valid `pages` parameter (e.g., `"1"`, `"1-3"`, `"1,3,5"`).
- **Auto without `pages`** reads by budget from page 1. Same session + same file version = continuation; file version change resets the cursor.
- **After `render`**, continue in render mode using the tool's precise remaining-page range. Do not treat a single `render` as "all pages read."
- **Auto returning a page image + actual viewing = inspected.** Do not require explicit `render` for every visual check.
- Single-batch page images are bounded by the upstream gateway's request body limit. Split into smaller batches when exceeded.

### Resolution

- Page-image resolution is determined by the upstream renderer. Current baseline is approximately **180 DPI**, subject to downsampling.
- Very small embedded images (≤ 10×10 px) may remain illegible even in page images; check the DOCX-extracted original when available.

## 4. Failure Handling

| Situation | Record As | What NOT To Do |
|-----------|-----------|----------------|
| Render fails (non-vision / unknown model) | `[Render failed] <file> page N — <error>` → partial | Don't mark as "passed"; don't say "fell back to text" |
| Text only, no image | `[Text layer read] <file> page N` | Don't claim visual inspection of figures |
| Auto returns page image | `[Viewed] <file> page N — <observation>` | Don't require explicit render as the only valid path |
| Illegible image | `[Illegible] <file> page N — <reason>` → partial | Don't guess content |
| Page missing | `[Missing] <file> page N` | Don't infer "not provided" |

**Golden rule**: No returned page image + no viewing = unviewed. Page images actually returned and viewed via auto or render both count toward the inspected set. Never assert what you didn't see.

## 5. DOCX Extraction Scope

- `extract_docx.py` processes ZIP-internal XML structures and embedded resources — **independent of PDF rendering**.
- It extracts: body paragraphs, tables (with **logical** row/cell positioning — `row:R` is a logical row index, not a Word physical page number or visible column position), embedded images via drawing references.
- It does **not** cover: headers, footers, footnotes, endnotes, comments, embedded OLE objects.
- Partial extraction is reported as `status: partial` with explicit `uncovered_containers` / `uncovered_parts`.
- **Limited DOCX extraction ≠ complete Office rendering.**

## 6. Integrity & Non-Fabrication

- **No seal/signature verification**: Visual inspection reports visibility (present/absent/illegible), never authenticity.
- **No link/QR following**: Hyperlinks and QR codes in documents are not followed by default.
- **No unauthorized content exfiltration outside the selected model channel**: Tender content (including extracted images, personnel info, pricing) must not be sent to OCR services, email, or unfamiliar URLs beyond what the user-selected model channel handles under disclosed authorization.
- **Image inspection requires actual viewing**: The image must actually be seen using an available tool or visible UI to count as viewed.

## 7. Cloud Model Channel Disclosure

When using a user-selected cloud model, text and images sent for processing are handled by that model's channel. **Fully local processing cannot be promised.** This must be clearly distinguished from unauthorized external transmission.

## 8. Installation verification

Use the [canonical PDF capability reference](pdf-capability-check.md) or its [Chinese counterpart](pdf-capability-check.zh-CN.md) as tool guidance when needed. Work directly on assigned materials; use a diagnostic sample only after a concrete capability failure. Export and measurement are optional methods, not an installation acceptance gate. Derive observations from actual material; historical fixture answers are not evidence.

## Export a viewed PDF page for local geometry

Check the current ToolCatalog for `ExportMedia` with exactly `media_ref` and `file_path`; availability is installation-specific. The tool is a medium-risk, reversible **mutation**, separate from read-only Read and subject to the platform's real approval policy. Its file writes require an authorized workspace destination with an existing parent and a new filename; existing targets are rejected, never overwritten. Do not infer availability from a version number or a rendered image alone.

Use a `dc-media://` reference actually supplied by the current Read page-image result or authorized attachment. Bind each reference to the current original PDF SHA-256, physical page number and actual viewed image invocation. Do not guess references, inspect media caches/tokens or recover bytes from diagnostic logs. For a multi-page render, preserve the returned reference-to-page mapping; if ambiguous, render one explicit page and verify its mapping.

Invoke `ExportMedia(media_ref=<actual reference>, file_path=<new path in registered private workspace>)`. Success returns a JSON text payload with `path`, `media_ref`, `mime_type`, `bytes`, and `sha256`; it exports original bytes without re-rendering or recompression, at most 32 MiB. It does **not** return a PDF hash or page number: those must come from the separately verified original-file manifest and Read mapping, and must not be invented as export fields. Preserve the actual payload, approval outcome and error if any. A failed write, rejected authorization or missing capability remains incomplete.

The geometry helper accepts only PNG/JPEG even though ExportMedia supports additional media formats. Pass the returned authorized `path`, and require helper `source.sha256` and `source.bytes` to equal the export `sha256` and `bytes`; require format/dimensions to match the actual image under the declared unrotated coordinate convention. Match the export `media_ref` back to the exact viewed Read image and original PDF hash/page chain. A missing or conflicting identity requires re-establishing the exact version and actually viewing it again, never merging stale observations. The export alone is not a successful measurement or visual acceptance.

Follow the complete [skill](SKILL.md) and [dependency setup](DEPENDENCIES.md). Only the current registered private workspace may hold exported pages, temporary data and runtime environments. Quantified geometric findings require actual pixel measurements mapped to the visible semantic objects; component counts are not automatically object counts. Preserve unresolved contradictions and report unknown when segmentation is unsuitable.
