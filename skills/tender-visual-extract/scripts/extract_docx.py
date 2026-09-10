#!/usr/bin/env python3
"""
extract_docx.py — Safe DOCX (OOXML/ZIP) extraction for document review.

Extracts:
  - Paragraph text with logical location paths (body-level index, or
    table/row/cell/paragraph for content inside tables). NOT Word page numbers.
  - Tables collected by DIRECT rows/cells only (nested tables are associated
    with their parent cell path, not merged into the parent table).
  - Content inside legal wrapper nodes (w:sdt / w:sdtContent) is collected at
    any supported nesting depth: body-level sdt, sdt inside sdt (bounded),
    sdt inside table cells (including sdt wrapping a nested table), and sdt
    wrapping table rows. Unsupported visible containers are recorded as
    uncovered with their logical location, never skipped silently.
  - Image reference inventory built from ACTUAL drawing/blip references in the
    document body (authoritative manifest). BOTH reference kinds are counted:
    r:embed (embedded image) and r:link (external/linked image). A blip with
    neither kind is still an unsupported reference — the denominator is never
    shrunk because an attribute is absent. Every reference records a status:
    resolved / missing-part / rejected / external-not-fetched /
    budget-exceeded / unsupported, plus its reference kind and logical
    location. External links are NEVER fetched and no network request is made.
  - Relationships from word/_rels/document.xml.rels
    (External TargetMode=External relationships are RECORDED, never followed)

Security (all enforced in code, not just documented):
  - ZIP entry path traversal (.. segments, absolute paths, backslash tricks) => reject
  - Symlink ZIP entries => reject
  - Duplicate canonical package part names => reject before parsing (ambiguity)
  - Duplicate relationship Ids => reject before resolution
  - XML entity expansion (DOCTYPE/ENTITY) => rejected at the parse layer for
    ALL supported encodings (UTF-8, UTF-16LE/BE detected from BOM or
    declaration); unsupported encodings are rejected explicitly.
  - ZIP bomb protection: total uncompressed size cap, single-entry cap, entry count cap
  - Overall extraction budget: max output bytes written for images
  - Consumption layer only uses entries that passed validation; rejected
    required parts fail the whole extraction; rejected optional media become
    incomplete items (never written to output).
  - Input file is NEVER modified (opened read-only; output goes to a separate
    directory). Output files are created exclusively (O_EXCL); pre-existing
    files with colliding names (or symlinks at target paths) cause failure,
    never overwrite. Unrelated pre-existing files in the output directory are
    NOT deleted or overwritten — the script only refuses name collisions.
  - Output paths: the realpath of each caller-supplied path is accepted as
    the target (a symlinked PARENT component is not refused; we do not promise
    parent-link rejection). The output directory itself being a symlink is
    refused. JSON output must not collide with the input file or any image
    output (compared by canonical path and device+inode, not string equality).

Coverage declaration (explicit, not implied):
  - Only word/document.xml and word/_rels/document.xml.rels are consumed.
  - Headers, footers, footnotes, endnotes, comments and other story parts are
    NOT extracted; if present in the package they are recorded as uncovered.
  - Visible containers not supported by the bounded walker (or wrapper nesting
    deeper than the supported bound) are recorded in uncovered_containers with
    their logical location; the extraction then reports partial status and a
    non-zero exit code. "No paragraphs + no tables + no uncovered + complete"
    is structurally impossible for a document with visible body content.

Exit codes:
  0 = success (extraction complete — all referenced images resolved, no
      uncovered containers/parts affecting the body)
  1 = partial extraction (some references unresolved, uncovered containers,
      or uncovered story parts; JSON status="partial")
  2 = input not a valid ZIP/DOCX
  3 = security violation (path traversal, symlink, entities, duplicates, bombs)
  4 = missing required document part
  5 = budget exceeded or write error
  64 = usage error

Usage:
  python3 extract_docx.py INPUT.docx --out-dir OUTDIR [options]

Options:
  --out-dir DIR          Output directory (required; images written here)
  --json PATH            Write JSON result here (default: OUTDIR/extraction.json)
  --max-total-bytes N    Total uncompressed bytes allowed across ZIP (default 200000000)
  --max-entry-bytes N    Single entry uncompressed size limit (default 50000000)
  --max-entries N        Max ZIP entry count (default 2000)
  --max-image-bytes N    Total bytes allowed for extracted images (default 100000000)
  --strict               Abort entirely on ANY dangerous entry (default: reject the
                         entry and continue if the rest is safe)
  --min-image-side N     Size gate: images whose width OR height is NOT GREATER
                         than this threshold are flagged readability=too_small.
                         Semantics: "must be greater than N". Default 10
                         (matching the confirmed model boundary width/height>10).
                         Must be >= 1.

Overwrite policy (documented, not silent):
  The script NEVER overwrites. Output image files and the JSON result are
  created with O_CREAT|O_EXCL. If any target path already exists (file,
  symlink, or any filesystem object), extraction fails with exit code 5
  before writing anything at that path. Re-running into the same directory
  is refused for colliding names; unrelated pre-existing files are left
  untouched (the manifest only references files written in this run). Use a
  fresh output directory per batch for clean isolation.

Only Python standard library is used (zipfile, xml.etree, json, argparse, etc.).
Portable: no hardcoded absolute paths; all locations come from CLI arguments.
No network access is performed at any point; external image links are recorded
as external-not-fetched, never downloaded.
"""

import argparse
import codecs
import hashlib
import io
import json
import os
import posixpath
import re
import stat
import struct
import sys
import zipfile
from xml.etree import ElementTree as ET

# ---------------------------------------------------------------------------
# XML namespaces
# ---------------------------------------------------------------------------
NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "pic": "http://schemas.openxmlformats.org/drawingml/2006/picture",
    "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
}

VML_NS = "urn:schemas-microsoft-com:vml"

W = NS["w"]
A = NS["a"]
R = NS["r"]

# Canonical package parts whose duplication is ambiguous and must be rejected.
CANONICAL_SINGLETON_PARTS = {
    "word/document.xml",
    "word/_rels/document.xml.rels",
    "[Content_Types].xml",
    "_rels/.rels",
}

# Story parts that may exist in a DOCX but are NOT covered by this extractor.
KNOWN_UNCOVERED_PART_PREFIXES = (
    "word/header",
    "word/footer",
    "word/footnotes",
    "word/endnotes",
    "word/comments",
)

IMAGE_CONTENT_PREFIX = "image/"

