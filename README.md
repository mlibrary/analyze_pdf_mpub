# fulcrum-cli — PDF Analyzer

A command-line tool that analyzes PDF files for accessibility and outputs structured JSON. It checks whether PDFs are tagged, navigable, and conformant with accessibility standards (PDF/UA, WCAG).

---

## Table of Contents

- [Overview](#overview)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Setting up veraPDF](#setting-up-verapdf)
- [Running the tool](#running-the-tool)
- [Output format](#output-format)
- [Troubleshooting](#troubleshooting)

---

## Overview

For each PDF it processes, the tool produces a `_fulcrum.json` file containing:

- **`document_type`** — whether the PDF has native embedded text, an OCR text layer, or is an unreadable image scan
- **`metadata`** — PDF version, author, creator tool, title, encryption status, font flags
- **`conformance`** — pass/fail results (with rule counts) for PDF/A-1b, PDF/UA-1, PDF/UA-2, WCAG 2.1, and WCAG 2.2 via veraPDF
- **`bookmarks`** — the table of contents/navigation outline
- **`page_info`** — character count per page (zero = image-only page)
- **`marked_content`** — the full accessibility tag tree (structure elements and alt text)

See [`JSON_FIELD_REFERENCE.md`](./JSON_FIELD_REFERENCE.md) for the complete field-by-field reference.

---

## Prerequisites

### 1. Python 3.9 or later

Check your version:

```bash
python3 --version
```

If you see `Python 3.9.x` or higher, you're good. 

### 2. veraPDF

veraPDF is the external standards-validation engine. It handles all the PDF/UA and WCAG conformance checks. Download from [verapdf.org](https://verapdf.org/home/#downloads), get the **CLI installer** for your platform (macOS or Linux).

Run the installer. It will place veraPDF at a path like:

- **Mac:** `~/Applications/verapdf/verapdf`
- **Linux:** `/usr/local/bin/verapdf`

---

## Installation

**1. Clone or download this repository**, then navigate to the `fulcrum-cli` folder:

```bash
cd path/to/fulcrum-cli
```

**2. Create a virtual environment**:

```bash
python3 -m venv .venv
```

**3. Activate it:**

```bash
# macOS / Linux
source .venv/bin/activate
```

You'll see `(.venv)` appear at the start of your shell prompt. You'll need to run this activate command once per terminal session.

**4. Install Python dependencies:**

```bash
pip install -r requirements.txt
```

This installs two libraries:

| Library | Purpose |
|---|---|
| `pikepdf` | Reads PDF internals: structure tree, metadata, permissions, content streams |
| `PyMuPDF` | Extracts text per page, detects image coverage |

---

## Setting up veraPDF

The easiest setup is copying the veraPDF installation folder into the project. The structure looks like this:

```
fulcrum-cli/
  verapdf/          ← drop the veraPDF install folder here
    verapdf         ← the executable (no extension on Mac/Linux)
    profiles/       ← standard profiles directory
    ...
```
The tool will find it automatically from there. No configuration needed. If veraPDF isn't found, the tool still runs — it just skips the conformance block and marks all standards as `"not present"`.

> **If veraPDF is installed somewhere non-standard**, pass it explicitly:
> ```bash
> python3 run.py --input pdfs/ --output results/ --verapdf /path/to/verapdf
> ```

---

## Running the tool

Make sure your virtual environment is active (`source .venv/bin/activate`).

### Processing a single PDF

```bash
python3 run.py --input path/to/file.pdf --output results/
```

Output: `results/file_fulcrum.json`

### Processing a folder of PDFs

```bash
python3 run.py --input path/to/pdf-folder/ --output results/
```

This processes every `.pdf` file in the folder and writes one `_fulcrum.json` per file into the `results/` directory.

Example with an explicit veraPDF path:

```bash
python3 run.py --input data/my-books/ --output results/my-books/ --verapdf ~/Applications/verapdf/verapdf
```

### All flags

| Flag | Required | Description |
|---|---|---|
| `--input` / `-i` | Yes | Path to a single PDF or a folder of PDFs |
| `--output` / `-o` | Yes | Directory to write JSON output files into |
| `--verapdf` | No | Explicit path to the veraPDF executable |

---

## Output format

Each PDF produces one JSON file named `{pdf-filename}_fulcrum.json`. Here is a minimal example:

```json
{
  "document_type": "native",
  "metadata": {
    "Content-Type": "application/pdf",
    "pdf_version": "1.6",
    "dc:title": "Accessible Book Title",
    "dc:creator": "Jane Smith",
    "pdf:docinfo:creator_tool": "Adobe InDesign",
    "is_tagged": "true",
    "has_xmp_metadata": "true",
    "is_encrypted": "false",
    "has_non_embedded_fonts": "false",
    "can_print": "true",
    "unreadable_chars_pct": "0.0",
    "ocr_page_count": "312"
  },
  "conformance": {
    "PDFA_1_B": { "status": "fail",          "passed_rules": 8,    "failed_rules": 3,    "total_rules": 11 },
    "PDFUA_1":  { "status": "fail",          "passed_rules": 5,    "failed_rules": 6,    "total_rules": 11 },
    "PDFUA_2":  { "status": "not available", "passed_rules": null, "failed_rules": null, "total_rules": null },
    "WCAG_2_2": { "status": "fail",          "passed_rules": 10,   "failed_rules": 6,    "total_rules": 16 }
  },
  "bookmarks": {
    "items": ["Chapter 1", "  Section 1.1", "  Section 1.2", "Chapter 2"]
  },
  "page_info": [
    { "char_count": 1842 },
    { "char_count": 2103 },
    { "char_count": 0 }
  ],
  "marked_content": [
    { "type": "Document", "alttext": null },
    { "type": "H1",       "alttext": null },
    { "type": "P",        "alttext": null },
    { "type": "Figure",   "alttext": "A bar chart showing annual revenue" }
  ]
}
```

For a complete description of every field, see [`JSON_FIELD_REFERENCE.md`](./JSON_FIELD_REFERENCE.md).
