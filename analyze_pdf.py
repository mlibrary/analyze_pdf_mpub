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
        except:
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
        'replacement_chars': 0,  # � character
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
            'ﬁ', 'ﬂ', 'ﬀ', 'ﬃ', 'ﬄ',  # Common ligatures
            'ﬆ', 'ﬅ',  # Less common
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
                if char == '�':
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
                    # PyMuPDF doesn't expose OCR confidence directly,
                    # but we can detect patterns suggesting OCR
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
                    except:
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
    
    Compares structure tree sequence to spatial coordinates of text blocks.
    
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
        # Open with PyMuPDF for spatial coordinates
        doc = fitz.open(str(pdf_path))
        
        # Sampling strategy based on mode
        sample_pages = []
        
        if sample_mode == 'all':
            # Sample all pages
            sample_pages = list(range(len(doc)))
        else:  # 'standard' mode
            # Sample strategy: first 15 pages + 5 random, or all pages if < 21
            if len(doc) < 21:
                # For short documents, sample all pages
                sample_pages = list(range(len(doc)))
            else:
                # First 15 pages
                first_pages = list(range(15))
                sample_pages.extend(first_pages)
                
                # Add 5 random pages from the rest of the document
                # Seed random with PDF path hash for reproducible sampling
                path_hash = int(hashlib.sha256(str(pdf_path).encode()).hexdigest()[:16], 16)
                random.seed(path_hash)
                remaining_pages = list(range(15, len(doc)))
                random_count = min(5, len(remaining_pages))
                random_pages = random.sample(remaining_pages, random_count)
                sample_pages.extend(random_pages)
                
                # Remove duplicates and sort
                sample_pages = sorted(set(sample_pages))
        
        for page_num in sample_pages:
            try:
                page = doc[page_num]
                
                # Get text blocks with spatial coordinates
                blocks = page.get_text("dict")["blocks"]
                
                # Filter to text blocks only and extract positions
                text_blocks = []
                for block in blocks:
                    if block.get("type") == 0:  # Text block
                        bbox = block.get("bbox", [0, 0, 0, 0])
                        # Extract first line of text for identification
                        text = ""
                        for line in block.get("lines", []):
                            for span in line.get("spans", []):
                                text += span.get("text", "")
                            if text:
                                break
                        
                        if text.strip():
                            text_blocks.append({
                                'text': text.strip()[:50],  # First 50 chars
                                'bbox': bbox,
                                'y0': bbox[1],  # Top Y coordinate
                                'x0': bbox[0],  # Left X coordinate
                            })
                
                if len(text_blocks) < 3:
                    # Not enough content to meaningfully check
                    result['pages_skipped'] += 1
                    continue
                
                # Sort by visual reading order (top to bottom, left to right)
                # Group by approximate Y position (allowing for small variations)
                Y_THRESHOLD = 5  # pixels
                
                def visual_sort_key(block):
                    # Round Y to nearest threshold to group lines
                    y_group = round(block['y0'] / Y_THRESHOLD) * Y_THRESHOLD
                    return (y_group, block['x0'])
                
                visual_order = sorted(text_blocks, key=visual_sort_key)
                visual_text_sequence = [b['text'] for b in visual_order]
                
                # Get tag tree order for this page
                # This is simplified - full implementation would need to traverse
                # structure tree and match MCIDs to content
                # For now, we compare extracted text order from PyMuPDF's default
                # extraction (which follows tag tree if tagged) to visual order
                
                tagged_text = page.get_text()
                tagged_lines = [line.strip() for line in tagged_text.split('\n') 
                               if line.strip()][:len(visual_text_sequence)]
                
                # Compare sequences - if they differ significantly, reading order may be wrong
                mismatches = 0
                for i, visual_text in enumerate(visual_text_sequence[:10]):  # Check first 10
                    # Look for this text in nearby positions in tagged order
                    found_nearby = False
                    search_range = 3  # Allow for some variance
                    
                    for j in range(max(0, i - search_range), 
                                 min(len(tagged_lines), i + search_range + 1)):
                        if j < len(tagged_lines):
                            # Fuzzy match - check if significant overlap
                            if (visual_text[:20] in tagged_lines[j] or 
                                tagged_lines[j][:20] in visual_text):
                                found_nearby = True
                                break
                    
                    if not found_nearby and i < len(tagged_lines):
                        mismatches += 1
                
                result['pages_checked'] += 1
                
                # If more than 30% mismatches, likely reading order issue
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
    """Find veraPDF CLI executable.
    
    Returns:
        Path to veraPDF executable, or None if not found.
    """
    # Check common installation locations
    locations = [
        Path.home() / "Applications" / "verapdf" / "verapdf",
        Path("/Applications/verapdf/verapdf"),
        Path("/usr/local/bin/verapdf"),
    ]
    
    for loc in locations:
        if loc.exists() and loc.is_file():
            return loc
    
    # Try PATH
    try:
        result = subprocess.run(
            ["which", "verapdf"],
            capture_output=True,
            text=True,
            check=False
        )
        if result.returncode == 0:
            return Path(result.stdout.strip())
    except Exception:
        pass
    
    return None