# Bounded wrapper traversal depth (fix-round-2 V04). Counts legal wrapper
# layers (sdt nesting) entered on the way to visible content. Paragraphs/tables
# themselves do not consume depth. 8 layers is far beyond realistic documents;
# anything deeper is recorded as uncovered, never silently skipped.
MAX_WRAPPER_DEPTH = 8

# Structural (non-visible) child tags skipped by the walker at each context.
_BODY_STRUCTURAL_TAGS = {f"{{{W}}}sectPr"}
_ROW_STRUCTURAL_TAGS = {f"{{{W}}}trPr"}
_CELL_STRUCTURAL_TAGS = {f"{{{W}}}tcPr"}
_SDT_STRUCTURAL_TAGS = {f"{{{W}}}sdtPr"}


class SecurityViolation(Exception):
    """Raised when a ZIP entry or XML content violates safety rules."""


class ExtractionError(Exception):
    """Raised for structural problems (not a ZIP, missing parts, etc.)."""


class BudgetExceeded(Exception):
    """Raised when the image extraction budget is exceeded."""


class OutputConflict(Exception):
    """Raised when output would overwrite or collide with an existing path."""


# ---------------------------------------------------------------------------
# Safe XML parsing: reject DTD/ENTITY at the parse layer, encoding-aware.
# ---------------------------------------------------------------------------
_SUPPORTED_ENCODINGS = {"utf-8", "utf-16le", "utf-16be"}


def _read_declared_encoding(text: str):
    """Read the encoding name from the XML declaration in decoded text."""
    m = re.search(r'<\?xml[^>]*\bencoding\s*=\s*["\']([^"\']+)["\']', text[:512])
    if not m:
        return None
    return m.group(1).strip().lower().replace("_", "-")


def _check_declared_consistency(declared, actual: str, context: str) -> None:
    """Reject when the declared encoding contradicts the actual byte-level
    encoding or is outside the supported set."""
    if declared is None:
        return
    aliases = {
        "utf-8": "utf-8", "utf8": "utf-8",
        "utf-16": actual if actual.startswith("utf-16") else None,
        "utf-16le": "utf-16le", "utf-16be": "utf-16be",
    }
    if declared not in aliases:
        raise SecurityViolation(
            f"XML in {context}: declared encoding '{declared}' is not in the "
            f"supported set (utf-8, utf-16le, utf-16be); rejected"
        )
    norm = aliases[declared]
    if norm is None or norm != actual:
        raise SecurityViolation(
            f"XML in {context}: declared encoding '{declared}' contradicts "
            f"the detected byte-level encoding '{actual}'; rejected"
        )


def _detect_and_decode(raw: bytes, context: str) -> tuple:
    """Detect the XML encoding, decode to str, and enforce consistency.

    Detection order (encoding is identified from BYTES before any text-level
    security check, so no encoding can bypass the DTD/ENTITY scan):
      1. BOM (authoritative).
      2. NUL-byte heuristic (XML Appendix E.2): U+0000 is not a legal XML
         character, so any NUL byte in the stream proves a multi-byte
         encoding; byte order is determined from the leading '<' (0x3C).
      3. Otherwise the stream must be valid UTF-8.
    After decoding, the declared encoding (if any) must match the detected
    encoding and be within the supported set; mismatches are rejected.
    Returns (text, encoding_name).
    """
    if not raw:
        raise ExtractionError(f"XML in {context}: empty part")

    # 1. BOM detection (authoritative over the declaration)
    if raw.startswith(codecs.BOM_UTF8):
        try:
            text = raw[len(codecs.BOM_UTF8):].decode("utf-8")
        except UnicodeDecodeError as exc:
            raise SecurityViolation(
                f"XML in {context}: UTF-8 BOM present but content is not "
                f"valid UTF-8; rejected ({exc})"
            )
        _check_declared_consistency(_read_declared_encoding(text), "utf-8", context)
        return text, "utf-8"
    if raw.startswith(codecs.BOM_UTF16_LE):
        text = raw.decode("utf-16-le")
        _check_declared_consistency(_read_declared_encoding(text), "utf-16le", context)
        return text, "utf-16le"
    if raw.startswith(codecs.BOM_UTF16_BE):
        text = raw.decode("utf-16-be")
        _check_declared_consistency(_read_declared_encoding(text), "utf-16be", context)
        return text, "utf-16be"

    # 2. NUL-byte heuristic: NUL cannot appear in well-formed XML in a
    #    single-byte-compatible encoding, so its presence identifies UTF-16.
    if b"\x00" in raw[:4096]:
        if raw[:2] == b"\x3c\x00":
            enc = "utf-16le"
        elif raw[:2] == b"\x00\x3c":
            enc = "utf-16be"
        else:
            raise SecurityViolation(
                f"XML in {context}: NUL bytes present but byte order does "
                f"not match a supported UTF-16 XML prolog; rejected"
            )
        try:
            text = raw.decode(enc)
        except UnicodeDecodeError as exc:
            raise SecurityViolation(
                f"XML in {context}: bytes are not decodable as {enc}; "
                f"rejected ({exc})"
            )
        _check_declared_consistency(_read_declared_encoding(text), enc, context)
        return text, enc

    # 3. No BOM, no NUL: must be valid UTF-8.
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SecurityViolation(
            f"XML in {context}: bytes are not valid UTF-8 and no supported "
            f"BOM/UTF-16 pattern detected; rejected ({exc})"
        )
    declared = _read_declared_encoding(text)
    _check_declared_consistency(declared, "utf-8", context)
    return text, "utf-8"


def safe_parse_xml(raw_bytes: bytes, context: str) -> ET.Element:
    """Parse XML with DTD/entity attacks rejected at the parse layer.

    Strategy (encoding-consistent, applied to ALL document/rels parts):
      1. Detect and decode the supported encoding to text. Unsupported or
         inconsistent encodings are rejected explicitly.
      2. In the DECODED text, reject any DOCTYPE or ENTITY declaration.
         This is encoding-independent: UTF-16 content can no longer bypass
         the check because we operate on characters, not bytes.
      3. Parse from the decoded text with ElementTree.
    """
    text, enc = _detect_and_decode(raw_bytes, context)

    if "<!DOCTYPE" in text or "<!ENTITY" in text:
        raise SecurityViolation(
            f"XML in {context} (encoding={enc}) contains DOCTYPE/ENTITY "
            f"declarations; rejected (entity expansion protection)"
        )

    try:
        return ET.fromstring(text)
    except ET.ParseError as exc:
        raise ExtractionError(f"XML parse failure in {context}: {exc}") from exc


