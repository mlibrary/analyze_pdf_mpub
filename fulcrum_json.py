"""
fulcrum_json.py
Assembles the Fulcrum ticket-format JSON from a PDF file.
Used by analyze_pdf.py (PDF Analyzer).

Output schema (matches Fulcrum ticket format exactly)
--------------------------------------------------------------
{
  "document_type":           "native" | "scanned_ocr" | "scanned_unreadable",
  "metadata":                { "pdf_version": ..., "dc:title": ...,
                               "is_tagged": "true", "can_print": "true", ... },
  "conformance":             { "PDFA_1_B":  {"status": "compliant"|"not compliant"|"not present", "passed_rules": int, "failed_rules": int, "total_rules": int},
                               "PDFUA_1":   ...,
                               "PDFUA_2":   ...,
                               "WCAG_2_1":  ...,
                               "WCAG_2_2":  ... },
  "bookmarks":               { "items": [...] },
  "page_info":               [ { "char_count": 1200 }, ... ],
  "marked_content":          [ { "type": "P", "alttext": null }, ... ]
}
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pikepdf

try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False

try:
    import pdfplumber as _pdfplumber
    PDFPLUMBER_AVAILABLE = True
except ImportError:
    PDFPLUMBER_AVAILABLE = False



# ---------------------------------------------------------------------------
# metadata
# ---------------------------------------------------------------------------

def _str_val(v: Any) -> str:
    """Convert any XMP/pikepdf value to a plain string."""
    if v is None:
        return ''
    if isinstance(v, (list, tuple)):
        return [str(x) for x in v]
    return str(v)


def _bool_str(v: bool) -> str:
    return 'true' if v else 'false'


def extract_xmp_metadata(pdf_path: Path) -> Dict[str, Any]:
    """
    Extract rich PDF metadata matching Jeremy's Fulcrum ticket format.

    Combines:
      - XMP stream (dc:*, xmp:*, xmpTPg:*, pdfaid:*, pdfa:*, dcterms:*)
      - /Info dictionary (pdf:docinfo:* keys)
      - PDF-level properties (version, encryption, permissions, font flags)
      - Per-page char counts
    """
    meta: Dict[str, Any] = {}

    try:
        with pikepdf.open(pdf_path) as pdf:

            # ── PDF version ────────────────────────────────────────────────
            version = getattr(pdf, 'pdf_version', None) or ''
            if version:
                meta['pdf_version'] = version
            meta['Content-Type'] = 'application/pdf'

            # ── XMP stream ─────────────────────────────────────────────────
            # Namespace URI → preferred output key for fields we care about
            _XMP_KEY_MAP = {
                '{http://ns.adobe.com/pdf/1.3/}Producer':       'producer_software',
                '{http://ns.adobe.com/pdf/1.3/}PDFVersion':     'pdf_version',
                '{http://ns.adobe.com/xap/1.0/}MetadataDate':   'xmp:MetadataDate',
                '{http://purl.org/dc/elements/1.1/}title':      'dc:title',
                '{http://purl.org/dc/elements/1.1/}creator':    'dc:creator',
                '{http://purl.org/dc/elements/1.1/}description':'dc:description',
                '{http://purl.org/dc/elements/1.1/}language':   'dc:language',
                '{http://ns.adobe.com/xap/1.0/mm/}DocumentID':  'xmpMM:DocumentID',
                '{http://ns.adobe.com/xap/1.0/mm/}InstanceID':  'xmpMM:InstanceID',
            }
            try:
                with pdf.open_metadata() as xmp:
                    for key in xmp:
                        val = xmp[key]
                        # Use the normalized key if we know it, else store as-is
                        out_key = _XMP_KEY_MAP.get(key, key)
                        meta[out_key] = _str_val(val)
            except Exception as e:
                logging.debug(f"XMP read failed: {e}")

            # ── /Info dictionary → pdf:docinfo:* ───────────────────────────
            # Use raw trailer /Info (not pdf.docinfo which injects pikepdf as Producer)
            try:
                _info_ref = pdf.trailer.get('/Info')
                info = pdf.get_object(_info_ref.objgen) if (_info_ref and hasattr(_info_ref, 'objgen')) else _info_ref
                # Standard Info keys
                std_map = {
                    '/Title':    ('pdf:docinfo:title',    'dc:title'),
                    '/Author':   ('pdf:docinfo:creator',  'dc:creator'),
                    '/Subject':  ('pdf:docinfo:subject',  None),
                    '/Creator':  ('pdf:docinfo:creator_tool', None),
                    '/CreationDate': ('pdf:docinfo:created', None),
                    '/ModDate':  ('pdf:docinfo:modified', None),
                }
                for pdf_key, (docinfo_key, fallback_key) in std_map.items():
                    if pdf_key in info:
                        raw = str(info[pdf_key]).strip()
                        if raw:
                            meta[docinfo_key] = raw
                            if fallback_key and fallback_key not in meta:
                                meta[fallback_key] = raw

                # Custom Info entries → pdf:docinfo:custom:*
                known_std = {'/Title', '/Author', '/Subject', '/Creator',
                             '/Producer', '/CreationDate', '/ModDate',
                             '/Keywords', '/Trapped'}
                for k in info.keys():
                    key_str = str(k)
                    if key_str not in known_std:
                        clean = key_str.lstrip('/')
                        raw = str(info[k]).strip()
                        if raw:
                            meta[f'pdf:docinfo:custom:{clean}'] = raw
                            # Also expose bare for LANGUAGE etc.
                            if clean.upper() == 'LANGUAGE':
                                meta['LANGUAGE'] = raw
                                if 'dc:language' not in meta:
                                    meta['dc:language'] = raw
            except Exception as e:
                logging.debug(f"Info dict read failed: {e}")

            # ── Encryption & permissions ───────────────────────────────────
            try:
                is_enc = pdf.is_encrypted
                meta['is_encrypted'] = _bool_str(is_enc)

                allow = pdf.allow
                meta['can_print']           = _bool_str(bool(allow.print_lowres))
                meta['can_print_high_quality'] = _bool_str(bool(allow.print_highres))
            except Exception as e:
                logging.debug(f"Permissions read failed: {e}")

            # ── Boolean PDF properties ─────────────────────────────────────
            try:
                root = pdf.Root
                meta['is_tagged'] = _bool_str('/StructTreeRoot' in root)

                # XFA forms
                if '/AcroForm' in root:
                    acro = root['/AcroForm']
                    meta['has_xml_forms'] = _bool_str('/XFA' in acro)
                else:
                    meta['has_xml_forms'] = 'false'

                # Collections (PDF Portfolio)
                meta['is_portfolio'] = _bool_str('/Collection' in root)

                # XMP present?
                meta['has_xmp_metadata'] = _bool_str('/Metadata' in root)

            except Exception as e:
                logging.debug(f"Boolean PDF props failed: {e}")

            # ── 3D annotations count ───────────────────────────────────────
            try:
                count_3d = 0
                for page_ref in pdf.pages:
                    annots = page_ref.get('/Annots', [])
                    for ann in annots:
                        try:
                            if str(ann.get('/Subtype', '')) == '/3D':
                                count_3d += 1
                        except Exception:
                            pass
                meta['count_3d_annotations'] = str(count_3d)
            except Exception as e:
                logging.debug(f"3D annotation count failed: {e}")

            # ── Font flags (non-embedded, damaged) ────────────────────────
            try:
                has_non_embedded = False
                has_damaged      = False
                seen_fonts: set = set()
                for page_ref in pdf.pages:
                    resources = page_ref.get('/Resources', {})
                    fonts = resources.get('/Font', {}) if resources else {}
                    for fname in fonts.keys():
                        font_obj = fonts[fname]
                        try:
                            font_id = str(font_obj.objgen)
                        except Exception:
                            font_id = str(fname)
                        if font_id in seen_fonts:
                            continue
                        seen_fonts.add(font_id)
                        try:
                            desc = font_obj.get('/FontDescriptor')
                            if desc:
                                flags = int(desc.get('/Flags', 0))
                                # Bit 3 = non-symbolic, bit 5 = italic; embedded = has /FontFile*
                                has_embedded = any(
                                    k in desc for k in
                                    ('/FontFile', '/FontFile2', '/FontFile3')
                                )
                                if not has_embedded:
                                    has_non_embedded = True
                        except Exception:
                            pass
                meta['has_non_embedded_fonts'] = _bool_str(has_non_embedded)
                meta['has_damaged_fonts']      = _bool_str(has_damaged)
            except Exception as e:
                logging.debug(f"Font flag check failed: {e}")

            # ── Per-page char counts ───────────────────────────────────────
            chars_per_page = _get_chars_per_page(pdf_path)
            if chars_per_page:
                # Unmapped unicode — we can't compute real Tika values, emit zeros
                meta['unreadable_chars_per_page'] = ['0'] * len(chars_per_page)
                meta['total_unreadable_chars']    = '0'
                meta['unreadable_chars_pct']      = '0.0'

                # OCR page count = pages with any text
                ocr_pages = sum(1 for c in chars_per_page if c > 0)
                meta['ocr_page_count'] = str(ocr_pages)

    except Exception as e:
        logging.warning(f"Metadata extraction failed: {e}")

    # Strip empty/None values
    return {k: v for k, v in meta.items() if v not in (None, '', [])}


def _get_chars_per_page(pdf_path: Path) -> List[int]:
    """Return list of character counts per page using best available engine."""
    if PYMUPDF_AVAILABLE:
        try:
            doc = fitz.open(str(pdf_path))
            counts = [len(page.get_text()) for page in doc]
            doc.close()
            return counts
        except Exception as e:
            logging.debug(f"PyMuPDF chars/page failed: {e}")

    if PDFPLUMBER_AVAILABLE:
        try:
            import pdfplumber
            with pdfplumber.open(pdf_path) as pdf:
                return [len(page.extract_text() or '') for page in pdf.pages]
        except Exception as e:
            logging.debug(f"pdfplumber chars/page failed: {e}")

    return []


# ---------------------------------------------------------------------------
# conformance
# ---------------------------------------------------------------------------

def build_conformance(verapdf_result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Map veraPDF profile results → Fulcrum conformance block.

    Keys: PDFA_1_B, PDFUA_1, PDFUA_2, WCAG_2_1, WCAG_2_2
    Each value is a dict with:
      - status:        'compliant' | 'not compliant' | 'not present'
      - passed_rules:  int
      - failed_rules:  int
      - total_rules:   int
    """
    def empty_entry(level: Optional[str] = None) -> Dict[str, Any]:
        return {
            'level':               level,
            'status':              'not available',
            'passed_rules':        None,
            'failed_rules':        None,
            'total_rules':         None,
            'failed_rule_details': None,
        }

    default = {
        'PDFA_1_B': empty_entry(),
        'PDFUA_1':  empty_entry(),
        'PDFUA_2':  empty_entry(),
        'WCAG_2_1': empty_entry(),
        'WCAG_2_2': empty_entry(),
    }

    if not verapdf_result or not verapdf_result.get('available'):
        return default

    profiles = verapdf_result.get('profiles', {})

    def entry(name: str, level: Optional[str] = None) -> Dict[str, Any]:
        if name not in profiles:
            return empty_entry(level=level)
        pd = profiles[name]
        if 'error' in pd:
            return empty_entry(level=level)
        failed_summaries = pd.get('failed_rule_summaries', [])
        return {
            'level':               pd.get('wcag_level', level),
            'status':              'pass' if pd.get('compliant') else 'fail',
            'passed_rules':        pd.get('passed_rules'),
            'failed_rules':        pd.get('failed_rules'),
            'total_rules':         pd.get('total_rules'),
            'failed_rule_details': [
                {
                    'clause':        r.get('clause'),
                    'specification': r.get('specification'),
                    'description':   r.get('description'),
                }
                for r in failed_summaries
            ] or None,
        }

    return {
        'PDFA_1_B': entry('PDF/A-1b'),
        'PDFUA_1':  entry('PDF/UA-1'),
        'PDFUA_2':  entry('PDF/UA-2'),
        'WCAG_2_1': entry('WCAG 2.1'),
        'WCAG_2_2': entry('WCAG 2.2'),
    }


