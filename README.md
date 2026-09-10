# Tender Review Visual Inspector

This Agent is a specialist member of the Tender Review team (`biao-shu-lian-he-shen-cha`). It receives delegations from `tender-review-lead` and returns located evidence and incomplete items, without making final team decisions. Team source/version follow the actual installation record.

## Capabilities and readiness

| Capability | Actual requirement |
|---|---|
| DOCX extraction | Python 3.9+ standard-library helper; body, tables and referenced images only, not full Office rendering |
| PDF text and page images | ToolCatalog-confirmed Read parameters, vision model and actual image receipts; retain per-page coverage |
| Authorized media export | ExportMedia actually available with media_ref/file_path; exclusive writes to an approved private workspace |
| Local pixel geometry | Current-turn managed Python >=3.10, locked Pillow 12.3.0 and an actually viewed, identity-matched PNG/JPEG; successful execution does not confirm semantic interpretation |

Unknown installations must complete a real non-sensitive Read→ExportMedia→geometry smoke test before declaring this chain ready. Previous Read smoke tests do not establish availability of the new export tool. No minimum platform version is fixed here before full-chain verification, and support in all earlier releases is not promised.

## Use constraints

Retain source image/PDF identities and physical page numbers, actual tool receipts, measurement settings and incomplete reasons. Quantified conclusions about count, relative extents, rankings or tip geometry require actual pixel evidence mapped to visible semantic objects. Connected regions are not semantic objects; pixel length/area is not chart data. If old observations conflict with measurements, recheck the exact image and segmentation suitability; report unknown until resolved rather than silently choosing an answer.

No seal/certificate authenticity decisions, compliance or winning-bid guarantees, or declarations of team completion. DOCX headers, footers, comments, footnotes and OLE content remain outside the declared extraction coverage.

## Documentation

- [Complete skill](skills/tender-visual-extract/SKILL.md) / [中文](skills/tender-visual-extract/SKILL.zh-CN.md)
- [PDF and export chain](skills/tender-visual-extract/pdf-capability-check.md) / [中文](skills/tender-visual-extract/pdf-capability-check.zh-CN.md)
- [Runtime and dependencies](skills/tender-visual-extract/DEPENDENCIES.md) / [中文](skills/tender-visual-extract/DEPENDENCIES.zh-CN.md)

## Privacy and license

Geometry measurements execute locally offline; text/images processed by a user-selected cloud model still use that model's channel, so fully local processing cannot be promised. No unauthorized OCR, email or unfamiliar URL transmission. Runtime environments, caches, temporary pages and results belong only in the current registered private workspace, never published source or unregistered temporary locations.

Agent content uses [MIT](LICENSE). Pillow separately uses MIT-CMU; see [NOTICE](NOTICE) and [upstream license](skills/tender-visual-extract/PILLOW-LICENSE.txt). Retain installed wheel bundled-library licenses and SBOM.