# ---------------------------------------------------------------------------
# ZIP safety checks
# ---------------------------------------------------------------------------
def check_zip_entry_name(name: str) -> None:
    """Reject path traversal, absolute paths, and backslash paths."""
    if not name:
        raise SecurityViolation("Empty ZIP entry name")
    if name.startswith("/") or name.startswith("\\"):
        raise SecurityViolation(f"Absolute ZIP entry path rejected: {name!r}")
    if len(name) >= 2 and name[1] == ":":
        raise SecurityViolation(f"Drive-letter absolute path rejected: {name!r}")
    normalized = posixpath.normpath(name.replace("\\", "/"))
    if normalized.startswith("../") or normalized == ".." or "/../" in normalized:
        raise SecurityViolation(f"Path traversal in ZIP entry rejected: {name!r}")
    for segment in name.replace("\\", "/").split("/"):
        if segment == "..":
            raise SecurityViolation(
                f"Path traversal segment '..' in ZIP entry rejected: {name!r}"
            )


def check_zip_entry_symlink(zinfo: zipfile.ZipInfo) -> None:
    """Reject symlink entries (external_attr encodes Unix mode in high 16 bits)."""
    unix_mode = (zinfo.external_attr >> 16) & 0xFFFF
    if unix_mode != 0 and stat.S_ISLNK(unix_mode):
        raise SecurityViolation(f"Symlink ZIP entry rejected: {zinfo.filename!r}")


def validate_zip_safety(
    zf: zipfile.ZipFile,
    max_total_bytes: int,
    max_entry_bytes: int,
    max_entries: int,
    strict: bool,
):
    """Validate the entire ZIP archive against bomb/traversal/duplicate limits.

    Returns (approved_infos_by_name, rejected_list):
      approved_infos_by_name: {name: ZipInfo} for entries that passed ALL
        safety checks. The consumption layer MUST use these exact ZipInfo
        objects only.
      rejected_list: [{name, reason}] for entries that failed checks.

    Duplicate canonical part names are ALWAYS rejected (ambiguity), even in
    non-strict mode — two sources for the same fact cannot be safely resolved.
    """
    infos = zf.infolist()
    if len(infos) > max_entries:
        raise SecurityViolation(
            f"ZIP entry count {len(infos)} exceeds limit {max_entries}"
        )
    total_uncompressed = sum(i.file_size for i in infos)
    if total_uncompressed > max_total_bytes:
        raise SecurityViolation(
            f"ZIP total uncompressed size {total_uncompressed} bytes exceeds "
            f"limit {max_total_bytes} bytes (possible ZIP bomb)"
        )

    # Duplicate name detection (all entries, strict requirement)
    seen_names = {}
    duplicate_names = set()
    for info in infos:
        norm = posixpath.normpath(info.filename.replace("\\", "/"))
        if norm in seen_names:
            duplicate_names.add(norm)
        else:
            seen_names[norm] = info

    rejected = []
    approved = {}
    for norm_name, info in seen_names.items():
        reasons = []
        if norm_name in duplicate_names:
            reasons.append("duplicate_part_name")
        try:
            check_zip_entry_name(info.filename)
        except SecurityViolation as e:
            reasons.append(f"path:{e}")
        try:
            check_zip_entry_symlink(info)
        except SecurityViolation as e:
            reasons.append(f"symlink:{e}")
        if info.file_size > max_entry_bytes:
            reasons.append(
                f"size:{info.file_size}>{max_entry_bytes}"
            )

        if reasons:
            reason_str = ";".join(reasons)
            if strict:
                raise SecurityViolation(
                    f"ZIP entry {info.filename!r} rejected: {reason_str}"
                )
            rejected.append({"name": info.filename, "reason": reason_str})
        else:
            approved[norm_name] = info

    # Duplicate canonical parts must always be a hard failure
    dup_canonical = duplicate_names & CANONICAL_SINGLETON_PARTS
    if dup_canonical:
        raise SecurityViolation(
            f"Duplicate canonical package part(s) {sorted(dup_canonical)}: "
            f"ambiguous content source; rejected before parsing"
        )

    return approved, rejected


def safe_read_info(
    zf: zipfile.ZipFile, info: zipfile.ZipInfo, max_bytes: int, context: str
) -> bytes:
    """Read a specific validated ZipInfo with size guard."""
    if info.file_size > max_bytes:
        raise SecurityViolation(
            f"{context}: entry {info.filename!r} size {info.file_size} > limit {max_bytes}"
        )
    data = zf.read(info)
    if len(data) > max_bytes:
        raise SecurityViolation(
            f"{context}: entry {info.filename!r} actual decompressed size "
            f"{len(data)} > limit {max_bytes}"
        )
    return data


# ---------------------------------------------------------------------------
# OOXML text/drawing helpers
# ---------------------------------------------------------------------------
def paragraph_text(p_elem) -> str:
    """Collect all w:t text in a paragraph (including inside hyperlinks),
    but NOT from nested tables (those are separate structures)."""
    parts = []
    for t in p_elem.iter(f"{{{W}}}t"):
        if t.text:
            parts.append(t.text)
    return "".join(parts)


def find_drawing_refs(elem):
    """Find image relationship references in drawings under elem.

    Returns a list of (rid_or_None, kind) tuples in document order, where
    kind is one of "embed" / "link" / "none" (a:blip) or "embed" (VML
    imagedata). fix-round-2 V06: a:blip r:link references are collected
    alongside r:embed; a blip carrying neither attribute yields (None, "none")
    so the reference denominator is never shrunk by missing attributes.
    """
    refs = []
    for blip in elem.iter(f"{{{A}}}blip"):
        embed = blip.get(f"{{{R}}}embed")
        link = blip.get(f"{{{R}}}link")
        if embed:
            refs.append((embed, "embed"))
        if link:
            refs.append((link, "link"))
        if not embed and not link:
            refs.append((None, "none"))
    for imgdata in elem.iter(f"{{{VML_NS}}}imagedata"):
        rid = imgdata.get(f"{{{R}}}id")
        if rid:
            refs.append((rid, "embed"))
    return refs


