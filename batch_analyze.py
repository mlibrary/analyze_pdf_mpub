#!/usr/bin/env python3
"""
Batch analyze all PDFs in a directory and calculate aggregate statistics.
"""

import argparse
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import List, Dict, Any


def analyze_single_pdf(pdf_path: Path, output_dir: Path, analyze_script: Path) -> Dict[str, Any]:
    """
    Run analyze_pdf.py on a single PDF.
    
    Args:
        pdf_path: Path to the PDF file.
        output_dir: Directory to store output files.
        analyze_script: Path to analyze_pdf.py script.
        
    Returns:
        Analysis results dict or None if analysis failed.
    """
    output_base = output_dir / pdf_path.stem
    
    try:
        # Run the analysis script
        result = subprocess.run(
            [
                sys.executable,
                str(analyze_script),
                '--input', str(pdf_path),
                '--output', str(output_base)
            ],
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout per PDF
        )
        
        if result.returncode != 0:
            print(f"Error analyzing {pdf_path.name}: {result.stderr}", file=sys.stderr)
            return None
        
        # Read the JSON output
        json_path = output_base.with_suffix('.json')
        if not json_path.exists():
            print(f"JSON output not found for {pdf_path.name}", file=sys.stderr)
            return None
        
        with open(json_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    except subprocess.TimeoutExpired:
        print(f"Timeout analyzing {pdf_path.name}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"Exception analyzing {pdf_path.name}: {e}", file=sys.stderr)
        return None


def main():
    parser = argparse.ArgumentParser(
        description="Batch analyze all PDFs in a directory."
    )
    parser.add_argument(
        '--input-dir',
        type=Path,
        required=True,
        help='Directory containing PDF files to analyze'
    )
    parser.add_argument(
        '--output-dir',
        type=Path,
        required=True,
        help='Directory to store output files'
    )
    parser.add_argument(
        '--analyze-script',
        type=Path,
        default=Path(__file__).parent / 'analyze_pdf.py',
        help='Path to analyze_pdf.py script'
    )
    
    args = parser.parse_args()
    
    # Validate input directory
    if not args.input_dir.exists() or not args.input_dir.is_dir():
        print(f"Error: Input directory not found: {args.input_dir}", file=sys.stderr)
        sys.exit(1)
    
    # Validate analyze script
    if not args.analyze_script.exists():
        print(f"Error: Analyze script not found: {args.analyze_script}", file=sys.stderr)
        sys.exit(1)
    
    # Create output directory
    args.output_dir.mkdir(parents=True, exist_ok=True)
    
    # Find all PDF files
    pdf_files = sorted(args.input_dir.glob('*.pdf'))
    total_pdfs = len(pdf_files)
    
    if total_pdfs == 0:
        print(f"No PDF files found in {args.input_dir}", file=sys.stderr)
        sys.exit(1)
    
    print(f"Found {total_pdfs} PDF files to analyze")
    print("-" * 80)
    
    # Analyze each PDF
    results = []
    page_counts = []
    
    for i, pdf_path in enumerate(pdf_files, 1):
        print(f"[{i}/{total_pdfs}] Analyzing {pdf_path.name}...", end=' ', flush=True)
        
        analysis = analyze_single_pdf(pdf_path, args.output_dir, args.analyze_script)
        
        if analysis:
            results.append({
                'filename': pdf_path.name,
                'pages': analysis.get('pages', 0),
                'analysis': analysis
            })
            page_counts.append(analysis.get('pages', 0))
            print(f"✓ ({analysis.get('pages', 0)} pages)")
        else:
            print("✗ Failed")
    
    print("-" * 80)
    
    # Calculate statistics
    successful = len(results)
    failed = total_pdfs - successful
    total_pages = sum(page_counts) if page_counts else 0
    
    # Calculate validation statistics
    pdfua1_pass = 0
    pdfua1_fail = 0
    wcag_pass = 0
    wcag_fail = 0
    verapdf_unavailable = 0
    
    for result in results:
        analysis = result.get('analysis', {})
        verapdf = analysis.get('verapdf', {})
        
        if not verapdf.get('available'):
            verapdf_unavailable += 1
            continue
        
        profiles = verapdf.get('profiles', {})
        
        # PDF/UA-1
        pdfua1 = profiles.get('PDF/UA-1', {})
        if 'error' not in pdfua1:
            if pdfua1.get('compliant', False):
                pdfua1_pass += 1
            else:
                pdfua1_fail += 1
        
        # WCAG 2.2
        wcag = profiles.get('WCAG 2.2 (Complete)', {})
        if 'error' not in wcag:
            if wcag.get('compliant', False):
                wcag_pass += 1
            else:
                wcag_fail += 1
    
    print(f"\nBatch Analysis Complete:")
    print(f"  Total PDFs: {total_pdfs}")
    print(f"  Successful: {successful}")
    print(f"  Failed: {failed}")
    
    if page_counts:
        min_pages = min(page_counts)
        max_pages = max(page_counts)
        avg_pages = sum(page_counts) / len(page_counts)
        
        print(f"\nPage Statistics:")
        print(f"  Minimum pages: {min_pages}")
        print(f"  Maximum pages: {max_pages}")
        print(f"  Average pages: {avg_pages:.2f}")
        print(f"  Total pages: {total_pages:,}")
    
    # Display validation statistics
    if successful > 0 and verapdf_unavailable < successful:
        print(f"\nValidation Statistics:")
        print(f"  PDF/UA-1:")
        print(f"    Pass: {pdfua1_pass}")
        print(f"    Fail: {pdfua1_fail}")
        print(f"  WCAG 2.2 (Complete):")
        print(f"    Pass: {wcag_pass}")
        print(f"    Fail: {wcag_fail}")
        if verapdf_unavailable > 0:
            print(f"  veraPDF unavailable: {verapdf_unavailable}")
    
    # Calculate page count distribution
    page_distribution = Counter(page_counts) if page_counts else Counter()
    
    # Save JSON summary
    summary_path = args.output_dir / 'batch_summary.json'
    summary = {
        'total_pdfs': total_pdfs,
        'successful': successful,
        'failed': failed,
        'page_statistics': {
            'min': min(page_counts) if page_counts else 0,
            'max': max(page_counts) if page_counts else 0,
            'avg': sum(page_counts) / len(page_counts) if page_counts else 0,
            'total': total_pages
        },
        'validation_statistics': {
            'pdfua1_pass': pdfua1_pass,
            'pdfua1_fail': pdfua1_fail,
            'wcag22_pass': wcag_pass,
            'wcag22_fail': wcag_fail,
            'verapdf_unavailable': verapdf_unavailable
        },
        'results': results
    }
    
    with open(summary_path, 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    
    print(f"\nJSON summary saved to: {summary_path}")
    
    # Generate and save text report
    text_report_path = args.output_dir / 'batch_summary.txt'
    with open(text_report_path, 'w', encoding='utf-8') as f:
        f.write('=' * 80 + '\n')
        f.write('PDF BATCH ANALYSIS RESULTS\n')
        f.write('=' * 80 + '\n')
        f.write('\n')
        f.write(f'Total PDFs analyzed: {successful}\n')
        if failed > 0:
            f.write(f'Failed analyses: {failed}\n')
        f.write(f'Total pages across all PDFs: {total_pages:,}\n')
        f.write('\n')
        
        if page_counts:
            f.write('AGGREGATE PAGE STATISTICS:\n')
            f.write(f'  Minimum pages: {min_pages}\n')
            f.write(f'  Maximum pages: {max_pages}\n')
            f.write(f'  Average pages: {avg_pages:.2f}\n')
            f.write('\n')
            
            # Add validation statistics
            if successful > 0 and verapdf_unavailable < successful:
                f.write('VALIDATION STATISTICS:\n')
                f.write(f'  PDF/UA-1:\n')
                f.write(f'    Pass: {pdfua1_pass}\n')
                f.write(f'    Fail: {pdfua1_fail}\n')
                f.write(f'  WCAG 2.2 (Complete):\n')
                f.write(f'    Pass: {wcag_pass}\n')
                f.write(f'    Fail: {wcag_fail}\n')
                if verapdf_unavailable > 0:
                    f.write(f'  veraPDF unavailable: {verapdf_unavailable}\n')
                f.write('\n')
            
            f.write('=' * 80 + '\n')
            f.write('\n')
            
            # Show distribution
            f.write('Page count distribution (top 20):\n')
            for i, (pages, count) in enumerate(page_distribution.most_common(20), 1):
                f.write(f'  {i:2d}. {pages:4d} pages: {count:3d} PDFs\n')
            
            if len(page_distribution) > 20:
                f.write(f'  ... and {len(page_distribution) - 20} more unique page counts\n')
            
            f.write('\n')
            f.write('=' * 80 + '\n')
            f.write('\n')
            
            # List all files analyzed
            f.write('FILES ANALYZED:\n')
            f.write('-' * 80 + '\n')
            for result in sorted(results, key=lambda x: x['pages'], reverse=True):
                filename = result['filename']
                pages = result['pages']
                analysis = result.get('analysis', {})
                verapdf = analysis.get('verapdf', {})
                
                # Get validation status
                pdfua_status = 'N/A'
                wcag_status = 'N/A'
                
                if verapdf.get('available'):
                    profiles = verapdf.get('profiles', {})
                    
                    pdfua1 = profiles.get('PDF/UA-1', {})
                    if 'error' not in pdfua1:
                        pdfua_status = 'PASS' if pdfua1.get('compliant', False) else 'FAIL'
                    
                    wcag = profiles.get('WCAG 2.2 (Complete)', {})
                    if 'error' not in wcag:
                        wcag_status = 'PASS' if wcag.get('compliant', False) else 'FAIL'
                
                f.write(f"  {filename:<50} {pages:>5} pages  PDF/UA-1: {pdfua_status:<4}  WCAG: {wcag_status:<4}\n")
            f.write('\n')
            f.write('=' * 80 + '\n')
    
    print(f"Text report saved to: {text_report_path}")
    
    # Display distribution summary to console
    if page_counts and len(page_distribution) > 0:
        print("\nPage count distribution (top 10):")
        for i, (pages, count) in enumerate(page_distribution.most_common(10), 1):
            print(f"  {i:2d}. {pages:4d} pages: {count:3d} PDFs")
        
        if len(page_distribution) > 10:
            print(f"  ... and {len(page_distribution) - 10} more unique page counts")


if __name__ == '__main__':
    main()