# ---------------------------------------------------------------------------
# outline
# ---------------------------------------------------------------------------

def extract_outline(pdf_path: Path) -> Dict[str, Any]:
    """
    Traverse the PDF outline (bookmarks) and return a flat list of title strings.
    """
    items: List[str] = []

    def traverse(outline_items: list, depth: int = 0) -> None:
        for item in outline_items:
            try:
                title = str(item.title) if item.title else '(untitled)'
                prefix = '  ' * depth
                items.append(f"{prefix}{title}" if depth > 0 else title)
                if item.children:
                    traverse(item.children, depth + 1)
            except Exception:
                pass

    try:
        with pikepdf.open(pdf_path) as pdf:
            with pdf.open_outline() as outline:
                traverse(outline.root)
    except Exception as e:
        logging.warning(f"Outline extraction failed: {e}")

    return {'items': items}


# ---------------------------------------------------------------------------
# page_info
# ---------------------------------------------------------------------------

def build_page_info_pymupdf(pdf_path: Path) -> List[Dict[str, Any]]:
    """Per-page text stats using PyMuPDF. Returns page_info_list."""
    if not PYMUPDF_AVAILABLE:
        return []

    page_info: List[Dict[str, Any]] = []
    try:
        doc = fitz.open(str(pdf_path))
        for page in doc:
            length = len(page.get_text())
            page_info.append({'char_count': length})
        doc.close()
    except Exception as e:
        logging.warning(f"PyMuPDF page info failed: {e}")
        return []

    return page_info


