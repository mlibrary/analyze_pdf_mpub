#!/usr/bin/env python3
"""
Fulcrum PDF Accessibility CLI
Processes a single PDF or a directory of PDFs and outputs Fulcrum-format JSON.

Usage:
    # Single file
    python run.py --input path/to/file.pdf --output path/to/output/

    # Batch (flat directory)
    python run.py --input path/to/pdfs/ --output path/to/output/

    # Batch (directory with subdirectories — structure is mirrored in output)
    python run.py --input path/to/pdfs/ --output path/to/output/

    # Specify veraPDF path explicitly (if not auto-detected)
    python run.py --input path/to/pdfs/ --output path/to/output/ --verapdf ~/Applications/verapdf/verapdf
"""

import argparse
import json
import os
import sys
import time
import traceback
from pathlib import Path


def process_pdf(pdf_path: Path) -> dict:
    """Run the PDF analyzer on a single PDF and return Fulcrum JSON."""
    from analyze_pdf import analyze_pdf_fulcrum
    return analyze_pdf_fulcrum(pdf_path)


def collect_pdfs(input_path: Path) -> 'list[tuple[Path, Path]]':
    """
    Return a sorted list of (pdf_path, relative_path) tuples.

    relative_path is the path of the PDF relative to input_path, used to
    mirror the input directory structure inside the output directory.

    For a single file input, relative_path is just the filename with no
    parent directory component.
    """
    if input_path.is_file():
        if input_path.suffix.lower() != '.pdf':
            raise SystemExit(f"Input file is not a PDF: {input_path}")
        return [(input_path, Path(input_path.name))]
    elif input_path.is_dir():
        pdfs = sorted(input_path.rglob('*.pdf'))
        if not pdfs:
            raise SystemExit(f"No PDF files found in: {input_path}")
        return [(p, p.relative_to(input_path)) for p in pdfs]
    else:
        raise SystemExit(f"Input path not found: {input_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Generate Fulcrum-format accessibility JSON for one or more PDFs.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        '--input', '-i',
        type=Path,
        required=True,
        help='Path to a single PDF file or a directory of PDFs',
    )
    parser.add_argument(
        '--output', '-o',
        type=Path,
        required=True,
        help='Directory to write JSON output files into',
    )
    parser.add_argument(
        '--verapdf',
        type=Path,
        default=None,
        help='Explicit path to the veraPDF executable (overrides auto-detection). '
             'Can also be set via the VERAPDF_PATH environment variable.',
    )
    args = parser.parse_args()

    # Inject verapdf path into environment so find_verapdf() picks it up
    if args.verapdf:
        os.environ['VERAPDF_PATH'] = str(args.verapdf.resolve())

    pdfs = collect_pdfs(args.input)
    args.output.mkdir(parents=True, exist_ok=True)

    total = len(pdfs)
    print(f"\nFulcrum PDF Accessibility CLI")
    print(f"PDFs   : {total}")
    print(f"Output : {args.output}")
    if args.verapdf:
        print(f"veraPDF: {args.verapdf}")
    print("-" * 60)

    success, failed = 0, 0
    batch_start = time.time()

    for i, (pdf_path, rel_path) in enumerate(pdfs, 1):
        # Mirror the input subdirectory structure under the output directory
        out_dir  = args.output / rel_path.parent
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{pdf_path.stem}.json"

        # Show relative path so subdirectory context is visible in the log
        display_name = str(rel_path)
        print(f"[{i}/{total}] {display_name} ...", end=" ", flush=True)
        t0 = time.time()

        try:
            result = process_pdf(pdf_path)
            out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
            elapsed = round(time.time() - t0, 2)
            print(f"✓ {elapsed}s → {out_path}")
            success += 1
        except Exception as e:
            elapsed = round(time.time() - t0, 2)
            print(f"✗ FAILED after {elapsed}s: {e}")
            traceback.print_exc()
            failed += 1

    total_time = round(time.time() - batch_start, 2)
    print("-" * 60)
    print(f"Done: {success} succeeded, {failed} failed — {total_time}s total\n")

    if failed > 0:
        sys.exit(1)


if __name__ == '__main__':
    main()