# ---------------------------------------------------------------------------
# Structure walker (V04/V05 + fix-round-2 V04): unified, order-preserving,
# bounded-depth wrapper traversal.
# ---------------------------------------------------------------------------
def walk_document(body_elem):
    """Walk the document body in document order, collecting paragraphs, tables
    and drawing references with explicit logical location paths.

    Legal wrapper handling (fix-round-2):
      - w:sdt/w:sdtContent is descended into recursively at body level, inside
        table cells, and inside sdt-wrapped table rows, up to MAX_WRAPPER_DEPTH
        wrapper layers. sdtPr children are structural and skipped.
      - Table rows may be wrapped: w:tbl > w:sdt > w:sdtContent > w:tr is
        treated as a row of that table (row numbering continues in document
        order; location paths mark the wrapper with '/sdt').
      - Any other visible container tag, or wrapper nesting beyond the bound,
        is recorded in uncovered_containers with its logical location; such
        content is NOT extracted and the result must not be claimed complete.

    Returns (paragraphs, tables, uncovered_containers):
      paragraphs: [{paragraph_index, text, location, drawing_relationship_ids,
                    drawing_references}]
      tables: [{table_index, location, rows: [[cell_text]]}]
      uncovered_containers: [{tag, location, note}]

    Location path grammar:
      body:N                        — N-th direct child of body (0-based)
      body:N/sdt:M                  — M-th sdtContent child under body child N
      body:N/table:T/row:R/cell:C   — table cell
      .../row:R/sdt/cell:C          — cell inside a sdt-wrapped row
    cell_index is a LOGICAL sequential index among the row's direct cells;
    it is NOT the visual column number (gridSpan/vMerge are not interpreted).
    """
    paragraphs = []
    tables = []
    uncovered = []
    counters = {"para": 0, "table": 0}

    def _collect_paragraph(p_elem, location):
        text = paragraph_text(p_elem)
        refs = find_drawing_refs(p_elem)
        entry = {
            "paragraph_index": counters["para"],
            "text": text,
            "location": location,
            # drawing_relationship_ids kept for compatibility (rid only)
            "drawing_relationship_ids": [rid for rid, _ in refs if rid],
            # fix-round-2 V06: full reference list with kind, incl. link/none
            "drawing_references": [
                {"rid": rid, "kind": kind} for rid, kind in refs
            ],
        }
        paragraphs.append(entry)
        counters["para"] += 1

    def _collect_table(tbl_elem, location):
        table_idx = counters["table"]
        counters["table"] += 1
        table_entry = {
            "table_index": table_idx,
            "location": location,
            "rows": [],
        }
        # Register BEFORE recursing so the tables list stays in document order
        tables.append(table_entry)
        rows_out = []

        # Rows: direct w:tr children, or rows wrapped in w:sdt/sdtContent
        row_items = []  # (tr_elem, row_location)
        row_num = 0
        for child in tbl_elem:
            tag = child.tag
            if tag == f"{{{W}}}tr":
                row_items.append((child, f"{location}/row:{row_num}"))
                row_num += 1
            elif tag == f"{{{W}}}sdt":
                sc = child.find(f"{{{W}}}sdtContent")
                if sc is None:
                    uncovered.append({
                        "tag": tag,
                        "location": f"{location}/rowwrapper:{row_num}",
                        "note": "sdt wrapping table row has no sdtContent",
                    })
                    row_num += 1
                    continue
                found_tr = False
                for sc_child in sc:
                    if sc_child.tag == f"{{{W}}}tr":
                        row_items.append(
                            (sc_child, f"{location}/row:{row_num}/sdt")
                        )
                        found_tr = True
                        row_num += 1
                    elif sc_child.tag in _SDT_STRUCTURAL_TAGS:
                        continue
                    else:
                        uncovered.append({
                            "tag": sc_child.tag,
                            "location": f"{location}/rowwrapper:{row_num}/sdt",
                            "note": "unsupported visible content inside "
                                    "sdt table-row wrapper",
                        })
                if not found_tr:
                    # sdt present but carried no row; still consumes a row
                    # slot? No — only actual rows advance numbering. Record
                    # the wrapper as uncovered if it held nothing visible.
                    uncovered.append({
                        "tag": tag,
                        "location": f"{location}/rowwrapper:{row_num}",
                        "note": "sdt table-row wrapper contained no w:tr",
                    })
            else:
                # tblPr, tblGrid and other structural table children are OK;
                # anything else at table level is a visible container we do
                # not support — record it.
                if tag not in {f"{{{W}}}tblPr", f"{{{W}}}tblGrid"}:
                    uncovered.append({
                        "tag": tag,
                        "location": f"{location}/tablechild:{row_num}",
                        "note": "unsupported visible container at table level",
                    })

        for tr, row_loc in row_items:
            # Cells: direct w:tc children, or cells wrapped in w:sdt/sdtContent
            cell_items = []  # (tc_elem, cell_location)
            cell_num = 0
            for child in tr:
                tag = child.tag
                if tag == f"{{{W}}}tc":
                    cell_items.append((child, f"{row_loc}/cell:{cell_num}"))
                    cell_num += 1
                elif tag == f"{{{W}}}sdt":
                    sc = child.find(f"{{{W}}}sdtContent")
                    if sc is None:
                        uncovered.append({
                            "tag": tag,
                            "location": f"{row_loc}/cellwrapper:{cell_num}",
                            "note": "sdt wrapping table cell has no sdtContent",
                        })
                        cell_num += 1
                        continue
                    found_tc = False
                    for sc_child in sc:
                        if sc_child.tag == f"{{{W}}}tc":
                            cell_items.append(
                                (sc_child, f"{row_loc}/cell:{cell_num}/sdt")
                            )
                            found_tc = True
                            cell_num += 1
                        elif sc_child.tag in _SDT_STRUCTURAL_TAGS:
                            continue
                        else:
                            uncovered.append({
                                "tag": sc_child.tag,
                                "location": f"{row_loc}/cellwrapper:{cell_num}/sdt",
                                "note": "unsupported visible content inside "
                                        "sdt table-cell wrapper",
                            })
                    if not found_tc:
                        uncovered.append({
                            "tag": tag,
                            "location": f"{row_loc}/cellwrapper:{cell_num}",
                            "note": "sdt table-cell wrapper contained no w:tc",
                        })
                elif tag in _ROW_STRUCTURAL_TAGS:
                    continue
                else:
                    uncovered.append({
                        "tag": tag,
                        "location": f"{row_loc}/rowchild:{cell_num}",
                        "note": "unsupported visible container at table row level",
                    })

            cells_out = []
            for tc, cell_loc in cell_items:
                cell_text_parts = _collect_cell_content(
                    tc, cell_loc, depth=0
                )
                cells_out.append("".join(cell_text_parts))
            rows_out.append(cells_out)

        table_entry["rows"] = rows_out
        return table_idx

    def _collect_cell_content(tc_elem, cell_loc, depth):
        """Collect text of a cell's paragraphs (direct or inside legal sdt
        wrappers). Nested tables are collected separately (not into the cell
        text) but their presence is honored. Returns list of paragraph texts.

        depth counts wrapper layers entered since the cell itself.
        """
        parts = []

        def _walk(children, loc_prefix, d):
            for idx, child in enumerate(children):
                tag = child.tag
                loc = f"{loc_prefix}:{idx}" if d > 0 else None
                if tag == f"{{{W}}}p":
                    _collect_paragraph(child, f"{cell_loc}/para")
                    parts.append(paragraph_text(child))
                elif tag == f"{{{W}}}tbl":
                    _collect_table(child, f"{cell_loc}/table")
                elif tag == f"{{{W}}}sdt":
                    if d + 1 > MAX_WRAPPER_DEPTH:
                        uncovered.append({
                            "tag": tag,
                            "location": f"{cell_loc}/wrapperdepth:{d + 1}",
                            "note": (
                                "wrapper nesting exceeds supported bound "
                                f"({MAX_WRAPPER_DEPTH}); content NOT extracted"
                            ),
                        })
                        continue
                    sc = child.find(f"{{{W}}}sdtContent")
                    if sc is None:
                        uncovered.append({
                            "tag": tag,
                            "location": f"{cell_loc}/wrapper:{d}",
                            "note": "sdt in cell has no sdtContent",
                        })
                        continue
                    _walk(list(sc), f"{cell_loc}/sdt", d + 1)
                elif tag in _CELL_STRUCTURAL_TAGS:
                    continue
                else:
                    uncovered.append({
                        "tag": tag,
                        "location": f"{cell_loc}/child:{idx}",
                        "note": "unsupported visible container in table cell",
                    })

        _walk(list(tc_elem), cell_loc, depth)
        return parts

    def _walk_body_children(children, loc_prefix, sdt_depth):
        """Unified body-level traversal: paragraphs, tables, legal sdt
        wrappers (recursive, bounded). Called for w:body children and for
        sdtContent children at any wrapper depth."""
        for idx, child in enumerate(children):
            tag = child.tag
            if sdt_depth == 0:
                loc = f"body:{idx}"
            else:
                loc = f"{loc_prefix}:{idx}"
            if tag == f"{{{W}}}p":
                _collect_paragraph(child, loc)
            elif tag == f"{{{W}}}tbl":
                _collect_table(child, loc)
            elif tag == f"{{{W}}}sdt":
                if sdt_depth + 1 > MAX_WRAPPER_DEPTH:
                    uncovered.append({
                        "tag": tag,
                        "location": loc,
                        "note": (
                            "wrapper nesting exceeds supported bound "
                            f"({MAX_WRAPPER_DEPTH}); content NOT extracted"
                        ),
                    })
                    continue
                sc = child.find(f"{{{W}}}sdtContent")
                if sc is None:
                    uncovered.append({
                        "tag": tag,
                        "location": loc,
                        "note": "sdt without sdtContent",
                    })
                    continue
                _walk_body_children(
                    list(sc), f"{loc}/sdt", sdt_depth + 1
                )
            elif tag == f"{{{W}}}sectPr":
                continue  # section properties: structural, not visible
            else:
                uncovered.append({"tag": tag, "location": loc})

    _walk_body_children(list(body_elem), "", 0)

    return paragraphs, tables, uncovered


