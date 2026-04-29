#!/usr/bin/env python3
"""
Analyze PDF accessibility features.
Outputs statistics about a PDF including:
- Number of pages
- Number of bookmarks
- Number of headings (by level)
- Number of figures
- Number of figures with alt text
- Heading hierarchy validation
- Document language declaration
- Alt text quality checks
- Table structure validation
- Reading order validation
Outputs both human-readable text and JSON formats.
"""
import argparse
import hashlib
import json
import logging
import random
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional
import pikepdf
from pikepdf import Name
try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False
    logging.warning("PyMuPDF not available - reading order checks will be skipped")
def setup_logging(verbose: bool = False) -> None:
    """Configure logging."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(levelname)s: %(message)s'
    )
def count_structure_elements(obj, tag_name: str, depth: int = 0, max_depth: int = 50) -> int:
    """
    Recursively count structure elements with a specific tag name.

    Args:
        obj: Structure tree object or array to search.
        tag_name: Tag name to count (e.g., '/H1', '/Figure').
        depth: Current recursion depth.
        max_depth: Maximum recursion depth to prevent infinite loops.

    Returns:
        Count of elements with the specified tag.
    """
    if depth > max_depth:
        return 0

    count = 0
    if isinstance(obj, pikepdf.Dictionary):
        if obj.get('/S') == Name(tag_name):
            count += 1
        if '/K' in obj:
            count += count_structure_elements(obj['/K'], tag_name, depth + 1, max_depth)
    elif isinstance(obj, (list, pikepdf.Array)):
        for item in obj:
            count += count_structure_elements(item, tag_name, depth + 1, max_depth)

    return count
def count_figures_with_alt(obj, depth: int = 0, max_depth: int = 50) -> tuple[int, int]:
    """
    Count Figure elements and how many have alt text.

    Args:
        obj: Structure tree object or array to search.
        depth: Current recursion depth.
        max_depth: Maximum recursion depth.

    Returns:
        Tuple of (total_figures, figures_with_alt).
    """
    if depth > max_depth:
        return 0, 0

    total = 0
    with_alt = 0

    if isinstance(obj, pikepdf.Dictionary):
        if obj.get('/S') == Name('/Figure'):
            total += 1
            # Check for Alt text
            if '/Alt' in obj and str(obj['/Alt']).strip():
                with_alt += 1

        if '/K' in obj:
            child_total, child_alt = count_figures_with_alt(obj['/K'], depth + 1, max_depth)
            total += child_total
            with_alt += child_alt

    elif isinstance(obj, (list, pikepdf.Array)):
        for item in obj:
            child_total, child_alt = count_figures_with_alt(item, depth + 1, max_depth)
            total += child_total
            with_alt += child_alt

    return total, with_alt
def count_bookmarks(pdf: pikepdf.Pdf) -> int:
    """
    Count bookmarks (outline entries) in the PDF.

    Args:
        pdf: The PDF document.

    Returns:
        Number of bookmark entries.
    """
    if '/Outlines' not in pdf.Root:
        return 0

    outlines = pdf.Root['/Outlines']
    if '/First' not in outlines:
        return 0

    count = 0
    current = outlines['/First']

    def count_outline_items(item, depth=0, max_depth=100):
        if depth > max_depth or item is None:
            return

        nonlocal count
        count += 1

        # Count children (deeper level - increment depth)
        if isinstance(item, pikepdf.Dictionary):
            if '/First' in item:
                count_outline_items(item['/First'], depth + 1, max_depth)

            # Count siblings (same level - do not increment depth)
            if '/Next' in item:
                count_outline_items(item['/Next'], depth, max_depth)

    try:
        count_outline_items(current)
    except Exception as e:
        logging.warning(f"Error counting bookmarks: {e}")

    return count
def extract_bookmark_structure(pdf: pikepdf.Pdf) -> List[Dict[str, Any]]:
    """
    Extract bookmark structure with titles and levels.

    Args:
        pdf: The PDF document.

    Returns:
        List of bookmark dicts with title and level.
    """
    if '/Outlines' not in pdf.Root:
        return []

    outlines = pdf.Root['/Outlines']
    if '/First' not in outlines:
        return []

    bookmarks = []

    def extract_outline_items(item, level=1, depth=0, max_depth=100):
        if depth > max_depth or item is None:
            return

        if isinstance(item, pikepdf.Dictionary):
            title = str(item.get('/Title', ''))
            bookmarks.append({'title': title, 'level': level})

            # Process children (deeper level - increment depth)
            if '/First' in item:
                extract_outline_items(item['/First'], level + 1, depth + 1, max_depth)

            # Process siblings (same level - do not increment depth)
            if '/Next' in item:
                extract_outline_items(item['/Next'], level, depth, max_depth)

    try:
        extract_outline_items(outlines['/First'])
    except Exception as e:
        logging.warning(f"Error extracting bookmarks: {e}")

    return bookmarks
def compare_bookmarks_to_headings(pdf: pikepdf.Pdf, struct_tree) -> Dict[str, Any]:
    """
    Compare bookmark structure to heading tag hierarchy.

    Args:
        pdf: The PDF document.
        struct_tree: Structure tree root K object.

    Returns:
        Dict with comparison results.
    """
    bookmarks = extract_bookmark_structure(pdf)

    # Extract heading structure
    headings = []

    def collect_headings(obj, depth=0, max_depth=50):
        if depth > max_depth:
            return

        if isinstance(obj, pikepdf.Dictionary):
            tag = obj.get('/S')
            if tag and str(tag) in ['/H1', '/H2', '/H3', '/H4', '/H5', '/H6']:
                level = int(str(tag)[2])
                # Try to get heading text
                title = ''
                if '/K' in obj:
                    # Would need to extract actual text - simplified
                    pass
                headings.append({'level': level, 'title': title})

            if '/K' in obj:
                collect_headings(obj['/K'], depth + 1)

        elif isinstance(obj, (list, pikepdf.Array)):
            for item in obj:
                collect_headings(item, depth + 1)

    collect_headings(struct_tree)

    # Compare counts and structure
    bookmark_count = len(bookmarks)
    heading_count = len(headings)

    # Check if bookmark levels roughly match heading levels
    bookmark_levels = [b['level'] for b in bookmarks]
    heading_levels = [h['level'] for h in headings]

    max_bookmark_level = max(bookmark_levels) if bookmark_levels else 0
    max_heading_level = max(heading_levels) if heading_levels else 0

    return {
        'bookmark_count': bookmark_count,
        'heading_count': heading_count,
        'bookmarks_exist': bookmark_count > 0,
        'max_bookmark_depth': max_bookmark_level,
        'max_heading_depth': max_heading_level,
        'depth_matches': max_bookmark_level == max_heading_level if bookmark_count > 0 else False,
        'coverage': (bookmark_count / heading_count * 100) if heading_count > 0 else 0,
    }
def check_internal_links(pdf: pikepdf.Pdf) -> Dict[str, Any]:
    """
    Check for internal cross-references implemented as links.

    Args:
        pdf: The PDF document.

    Returns:
        Dict with internal link statistics.
    """
    stats = {
        'total_annotations': 0,
        'link_annotations': 0,
        'internal_links': 0,
        'external_links': 0,
        'pages_with_links': 0,
    }

    try:
        pages_with_links = set()

        # Sample pages for performance
        sample_pages = list(range(min(20, len(pdf.pages)))) + \
                      list(range(max(0, len(pdf.pages) - 10), len(pdf.pages)))
        sample_pages = sorted(set(sample_pages))

        for page_num in sample_pages:
            page = pdf.pages[page_num]

            if '/Annots' not in page:
                continue

            annots = page.Annots
            if not annots:
                continue

            page_has_links = False

            for annot in annots:
                if not isinstance(annot, pikepdf.Dictionary):
                    continue

                stats['total_annotations'] += 1

                if annot.get('/Subtype') == Name('/Link'):
                    stats['link_annotations'] += 1
                    page_has_links = True

                    # Check if internal or external
                    if '/A' in annot:
                        action = annot['/A']
                        if isinstance(action, pikepdf.Dictionary):
                            action_type = action.get('/S')
                            if action_type == Name('/GoTo'):
                                stats['internal_links'] += 1
                            elif action_type == Name('/URI'):
                                stats['external_links'] += 1
                    elif '/Dest' in annot:
                        # Direct destination = internal link
                        stats['internal_links'] += 1

            if page_has_links:
                pages_with_links.add(page_num)

        stats['pages_with_links'] = len(pages_with_links)

    except Exception as e:
        stats['error'] = str(e)
        logging.warning(f"Error checking internal links: {e}")

    return stats
def check_document_title(pdf: pikepdf.Pdf) -> Dict[str, Any]:
    """
    Check document title in metadata.

    Args:
        pdf: The PDF document.

    Returns:
        Dict with title information.
    """
    result = {
        'title_in_metadata': False,
        'title': None,
        'author': None,
        'subject': None,
    }

    try:
        # Check document info dictionary
        if '/Info' in pdf.trailer:
            info = pdf.trailer['/Info']
            if isinstance(info, pikepdf.Dictionary):
                if '/Title' in info:
                    result['title_in_metadata'] = True
                    result['title'] = str(info['/Title'])
                if '/Author' in info:
                    result['author'] = str(info['/Author'])
                if '/Subject' in info:
                    result['subject'] = str(info['/Subject'])

        # Also check XMP metadata in catalog
        if '/Metadata' in pdf.Root:
            # XMP metadata exists (would need XML parsing for full extraction)
            pass

    except Exception as e:
        result['error'] = str(e)
        logging.warning(f"Error checking document title: {e}")

    return result
def check_heading_hierarchy(obj, depth: int = 0, max_depth: int = 50) -> List[Dict[str, Any]]:
    """
    Check heading hierarchy for logical structure.

    Args:
        obj: Structure tree object or array to search.
        depth: Current recursion depth.
        max_depth: Maximum recursion depth.

    Returns:
        List of heading hierarchy issues found.
    """
    issues = []
    headings_in_order = []

    def collect_headings(obj, depth=0):
        if depth > max_depth:
            return

        if isinstance(obj, pikepdf.Dictionary):
            tag = obj.get('/S')
            if tag and str(tag) in ['/H1', '/H2', '/H3', '/H4', '/H5', '/H6']:
                level = int(str(tag)[2])  # Extract number from /H1, /H2, etc.
                headings_in_order.append(level)

            if '/K' in obj:
                collect_headings(obj['/K'], depth + 1)

        elif isinstance(obj, (list, pikepdf.Array)):
            for item in obj:
                collect_headings(item, depth + 1)

    collect_headings(obj)

    # Check for logical progression
    prev_level = 0
    for i, level in enumerate(headings_in_order):
        if prev_level > 0:
            # Check for skipped levels (e.g., H1 -> H3)
            if level > prev_level + 1:
                issues.append({
                    'type': 'skipped_level',
                    'message': f"Heading jumps from H{prev_level} to H{level} (position {i})",
                    'position': i,
                    'from_level': prev_level,
                    'to_level': level
                })
        prev_level = level

    return issues
def check_document_language(pdf: pikepdf.Pdf) -> Optional[str]:
    """
    Check if document language is declared.

    Args:
        pdf: The PDF document.

    Returns:
        Language code if declared, None otherwise.
    """
    # Check catalog level
    if '/Lang' in pdf.Root:
        return str(pdf.Root['/Lang'])

    # Check metadata
    if '/Metadata' in pdf.Root:
        try:
            metadata = pdf.Root['/Metadata']
            # XMP metadata would need XML parsing - simplified check
            return None
        except Exception:
            pass

    return None
GENERIC_ALT_PATTERNS = [
    r'^image$',
    r'^figure$',
    r'^picture$',
    r'^untitled$',
    r'^photo$',
    r'^img$',
    r'^image\s*\d*$',
    r'^figure\s*\d*$',
    r'^\s*$',  # Empty or whitespace only
]
def is_generic_alt_text(alt_text: str) -> bool:
    """
    Check if alt text is generic or unhelpful.

    Args:
        alt_text: The alt text to check.

    Returns:
        True if alt text is generic.
    """
    if not alt_text or not alt_text.strip():
        return True

    alt_lower = alt_text.lower().strip()

    for pattern in GENERIC_ALT_PATTERNS:
        if re.match(pattern, alt_lower):
            return True

    return False
def analyze_alt_text_quality(obj, depth: int = 0, max_depth: int = 50) -> Dict[str, int]:
    """
    Analyze quality of alt text for figures.

    Args:
        obj: Structure tree object or array to search.
        depth: Current recursion depth.
        max_depth: Maximum recursion depth.

    Returns:
        Dict with counts: total, with_alt, empty_alt, generic_alt, good_alt.
    """
    stats = {
        'total': 0,
        'with_alt': 0,
        'empty_alt': 0,
        'generic_alt': 0,
        'good_alt': 0,
    }

    if depth > max_depth:
        return stats

    if isinstance(obj, pikepdf.Dictionary):
        if obj.get('/S') == Name('/Figure'):
            stats['total'] += 1

            if '/Alt' in obj:
                alt_text = str(obj['/Alt']).strip()
                if alt_text:
                    stats['with_alt'] += 1
                    if is_generic_alt_text(alt_text):
                        stats['generic_alt'] += 1
                    else:
                        stats['good_alt'] += 1
                else:
                    stats['empty_alt'] += 1
            else:
                stats['empty_alt'] += 1

        if '/K' in obj:
            child_stats = analyze_alt_text_quality(obj['/K'], depth + 1, max_depth)
            for key in stats:
                stats[key] += child_stats[key]

    elif isinstance(obj, (list, pikepdf.Array)):
        for item in obj:
            child_stats = analyze_alt_text_quality(item, depth + 1, max_depth)
            for key in stats:
                stats[key] += child_stats[key]

    return stats
def check_table_headers(obj, depth: int = 0, max_depth: int = 50) -> Dict[str, int]:
    """
    Check if tables have header cells.

    Args:
        obj: Structure tree object or array to search.
        depth: Current recursion depth.
        max_depth: Maximum recursion depth.

    Returns:
        Dict with counts: total_tables, tables_with_headers.
    """
    stats = {
        'total_tables': 0,
        'tables_with_headers': 0,
        'total_th': 0,
        'total_td': 0,
    }

    if depth > max_depth:
        return stats

    def count_in_table(table_obj, depth=0):
        has_th = False
        th_count = 0
        td_count = 0

        if depth > max_depth:
            return has_th, th_count, td_count

        if isinstance(table_obj, pikepdf.Dictionary):
            tag = table_obj.get('/S')
            if tag == Name('/TH'):
                has_th = True
                th_count += 1
            elif tag == Name('/TD'):
                td_count += 1

            if '/K' in table_obj:
                child_has_th, child_th, child_td = count_in_table(table_obj['/K'], depth + 1)
                has_th = has_th or child_has_th
                th_count += child_th
                td_count += child_td

        elif isinstance(table_obj, (list, pikepdf.Array)):
            for item in table_obj:
                child_has_th, child_th, child_td = count_in_table(item, depth + 1)
                has_th = has_th or child_has_th
                th_count += child_th
                td_count += child_td

        return has_th, th_count, td_count

    if isinstance(obj, pikepdf.Dictionary):
        if obj.get('/S') == Name('/Table'):
            stats['total_tables'] += 1
            has_th, th_count, td_count = count_in_table(obj.get('/K', []))
            if has_th:
                stats['tables_with_headers'] += 1
            stats['total_th'] += th_count
            stats['total_td'] += td_count

        if '/K' in obj:
            child_stats = check_table_headers(obj['/K'], depth + 1, max_depth)
            for key in stats:
                stats[key] += child_stats[key]

    elif isinstance(obj, (list, pikepdf.Array)):
        for item in obj:
            child_stats = check_table_headers(item, depth + 1, max_depth)
            for key in stats:
                stats[key] += child_stats[key]

    return stats
def analyze_text_extraction_quality(pdf_path: Path) -> Dict[str, Any]:
    """
    Analyze text extraction quality using PyMuPDF.

    Checks for:
    - Unmapped Unicode characters
    - Copy-paste artifacts (ligatures, encoding issues)
    - Text rendered as images
    - OCR confidence (if available)

    Args:
        pdf_path: Path to the PDF file.

    Returns:
        Dict with text quality statistics.
    """
    if not PYMUPDF_AVAILABLE:
        return {
            'available': False,
            'error': 'PyMuPDF not installed'
        }

    stats = {
        'available': True,
        'total_chars': 0,
        'unmapped_chars': 0,
        'suspicious_chars': 0,
        'ligature_artifacts': 0,
        'replacement_chars': 0,  # ? character
        'control_chars': 0,
        'ocr_detected': False,
        'low_confidence_ocr': 0,
        'image_text_likely': False,
        'sample_issues': [],
    }

    try:
        doc = fitz.open(str(pdf_path))

        # Sample first 10 pages and last 5 pages
        sample_pages = list(range(min(10, len(doc)))) + \
                      list(range(max(0, len(doc) - 5), len(doc)))
        sample_pages = sorted(set(sample_pages))

        ligature_patterns = [
            '\ufb01', '\ufb02', '\ufb00', '\ufb03', '\ufb04',  # Common ligatures
            '\ufb06', '\ufb05',  # Less common
        ]

        total_text_length = 0
        total_image_objects = 0

        for page_num in sample_pages:
            page = doc[page_num]

            # Extract text
            text = page.get_text()
            total_text_length += len(text)

            # Count image objects
            image_list = page.get_images()
            total_image_objects += len(image_list)

            # Analyze characters
            for char in text:
                stats['total_chars'] += 1

                # Check for replacement character (unmapped Unicode)
                if char == '\ufffd':
                    stats['replacement_chars'] += 1
                    if len(stats['sample_issues']) < 20:
                        stats['sample_issues'].append({
                            'page': page_num + 1,
                            'type': 'replacement_char',
                            'context': text[max(0, text.find(char) - 20):
                                          text.find(char) + 20]
                        })

                # Check for control characters (except whitespace)
                if ord(char) < 32 and char not in '\n\r\t':
                    stats['control_chars'] += 1

                # Check for unmapped/suspicious Unicode ranges
                code_point = ord(char)

                # Private Use Area (often indicates unmapped characters)
                if 0xE000 <= code_point <= 0xF8FF:
                    stats['unmapped_chars'] += 1
                    if len(stats['sample_issues']) < 20:
                        stats['sample_issues'].append({
                            'page': page_num + 1,
                            'type': 'private_use_area',
                            'char': char,
                            'code_point': hex(code_point)
                        })

                # Suspicious high Unicode ranges
                if code_point > 0x10000:
                    stats['suspicious_chars'] += 1

            # Check for excessive ligatures (suggests copy-paste artifacts)
            for ligature in ligature_patterns:
                count = text.count(ligature)
                if count > 0:
                    stats['ligature_artifacts'] += count

            # Check for OCR metadata
            text_dict = page.get_text("dict")
            for block in text_dict.get("blocks", []):
                if block.get("type") == 0:  # Text block
                    pass

        # Heuristic: if very few characters but many images, likely image-based text
        if total_text_length < 100 and total_image_objects > len(sample_pages) * 2:
            stats['image_text_likely'] = True

        doc.close()

    except Exception as e:
        stats['error'] = str(e)
        logging.warning(f"Error analyzing text extraction quality: {e}")

    return stats
def check_font_unicode_mappings(pdf: pikepdf.Pdf) -> Dict[str, Any]:
    """
    Check font Unicode mappings in the PDF.

    Args:
        pdf: The PDF document.

    Returns:
        Dict with font mapping statistics.
    """
    stats = {
        'total_fonts': 0,
        'fonts_without_tounicode': 0,
        'embedded_fonts': 0,
        'non_embedded_fonts': 0,
        'font_issues': [],
    }

    try:
        # Sample first few pages to check fonts
        for page_num in range(min(10, len(pdf.pages))):
            page = pdf.pages[page_num]

            if '/Resources' not in page:
                continue

            resources = page.Resources
            if '/Font' not in resources:
                continue

            fonts = resources['/Font']

            for font_name, font_ref in fonts.items():
                if not isinstance(font_ref, pikepdf.Dictionary):
                    try:
                        font_obj = font_ref
                    except Exception:
                        continue
                else:
                    font_obj = font_ref

                stats['total_fonts'] += 1

                # Check for ToUnicode CMap
                if '/ToUnicode' not in font_obj:
                    stats['fonts_without_tounicode'] += 1
                    if len(stats['font_issues']) < 10:
                        stats['font_issues'].append({
                            'page': page_num + 1,
                            'font': str(font_name),
                            'issue': 'missing_tounicode'
                        })

                # Check if font is embedded
                if '/FontDescriptor' in font_obj:
                    desc = font_obj['/FontDescriptor']
                    if isinstance(desc, pikepdf.Dictionary):
                        # Check for font file (embedded)
                        if any(key in desc for key in ['/FontFile', '/FontFile2',
                                                       '/FontFile3']):
                            stats['embedded_fonts'] += 1
                        else:
                            stats['non_embedded_fonts'] += 1
                else:
                    stats['non_embedded_fonts'] += 1

    except Exception as e:
        stats['error'] = str(e)
        logging.warning(f"Error checking font mappings: {e}")

    return stats
def check_reading_order(pdf_path: Path, pdf: pikepdf.Pdf, sample_mode: str = 'all') -> Dict[str, Any]:
    """
    Check if reading order in tag tree matches visual reading order.

    NOTE: This is a weak heuristic. See README for known limitations including
    false negatives on multi-column layouts and false positives from repeated
    strings. Results should not be weighted heavily in scoring.

    Args:
        pdf_path: Path to the PDF file.
        pdf: The PDF document (pikepdf).
        sample_mode: Sampling strategy - 'all' or 'standard'.

    Returns:
        Dict with reading order analysis.
    """
    result = {
        'available': PYMUPDF_AVAILABLE,
        'pages_checked': 0,
        'pages_skipped': 0,
        'pages_with_issues': 0,
        'total_mismatches': 0,
        'issue_details': [],
    }

    if not PYMUPDF_AVAILABLE:
        result['error'] = 'PyMuPDF not available'
        return result

    try:
        doc = fitz.open(str(pdf_path))

        sample_pages = []

        if sample_mode == 'all':
            sample_pages = list(range(len(doc)))
        else:  # 'standard' mode
            if len(doc) < 21:
                sample_pages = list(range(len(doc)))
            else:
                first_pages = list(range(15))
                sample_pages.extend(first_pages)

                path_hash = int(hashlib.sha256(str(pdf_path).encode()).hexdigest()[:16], 16)
                random.seed(path_hash)
                remaining_pages = list(range(15, len(doc)))
                random_count = min(5, len(remaining_pages))
                random_pages = random.sample(remaining_pages, random_count)
                sample_pages.extend(random_pages)

                sample_pages = sorted(set(sample_pages))

        for page_num in sample_pages:
            try:
                page = doc[page_num]

                blocks = page.get_text("dict")["blocks"]

                text_blocks = []
                for block in blocks:
                    if block.get("type") == 0:  # Text block
                        bbox = block.get("bbox", [0, 0, 0, 0])
                        text = ""
                        for line in block.get("lines", []):
                            for span in line.get("spans", []):
                                text += span.get("text", "")
                            if text:
                                break

                        if text.strip():
                            text_blocks.append({
                                'text': text.strip()[:50],
                                'bbox': bbox,
                                'y0': bbox[1],
                                'x0': bbox[0],
                            })

                if len(text_blocks) < 3:
                    result['pages_skipped'] += 1
                    continue

                Y_THRESHOLD = 5

                def visual_sort_key(block):
                    y_group = round(block['y0'] / Y_THRESHOLD) * Y_THRESHOLD
                    return (y_group, block['x0'])

                visual_order = sorted(text_blocks, key=visual_sort_key)
                visual_text_sequence = [b['text'] for b in visual_order]

                tagged_text = page.get_text()
                tagged_lines = [line.strip() for line in tagged_text.split('\n')
                               if line.strip()][:len(visual_text_sequence)]

                mismatches = 0
                for i, visual_text in enumerate(visual_text_sequence[:10]):
                    found_nearby = False
                    search_range = 3

                    for j in range(max(0, i - search_range),
                                 min(len(tagged_lines), i + search_range + 1)):
                        if j < len(tagged_lines):
                            if (visual_text[:20] in tagged_lines[j] or
                                tagged_lines[j][:20] in visual_text):
                                found_nearby = True
                                break

                    if not found_nearby and i < len(tagged_lines):
                        mismatches += 1

                result['pages_checked'] += 1

                if len(visual_text_sequence) > 0:
                    mismatch_rate = mismatches / min(len(visual_text_sequence), 10)

                    if mismatch_rate > 0.3:
                        result['pages_with_issues'] += 1
                        result['total_mismatches'] += mismatches

                        if len(result['issue_details']) < 3:
                            result['issue_details'].append({
                                'page': page_num + 1,
                                'mismatch_count': mismatches,
                                'total_blocks': len(visual_text_sequence),
                                'mismatch_rate': f"{mismatch_rate:.1%}"
                            })

            except Exception as e:
                logging.debug(f"Error checking reading order on page {page_num}: {e}")
                continue

        doc.close()

    except Exception as e:
        result['error'] = str(e)
        logging.warning(f"Error checking reading order: {e}")

    return result
def find_verapdf() -> Optional[Path]:
    """
    Find veraPDF CLI executable.

    Search order:
    1. VERAPDF_PATH environment variable (highest priority)
    2. verapdf/ subfolder next to this script (portable, project-local install)
    3. Common system install locations (Mac + Linux)
    4. PATH (via `which`)
    """
    import os

    # 1. Explicit env var
    env_path = os.environ.get("VERAPDF_PATH")
    if env_path:
        p = Path(env_path)
        if p.exists() and p.is_file():
            return p
        logging.warning(f"VERAPDF_PATH set to {env_path!r} but file not found there.")

    # 2. Project-local install: <this script's dir>/verapdf/verapdf
    script_dir = Path(__file__).resolve().parent
    local = script_dir / "verapdf" / "verapdf"
    if local.exists() and local.is_file():
        return local

    # 3. Common system locations
    locations = [
        Path.home() / "Applications" / "verapdf" / "verapdf",
        Path("/Applications/verapdf/verapdf"),
        Path("/usr/local/bin/verapdf"),
        Path("/usr/bin/verapdf"),
    ]
    for loc in locations:
        if loc.exists() and loc.is_file():
            return loc

    # 4. PATH
    try:
        result = subprocess.run(
            ["which", "verapdf"],
            capture_output=True, text=True, check=False
        )
        if result.returncode == 0:
            return Path(result.stdout.strip())
    except Exception:
        pass

    return None
def _find_profile(verapdf_path: Path, *patterns: str) -> Optional[Path]:
    """Search the veraPDF profiles directory for the first glob pattern that matches."""
    profiles_dir = verapdf_path.parent / 'profiles'
    for pattern in patterns:
        matches = list(profiles_dir.glob(pattern))
        if matches:
            return matches[0]
    return None


def _wcag_level_from_profile(profile_path: Optional[Path]) -> Optional[str]:
    """Extract the WCAG conformance level (A, AA, AAA) from the profile filename."""
    if not profile_path:
        return None
    name = profile_path.stem.upper()
    if name.endswith('-AA') or '-AA-' in name:
        return 'AA'
    if name.endswith('-A') or '-A-' in name:
        return 'A'
    if 'COMPLETE' in name:
        return 'AA'  # veraPDF "Complete" profile covers all WCAG 2.x levels
    return None


def find_wcag_21_profile(verapdf_path: Path) -> Optional[Path]:
    """Locate WCAG 2.1 profile XML (AA level preferred, then A)."""
    return _find_profile(
        verapdf_path,
        '**/WCAG-2-1-AA.xml',
        '**/WCAG-2-1-A.xml',
        '**/WCAG*2-1*.xml',
    )


def find_wcag_22_profile(verapdf_path: Path) -> Optional[Path]:
    """Locate WCAG 2.2 profile XML (AA or Complete)."""
    return _find_profile(
        verapdf_path,
        '**/WCAG-2-2-AA.xml',
        '**/WCAG-2-2-Complete.xml',
        '**/WCAG*2-2*.xml',
        '**/WCAG*Complete*.xml',
    )


def run_verapdf_validation(pdf_path: Path) -> Dict[str, Any]:
    """
    Run veraPDF validation for PDF/A-1b, PDF/UA-1, PDF/UA-2, WCAG 2.1, and WCAG 2.2.
    Profile names match Jeremy's Fulcrum conformance keys.
    """
    result = {
        'available': False,
        'profiles': {},
    }

    verapdf_path = find_verapdf()
    if not verapdf_path:
        result['error'] = 'veraPDF not found. Install from https://verapdf.org/'
        logging.warning(result['error'])
        return result

    result['available'] = True

    wcag_21_profile = find_wcag_21_profile(verapdf_path)
    wcag_22_profile = find_wcag_22_profile(verapdf_path)

    profiles = [
        ('PDF/A-1b', '1b',             False, None),
        ('PDF/UA-1', 'ua1',            False, None),
        ('PDF/UA-2', 'ua2',            False, None),
        ('WCAG 2.1', wcag_21_profile,  True,  _wcag_level_from_profile(wcag_21_profile)),
        ('WCAG 2.2', wcag_22_profile,  True,  _wcag_level_from_profile(wcag_22_profile)),
    ]

    for profile_name, profile_ref, is_custom, wcag_level in profiles:
        logging.info(f"Running veraPDF validation: {profile_name}")

        try:
            if is_custom:
                if not isinstance(profile_ref, Path) or not profile_ref or not profile_ref.exists():
                    result['profiles'][profile_name] = {
                        'error': f'Custom profile not found: {profile_ref}'
                    }
                    logging.warning(f"{profile_name} profile not found at {profile_ref}")
                    continue

                cmd = [
                    str(verapdf_path),
                    '--profile', str(profile_ref),
                    '--format', 'json',
                    str(pdf_path.absolute())
                ]
            else:
                cmd = [
                    str(verapdf_path),
                    '--flavour', profile_ref,
                    '--format', 'json',
                    str(pdf_path.absolute())
                ]

            proc_result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=None,
                check=False
            )

            if proc_result.returncode != 0 and not proc_result.stdout:
                result['profiles'][profile_name] = {
                    'error': f'veraPDF failed with exit code {proc_result.returncode}',
                    'stderr': proc_result.stderr[:500] if proc_result.stderr else ''
                }
                continue

            try:
                output = json.loads(proc_result.stdout)
                jobs = output.get('report', {}).get('jobs', [])

                if not jobs:
                    result['profiles'][profile_name] = {'error': 'No validation results in output'}
                    continue

                validation_result = jobs[0].get('validationResult', [])
                if not validation_result:
                    result['profiles'][profile_name] = {'error': 'Empty validation result'}
                    continue

                details = validation_result[0].get('details', {})

                passed_rules  = details.get('passedRules', 0)
                failed_rules  = details.get('failedRules', 0)
                passed_checks = details.get('passedChecks', 0)
                failed_checks = details.get('failedChecks', 0)
                total_rules   = passed_rules + failed_rules
                compliant     = failed_rules == 0

                profile_result = {
                    'compliant':      compliant,
                    'wcag_level':     wcag_level,
                    'passed_rules':   passed_rules,
                    'failed_rules':   failed_rules,
                    'total_rules':    total_rules,
                    'passed_checks':  passed_checks,
                    'failed_checks':  failed_checks,
                    'total_checks':   passed_checks + failed_checks,
                }

                rule_summaries  = details.get('ruleSummaries', [])
                failed_summaries = [r for r in rule_summaries if r.get('status') == 'failed']

                if failed_summaries:
                    profile_result['failed_rule_summaries'] = [
                        {
                            'clause':        r.get('clause', 'Unknown'),
                            'specification': r.get('specification', 'Unknown'),
                            'description':   r.get('description', ''),
                            'failed_checks': r.get('failedChecks', 0),
                        }
                        for r in failed_summaries
                    ]

                result['profiles'][profile_name] = profile_result

            except json.JSONDecodeError as e:
                result['profiles'][profile_name] = {
                    'error': f'Failed to parse veraPDF JSON output: {e}'
                }

        except subprocess.TimeoutExpired:
            result['profiles'][profile_name] = {'error': 'Validation timed out after 5 minutes'}
        except Exception as e:
            result['profiles'][profile_name] = {'error': f'Validation error: {e}'}

    return result
def check_mime_type(pdf_path: Path) -> str:
    """Verify MIME type from file magic bytes."""
    try:
        with open(pdf_path, 'rb') as f:
            header = f.read(5)
        return 'application/pdf' if header.startswith(b'%PDF-') else 'application/octet-stream'
    except Exception:
        return 'unknown'


def detect_ocr_status(pdf_path: Path, sample_pages: int = 10) -> Dict[str, Any]:
    """
    Detect OCR/scan status using pdfplumber — no PyMuPDF required.

    Samples up to `sample_pages` pages and counts characters via pdfplumber.
    Thresholds derived empirically from HEB collection data:
      - scanned_unreadable : avg < 15 chars/page  (pure image scan, no OCR layer)
      - scanned_ocr        : 15 <= avg < 100 chars/page (OCR layer present but sparse)
      - native             : avg >= 100 chars/page (embedded text)

    Returns:
        Dict with 'status', 'confidence' (0-1), 'avg_chars_per_page'.
    """
    try:
        import pdfplumber
        with pdfplumber.open(pdf_path) as pdf:
            pages = pdf.pages[:min(sample_pages, len(pdf.pages))]
            char_counts = [len(p.chars or []) for p in pages]

        if not char_counts:
            return {'status': 'unknown', 'confidence': 0.0, 'avg_chars_per_page': 0}

        avg = sum(char_counts) / len(char_counts)

        if avg >= 100:
            # 100 chars/pg → ~70%, 300+ chars/pg → 100%
            confidence = round(min(1.0, 0.70 + (avg - 100) / 667), 2)
            status = 'native'
        elif avg >= 15:
            confidence = 0.75
            status = 'scanned_ocr'
        else:
            confidence = 0.90
            status = 'scanned_unreadable'

        return {'status': status, 'confidence': confidence, 'avg_chars_per_page': round(avg, 1)}

    except Exception as e:
        return {'status': 'error', 'error': str(e), 'avg_chars_per_page': 0}


def detect_document_type(pdf_path: Path, sample_pages: int = 10) -> Dict[str, Any]:
    """
    Classify a PDF as 'native', 'scanned_ocr', or 'scanned_unreadable'.

    Uses two independent signals:

    1. Rendering mode 3 (Tr=3 operator in content stream) — the definitive
       marker that invisible OCR text has been overlaid on a scanned image.
       Parsed directly from each page's content stream via pikepdf.

    2. Full-page image coverage (>85% of page area) via PyMuPDF — confirms
       the page is a raster scan rather than a native PDF page.

    Classification logic (signals applied in priority order):
      scanned_ocr        : rendering mode 3 detected on any sampled page
      scanned_unreadable : full-page images present but zero chars extracted
      native             : no scan indicators found

    Returns:
        {
            'document_type':     'native' | 'scanned_ocr' | 'scanned_unreadable',
            'render_mode_3_detected': bool,
            'full_page_images':  int,   # pages with >85% image coverage
            'method':            str,
        }
    """
    SCAN_COVERAGE_THRESHOLD = 0.85
    SAMPLE = sample_pages

    result = {
        'document_type':          'native',
        'render_mode_3_detected': False,
        'full_page_images':       0,
        'method':                 'pikepdf_content_stream+pymupdf_coverage',
    }

    # ── Signal 1: rendering mode 3 via pikepdf content stream parsing ──────
    try:
        with pikepdf.open(pdf_path) as pdf:
            pages_to_check = pdf.pages[:min(SAMPLE, len(pdf.pages))]
            for page in pages_to_check:
                try:
                    for operands, operator in pikepdf.parse_content_stream(page):
                        if str(operator) == 'Tr':
                            if operands and int(str(operands[0])) == 3:
                                result['render_mode_3_detected'] = True
                                break
                except Exception:
                    pass
                if result['render_mode_3_detected']:
                    break
    except Exception as e:
        logging.warning(f"Content stream parsing failed: {e}")

    if result['render_mode_3_detected']:
        result['document_type'] = 'scanned_ocr'
        return result

    # ── Signal 2: full-page image coverage + char count via PyMuPDF ────────
    if PYMUPDF_AVAILABLE:
        try:
            doc = fitz.open(str(pdf_path))
            pages_to_check = list(doc)[:min(SAMPLE, len(doc))]
            total_chars = 0
            full_page_images = 0

            for page in pages_to_check:
                page_area = page.rect.width * page.rect.height
                total_chars += len(page.get_text())

                if page_area == 0:
                    continue
                for img in page.get_images(full=True):
                    xref = img[0]
                    for rect in page.get_image_rects(xref):
                        coverage = (rect.width * rect.height) / page_area
                        if coverage > SCAN_COVERAGE_THRESHOLD:
                            full_page_images += 1

            doc.close()
            result['full_page_images'] = full_page_images

            if full_page_images > 0:
                if total_chars == 0:
                    result['document_type'] = 'scanned_unreadable'
                else:
                    result['document_type'] = 'scanned_ocr'

        except Exception as e:
            logging.warning(f"PyMuPDF document type detection failed: {e}")

    return result


def detect_images_pdfplumber(pdf_path: Path) -> Dict[str, Any]:
    """
    Detect embedded images using pdfplumber (fallback when PyMuPDF is unavailable).

    Filters out full-page scans using an 85% coverage threshold, same logic as
    the PyMuPDF version.
    """
    SCAN_COVERAGE_THRESHOLD = 0.85
    stats = {
        'available': True,
        'total_figures': 0,
        'full_page_scans': 0,
        'method': 'pdfplumber_coverage_filter',
    }
    try:
        import pdfplumber
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                page_area = (page.width or 0) * (page.height or 0)
                if page_area == 0:
                    continue
                for img in (page.images or []):
                    img_w = abs((img.get('x1') or 0) - (img.get('x0') or 0))
                    img_h = abs((img.get('y1') or 0) - (img.get('y0') or 0))
                    coverage = (img_w * img_h) / page_area
                    if coverage > SCAN_COVERAGE_THRESHOLD:
                        stats['full_page_scans'] += 1
                    else:
                        stats['total_figures'] += 1
    except Exception as e:
        stats['error'] = str(e)
        logging.warning(f"pdfplumber image detection error: {e}")
    return stats


def detect_images_pymupdf(pdf_path: Path) -> Dict[str, Any]:
    """
    Detect embedded images using PyMuPDF as a fallback for untagged PDFs.

    Filters out full-page images (page scans) by coverage ratio so only
    actual figures/photos are counted.

    Args:
        pdf_path: Path to the PDF file.

    Returns:
        Dict with image detection results.
    """
    if not PYMUPDF_AVAILABLE:
        return {'available': False, 'total_figures': 0}

    stats = {
        'available': True,
        'total_figures': 0,
        'full_page_scans': 0,
        'method': 'pymupdf_coverage_filter',
    }

    SCAN_COVERAGE_THRESHOLD = 0.85  # images covering >85% of page = page scan

    try:
        doc = fitz.open(str(pdf_path))
        for page in doc:
            page_area = page.rect.width * page.rect.height
            if page_area == 0:
                continue
            for img in page.get_images(full=True):
                xref = img[0]
                rects = page.get_image_rects(xref)
                for rect in rects:
                    coverage = (rect.width * rect.height) / page_area
                    if coverage > SCAN_COVERAGE_THRESHOLD:
                        stats['full_page_scans'] += 1
                    else:
                        stats['total_figures'] += 1
        doc.close()
    except Exception as e:
        stats['error'] = str(e)
        logging.warning(f"Error detecting images with PyMuPDF: {e}")

    return stats
def analyze_pdf(pdf_path: Path, reading_order_sample: str = 'all') -> Dict[str, Any]:
    """
    Analyze a PDF and return statistics.

    Args:
        pdf_path: Path to the PDF file.
        reading_order_sample: Reading order sampling strategy - 'all' or 'standard'.

    Returns:
        Dictionary containing analysis results.
    """
    logging.info(f"Analyzing: {pdf_path.name}")

    mime_type  = check_mime_type(pdf_path)
    ocr_status = detect_ocr_status(pdf_path)

    with pikepdf.open(pdf_path) as pdf:
        page_count    = len(pdf.pages)
        bookmark_count = count_bookmarks(pdf)
        doc_language  = check_document_language(pdf)
        has_structure = '/StructTreeRoot' in pdf.Root

        # PDF version + PDF/A detection
        pdf_version = getattr(pdf, 'pdf_version', None)
        is_pdf_a    = False
        pdf_a_level = None
        try:
            meta = pdf.open_metadata()
            part = meta.get('{http://www.aiim.org/pdfa/ns/id/}part')
            conformance = meta.get('{http://www.aiim.org/pdfa/ns/id/}conformance')
            if part:
                is_pdf_a    = True
                pdf_a_level = f"{part}{conformance.lower() if conformance else ''}"
        except Exception:
            pass

        if not has_structure:
            logging.warning("PDF is not tagged (no structure tree)")

            text_quality    = analyze_text_extraction_quality(pdf_path)
            font_mappings   = check_font_unicode_mappings(pdf)
            internal_links  = check_internal_links(pdf)
            doc_title_info  = check_document_title(pdf)
            reading_order   = check_reading_order(pdf_path, pdf, reading_order_sample)

            # Image detection: PyMuPDF preferred, pdfplumber fallback
            if PYMUPDF_AVAILABLE:
                img_detection = detect_images_pymupdf(pdf_path)
            else:
                img_detection = detect_images_pdfplumber(pdf_path)

            untagged_result = {
                'file':       str(pdf_path),
                'timestamp':  datetime.now().isoformat(),
                'pages':      page_count,
                'bookmarks':  bookmark_count,
                'tagged':     False,
                'language':   doc_language,
                'mime_type':  mime_type,
                'ocr_status': ocr_status,
                'pdf_version': pdf_version,
                'is_pdf_a':   is_pdf_a,
                'pdf_a_level': pdf_a_level,
                'headings':   {},
                'heading_hierarchy': {'valid': False, 'issues': []},
                'figures': {
                    'total':          img_detection.get('total_figures', 0),
                    'with_alt_text':  0,
                    'empty_alt':      0,
                    'generic_alt':    0,
                    'good_alt':       0,
                    'source':         img_detection.get('method', 'fallback'),
                    'full_page_scans': img_detection.get('full_page_scans', 0),
                },
                'tables':      {'total_tables': 0, 'tables_with_headers': 0, 'total_th': 0, 'total_td': 0},
                'text_quality': text_quality,
                'font_mappings': font_mappings,
                'bookmark_comparison': {
                    'bookmark_count': bookmark_count, 'heading_count': 0,
                    'bookmarks_exist': bookmark_count > 0, 'max_bookmark_depth': 0,
                    'max_heading_depth': 0, 'depth_matches': False, 'coverage': 0,
                },
                'internal_links':  internal_links,
                'document_title':  doc_title_info,
                'reading_order':   reading_order,
            }

            verapdf_validation = run_verapdf_validation(pdf_path)
            untagged_result['verapdf'] = verapdf_validation
            return untagged_result

        struct_root = pdf.Root['/StructTreeRoot']
        k = struct_root.get('/K', [])

        heading_counts = {}
        for level in range(1, 7):
            tag   = f'/H{level}'
            count = count_structure_elements(k, tag)
            if count > 0:
                heading_counts[f'H{level}'] = count

        hierarchy_issues   = check_heading_hierarchy(k)
        alt_stats          = analyze_alt_text_quality(k)
        table_stats        = check_table_headers(k)
        text_quality       = analyze_text_extraction_quality(pdf_path)
        font_mappings      = check_font_unicode_mappings(pdf)
        bookmark_comparison = compare_bookmarks_to_headings(pdf, k)
        internal_links     = check_internal_links(pdf)
        doc_title_info     = check_document_title(pdf)
        reading_order      = check_reading_order(pdf_path, pdf, reading_order_sample)

    verapdf_validation = run_verapdf_validation(pdf_path)

    return {
        'file':       str(pdf_path),
        'timestamp':  datetime.now().isoformat(),
        'pages':      page_count,
        'bookmarks':  bookmark_count,
        'tagged':     True,
        'language':   doc_language,
        'mime_type':  mime_type,
        'ocr_status': ocr_status,
        'pdf_version': pdf_version,
        'is_pdf_a':   is_pdf_a,
        'pdf_a_level': pdf_a_level,
        'headings':   heading_counts,
        'heading_hierarchy': {'valid': len(hierarchy_issues) == 0, 'issues': hierarchy_issues},
        'figures':    {**alt_stats, 'source': 'structure_tree'},
        'tables':     table_stats,
        'text_quality': text_quality,
        'font_mappings': font_mappings,
        'bookmark_comparison': bookmark_comparison,
        'internal_links': internal_links,
        'document_title': doc_title_info,
        'reading_order':  reading_order,
        'verapdf':    verapdf_validation,
    }
def format_text_report(analysis: Dict[str, Any]) -> str:
    """Format analysis results as human-readable text."""
    lines = []
    lines.append("=" * 70)
    lines.append("PDF ACCESSIBILITY ANALYSIS")
    lines.append("=" * 70)
    lines.append("")
    lines.append(f"File: {Path(analysis['file']).name}")
    lines.append(f"Path: {analysis['file']}")
    lines.append("")

    lines.append("DOCUMENT STATISTICS")
    lines.append("-" * 70)
    lines.append(f"  Pages: {analysis['pages']}")
    lines.append(f"  Bookmarks: {analysis['bookmarks']}")
    lines.append(f"  Tagged: {'Yes ✓' if analysis['tagged'] else 'No ✗'}")

    pdf_ver = analysis.get('pdf_version')
    if pdf_ver:
        label = f"PDF {pdf_ver}"
        if analysis.get('is_pdf_a'):
            label += f" / PDF/A-{analysis.get('pdf_a_level', '?')}"
        lines.append(f"  File Format: {label}")

    lang = analysis.get('language')
    lines.append(f"  Language: {lang + ' ✓' if lang else 'Not declared ✗'}")
    lines.append("")

    if analysis['tagged']:
        lines.append("HEADINGS")
        lines.append("-" * 70)
        headings = analysis['headings']
        if headings:
            total_headings = sum(headings.values())
            lines.append(f"  Total headings: {total_headings}")
            for level in ['H1', 'H2', 'H3', 'H4', 'H5', 'H6']:
                if level in headings:
                    lines.append(f"    {level}: {headings[level]}")
            hierarchy = analysis.get('heading_hierarchy', {})
            if hierarchy.get('valid'):
                lines.append(f"  Heading hierarchy: Valid ✓")
            else:
                issues = hierarchy.get('issues', [])
                lines.append(f"  Heading hierarchy: {len(issues)} issue(s) found ✗")
                for issue in issues[:5]:
                    lines.append(f"    • {issue['message']}")
                if len(issues) > 5:
                    lines.append(f"    ... and {len(issues) - 5} more")
        else:
            lines.append("  No headings found")
        lines.append("")

        lines.append("FIGURES & ALT TEXT")
        lines.append("-" * 70)
        fig_data = analysis['figures']
        total = fig_data['total']
        lines.append(f"  Total figures: {total}")
        if total > 0:
            good_alt    = fig_data.get('good_alt', 0)
            generic_alt = fig_data.get('generic_alt', 0)
            empty_alt   = fig_data.get('empty_alt', 0)
            lines.append(f"  Figures with good alt text: {good_alt}")
            lines.append(f"  Figures with generic alt text: {generic_alt}")
            lines.append(f"  Figures with empty/missing alt text: {empty_alt}")
            good_pct = (good_alt / total * 100) if total > 0 else 0
            status = '✓' if good_alt == total else ('⚠' if good_alt > total * 0.5 else '✗')
            lines.append(f"  Good alt text coverage: {good_pct:.1f}% {status}")
        lines.append("")
    else:
        # Untagged — show PyMuPDF fallback image results
        lines.append("FIGURES (PyMuPDF detection — untagged PDF)")
        lines.append("-" * 70)
        fig_data   = analysis.get('figures', {})
        total      = fig_data.get('total', 0)
        scans      = fig_data.get('full_page_scans', 0)
        lines.append(f"  Embedded figures detected: {total}")
        if scans:
            lines.append(f"  Full-page scans filtered out: {scans}")
        lines.append(f"  Alt text status: Cannot verify (PDF is untagged)")
        lines.append("")

    # Text extraction quality
    text_quality = analysis.get('text_quality', {})
    if text_quality.get('available'):
        lines.append("TEXT EXTRACTION QUALITY")
        lines.append("-" * 70)
        total_chars = text_quality.get('total_chars', 0)
        if total_chars > 0:
            unmapped    = text_quality.get('unmapped_chars', 0)
            replacement = text_quality.get('replacement_chars', 0)
            ligatures   = text_quality.get('ligature_artifacts', 0)
            lines.append(f"  Total characters analyzed: {total_chars:,}")
            lines.append(f"  Unmapped Unicode chars: {'None ✓' if unmapped == 0 else str(unmapped) + ' ✗'}")
            lines.append(f"  Replacement chars: {'None ✓' if replacement == 0 else str(replacement) + ' ✗'}")
            if ligatures:
                lines.append(f"  Ligature chars: {ligatures}")
            if text_quality.get('image_text_likely'):
                lines.append(f"  Image-based text likely: Yes ✗")
        else:
            lines.append("  No text content found ⚠")
        lines.append("")

    # Font mappings
    font_maps = analysis.get('font_mappings', {})
    if font_maps.get('total_fonts', 0) > 0:
        lines.append("FONT UNICODE MAPPINGS")
        lines.append("-" * 70)
        total             = font_maps['total_fonts']
        without_tounicode = font_maps.get('fonts_without_tounicode', 0)
        lines.append(f"  Total fonts (sampled): {total}")
        lines.append(f"  Embedded fonts: {font_maps.get('embedded_fonts', 0)}")
        lines.append(f"  Non-embedded fonts: {font_maps.get('non_embedded_fonts', 0)}")
        if without_tounicode > 0:
            pct = (without_tounicode / total * 100)
            lines.append(f"  Fonts without ToUnicode CMap: {without_tounicode} ({pct:.1f}%) ✗")
        else:
            lines.append(f"  All fonts have ToUnicode CMap: ✓")
        lines.append("")

    # Document metadata
    doc_title = analysis.get('document_title', {})
    lines.append("DOCUMENT METADATA")
    lines.append("-" * 70)
    if doc_title.get('title_in_metadata'):
        title = doc_title.get('title', '')
        lines.append(f"  Title: {title[:60]}{'...' if len(title) > 60 else ''} ✓")
    else:
        lines.append(f"  Title: Not set ✗")
    if doc_title.get('author'):
        lines.append(f"  Author: {doc_title.get('author', '')[:40]}")
    lines.append("")

    # veraPDF
    verapdf = analysis.get('verapdf', {})
    if verapdf.get('available'):
        lines.append("VERAPDF VALIDATION")
        lines.append("-" * 70)
        profiles = verapdf.get('profiles', {})
        for profile_name, profile_data in profiles.items():
            if 'error' in profile_data:
                lines.append(f"  {profile_name}: ERROR — {profile_data['error']}")
                continue
            compliant = profile_data.get('compliant', False)
            status    = '✓ PASS' if compliant else '✗ FAIL'
            lines.append(f"  {profile_name}: {status}")
            lines.append(f"    Passed rules: {profile_data.get('passed_rules', 0)}/{profile_data.get('total_rules', 0)}")
            lines.append(f"    Failed rules: {profile_data.get('failed_rules', 0)}")
            for i, rule in enumerate(profile_data.get('failed_rule_summaries', [])[:3], 1):
                lines.append(f"      {i}. {rule.get('specification','')} §{rule.get('clause','')}: {rule.get('description','')[:80]}...")
            lines.append("")

    # Summary
    lines.append("ACCESSIBILITY SUMMARY")
    lines.append("-" * 70)
    checks_passed = 0
    checks_total  = 0

    def add_check(passed, label_pass, label_fail):
        nonlocal checks_passed, checks_total
        checks_total += 1
        if passed:
            checks_passed += 1
            lines.append(f"  ✓ {label_pass}")
        else:
            lines.append(f"  ✗ {label_fail}")

    add_check(analysis['tagged'], "PDF is tagged", "PDF is not tagged")
    add_check(bool(analysis.get('language')), "Document language declared", "Document language not declared")

    text_quality = analysis.get('text_quality', {})
    if text_quality.get('available') and text_quality.get('total_chars', 0) > 0:
        no_unicode_issues = text_quality.get('unmapped_chars', 0) == 0 and text_quality.get('replacement_chars', 0) == 0
        add_check(no_unicode_issues, "No Unicode mapping issues", "Unicode mapping issues detected")
        add_check(not text_quality.get('image_text_likely'), "Text is properly extractable", "Document appears image-based")

    font_maps = analysis.get('font_mappings', {})
    if font_maps.get('total_fonts', 0) > 0:
        add_check(font_maps.get('fonts_without_tounicode', 0) == 0, "All fonts have Unicode mappings", "Some fonts missing Unicode mappings")

    if analysis.get('bookmarks', 0) > 0:
        add_check(True, "Bookmarks present for navigation", "")

    doc_title = analysis.get('document_title', {})
    add_check(doc_title.get('title_in_metadata'), "Document title in metadata", "Document title not in metadata")

    # Reading order — reported but NOT counted in score (confirmed weak heuristic)
    reading_order = analysis.get('reading_order', {})
    if reading_order.get('available') and reading_order.get('pages_checked', 0) > 0:
        pages_with_issues = reading_order.get('pages_with_issues', 0)
        pages_checked     = reading_order.get('pages_checked', 0)
        issue_pct         = (pages_with_issues / pages_checked * 100) if pages_checked > 0 else 0
        note = f"(informational only — heuristic, not scored)"
        if pages_with_issues == 0:
            lines.append(f"  ~ Reading order looks OK {note}")
        else:
            lines.append(f"  ~ Reading order issues on {issue_pct:.0f}% of pages {note}")

    verapdf = analysis.get('verapdf', {})
    if verapdf.get('available'):
        for profile_name, profile_data in verapdf.get('profiles', {}).items():
            if 'error' not in profile_data:
                add_check(profile_data.get('compliant', False),
                          f"{profile_name} compliant",
                          f"{profile_name} non-compliant ({profile_data.get('failed_rules', 0)} failures)")

    lines.append("")
    score_pct = (checks_passed / checks_total * 100) if checks_total > 0 else 0
    lines.append(f"Overall: {checks_passed}/{checks_total} checks passed ({score_pct:.0f}%)")
    lines.append("")
    lines.append("=" * 70)

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Fulcrum ticket-format JSON output
# ---------------------------------------------------------------------------

def analyze_pdf_fulcrum(pdf_path: Path) -> Dict[str, Any]:
    """
    Run veraPDF validation and assemble the Fulcrum ticket-format JSON
    using the PDF Analyzer stack (pikepdf + PyMuPDF).

    Returns the Fulcrum ticket-format JSON schema from fulcrum_json.assemble().
    """
    from fulcrum_json import assemble
    verapdf      = run_verapdf_validation(pdf_path)
    doc_type     = detect_document_type(pdf_path)
    return assemble(pdf_path, verapdf, doc_type=doc_type, page_info_engine='pymupdf', source='pdf_analyzer')


def main():
    parser = argparse.ArgumentParser(
        description="Analyze PDF accessibility features and output statistics."
    )
    parser.add_argument('--input',  type=Path, required=True, help='Path to PDF file to analyze')
    parser.add_argument('--output', type=Path, help='Base path for output files (without extension)')
    parser.add_argument('--verbose', action='store_true', help='Enable verbose logging')
    parser.add_argument(
        '--reading-order-sample',
        type=str, choices=['all', 'standard'], default='all',
        help='"all" = check all pages (default), "standard" = first 15 + 5 random'
    )

    args = parser.parse_args()
    setup_logging(args.verbose)

    if not args.input.exists():
        raise FileNotFoundError(f"Input PDF not found: {args.input}")

    output_base = args.output if args.output else args.input.parent / f"{args.input.stem}_analysis"
    output_txt  = output_base.with_suffix('.txt')
    output_json = output_base.with_suffix('.json')

    analysis    = analyze_pdf(args.input, args.reading_order_sample)
    text_report = format_text_report(analysis)

    output_txt.parent.mkdir(parents=True, exist_ok=True)
    output_txt.write_text(text_report, encoding='utf-8')
    logging.info(f"Text report written to: {output_txt}")

    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(analysis, indent=2, ensure_ascii=False), encoding='utf-8')
    logging.info(f"JSON report written to: {output_json}")

    print()
    print(text_report)

if __name__ == '__main__':
    main()
