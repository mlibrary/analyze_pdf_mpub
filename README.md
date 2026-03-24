# PDF Accessibility Analyzer

A comprehensive Python tool for analyzing PDF documents for accessibility features and compliance with international standards.

## Overview

This tool performs detailed accessibility analysis of PDF documents, checking for compliance with PDF/UA (ISO 14289) and WCAG 2.2 standards. It generates both human-readable text reports and machine-readable JSON output, making it suitable for both manual review and automated accessibility testing pipelines.

## Features

### Document Structure Analysis
- **Tagged PDF Detection**: Identifies whether the PDF has a logical structure tree
- **Bookmark Analysis**: Counts and extracts document outline/bookmark hierarchy
- **Heading Structure**: Detects and validates heading tags (H1-H6) and hierarchy
- **Document Language**: Checks for proper language declaration
- **Metadata Validation**: Verifies document title, author, and other metadata

### Content Accessibility
- **Figure Analysis**: Counts figures and checks for alternative text (alt text)
- **Text Extraction Quality**: Validates that text can be properly extracted (not image-based)
- **Unicode Mapping**: Checks for unmapped or replacement characters that may cause issues
- **Font Embedding**: Identifies fonts without proper ToUnicode CMaps
- **Reading Order**: Validates that logical structure matches visual reading order

### Standards Compliance
Validates against multiple accessibility standards using veraPDF:
- **PDF/UA-1** (ISO 14289-1:2014) - Universal Accessibility standard
- **PDF/UA-2** (ISO 14289-2:2024) - Latest Universal Accessibility standard
- **WCAG 2.2 Complete** - Web Content Accessibility Guidelines machine-testable criteria
- **WTPDF 1.0** - Well-Tagged PDF accessibility standard

### Output Formats
- **Text Report**: Human-readable formatted report with pass/fail indicators
- **JSON Report**: Structured data for programmatic analysis and integration
- **Console Output**: Summary displayed in terminal

## Requirements

### Dependencies
```bash
pip install pikepdf PyMuPDF
```

- **pikepdf**: PDF manipulation and structure analysis
- **PyMuPDF** (fitz): Additional PDF analysis capabilities (optional but recommended)
- **veraPDF**: External validator (must be installed separately and available in PATH)

### Installing veraPDF
Download and install veraPDF from: https://verapdf.org/

Ensure the `verapdf` command is available in your system PATH.

## Installation

1. Clone or download this repository
2. Install Python dependencies:
   ```bash
   pip install pikepdf PyMuPDF
   ```
3. Install veraPDF (see above)

## Usage

### Basic Usage
```bash
python3 analyze_pdf.py --input /path/to/document.pdf
```

This will create two files:
- `document_analysis.txt` - Human-readable report
- `document_analysis.json` - Machine-readable data

### Specify Output Location
```bash
python3 analyze_pdf.py --input document.pdf --output reports/my_analysis
```

Creates:
- `reports/my_analysis.txt`
- `reports/my_analysis.json`

### Verbose Logging
```bash
python3 analyze_pdf.py --input document.pdf --verbose
```

Shows detailed debug information during analysis.

### Reading Order Sampling
For large documents, you can control reading order analysis:

```bash
# Check all pages (default)
python3 analyze_pdf.py --input document.pdf --reading-order-sample all

# Sample strategy: first 15 pages + 5 random pages
python3 analyze_pdf.py --input document.pdf --reading-order-sample standard
```

## Command-Line Options

| Option | Description | Default |
|--------|-------------|---------|
| `--input PATH` | Path to PDF file to analyze (required) | - |
| `--output PATH` | Base path for output files (without extension) | `{input_stem}_analysis` |
| `--verbose` | Enable verbose debug logging | `False` |
| `--reading-order-sample {all\|standard}` | Reading order sampling strategy | `all` |

## Output Structure

### Text Report
The text report includes:
- Document statistics (pages, bookmarks, tagging status)
- Text extraction quality metrics
- Font Unicode mapping analysis
- Document metadata
- Reading order validation results
- veraPDF compliance results with detailed rule failures
- Overall accessibility summary with pass/fail checklist

### JSON Report
The JSON report contains structured data with the same information, suitable for:
- Automated testing pipelines
- Data analysis and reporting
- Integration with other tools
- Historical tracking of accessibility metrics

## Example Output

```
======================================================================
PDF ACCESSIBILITY ANALYSIS
======================================================================

File: document.pdf
Path: /path/to/document.pdf

DOCUMENT STATISTICS
----------------------------------------------------------------------
  Pages: 281
  Bookmarks: 0
  Tagged: No ✗
  Language: Not declared ✗

TEXT EXTRACTION QUALITY
----------------------------------------------------------------------
  Total characters analyzed: 27,750
  Unmapped Unicode chars: None ✓
  Replacement chars: None ✓

FONT UNICODE MAPPINGS
----------------------------------------------------------------------
  Total fonts (sampled): 28
  Embedded fonts: 1
  Non-embedded fonts: 27
  Fonts without ToUnicode CMap: 19 (67.9%) ✗

ACCESSIBILITY SUMMARY
----------------------------------------------------------------------
  ✗ PDF is not tagged
  ✗ Document language not declared
  ✓ No Unicode mapping issues detected
  ✓ Text is properly extractable (not image-based)
  ✗ Some fonts missing Unicode mappings
  ✓ Document title in metadata
  ✗ Reading order issues detected (18.5% of pages)
  ✗ PDF/UA-1 non-compliant (10 failures)

Overall: 3/11 checks passed (27%)
```

## Understanding Results

### Pass/Fail Indicators
- ✓ **Green checkmark**: Feature passes accessibility check
- ✗ **Red X**: Feature fails accessibility check

### Common Issues
- **Not Tagged**: PDF lacks logical structure tree (required for accessibility)
- **Language Not Declared**: Screen readers need language info for proper pronunciation
- **Missing Alt Text**: Images/figures without alternative text descriptions
- **Reading Order Issues**: Content structure doesn't match visual reading order
- **Font Issues**: Fonts without proper Unicode mappings affect copy-paste and screen readers

### WCAG Compliance Note
The veraPDF WCAG 2.2 validation covers machine-testable success criteria (Level A and AA). Full WCAG 2.2 conformance requires additional manual testing of:
- Content quality and clarity
- Cognitive accessibility
- User experience factors
- Context-specific requirements

## Use Cases

- **Document Remediation**: Identify accessibility issues before publishing
- **Compliance Testing**: Verify PDF/UA and WCAG compliance
- **Quality Assurance**: Automated accessibility checks in CI/CD pipelines
- **Accessibility Audits**: Generate detailed reports for stakeholders
- **Batch Processing**: Analyze multiple documents systematically

## Limitations

- Requires veraPDF to be installed for compliance validation
- Reading order analysis is sample-based for performance on large documents
- Does not perform subjective quality checks (e.g., alt text quality, content clarity)
- Some advanced structure elements may require manual verification

## License

[Specify license here]

## Contributing

[Contribution guidelines if applicable]

## Support

For issues or questions, please [specify contact method or issue tracker].