# ---------------------------------------------------------------------------
# Relationships parsing (V03 fix: duplicate Id detection)
# ---------------------------------------------------------------------------
def parse_relationships(rels_xml: bytes):
    """Parse word/_rels/document.xml.rels.

    Returns (internal_map, external_list):
      internal_map: {rId: target} for TargetMode != External
      external_list: [{id, type, target}] for TargetMode=External (RECORDED ONLY)

    Duplicate relationship Ids are rejected (ambiguous reference target).
    """
    root = safe_parse_xml(rels_xml, "word/_rels/document.xml.rels")
    internal = {}
    external = []
    seen_ids = set()
    for rel in root.iter(f"{{{NS['rel']}}}Relationship"):
        rid = rel.get("Id", "")
        rtype = rel.get("Type", "")
        target = rel.get("Target", "")
        mode = rel.get("TargetMode", "")
        if rid in seen_ids:
            raise SecurityViolation(
                f"Duplicate relationship Id {rid!r} in document.xml.rels; "
                f"ambiguous reference target rejected"
            )
        seen_ids.add(rid)
        if mode == "External":
            external.append({"id": rid, "type": rtype, "target": target})
        else:
            internal[rid] = target
    return internal, external


# ---------------------------------------------------------------------------
# Package-internal URI normalization (V03 fix)
# ---------------------------------------------------------------------------
def normalize_package_uri(target: str) -> str:
    """Normalize a relative package-internal URI target to canonical part name.

    Rules:
      - Resolve relative to word/ (document part base).
      - Collapse ./ segments via posixpath.normpath.
      - Reject any result that escapes the package root (..) or is absolute.
      - Preserve the ORIGINAL target in the manifest for traceability.
    Returns normalized part name or raises SecurityViolation.
    """
    # Strip fragment/query if present (rare but possible)
    clean = target.split("#")[0].split("?")[0]
    # Reject absolute and backslash paths
    if clean.startswith("/") or "\\" in clean:
        raise SecurityViolation(
            f"Relationship target {target!r} is absolute or contains "
            f"backslash; rejected"
        )
    resolved = posixpath.normpath(posixpath.join("word", clean))
    if resolved.startswith("../") or resolved == ".." or resolved.startswith("/"):
        raise SecurityViolation(
            f"Relationship target {target!r} escapes package root; rejected"
        )
    return resolved


# ---------------------------------------------------------------------------
# Image probing
# ---------------------------------------------------------------------------
def image_extension_from_target(target: str) -> str:
    ext = posixpath.splitext(target)[1].lower()
    allowed = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".tif", ".emf", ".wmf", ".webp", ".svg"}
    return ext if ext in allowed else ".bin"


