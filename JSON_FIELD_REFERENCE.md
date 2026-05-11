# PDF Accessibility JSON Field Reference

**Pipeline:** `analyze_pdf_fulcrum()` via pikepdf · PyMuPDF · veraPDF  
**Last updated:** April 2026

This document describes every field in the JSON output produced by the PDF accessibility pipeline. Each entry lists the field name, data type, and a plain-language description of what it captures. Fields are only present when the source PDF contains the relevant data (absent fields are omitted from the output object).

---

## Table of Contents

- [document\_type](#document_type)
- [conformance](#conformance)
- [marked\_content](#marked_content)
- [metadata](#metadata)
  - [Core document info](#core-document-info)
  - [Accessibility flags](#accessibility-flags)
  - [Text and Unicode quality](#text-and-unicode-quality)
  - [XMP timestamps and identifiers](#xmp-timestamps-and-identifiers)
- [bookmarks](#bookmarks)
- [page\_info](#page_info)

---

## document_type

**Type:** `string`

Classifies the PDF into one of three categories based on how its text content was produced. Determined using two signals: rendering mode 3 detection in the PDF content stream (the definitive OCR marker), and full-page image coverage ratio via PyMuPDF.

| Value | Meaning |
|---|---|
| `native` | PDF contains embedded, digitally-authored text. No scan indicators found. |
| `scanned_ocr` | PDF is a scanned image with an OCR text layer overlaid (rendering mode 3 detected, or full-page images with extractable text). |
| `scanned_unreadable` | PDF is a scanned image with no readable text layer. Pages are image-only. |

---

## conformance

**Type:** `object`

Whether the PDF meets formal accessibility and archival standards, as evaluated by veraPDF. Contains five sub-objects, one per standard checked.

Each sub-object has the following structure:

| Field | Type | Description |
|---|---|---|
| `level` | `string \| null` | The conformance level being tested. `"AA"` for WCAG 2.1 and WCAG 2.2 (both evaluated at Level AA). `null` for PDF/A-1b, PDF/UA-1, and PDF/UA-2, which have no A/AA distinction. |
| `status` | `string` | `"pass"`, `"fail"`, or `"not available"` (could not be evaluated). |
| `passed_rules` | `integer \| null` | Number of validation rules the PDF passed. `null` if the profile could not run. |
| `failed_rules` | `integer \| null` | Number of validation rules the PDF failed. `null` if the profile could not run. |
| `total_rules` | `integer \| null` | Total number of rules evaluated (`passed + failed`). `null` if the profile could not run. |
| `failed_rule_details` | `array \| null` | List of failed rules. Each entry has `clause` (section reference), `specification` (standard name), and `description` (explanation of what failed). `null` if no failures or profile did not run. |

### Standards checked

| Key | Standard | Description |
|---|---|---|
| `PDFA_1_B` | PDF/A-1b | ISO 19005-1 archival format compliance. Ensures the file is self-contained and renderable without external resources. |
| `PDFUA_1` | PDF/UA-1 | ISO 14289-1 universal accessibility compliance. The original PDF accessibility standard; widely supported by assistive technology. |
| `PDFUA_2` | PDF/UA-2 | ISO 14289-2 universal accessibility compliance. Newer standard based on PDF 2.0; stricter tagging requirements. |
| `WCAG_2_2` | WCAG 2.2 | Web Content Accessibility Guidelines 2.2 compliance, evaluated via veraPDF custom profile. |

**Example:**

```json
"conformance": {
  "PDFA_1_B": { "level": null, "status": "fail",          "passed_rules": 8,    "failed_rules": 3,    "total_rules": 11,   "failed_rule_details": [{ "clause": "6.1.3", "specification": "ISO 19005-1", "description": "Font not embedded" }] },
  "PDFUA_1":  { "level": null, "status": "fail",          "passed_rules": 5,    "failed_rules": 6,    "total_rules": 11,   "failed_rule_details": [{ "clause": "7.1", "specification": "ISO 14289-1", "description": "Document is not tagged" }] },
  "PDFUA_2":  { "level": null, "status": "not available", "passed_rules": null, "failed_rules": null, "total_rules": null, "failed_rule_details": null },
  "WCAG_2_2": { "level": "AA", "status": "fail",          "passed_rules": 12,   "failed_rules": 4,    "total_rules": 16,   "failed_rule_details": [{ "clause": "1.1.1", "specification": "WCAG2.2", "description": "Figure missing alternative text" }] }
}
```

---

## marked_content

**Type:** `array of object`

Tag tree elements extracted from the PDF structure tree (`StructTreeRoot`). Each element represents one node in the accessibility tag hierarchy. An **empty array** means the PDF is untagged and no structure tree exists.

| Field | Type | Description |
|---|---|---|
| `[].type` | `string` | Tag type of the structure element (e.g. `Document`, `Part`, `P`, `Span`, `Figure`, `Table`, `H1`–`H6`). |
| `[].alttext` | `string \| null` | Alternative text (`/Alt` attribute). `null` if not set. |

---

## metadata

**Type:** `object`

Document-level metadata extracted from the PDF info dictionary and XMP stream. Fields are present only when the source PDF contains them.

### Core document info

| Field | Type | Description |
|---|---|---|
| `Content-Type` | `string` | MIME type of the file. Always `"application/pdf"`. |
| `dc:title` | `string` | Document title from XMP Dublin Core metadata. |
| `dc:creator` | `string` | Author(s) from XMP Dublin Core metadata. |
| `pdf_version` | `string` | PDF specification version, e.g. `"1.6"`. |
| `producer_software` | `string` | Software used to generate the final PDF file (i.e., the tool that converted or exported the document into PDF format). Extracted from the XMP metadata stream. |
| `pdf:docinfo:title` | `string` | Document title from the older PDF info dictionary (may differ from `dc:title`). |
| `pdf:docinfo:creator` | `string` | Author from the PDF info dictionary. |
| `pdf:docinfo:creator_tool` | `string` | Software used to create the original document before it was converted into a PDF (e.g., "Adobe InDesign"). Extracted from the /Creator field in the PDF’s document info dictionary. |
| `pdf:docinfo:created` | `string` | Creation date from the PDF info dictionary (ISO 8601 format). |
| `pdf:docinfo:modified` | `string` | Last modified date from the PDF info dictionary (ISO 8601 format). |

### Accessibility flags

| Field | Type | Description |
|---|---|---|
| `is_tagged` | `string (bool)` | `"true"` if the PDF contains a structure/tag tree. The single most important accessibility indicator; splits tagged from untagged files. |
| `has_xmp_metadata` | `string (bool)` | `"true"` if the PDF contains an XMP metadata stream. |
| `has_xml_forms` | `string (bool)` | `"true"` if the PDF contains XFA (XML Forms Architecture) form data. |
| `is_portfolio` | `string (bool)` | `"true"` if the PDF is a portfolio or collection of embedded files. |
| `is_encrypted` | `string (bool)` | `"true"` if the PDF is password-protected or has restricted permissions. |
| `has_non_embedded_fonts` | `string (bool)` | `"true"` if any font is not embedded in the file (may cause rendering or reading failures on other systems). |
| `has_damaged_fonts` | `string (bool)` | `"true"` if a damaged or corrupt font was detected (may cause garbled text output). |
| `count_3d_annotations` | `string (int)` | Count of 3D annotations in the document. Typically `"0"`. |
| `can_print` | `string (bool)` | `"true"` if the document permissions allow printing. |
| `can_print_high_quality` | `string (bool)` | `"true"` if high-quality (faithful) printing is permitted. |

### Text and Unicode quality

| Field | Type | Description |
|---|---|---|
| `unreadable_chars_per_page` | `array of int` | Count of characters per page that cannot be mapped to Unicode (these characters are unreadable by screen readers). |
| `total_unreadable_chars` | `string (int)` | Total unmapped Unicode characters across the entire document. |
| `unreadable_chars_pct` | `string (float)` | Percentage of all characters that are unmapped. High values indicate serious text accessibility issues. |
| `ocr_page_count` | `string (int)` | Number of pages identified as containing OCR-processed text. |

### XMP timestamps and identifiers

These fields are technical document identifiers used for tracking and provenance. They are not used for accessibility scoring.

| Field | Type | Description |
|---|---|---|
| `xmp:MetadataDate` | `string` | Date XMP metadata was last updated (ISO 8601). |
| `xmpMM:DocumentID` | `string` | Unique document identifier from XMP (UUID format). |
| `xmpMM:InstanceID` | `string` | Unique instance identifier (changes each time the file is saved). |

---

## bookmarks

**Type:** `object`

The document's bookmark/navigation outline (table of contents structure). Populated from the PDF `/Outlines` dictionary.

| Field | Type | Description |
|---|---|---|
| `items` | `array of string` | Bookmark titles in order, indented with spaces to reflect nesting depth. An empty array means no bookmarks are present. |

---

## page_info

**Type:** `array of object`

One entry per page. Provides per-page text content metrics.

| Field | Type | Description |
|---|---|---|
| `[].char_count` | `integer` | Number of extractable text characters on this page. Zero means the page is image-only with no readable text. |