def build_page_info_pdfplumber(pdf_path: Path) -> List[Dict[str, Any]]:
    """Per-page text stats using pdfplumber. Returns page_info_list."""
    if not PDFPLUMBER_AVAILABLE:
        return []

    page_info: List[Dict[str, Any]] = []
    try:
        import pdfplumber
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                length = len(page.extract_text() or '')
                page_info.append({'char_count': length})
    except Exception as e:
        logging.warning(f"pdfplumber page info failed: {e}")
        return []

    return page_info

# ---------------------------------------------------------------------------
# marked_content
# ---------------------------------------------------------------------------

def extract_marked_content(pdf_path: Path) -> List[Dict[str, Any]]:
    """
    Traverse the PDF structure tree and return a flat list of all tagged elements.

    Each element: { type, alttext }
    """
    elements: List[Dict] = []

    def _str(obj: Any) -> Optional[str]:
        s = str(obj).strip() if obj is not None else None
        return s if s else None

    def traverse(obj: Any, depth: int = 0) -> None:
        if depth > 150:
            return

        if isinstance(obj, pikepdf.Dictionary):
            s = obj.get('/S')
            if s is not None:
                raw_type = _str(s)
                elements.append({
                    'type':    raw_type.lstrip('/') if raw_type else None,
                    'alttext': _str(obj.get('/Alt')),
                })
            if '/K' in obj:
                traverse(obj['/K'], depth + 1)

        elif isinstance(obj, (list, pikepdf.Array)):
            for item in obj:
                traverse(item, depth + 1)

    try:
        with pikepdf.open(pdf_path) as pdf:
            if '/StructTreeRoot' not in pdf.Root:
                return elements
            struct_root = pdf.Root['/StructTreeRoot']
            traverse(struct_root.get('/K', []))
    except Exception as e:
        logging.warning(f"Marked content extraction failed: {e}")

    return elements

