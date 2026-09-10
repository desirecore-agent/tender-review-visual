# Raster geometry dependency

This optional helper requires Python >= 3.10 and exactly Pillow 12.3.0, the current PyPI release verified on 2026-09-05. It does not add dependencies to the existing standard-library DOCX helper. Python 3.9 is insufficient for this optional capability. Use a maintained stable interpreter supported by the supplied wheel; no matching wheel means unavailable, not a source-build fallback.

Create a private virtual environment in this Agent's own workspace using its configured supported Python runtime. From the installed skill directory, run that environment's interpreter with:

```text
-m pip install --index-url https://pypi.org/simple --only-binary=:all: --require-hashes -r requirements-geometry.lock
```

This explicitly authorized dependency installation accesses official package infrastructure; measurement itself is offline. The lock contains 86 non-yanked wheel SHA-256 hashes from the official 12.3.0 PyPI JSON, no source distributions and no transitive Python packages. Unsupported interpreter/platform combinations fail installation. Check installed Pillow version, then run a non-sensitive local image smoke measurement before claiming readiness. Do not publish the environment or copy credentials/runtime paths into the skill.

Pillow's license expression is MIT-CMU. Preserve its supplied license notices. Binary wheels may bundle separately licensed image libraries; retain wheel license files and the embedded SBOM. `PILLOW-LICENSE.txt` preserves the upstream Pillow license; it is not a replacement for wheel notices. Review dependency security advisories before a future upgrade and regenerate the exact lock, review and smoke test together.

The official 12.3.0 notes include fixes for PDF decompression, EPS loops, JPEG2000 resource use, several memory-access problems and Windows viewer command injection. This helper admits only PNG/JPEG and never calls viewers, OCR, image display, PDF parsing or network functions. Version pinning and size limits do not guarantee an absence of future decoder vulnerabilities. The caller must impose the documented execution timeout.

Sources checked 2026-09-05: [PyPI release metadata](https://pypi.org/pypi/Pillow/12.3.0/json), [release notes](https://pillow.readthedocs.io/en/stable/releasenotes/12.3.0.html), [license](https://pillow.readthedocs.io/en/stable/about.html#license). The private provenance file and verification environment are audit-only, excluded from publication.

## Runtime and private workspace

First inspect Managed runtimes in the current turn's `<env>` and use an actually executable Python path reporting version >=3.10; run its version command. If absent, install Python (Hatch) through the real Runtime Environments GUI, wait for success, then start a new turn to refresh environment facts. There is no Agent tool named Runtime for installation; do not invent one. Preserve the command, exit code and real error on installation failure and mark the capability unready. Never borrow a Codex/developer-tree or another Agent's interpreter.

Only this Agent's private workspace registered in current context may hold its virtual environment, pip cache, temporary files, page images and results. Do not put them in the published source root or skill directory, or use unregistered global temporary directories. Create a fresh private directory and explicitly set TEMP/TMP/TMPDIR and pip cache there; run the actual interpreter with `-m venv`, then install the lock using the new environment's interpreter. Verify and correctly quote paths, never guess a home. Record real exit codes/errors for preparation, installation, export and measurement. Retain initial failures after a successful retry rather than claiming every command succeeded.