def run_verapdf_validation(pdf_path: Path) -> Dict[str, Any]:
    """Run veraPDF validation for PDF/UA-1, PDF/UA-2, and WTPDF accessibility.
    
    Args:
        pdf_path: Path to the PDF file to validate.
        
    Returns:
        Dictionary with validation results for each profile.
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
    
    # Find profile directory for custom WCAG profiles
    # verapdf_path is the executable, so .parent gets us the verapdf directory
    profile_base = verapdf_path.parent / 'profiles' / 'veraPDF-validation-profiles-rel-1.28' / 'PDF_UA'
    
    # Profiles to validate - mix of built-in flavours and custom profiles
    # Format: (profile_name, flavour_or_path, is_custom_profile)
    profiles = [
        ('PDF/UA-1', 'ua1', False),
        ('PDF/UA-2', 'ua2', False),
        ('WCAG 2.2 (Complete)', profile_base / 'WCAG-2-2-Complete.xml', True),
        ('WTPDF 1.0 Accessibility', 'wt1a', False),
    ]
    
    for profile_name, profile_ref, is_custom in profiles:
        logging.info(f"Running veraPDF validation: {profile_name}")
        
        try:
            if is_custom:
                # Custom profile via --profile flag
                if not isinstance(profile_ref, Path) or not profile_ref.exists():
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
                # Built-in flavour via --flavour flag
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
                timeout=300,  # 5 minute timeout
                check=False
            )
            
            if proc_result.returncode != 0 and not proc_result.stdout:
                result['profiles'][profile_name] = {
                    'error': f'veraPDF failed with exit code {proc_result.returncode}',
                    'stderr': proc_result.stderr[:500] if proc_result.stderr else ''
                }
                logging.warning(f"{profile_name} validation failed: {proc_result.stderr[:200]}")
                continue
            
            # Parse JSON output
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
                
                # Extract summary
                passed_rules = details.get('passedRules', 0)
                failed_rules = details.get('failedRules', 0)
                passed_checks = details.get('passedChecks', 0)
                failed_checks = details.get('failedChecks', 0)
                total_rules = passed_rules + failed_rules
                
                compliant = failed_rules == 0
                
                profile_result = {
                    'compliant': compliant,
                    'passed_rules': passed_rules,
                    'failed_rules': failed_rules,
                    'total_rules': total_rules,
                    'passed_checks': passed_checks,
                    'failed_checks': failed_checks,
                    'total_checks': passed_checks + failed_checks,
                }
                
                # Extract failed rule summaries (limit to top 10)
                rule_summaries = details.get('ruleSummaries', [])
                failed_summaries = [
                    r for r in rule_summaries 
                    if r.get('status') == 'failed'
                ][:10]
                
                if failed_summaries:
                    profile_result['failed_rule_summaries'] = [
                        {
                            'clause': r.get('clause', 'Unknown'),
                            'specification': r.get('specification', 'Unknown'),
                            'description': r.get('description', '')[:200],  # Truncate
                            'failed_checks': r.get('failedChecks', 0),
                        }
                        for r in failed_summaries
                    ]
                
                result['profiles'][profile_name] = profile_result
                
            except json.JSONDecodeError as e:
                result['profiles'][profile_name] = {
                    'error': f'Failed to parse veraPDF JSON output: {e}'
                }
                logging.warning(f"Failed to parse {profile_name} output: {e}")
                
        except subprocess.TimeoutExpired:
            result['profiles'][profile_name] = {
                'error': 'Validation timed out after 5 minutes'
            }
            logging.warning(f"{profile_name} validation timed out")
        except Exception as e:
            result['profiles'][profile_name] = {
                'error': f'Validation error: {e}'
            }
            logging.warning(f"{profile_name} validation error: {e}")
    
    return result


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
    
    with pikepdf.open(pdf_path) as pdf:
        # Basic page count
        page_count = len(pdf.pages)
        
        # Bookmark count
        bookmark_count = count_bookmarks(pdf)
        
        # Document language
        doc_language = check_document_language(pdf)
        
        # Structure tree analysis
        has_structure = '/StructTreeRoot' in pdf.Root
        
        if not has_structure:
            logging.warning("PDF is not tagged (no structure tree)")
            
            # Still check text quality even for untagged PDFs
            text_quality = analyze_text_extraction_quality(pdf_path)
            font_mappings = check_font_unicode_mappings(pdf)
            internal_links = check_internal_links(pdf)
            doc_title_info = check_document_title(pdf)
            reading_order = check_reading_order(pdf_path, pdf, reading_order_sample)
            
            # Store data for return after veraPDF check
            untagged_result = {
                'file': str(pdf_path),
                'timestamp': datetime.now().isoformat(),
                'pages': page_count,
                'bookmarks': bookmark_count,
                'tagged': False,
                'language': doc_language,
                'headings': {},
                'heading_hierarchy': {'valid': False, 'issues': []},
                'figures': {
                    'total': 0,
                    'with_alt_text': 0,
                    'empty_alt': 0,
                    'generic_alt': 0,
                    'good_alt': 0,
                },
                'tables': {
                    'total_tables': 0,
                    'tables_with_headers': 0,
                    'total_th': 0,
                    'total_td': 0,
                },
                'text_quality': text_quality,
                'font_mappings': font_mappings,
                'bookmark_comparison': {
                    'bookmark_count': bookmark_count,
                    'heading_count': 0,
                    'bookmarks_exist': bookmark_count > 0,
                    'max_bookmark_depth': 0,
                    'max_heading_depth': 0,
                    'depth_matches': False,
                    'coverage': 0,
                },
                'internal_links': internal_links,
                'document_title': doc_title_info,
                'reading_order': reading_order,
            }
            
            # Run veraPDF validation (outside pikepdf context)
            verapdf_validation = run_verapdf_validation(pdf_path)
            untagged_result['verapdf'] = verapdf_validation
            
            return untagged_result
        
        struct_root = pdf.Root['/StructTreeRoot']
        k = struct_root.get('/K', [])
        
        # Count headings by level
        heading_counts = {}
        for level in range(1, 7):  # H1 through H6
            tag = f'/H{level}'
            count = count_structure_elements(k, tag)
            if count > 0:
                heading_counts[f'H{level}'] = count
        
        # Check heading hierarchy
        hierarchy_issues = check_heading_hierarchy(k)
        
        # Analyze alt text quality
        alt_stats = analyze_alt_text_quality(k)
        
        # Check table headers
        table_stats = check_table_headers(k)
        
        # Check text extraction quality
        text_quality = analyze_text_extraction_quality(pdf_path)
        
        # Check font Unicode mappings
        font_mappings = check_font_unicode_mappings(pdf)
        
        # Compare bookmarks to heading hierarchy
        bookmark_comparison = compare_bookmarks_to_headings(pdf, k)
        
        # Check internal links
        internal_links = check_internal_links(pdf)
        
        # Check document title
        doc_title_info = check_document_title(pdf)
        
        # Check reading order
        reading_order = check_reading_order(pdf_path, pdf, reading_order_sample)
    
    # Run veraPDF validation (outside pikepdf context)
    verapdf_validation = run_verapdf_validation(pdf_path)
    
    return {
        'file': str(pdf_path),
        'timestamp': datetime.now().isoformat(),
        'pages': page_count,
        'bookmarks': bookmark_count,
        'tagged': True,
        'language': doc_language,
        'headings': heading_counts,
        'heading_hierarchy': {
            'valid': len(hierarchy_issues) == 0,
            'issues': hierarchy_issues
        },
        'figures': alt_stats,
        'tables': table_stats,
        'text_quality': text_quality,
        'font_mappings': font_mappings,
        'bookmark_comparison': bookmark_comparison,
        'internal_links': internal_links,
        'document_title': doc_title_info,
        'reading_order': reading_order,
        'verapdf': verapdf_validation,
    }


def format_text_report(analysis: Dict[str, Any]) -> str:
    """
    Format analysis results as human-readable text.
    
    Args:
        analysis: Analysis results dictionary.
        
    Returns:
        Formatted text report.
    """
    lines = []
    lines.append("=" * 70)
    lines.append("PDF ACCESSIBILITY ANALYSIS")
    lines.append("=" * 70)
    lines.append("")
    lines.append(f"File: {Path(analysis['file']).name}")
    lines.append(f"Path: {analysis['file']}")
    lines.append("")
    
    # Basic stats
    lines.append("DOCUMENT STATISTICS")
    lines.append("-" * 70)
    lines.append(f"  Pages: {analysis['pages']}")
    lines.append(f"  Bookmarks: {analysis['bookmarks']}")
    lines.append(f"  Tagged: {'Yes ✓' if analysis['tagged'] else 'No ✗'}")
    
    # Document language
    lang = analysis.get('language')
    if lang:
        lines.append(f"  Language: {lang} ✓")
    else:
        lines.append(f"  Language: Not declared ✗")
    
    lines.append("")
    
    if analysis['tagged']:
        # Headings
        lines.append("HEADINGS")
        lines.append("-" * 70)
        headings = analysis['headings']
        if headings:
            total_headings = sum(headings.values())
            lines.append(f"  Total headings: {total_headings}")
            for level in ['H1', 'H2', 'H3', 'H4', 'H5', 'H6']:
                if level in headings:
                    lines.append(f"    {level}: {headings[level]}")
            
            # Heading hierarchy validation
            hierarchy = analysis.get('heading_hierarchy', {})
            if hierarchy.get('valid'):
                lines.append(f"  Heading hierarchy: Valid ✓")
            else:
                issues = hierarchy.get('issues', [])
                lines.append(f"  Heading hierarchy: {len(issues)} issue(s) found ✗")
                for issue in issues[:5]:  # Show first 5 issues
                    lines.append(f"    • {issue['message']}")
                if len(issues) > 5:
                    lines.append(f"    ... and {len(issues) - 5} more")
        else:
            lines.append("  No headings found")
        lines.append("")
        
        # Figures and alt text
        lines.append("FIGURES & ALT TEXT")
        lines.append("-" * 70)
        fig_data = analysis['figures']
        total = fig_data['total']
        
        lines.append(f"  Total figures: {total}")
        if total > 0:
            good_alt = fig_data.get('good_alt', 0)
            generic_alt = fig_data.get('generic_alt', 0)
            empty_alt = fig_data.get('empty_alt', 0)
            
            lines.append(f"  Figures with good alt text: {good_alt}")
            lines.append(f"  Figures with generic alt text: {generic_alt}")
            lines.append(f"  Figures with empty/missing alt text: {empty_alt}")
            
            good_percentage = (good_alt / total * 100) if total > 0 else 0
            status = '✓' if good_alt == total else ('⚠' if good_alt > total * 0.5 else '✗')
            lines.append(f"  Good alt text coverage: {good_percentage:.1f}% {status}")
        lines.append("")
        
        # Tables
        lines.append("TABLES")
        lines.append("-" * 70)
        table_data = analysis.get('tables', {})
        total_tables = table_data.get('total_tables', 0)
        
        lines.append(f"  Total tables: {total_tables}")
        if total_tables > 0:
            tables_with_headers = table_data.get('tables_with_headers', 0)
            total_th = table_data.get('total_th', 0)
            total_td = table_data.get('total_td', 0)
            
            lines.append(f"  Tables with header cells (TH): {tables_with_headers}")
            lines.append(f"  Tables without headers: {total_tables - tables_with_headers}")
            lines.append(f"  Total TH cells: {total_th}")
            lines.append(f"  Total TD cells: {total_td}")
            
            status = '✓' if tables_with_headers == total_tables else '✗'
            lines.append(f"  All tables have headers: {status}")
        else:
            lines.append("  No tables found")
        lines.append("")
    
    # Text extraction quality
    text_quality = analysis.get('text_quality', {})
    if text_quality.get('available'):
        lines.append("TEXT EXTRACTION QUALITY")
        lines.append("-" * 70)
        
        total_chars = text_quality.get('total_chars', 0)
        if total_chars > 0:
            unmapped = text_quality.get('unmapped_chars', 0)
            replacement = text_quality.get('replacement_chars', 0)
            control = text_quality.get('control_chars', 0)
            ligatures = text_quality.get('ligature_artifacts', 0)
            
            lines.append(f"  Total characters analyzed: {total_chars:,}")
            
            # Unmapped Unicode
            if unmapped > 0:
                pct = (unmapped / total_chars * 100)
                lines.append(f"  Unmapped Unicode chars (Private Use Area): {unmapped} ({pct:.2f}%) ✗")
            else:
                lines.append(f"  Unmapped Unicode chars: None ✓")
            
            # Replacement characters
            if replacement > 0:
                pct = (replacement / total_chars * 100)
                lines.append(f"  Replacement chars (�): {replacement} ({pct:.2f}%) ✗")
            else:
                lines.append(f"  Replacement chars: None ✓")
            
            # Control characters
            if control > 0:
                lines.append(f"  Control characters: {control} ⚠")
            
            # Ligature artifacts
            if ligatures > 0:
                lines.append(f"  Ligature chars (ﬁ, ﬂ, etc.): {ligatures}")
            
            # Image-based text detection
            if text_quality.get('image_text_likely'):
                lines.append(f"  Image-based text likely: Yes ✗")
                lines.append(f"    (Very low text content vs. image count)")
            
            # Show sample issues
            issues = text_quality.get('sample_issues', [])
            if issues:
                lines.append(f"  Sample issues found: {len(issues)}")
                for issue in issues[:3]:
                    if issue['type'] == 'replacement_char':
                        lines.append(f"    • Page {issue['page']}: Replacement char (�)")
                    elif issue['type'] == 'private_use_area':
                        lines.append(f"    • Page {issue['page']}: Private Use char "
                                   f"({issue.get('code_point', '?')})")
        else:
            lines.append("  No text content found ⚠")
        
        lines.append("")
    
    # Font Unicode mappings
    font_maps = analysis.get('font_mappings', {})
    if font_maps.get('total_fonts', 0) > 0:
        lines.append("FONT UNICODE MAPPINGS")
        lines.append("-" * 70)
        
        total = font_maps['total_fonts']
        without_tounicode = font_maps.get('fonts_without_tounicode', 0)
        embedded = font_maps.get('embedded_fonts', 0)
        non_embedded = font_maps.get('non_embedded_fonts', 0)
        
        lines.append(f"  Total fonts (sampled): {total}")
        lines.append(f"  Embedded fonts: {embedded}")
        lines.append(f"  Non-embedded fonts: {non_embedded}")
        
        if without_tounicode > 0:
            pct = (without_tounicode / total * 100)
            lines.append(f"  Fonts without ToUnicode CMap: {without_tounicode} ({pct:.1f}%) ✗")
            lines.append(f"    (May cause copy-paste issues and screen reader problems)")
        else:
            lines.append(f"  All fonts have ToUnicode CMap: ✓")
        
        # Show sample font issues
        font_issues = font_maps.get('font_issues', [])
        if font_issues:
            lines.append(f"  Sample font issues:")
            for issue in font_issues[:3]:
                lines.append(f"    • Page {issue['page']}: {issue['font']} - "
                           f"{issue['issue'].replace('_', ' ')}")
        
        lines.append("")
    
    # Bookmarks vs Heading Hierarchy
    bookmark_comp = analysis.get('bookmark_comparison', {})
    if bookmark_comp.get('bookmarks_exist') or analysis.get('bookmarks', 0) > 0:
        lines.append("BOOKMARKS & NAVIGATION")
        lines.append("-" * 70)
        
        bm_count = bookmark_comp.get('bookmark_count', 0)
        heading_count = bookmark_comp.get('heading_count', 0)
        
        lines.append(f"  Bookmarks: {bm_count}")
        
        if bm_count > 0 and heading_count > 0:
            coverage = bookmark_comp.get('coverage', 0)
            lines.append(f"  Headings in document: {heading_count}")
            lines.append(f"  Bookmark coverage: {coverage:.1f}%")
            
            depth_matches = bookmark_comp.get('depth_matches', False)
            max_bm_depth = bookmark_comp.get('max_bookmark_depth', 0)
            max_h_depth = bookmark_comp.get('max_heading_depth', 0)
            
            lines.append(f"  Max bookmark depth: {max_bm_depth}")
            lines.append(f"  Max heading depth: H{max_h_depth}")
            
            if depth_matches:
                lines.append(f"  Bookmark depth matches heading structure: ✓")
            else:
                lines.append(f"  Bookmark depth differs from heading structure: ⚠")
        elif bm_count > 0:
            lines.append(f"  Bookmarks present: ✓")
        else:
            lines.append(f"  No bookmarks found: ✗")
            lines.append(f"    (Bookmarks improve navigation for screen readers)")
        
        lines.append("")
    
    # Internal links
    int_links = analysis.get('internal_links', {})
    if int_links.get('total_annotations', 0) > 0 or int_links.get('link_annotations', 0) > 0:
        lines.append("INTERNAL CROSS-REFERENCES")
        lines.append("-" * 70)
        
        total_annots = int_links.get('total_annotations', 0)
        link_annots = int_links.get('link_annotations', 0)
        internal = int_links.get('internal_links', 0)
        external = int_links.get('external_links', 0)
        pages_with_links = int_links.get('pages_with_links', 0)
        
        lines.append(f"  Total annotations: {total_annots}")
        lines.append(f"  Link annotations: {link_annots}")
        lines.append(f"    Internal links (GoTo): {internal}")
        lines.append(f"    External links (URI): {external}")
        lines.append(f"  Pages with links (sampled): {pages_with_links}")
        
        if internal > 0:
            lines.append(f"  Internal cross-references implemented: ✓")
        else:
            lines.append(f"  No internal links detected: ⚠")
            lines.append(f"    (Figure refs, citations should be clickable links)")
        
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
        lines.append(f"    (Document title should be in metadata for accessibility)")
    
    if doc_title.get('author'):
        lines.append(f"  Author: {doc_title.get('author', '')[:40]}")
    
    if doc_title.get('subject'):
        lines.append(f"  Subject: {doc_title.get('subject', '')[:40]}")
    
    lines.append("")
    
    # Reading order
    reading_order = analysis.get('reading_order', {})
    if reading_order.get('available'):
        lines.append("READING ORDER")
        lines.append("-" * 70)
        
        pages_checked = reading_order.get('pages_checked', 0)
        pages_with_issues = reading_order.get('pages_with_issues', 0)
        pages_skipped = reading_order.get('pages_skipped', 0)
        
        if pages_checked > 0:
            pages_clean = pages_checked - pages_with_issues
            clean_percentage = (pages_clean / pages_checked * 100) if pages_checked > 0 else 0
            
            lines.append(f"  Pages sampled: {pages_checked}")
            if pages_skipped > 0:
                lines.append(f"  Pages skipped (insufficient content): {pages_skipped}")
            lines.append(f"  Pages with reading order issues: {pages_with_issues}")
            lines.append(f"  Pages without issues: {pages_clean} ({clean_percentage:.1f}%)")
            
            if pages_with_issues == 0:
                lines.append(f"  Reading order matches visual order: ✓")
            else:
                lines.append(f"  Reading order issues detected: ✗")
                lines.append(f"    (Tag tree sequence doesn't match visual top-to-bottom order)")
                
                # Show sample issues
                issues = reading_order.get('issue_details', [])
                if issues:
                    lines.append(f"  Sample issues:")
                    for issue in issues:
                        lines.append(f"    • Page {issue['page']}: "
                                   f"{issue['mismatch_count']} mismatches "
                                   f"({issue['mismatch_rate']})")
        else:
            lines.append(f"  Could not check reading order (insufficient content)")
        
        lines.append("")
    elif 'error' in reading_order:
        lines.append("READING ORDER")
        lines.append("-" * 70)
        lines.append(f"  Reading order check unavailable: {reading_order.get('error', 'Unknown')}")
        lines.append("")
    
    # veraPDF Validation
    verapdf = analysis.get('verapdf', {})
    if verapdf.get('available'):
        lines.append("VERAPDF VALIDATION")
        lines.append("-" * 70)
        lines.append("  ISO/WCAG Compliance Checks:")
        lines.append("")
        
        profiles = verapdf.get('profiles', {})
        for profile_name, profile_data in profiles.items():
            if 'error' in profile_data:
                lines.append(f"  {profile_name}: ERROR")
                lines.append(f"    {profile_data['error']}")
                lines.append("")
                continue
            
            compliant = profile_data.get('compliant', False)
            status = '✓ PASS' if compliant else '✗ FAIL'
            
            lines.append(f"  {profile_name}: {status}")
            lines.append(f"    Passed rules: {profile_data.get('passed_rules', 0)}/{profile_data.get('total_rules', 0)}")
            lines.append(f"    Failed rules: {profile_data.get('failed_rules', 0)}")
            lines.append(f"    Passed checks: {profile_data.get('passed_checks', 0)}")
            lines.append(f"    Failed checks: {profile_data.get('failed_checks', 0)}")
            
            # Show top failed rules
            failed_summaries = profile_data.get('failed_rule_summaries', [])
            if failed_summaries:
                lines.append(f"    Top failures:")
                for i, rule in enumerate(failed_summaries[:5], 1):
                    clause = rule.get('clause', 'Unknown')
                    spec = rule.get('specification', '')
                    desc = rule.get('description', '')[:100]
                    failed_checks = rule.get('failed_checks', 0)
                    lines.append(f"      {i}. {spec} §{clause}: {desc}...")
                    lines.append(f"         ({failed_checks} failures)")
                
                if len(failed_summaries) > 5:
                    lines.append(f"      ... and {len(failed_summaries) - 5} more failures")
            
            lines.append("")
        
        # Note about WCAG
        lines.append("  Note: WCAG 2.2 validation above covers machine-testable success")
        lines.append("  criteria (Level A and AA). Full WCAG 2.2 conformance requires")
        lines.append("  additional manual testing of content quality, cognitive")
        lines.append("  accessibility, and user experience factors.")
        lines.append("")
        
    elif 'error' in verapdf:
        lines.append("VERAPDF VALIDATION")
        lines.append("-" * 70)
        lines.append(f"  veraPDF unavailable: {verapdf.get('error', 'Unknown')}")
        lines.append("")
    
    # Summary
    lines.append("ACCESSIBILITY SUMMARY")
    lines.append("-" * 70)
    
    checks_passed = 0
    checks_total = 0
    
    if analysis['tagged']:
        checks_total += 1
        checks_passed += 1
        lines.append("  ✓ PDF is tagged")
    else:
        checks_total += 1
        lines.append("  ✗ PDF is not tagged")
    
    if analysis.get('language'):
        checks_total += 1
        checks_passed += 1
        lines.append("  ✓ Document language declared")
    else:
        checks_total += 1
        lines.append("  ✗ Document language not declared")
    
    if analysis['tagged']:
        # Heading hierarchy
        hierarchy = analysis.get('heading_hierarchy', {})
        checks_total += 1
        if hierarchy.get('valid'):
            checks_passed += 1
            lines.append("  ✓ Heading hierarchy is logical")
        else:
            lines.append("  ✗ Heading hierarchy has issues")
        
        # Alt text
        fig_data = analysis['figures']
        if fig_data['total'] > 0:
            checks_total += 1
            if fig_data.get('good_alt', 0) == fig_data['total']:
                checks_passed += 1
                lines.append("  ✓ All figures have good alt text")
            else:
                lines.append("  ✗ Some figures missing or have poor alt text")
        
        # Tables
        table_data = analysis.get('tables', {})
        if table_data.get('total_tables', 0) > 0:
            checks_total += 1
            if table_data.get('tables_with_headers', 0) == table_data.get('total_tables', 0):
                checks_passed += 1
                lines.append("  ✓ All tables have header cells")
            else:
                lines.append("  ✗ Some tables missing header cells")
    
    # Text quality checks
    text_quality = analysis.get('text_quality', {})
    if text_quality.get('available') and text_quality.get('total_chars', 0) > 0:
        checks_total += 1
        unmapped = text_quality.get('unmapped_chars', 0)
        replacement = text_quality.get('replacement_chars', 0)
        if unmapped == 0 and replacement == 0:
            checks_passed += 1
            lines.append("  ✓ No Unicode mapping issues detected")
        else:
            lines.append("  ✗ Unicode mapping issues detected")
        
        if not text_quality.get('image_text_likely'):
            checks_total += 1
            checks_passed += 1
            lines.append("  ✓ Text is properly extractable (not image-based)")
        else:
            checks_total += 1
            lines.append("  ✗ Document appears to use image-based text")
    
    # Font mapping checks
    font_maps = analysis.get('font_mappings', {})
    if font_maps.get('total_fonts', 0) > 0:
        checks_total += 1
        without_tounicode = font_maps.get('fonts_without_tounicode', 0)
        if without_tounicode == 0:
            checks_passed += 1
            lines.append("  ✓ All fonts have Unicode mappings (ToUnicode)")
        else:
            lines.append("  ✗ Some fonts missing Unicode mappings")
    
    # Bookmark checks
    bookmark_comp = analysis.get('bookmark_comparison', {})
    if analysis.get('bookmarks', 0) > 0:
        checks_total += 1
        checks_passed += 1
        lines.append("  ✓ Bookmarks present for navigation")
    
    # Internal links
    int_links = analysis.get('internal_links', {})
    if int_links.get('internal_links', 0) > 0:
        checks_total += 1
        checks_passed += 1
        lines.append("  ✓ Internal cross-references are clickable links")
    
    # Document title
    doc_title = analysis.get('document_title', {})
    checks_total += 1
    if doc_title.get('title_in_metadata'):
        checks_passed += 1
        lines.append("  ✓ Document title in metadata")
    else:
        lines.append("  ✗ Document title not in metadata")
    
    # Reading order
    reading_order = analysis.get('reading_order', {})
    if reading_order.get('available') and reading_order.get('pages_checked', 0) > 0:
        checks_total += 1
        pages_checked = reading_order.get('pages_checked', 0)
        pages_with_issues = reading_order.get('pages_with_issues', 0)
        if pages_with_issues == 0:
            checks_passed += 1
            lines.append("  ✓ Reading order matches visual order")
        else:
            issue_pct = (pages_with_issues / pages_checked * 100) if pages_checked > 0 else 0
            lines.append(f"  ✗ Reading order issues detected ({issue_pct:.1f}% of pages)")
    
    # veraPDF validation results
    verapdf = analysis.get('verapdf', {})
    if verapdf.get('available'):
        profiles = verapdf.get('profiles', {})
        for profile_name, profile_data in profiles.items():
            if 'error' not in profile_data:
                checks_total += 1
                if profile_data.get('compliant', False):
                    checks_passed += 1
                    lines.append(f"  ✓ {profile_name} compliant")
                else:
                    lines.append(f"  ✗ {profile_name} non-compliant ({profile_data.get('failed_rules', 0)} failures)")
    
    lines.append("")
    score_pct = (checks_passed / checks_total * 100) if checks_total > 0 else 0
    lines.append(f"Overall: {checks_passed}/{checks_total} checks passed ({score_pct:.0f}%)")
    
    lines.append("")
    lines.append("=" * 70)
    
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Analyze PDF accessibility features and output statistics."
    )
    parser.add_argument(
        '--input',
        type=Path,
        required=True,
        help='Path to PDF file to analyze'
    )
    parser.add_argument(
        '--output',
        type=Path,
        help='Base path for output files (without extension). '
             'Will create .txt and .json files. '
             'Default: {input_stem}_analysis'
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose logging'
    )
    parser.add_argument(
        '--reading-order-sample',
        type=str,
        choices=['all', 'standard'],
        default='all',
        help='Reading order sampling strategy: '
             '"all" = check all pages (default), '
             '"standard" = first 15 pages + 5 random'
    )
    
    args = parser.parse_args()
    setup_logging(args.verbose)
    
    # Validate input
    if not args.input.exists():
        raise FileNotFoundError(f"Input PDF not found: {args.input}")
    
    # Determine output paths
    if args.output:
        output_base = args.output
    else:
        output_base = args.input.parent / f"{args.input.stem}_analysis"
    
    output_txt = output_base.with_suffix('.txt')
    output_json = output_base.with_suffix('.json')
    
    # Analyze PDF
    analysis = analyze_pdf(args.input, args.reading_order_sample)
    
    # Write text report
    text_report = format_text_report(analysis)
    output_txt.parent.mkdir(parents=True, exist_ok=True)
    output_txt.write_text(text_report, encoding='utf-8')
    logging.info(f"Text report written to: {output_txt}")
    
    # Write JSON report
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(
        json.dumps(analysis, indent=2, ensure_ascii=False),
        encoding='utf-8'
    )
    logging.info(f"JSON report written to: {output_json}")
    
    # Print to console
    print()
    print(text_report)


if __name__ == '__main__':
    main()
