# PDF Accessibility JSON Field Reference

**Pipeline:** `analyze_pdf_fulcrum()` via pikepdf · PyMuPDF · veraPDF  
**Last updated:** November 2026

This document describes the fields in the JSON output produced by `run.py`. Some metadata fields are omitted when their source values are absent; other fields are always included or use `null` when unavailable.

---

## Table of Contents

- [document\_type](#document_type)
- [md5](#md5)
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

**Type:** `object`

The output is the complete result from the content-stream classifier, not just the classification label. The `document_type` member contains one of these values:

| Value | Meaning |
|---|---|
| `native` | Visible text was found and the classifier did not identify a strong OCR signal. |
| `scanned_ocr` | The classifier identified an OCR text layer using invisible text operators. |
| `scanned_unreadable` | No visible text or OCR text operators were found in the sampled content. |

The classifier inspects up to 10 pages from the middle of the PDF. It classifies as OCR when at least 75% of sampled text-rendering-mode (`Tr`) operators use mode 3, or when some mode-3 operators are present but no visible text is found.

| Member | Type | Description |
|---|---|---|
| `document_type.document_type` | `string` | One of the three classification values above. |
| `document_type.render_mode_3_detected` | `boolean` | `true` when the mode-3 operator ratio reaches the 0.75 threshold. |
| `document_type.tr3_ratio` | `number` | Fraction of sampled `Tr` operators that use mode 3. |
| `document_type.tr3_ops` | `integer` | Number of sampled mode-3 `Tr` operators. |
| `document_type.total_tr_ops` | `integer` | Number of sampled `Tr` operators. |
| `document_type.visible_chars` | `integer` | Number of characters found in text-showing operators outside mode 3. |
| `document_type.classification_note` | `string`, optional | Explanation for the low-ratio OCR fallback; omitted otherwise. |
| `document_type.error` | `string`, optional | Content-stream parsing error, when one occurs. |
| `document_type.method` | `string` | Classifier implementation identifier; currently `"pikepdf_content_stream"`. |

---

## md5

**Type:** `string`

Lowercase hexadecimal MD5 digest of the input PDF bytes.

---

## conformance

**Type:** `object`

Whether the PDF meets formal accessibility and archival standards, as evaluated by veraPDF. Contains four sub-objects, one per standard checked.

Each sub-object has the following structure:

| Field | Type | Description |
|---|---|---|
| `level` | `string \| null` | The conformance level being tested. Currently `"AA"` for WCAG 2.2; `null` for PDF/A-1b, PDF/UA-1, and PDF/UA-2. |
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

Document-level metadata extracted from the PDF info dictionary and XMP stream. Some properties are always emitted when extraction succeeds; source metadata fields are omitted when absent. Recognized XMP fields are normalized to the names below, while unrecognized XMP and custom PDF info fields may also appear under their source-derived names.

### Core document info

| Field | Type | Description |
|---|---|---|
| `Content-Type` | `string` | MIME type of the file. Always `"application/pdf"`. |
| `dc:title` | `string` | Document title from XMP Dublin Core metadata. |
| `dc:creator` | `string` | Author(s) from XMP Dublin Core metadata. |
| `dc:description` | `string` | Description from XMP Dublin Core metadata. |
| `dc:language` | `string` | Language from XMP or the PDF info dictionary. |
| `pdf_version` | `string` | PDF specification version, e.g. `"1.6"`. |
| `producer_software` | `string` | Software used to generate the final PDF file (i.e., the tool that converted or exported the document into PDF format). Extracted from the XMP metadata stream. |
| `pdf:docinfo:title` | `string` | Document title from the older PDF info dictionary (may differ from `dc:title`). |
| `pdf:docinfo:creator` | `string` | Author from the PDF info dictionary. |
| `pdf:docinfo:subject` | `string` | Subject from the PDF info dictionary. |
| `pdf:docinfo:creator_tool` | `string` | Software used to create the original document before it was converted into a PDF (e.g., "Adobe InDesign"). Extracted from the /Creator field in the PDF’s document info dictionary. |
| `pdf:docinfo:created` | `string` | Creation date from the PDF info dictionary (ISO 8601 format). |
| `pdf:docinfo:modified` | `string` | Last modified date from the PDF info dictionary (ISO 8601 format). |
| `pdf:docinfo:custom:{name}` | `string` | A non-standard entry from the PDF info dictionary. A `LANGUAGE` entry is also exposed as `LANGUAGE` and, if absent, `dc:language`. |

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
| `unreadable_chars_per_page` | `array of string` | Currently emitted as `"0"` for every page with extractable character counts; this pipeline does not calculate actual unmapped Unicode counts. |
| `total_unreadable_chars` | `string (int)` | Currently emitted as `"0"`; this pipeline does not calculate actual unmapped Unicode counts. |
| `unreadable_chars_pct` | `string (float)` | Currently emitted as `"0.0"`; this pipeline does not calculate an actual percentage. |
| `ocr_page_count` | `string (int)` | Count of pages with at least one extractable text character. This is not a determination that those pages were OCR-processed. |

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
| `[].char_count` | `integer` | Number of extractable text characters on this page. Zero means no text was extracted; the page may be image-only or otherwise have no extractable text. |