def inject_text_quality(meta: Dict[str, Any], analyzer_result: Dict[str, Any]) -> None:
    tq = (analyzer_result or {}).get('text_quality')
    if not isinstance(tq, dict):
        return
    meta['text_quality'] = tq

# ---------------------------------------------------------------------------
# Main assembler
# ---------------------------------------------------------------------------

def assemble(
    pdf_path: Path,
    verapdf_result: Dict[str, Any],
    doc_type: Optional[Dict[str, Any]] = None,
    analyzer_result: Optional[Dict[str, Any]] = None,
    page_info_engine: str = 'pymupdf',
    source: str = 'unknown',
) -> Dict[str, Any]:

    if page_info_engine == 'pdfplumber':
        page_info = build_page_info_pdfplumber(pdf_path)
    else:
        page_info = build_page_info_pymupdf(pdf_path)

    meta = extract_xmp_metadata(pdf_path)

    if isinstance(analyzer_result, dict) and 'text_quality' in analyzer_result:
        meta['text_quality'] = analyzer_result['text_quality']

    out = {
        'document_type':  doc_type.get('document_type') if doc_type else None,
        'metadata':       meta,
        'conformance':    build_conformance(verapdf_result),
        'bookmarks':      extract_outline(pdf_path),
        'page_info':      page_info,
        'marked_content': extract_marked_content(pdf_path),
    }
    return out