def probe_image_dimensions(data: bytes):
    """Best-effort (width, height) probe for PNG/GIF/BMP/JPEG. Never raises."""
    if data[:8] == b"\x89PNG\r\n\x1a\n" and data[12:16] == b"IHDR" and len(data) >= 24:
        w, h = struct.unpack(">II", data[16:24])
        return (w, h)
    if data[:6] in (b"GIF87a", b"GIF89a") and len(data) >= 10:
        w, h = struct.unpack("<HH", data[6:10])
        return (w, h)
    if data[:2] == b"BM" and len(data) >= 26:
        w, h = struct.unpack("<ii", data[18:26])
        return (abs(w), abs(h))
    if data[:2] == b"\xff\xd8":
        i = 2
        n = len(data)
        while i + 9 <= n:
            if data[i] != 0xFF:
                i += 1
                continue
            marker = data[i + 1]
            if marker == 0xFF:
                i += 1
                continue
            if marker in (0xC0, 0xC1, 0xC2, 0xC3):
                h, w = struct.unpack(">HH", data[i + 5:i + 9])
                return (w, h)
            if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
                i += 2
                continue
            if i + 4 > n:
                break
            (seg_len,) = struct.unpack(">H", data[i + 2:i + 4])
            i += 2 + seg_len
    return None


def readability_status(dims, min_side: int):
    """V07 fix: 'must be greater than' semantics.

    Returns 'too_small' when a probeable dimension is NOT GREATER than
    min_side (i.e., <= min_side is rejected). Default min_side=10 means
    the minimum acceptable dimension is 11, matching the confirmed model
    boundary (width AND height must be > 10).
    Returns 'unknown_dimensions' when format cannot be probed (never a pass).
    Returns None when the image passes the size gate (still requires Read).
    """
    if dims is None:
        return "unknown_dimensions"
    w, h = dims
    if w <= min_side or h <= min_side:
        return "too_small"
    return None


# ---------------------------------------------------------------------------
# Output safety (H01 fix; doc alignment fix-round-2 non-blocking obs. 1 & 2)
# ---------------------------------------------------------------------------
def _canonical(path: str) -> str:
    return os.path.realpath(path)


def _file_identity(path: str):
    """Return (device, inode) for an existing path, or None if absent."""
    try:
        st = os.lstat(path)
        return (st.st_dev, st.st_ino)
    except OSError:
        return None


def validate_output_safety(input_path: str, out_dir: str, json_path: str,
                           image_names: list):
    """Pre-validate all output paths BEFORE any write.

    Policy (documented honestly — matches actual behavior):
      - The realpath of each caller-supplied path is accepted as the write
        target. A symlinked PARENT directory component is NOT refused; this
        script does not promise parent-link rejection (the trusted caller
        chooses the path). The output directory ITSELF being a symlink is
        refused.
      - A non-empty output directory is accepted; only NAME COLLISIONS with
        the files this run would write are refused. Unrelated pre-existing
        files are never touched, deleted, or overwritten.

    Checks:
      1. Output directory itself is not a symlink.
      2. JSON path does not collide with input file (canonical path AND
         device+inode).
      3. No image path collides with JSON path or input file.
      4. No image/JSON target path already exists (file, symlink, anything).

    Raises OutputConflict on any violation. This runs BEFORE extraction
    writes anything, and each write still uses O_EXCL as a second barrier
    against TOCTOU.
    """
    real_input = _canonical(input_path)
    real_json = _canonical(json_path)

    # JSON must not be the input file
    if real_json == real_input:
        raise OutputConflict(
            f"JSON output path {json_path!r} resolves to the same file as "
            f"input {input_path!r}; refusing to overwrite input"
        )
    # inode-level check (handles hardlinks with different names)
    input_id = _file_identity(input_path)
    json_id = _file_identity(json_path)
    if input_id and json_id and input_id == json_id:
        raise OutputConflict(
            f"JSON output path {json_path!r} is the same inode as input "
            f"{input_path!r}; refusing to overwrite input"
        )

    # The output directory itself must not be a symlink (the leaf target is
    # caller-chosen and accepted by realpath; parent components are not
    # promised to be link-free — see docstring policy).
    if os.path.islink(out_dir):
        raise OutputConflict(
            f"Output directory {out_dir!r} is a symlink; refusing to write "
            f"through a symlinked output directory"
        )

    real_out_dir = _canonical(out_dir)

    # No image may collide with input or JSON
    for img_name in image_names:
        img_path = os.path.join(real_out_dir, img_name)
        real_img = _canonical(img_path)
        if real_img == real_input:
            raise OutputConflict(
                f"Image output {img_name!r} resolves to input file; refused"
            )
        if real_img == real_json:
            raise OutputConflict(
                f"Image output {img_name!r} collides with JSON path; refused"
            )
        # Must not already exist
        if os.path.lexists(img_path):
            raise OutputConflict(
                f"Output path already exists (file/symlink): {img_path!r}; "
                f"refusing to overwrite. Use a fresh output directory."
            )
        img_id = _file_identity(img_path)
        if img_id and input_id and img_id == input_id:
            raise OutputConflict(
                f"Image output {img_name!r} is same inode as input; refused"
            )

    # JSON must not already exist
    if os.path.lexists(json_path):
        raise OutputConflict(
            f"JSON output path already exists: {json_path!r}; refusing to "
            f"overwrite. Use a fresh output directory."
        )


def exclusive_write_bytes(path: str, data: bytes) -> None:
    """Write bytes with O_CREAT|O_EXCL — fails if path already exists.
    This is the TOCTOU-safe second barrier (validate_output_safety is first)."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    try:
        os.write(fd, data)
    finally:
        os.close(fd)


def exclusive_write_text(path: str, text: str) -> None:
    exclusive_write_bytes(path, text.encode("utf-8"))


# ---------------------------------------------------------------------------
# Main extraction logic
# ---------------------------------------------------------------------------
def extract_docx(
    input_path: str,
    out_dir: str,
    json_path: str,
    max_total_bytes: int,
    max_entry_bytes: int,
    max_entries: int,
    max_image_bytes: int,
    strict: bool,
    min_image_side: int = 10,
) -> dict:
    # Validate min_image_side parameter
    if min_image_side < 1:
        raise ValueError(
            f"--min-image-side must be >= 1 (got {min_image_side}); "
            f"zero or negative values would disable the size gate"
        )

    result = {
        "input_file": os.path.basename(input_path),
        "input_sha256": None,
        "status": "complete",
        "position_note": (
            "All positions (paragraph_index, table_index, location paths) are "
            "LOGICAL document positions, NOT Word page numbers. DOCX has no "
            "fixed pagination. cell_index is a logical sequential index among "
            "a row's direct cells, NOT the visual column number."
        ),
        "security": {"rejected_entries": [], "external_relationships": []},
        "paragraphs": [],
        "tables": [],
        "images": [],
        "uncovered_containers": [],
        "uncovered_parts": [],
    }

    # Hash the input file (read-only)
    h = hashlib.sha256()
    with open(input_path, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            h.update(chunk)
    result["input_sha256"] = h.hexdigest()

    # Open ZIP read-only
    try:
        zf = zipfile.ZipFile(input_path, mode="r")
    except zipfile.BadZipFile as exc:
        raise ExtractionError(f"Not a valid ZIP/DOCX file: {exc}") from exc

    with zf:
        # Safety validation (returns approved ZipInfo map)
        approved, rejected = validate_zip_safety(
            zf, max_total_bytes, max_entry_bytes, max_entries, strict
        )
        result["security"]["rejected_entries"] = rejected

        # Record uncovered story parts (headers/footers/etc.)
        for name in approved:
            if any(name.startswith(p) for p in KNOWN_UNCOVERED_PART_PREFIXES):
                result["uncovered_parts"].append({
                    "part": name,
                    "note": "present in package but not extracted by this tool",
                })

        # Read document.xml — REQUIRED part; if rejected, fail entirely
        doc_part = "word/document.xml"
        if doc_part not in approved:
            if any(r["name"] == doc_part or posixpath.normpath(r["name"]) == doc_part
                   for r in rejected):
                raise SecurityViolation(
                    f"Required part {doc_part!r} was rejected by safety "
                    f"validation; extraction fails entirely"
                )
            raise ExtractionError(
                f"Missing {doc_part} — not a valid DOCX structure"
            )
        doc_bytes = safe_read_info(
            zf, approved[doc_part], max_entry_bytes, "document.xml"
        )
        doc_root = safe_parse_xml(doc_bytes, doc_part)

        # Parse relationships — REQUIRED if referenced
        rels_part = "word/_rels/document.xml.rels"
        internal_rels = {}
        external_rels = []
        if rels_part in approved:
            rels_bytes = safe_read_info(
                zf, approved[rels_part], max_entry_bytes, rels_part
            )
            internal_rels, external_rels = parse_relationships(rels_bytes)
            result["security"]["external_relationships"] = external_rels
        elif any(posixpath.normpath(r["name"]) == rels_part for r in rejected):
            raise SecurityViolation(
                f"Required relationships part {rels_part!r} was rejected; "
                f"extraction fails entirely"
            )

        # Walk body structure (V04/V05 + fix-round-2 bounded wrapper traversal)
        body = doc_root.find(f"{{{W}}}body")
        if body is None:
            raise ExtractionError("No w:body found in document.xml")

        paragraphs, tables, uncovered_containers = walk_document(body)
        result["paragraphs"] = paragraphs
        result["tables"] = tables
        result["uncovered_containers"] = uncovered_containers

        # ── Image reference manifest (V06 + fix-round-2 V06): built from ALL
        #    actual body references, embed AND link kinds alike. ──
        referenced_images = []  # [(rid_or_None, kind, location, paragraph_index)]
        for p in paragraphs:
            for ref in p.get("drawing_references", []):
                referenced_images.append(
                    (ref["rid"], ref["kind"], p["location"], p["paragraph_index"])
                )

        image_budget_used = 0
        image_count = 0
        planned_outputs = []
        manifest_entries = []

        for rid, kind, location, para_idx in referenced_images:
            entry = {
                "relationship_id": rid,
                "reference_kind": kind,
                "location": location,
                "paragraph_index": para_idx,
                "status": None,
            }

            # Reference with no relationship Id (blip without embed/link):
            # denominator is not shrunk — record as unsupported.
            if rid is None:
                entry["status"] = "unsupported"
                entry["note"] = (
                    "a:blip carries neither r:embed nor r:link; reference "
                    "cannot be resolved to any relationship"
                )
                manifest_entries.append(entry)
                continue

            # External relationship (r:link targets are typically External):
            # recorded, NEVER fetched, no network request made.
            ext_match = [e for e in external_rels if e["id"] == rid]
            if ext_match:
                entry["status"] = "external-not-fetched"
                entry["target"] = ext_match[0].get("target")
                entry["note"] = (
                    "External relationship; recorded but never fetched. "
                    "No network request is made by this tool."
                )
                manifest_entries.append(entry)
                continue

            if rid not in internal_rels:
                entry["status"] = "unsupported"
                entry["note"] = "rId not found in document relationships"
                manifest_entries.append(entry)
                continue

            target = internal_rels[rid]
            try:
                resolved = normalize_package_uri(target)
            except SecurityViolation as e:
                entry["status"] = "rejected"
                entry["note"] = str(e)
                manifest_entries.append(entry)
                continue

            entry["source_path_in_docx"] = resolved
            entry["original_target"] = target

            if resolved not in approved:
                rej_match = [r for r in rejected
                             if posixpath.normpath(r["name"]) == resolved]
                if rej_match:
                    entry["status"] = "rejected"
                    entry["note"] = f"ZIP entry rejected: {rej_match[0]['reason']}"
                else:
                    entry["status"] = "missing-part"
                    entry["note"] = "Relationship target does not exist in package"
                manifest_entries.append(entry)
                continue

            info = approved[resolved]
            # Budget check BEFORE reading
            if info.file_size > max_image_bytes - image_budget_used:
                entry["status"] = "budget-exceeded"
                entry["note"] = (
                    f"Image size {info.file_size} exceeds remaining budget "
                    f"{max_image_bytes - image_budget_used}"
                )
                manifest_entries.append(entry)
                continue

            # Will be resolved — plan the output
            ext = image_extension_from_target(resolved)
            safe_name = f"image_{image_count:03d}{ext}"
            entry["extracted_to"] = safe_name
            entry["status"] = "resolved"
            entry["_info"] = info
            entry["_resolved"] = resolved
            image_count += 1
            planned_outputs.append(safe_name)
            manifest_entries.append(entry)

        # Validate all output paths (H01) — before any disk write
        os.makedirs(out_dir, exist_ok=True)
        validate_output_safety(input_path, out_dir, json_path, planned_outputs)

        # Second pass: actually read and write resolved images
        for entry in manifest_entries:
            if entry["status"] != "resolved":
                continue
            info = entry.pop("_info")
            resolved = entry.pop("_resolved")
            try:
                img_data = safe_read_info(
                    zf, info, max_entry_bytes, f"image {resolved}"
                )
            except SecurityViolation as e:
                entry["status"] = "rejected"
                entry["note"] = str(e)
                entry.pop("extracted_to", None)
                continue
            image_budget_used += len(img_data)
            if image_budget_used > max_image_bytes:
                entry["status"] = "budget-exceeded"
                entry["note"] = "Total image budget exceeded during extraction"
                entry.pop("extracted_to", None)
                continue

            dims = probe_image_dimensions(img_data)
            readability = readability_status(dims, min_image_side)

            out_path = os.path.join(out_dir, entry["extracted_to"])
            try:
                exclusive_write_bytes(out_path, img_data)
            except FileExistsError:
                raise OutputConflict(
                    f"Output path appeared during extraction (TOCTOU): "
                    f"{out_path!r}; aborting"
                )

            entry.update({
                "size_bytes": len(img_data),
                "sha256": hashlib.sha256(img_data).hexdigest(),
                "dimensions": list(dims) if dims else None,
                "readability": readability,
                "position_note": "logical position, not page number",
            })

        result["images"] = manifest_entries

        # ── Status determination by TRUE coverage (fix-round-2) ──
        # complete — every image reference resolved AND no uncovered
        #            containers in the body.
        # partial  — some references unresolved (external/missing/budget),
        #            or uncovered containers present (content NOT extracted).
        # rejected — references exist, NONE resolved, no external-not-fetched,
        #            and no uncovered containers (fix-round-1 semantics for
        #            purely-hard-failure documents preserved).
        statuses = [e["status"] for e in manifest_entries]
        n_resolved = sum(1 for s in statuses if s == "resolved")
        n_external = sum(1 for s in statuses if s == "external-not-fetched")
        has_uncovered = bool(uncovered_containers)

        if has_uncovered:
            result["status"] = "partial"
        elif not manifest_entries:
            result["status"] = "complete"
        elif n_resolved == len(manifest_entries):
            result["status"] = "complete"
        elif n_resolved == 0 and n_external == 0:
            result["status"] = "rejected"
        else:
            result["status"] = "partial"

    # Write JSON output (exclusive creation)
    json_dir = os.path.dirname(json_path)
    if json_dir:
        os.makedirs(json_dir, exist_ok=True)
    try:
        exclusive_write_text(
            json_path, json.dumps(result, ensure_ascii=False, indent=2)
        )
    except FileExistsError:
        raise OutputConflict(
            f"JSON output path appeared during extraction (TOCTOU): {json_path!r}"
        )

    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Safe DOCX text/table/image extraction (stdlib only)."
    )
    parser.add_argument("input", help="Path to the .docx file (read-only)")
    parser.add_argument(
        "--out-dir", required=True, help="Directory for extracted images"
    )
    parser.add_argument(
        "--json",
        default=None,
        help="Path for JSON result (default: OUT_DIR/extraction.json)",
    )
    parser.add_argument(
        "--max-total-bytes", type=int, default=200_000_000,
        help="Total uncompressed ZIP size limit (default 200MB)",
    )
    parser.add_argument(
        "--max-entry-bytes", type=int, default=50_000_000,
        help="Single entry uncompressed size limit (default 50MB)",
    )
    parser.add_argument(
        "--max-entries", type=int, default=2000,
        help="Maximum ZIP entry count (default 2000)",
    )
    parser.add_argument(
        "--max-image-bytes", type=int, default=100_000_000,
        help="Total image extraction budget (default 100MB)",
    )
    parser.add_argument(
        "--strict", action="store_true",
        help="Abort on ANY dangerous entry instead of skipping it",
    )
    parser.add_argument(
        "--min-image-side", type=int, default=10,
        help=(
            "Size gate with 'must be GREATER THAN' semantics: an image whose "
            "width OR height is <= this value is flagged readability=too_small "
            "and must be treated as an INCOMPLETE item (never sent to vision "
            "models, never counted as visually inspected). Default 10 "
            "(minimum acceptable dimension is therefore 11, matching the "
            "confirmed model boundary width/height>10). Must be >= 1."
        ),
    )
    args = parser.parse_args()

    if not os.path.isfile(args.input):
        print(f"ERROR: input file not found: {args.input}", file=sys.stderr)
        sys.exit(64)

    json_path = args.json or os.path.join(args.out_dir, "extraction.json")

    try:
        result = extract_docx(
            input_path=args.input,
            out_dir=args.out_dir,
            json_path=json_path,
            max_total_bytes=args.max_total_bytes,
            max_entry_bytes=args.max_entry_bytes,
            max_entries=args.max_entries,
            max_image_bytes=args.max_image_bytes,
            strict=args.strict,
            min_image_side=args.min_image_side,
        )
    except SecurityViolation as exc:
        print(f"SECURITY REJECTED: {exc}", file=sys.stderr)
        sys.exit(3)
    except ExtractionError as exc:
        print(f"EXTRACTION ERROR: {exc}", file=sys.stderr)
        sys.exit(2)
    except OutputConflict as exc:
        print(f"OUTPUT CONFLICT: {exc}", file=sys.stderr)
        sys.exit(5)
    except BudgetExceeded as exc:
        print(f"BUDGET EXCEEDED: {exc}", file=sys.stderr)
        sys.exit(5)
    except ValueError as exc:
        print(f"PARAMETER ERROR: {exc}", file=sys.stderr)
        sys.exit(64)
    except OSError as exc:
        print(f"IO ERROR: {exc}", file=sys.stderr)
        sys.exit(5)

    status = result["status"]
    summary = {
        "status": status,
        "paragraphs": len(result["paragraphs"]),
        "tables": len(result["tables"]),
        "images_total": len(result["images"]),
        "images_resolved": sum(
            1 for i in result["images"] if i["status"] == "resolved"
        ),
        "images_unresolved": [
            {"rid": i["relationship_id"], "kind": i.get("reference_kind"),
             "status": i["status"]}
            for i in result["images"] if i["status"] != "resolved"
        ],
        "rejected_entries": result["security"]["rejected_entries"],
        "external_relationships_recorded": len(
            result["security"]["external_relationships"]
        ),
        "uncovered_containers": result["uncovered_containers"],
        "uncovered_parts": result["uncovered_parts"],
        "json_output": json_path,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    # Exit code semantics (unified with documentation):
    #   0 = complete (all referenced images resolved or none referenced,
    #       and no uncovered containers/parts)
    #   5 = any image reference hit the budget limit (matches documented
    #       "budget exceeded = 5"), regardless of other partial results
    #   1 = partial/rejected coverage without budget involvement (JSON was
    #       still written; incomplete items are listed, never claimed done)
    if any(i["status"] == "budget-exceeded" for i in result["images"]):
        sys.exit(5)
    if status == "complete":
        sys.exit(0)
    sys.exit(1)


if __name__ == "__main__":
    main()
