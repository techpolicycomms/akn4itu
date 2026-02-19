# AKN4ITU: ITU Final Acts PDF to AKN4UN XML Converter

**Converts ITU Plenipotentiary Conference Final Acts (PDF) into machine-readable AKN4UN (Akoma Ntoso for UN) XML markup.**

Developed as a proof-of-concept for the ITU Innovation Hub to explore automated semantic markup of ITU normative and deliberative documents, following the [UN Semantic Interoperability Framework (UNSIF)](https://unsceb.org/unsif-akn4un) and the [AKN4UN Guidelines](https://unsceb-hlcm.github.io/).

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [Prerequisites](#prerequisites)
3. [Installation](#installation)
4. [Usage](#usage)
5. [Output Structure](#output-structure)
6. [AKN4UN Mapping for ITU Documents](#akn4un-mapping-for-itu-documents)
7. [Architecture](#architecture)
8. [Process Report](#process-report)
9. [Challenges and Limitations of Working with PDF](#challenges-and-limitations-of-working-with-pdf)
10. [Known Limitations of the Current Converter](#known-limitations-of-the-current-converter)
11. [Future Improvements](#future-improvements)
12. [References](#references)
13. [Project Files](#project-files)

---

## Quick Start

```bash
# 1. Clone the repository
git clone https://github.com/AJamie27/akn4itu.git
cd akn4itu

# 2. Install dependencies
pip install -r requirements.txt

# 3. Download the input PDF (not included in repo due to size)
#    See "Input PDF" section below for the download link

# 4. Run the converter
python itu_final_acts_to_akn.py S-CONF-ACTF-2018-R1-PDF-E.pdf

# 5. Run with individual files per resolution/decision
python itu_final_acts_to_akn.py S-CONF-ACTF-2018-R1-PDF-E.pdf --individual

# 6. Specify a custom output directory
python itu_final_acts_to_akn.py S-CONF-ACTF-2018-R1-PDF-E.pdf --output-dir ./output --individual
```

### Input PDF

The input PDF (`S-CONF-ACTF-2018-R1-PDF-E.pdf`, ~25 MB) is not included in this repository due to its size. Download it from the official ITU source:

**[ITU Final Acts PP-18 (PDF)](https://www.itu.int/pub/S-CONF-ACTF-2018)**

Place the downloaded file in the same directory as `itu_final_acts_to_akn.py` before running the converter.

---

## Prerequisites

| Requirement | Minimum Version | Notes |
|-------------|----------------|-------|
| **Python** | 3.9+ | Tested on 3.11.9 (Windows) |
| **Operating System** | Windows / macOS / Linux | Cross-platform |
| **Disk space** | ~50 MB | For dependencies + output XML |

No external services, databases, or API keys are required. The converter runs entirely offline.

---

## Installation

### Option A: Direct install (recommended for quick use)

```bash
# Clone or copy the project folder, then:
cd akn4itu
pip install -r requirements.txt
```

### Option B: Virtual environment (recommended for isolation)

**Windows (PowerShell):**
```powershell
cd akn4itu
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

**macOS / Linux:**
```bash
cd akn4itu
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Dependencies

| Package | Purpose |
|---------|---------|
| [PyMuPDF](https://pymupdf.readthedocs.io/) (imported as `fitz`) | PDF text extraction with font/position awareness |
| [lxml](https://lxml.de/) | XML generation with namespace support |

---

## Usage

```
python itu_final_acts_to_akn.py <input_pdf> [--output-dir <dir>] [--individual]
```

| Argument | Required | Description |
|----------|----------|-------------|
| `input_pdf` | Yes | Path to the ITU Final Acts PDF file |
| `--output-dir` | No | Output directory (defaults to same directory as the PDF) |
| `--individual` | No | Also generate a separate XML file for each resolution/decision |

### Example run

```
$ python itu_final_acts_to_akn.py S-CONF-ACTF-2018-R1-PDF-E.pdf --individual

Reading PDF: S-CONF-ACTF-2018-R1-PDF-E.pdf
Parsing document structure...
Found 64 documents across 3 parts:
  DECISIONS: 2 documents
  RESOLUTIONS: 61 documents
  RECOMMENDATION: 1 documents

Generating AKN4UN XML...
Written: pp18_final_acts_akn.xml

Writing individual documents to: individual/
Written: individual/dec_5.xml
Written: individual/dec_11.xml
Written: individual/res_2.xml
...
Written: individual/rec_7.xml

Conversion complete!
```

---

## Output Structure

```
akn4itu/
  pp18_final_acts_akn.xml       # Full collection (all 64 documents in one file)
  individual/                    # One XML file per document
    dec_5.xml                    #   Decision 5
    dec_11.xml                   #   Decision 11
    res_2.xml                    #   Resolution 2
    res_11.xml                   #   Resolution 11
    ...                          #   (61 resolutions total)
    rec_7.xml                    #   Recommendation 7
```

### Output statistics (PP-18 Final Acts)

| Metric | Value |
|--------|-------|
| Total documents parsed | 64 |
| Decisions | 2 |
| Resolutions | 61 |
| Recommendations | 1 |
| Preamble recitals extracted | 1,326 |
| Operative paragraphs extracted | 1,228 |
| Operative sections (resolves, decides, instructs...) | 164 |
| Collection XML file size | 1.47 MB |

---

## AKN4UN Mapping for ITU Documents

The converter maps ITU document structures to AKN4UN elements following the [AKN4UN Guidelines Part 1](https://unsceb-hlcm.github.io/) and the [Deliberative Documents modelling](https://unsceb-hlcm.github.io/part2/).

### Document type mapping

| ITU Document | AKN Document Type | Subtype | Name |
|--------------|-------------------|---------|------|
| Resolution | `<statement>` | `deliberation` | `resolution` |
| Decision | `<statement>` | `deliberation` | `decision` |
| Recommendation | `<statement>` | `deliberation` | `recommendation` |
| Final Acts (collection) | `<documentCollection>` | `publication` | `finalActs` |

### Structural mapping

| PDF Content | AKN4UN Element | Notes |
|-------------|---------------|-------|
| Document title | `<preface>` > `<longTitle>` > `<docType>`, `<docNumber>` | |
| Descriptive title | `<preface>` > `<container name="title">` | |
| "The Plenipotentiary Conference..." | `<preamble>` > `<formula name="enactingFormula">` | |
| *considering*, *noting*, *recalling*... | `<preamble>` > `<recitals>` > `<recital>` | Grouped by keyword |
| *resolves*, *decides*, *instructs*... | `<mainBody>` > `<hcontainer>` | One per operative keyword |
| Numbered paragraphs (1, 2, 3...) | `<paragraph>` with `<num>` | |
| Sub-paragraphs (1.1, 1.2 or a, b, c) | `<list>` > `<point>` with `<num>` | |
| Annexes | `<attachments>` > `<attachment>` | |

### IRI naming convention

Following AKN4UN naming rules:

```
Work:         /akn/un/statement/deliberation/itu-pp/2018-11-15/res-2
Expression:   /akn/un/statement/deliberation/itu-pp/2018-11-15/res-2/eng@2018-11-15
Manifestation:/akn/un/statement/deliberation/itu-pp/2018-11-15/res-2/eng@2018-11-15/.xml
```

| IRI Component | Value | Source |
|---------------|-------|--------|
| Jurisdiction | `un` | ISO 3166/MA code for the UN system |
| Document type | `statement` | AKN type for deliberative documents |
| Subtype | `deliberation` | AKN4UN subtype |
| Actor | `itu-pp` | ITU Plenipotentiary Conference |
| Date | `2018-11-15` | Conference closing date |
| Number | `res-2`, `dec-5`, etc. | Document identifier |
| Language | `eng` | ISO 639-2 Alpha-3 |

### Element identifiers (eId)

```xml
<recitals eId="recs_considering">         <!-- grouped by keyword -->
  <recital eId="rec_1">                   <!-- sequential numbering -->
<hcontainer eId="hcont_resolves">          <!-- operative section -->
  <paragraph eId="para_4">                <!-- paragraph number -->
    <list eId="para_4__list_1">           <!-- nested list -->
      <point eId="para_4__point_4-1">     <!-- sub-paragraph -->
```

---

## Architecture

The converter consists of four main components:

```
PDF File
   |
   v
[PDFExtractor]  -- PyMuPDF: text extraction + page header removal
   |
   v
[FinalActsParser]  -- Regex-based structure detection
   |                   - TOC-based document boundary detection
   |                   - Preamble keyword parsing (37 keywords)
   |                   - Operative keyword parsing (37 keywords)
   |                   - Numbered paragraph splitting
   |                   - Sub-paragraph detection (decimal & letter)
   v
[AKNGenerator]  -- lxml: XML tree construction
   |               - FRBR metadata (Work/Expression/Manifestation)
   |               - AKN4UN structural elements
   |               - Proper namespace handling
   v
[XML Writer]  -- Formatted output with declaration
   |
   v
AKN4UN XML Files
```

### Key design decisions

1. **TOC-driven document splitting**: The PDF's embedded table of contents is used to identify the page ranges for each resolution/decision, which is far more reliable than trying to detect document boundaries from the text alone.

2. **Keyword-based section parsing**: Preamble and operative sections are identified by matching against curated keyword lists (e.g., *considering*, *noting*, *resolves*, *instructs the Secretary-General*). Keywords are sorted longest-first to ensure the most specific match wins (e.g., "instructs the Secretary-General" is matched before "instructs").

3. **Surgical page header removal**: Page headers like "Res. 2 / 21" are removed by identifying the doc-reference line and only stripping immediately adjacent lines. This prevents paragraph numbers from being accidentally removed.

4. **Separation of parsing and generation**: The parsed intermediate representation (dataclasses) is cleanly separated from the XML generation, making it possible to swap in a different output format or a different input source.

---

## Process Report

### Methodology

The development followed this process:

#### Phase 1: Research and specification study

- Studied the [AKN4UN Guidelines Part 1](https://unsceb-hlcm.github.io/) (content modelling, metadata, naming conventions)
- Studied the [AKN4UN Guidelines Part 2](https://unsceb-hlcm.github.io/part2/) (document class modelling for normative, deliberative, administrative documents)
- Studied the [GA Resolution modelling examples](https://unsceb-hlcm.github.io/part3_ga/index-1.html) for practical XML patterns
- Reviewed the [Akoma Ntoso 3.0 XSD schema](https://docs.oasis-open.org/legaldocml/akn-core/v1.0/os/part2-specs/schemas/) for element definitions
- Reviewed ITU reference documents (Guidelines for Document Management, T-REC-X.2011)

#### Phase 2: PDF structure analysis

- Extracted the PDF's embedded table of contents (74 entries across 7 Parts)
- Analyzed font usage to distinguish headers (Calibri 12pt), body text (Calibri 10.6pt), italic keywords (Calibri-Italic 10.6pt), and page headers (Calibri-Bold 7.8pt)
- Sampled multiple pages to understand the exact text patterns for preamble keywords, operative keywords, and paragraph numbering
- Identified the consistent structure: Title > Enacting Formula > Preamble Sections > Operative Sections

#### Phase 3: Iterative development and testing

- Built the PDF extractor with PyMuPDF for text extraction and page header removal
- Built the document parser with regex-based structure detection
- Built the AKN4UN XML generator with lxml
- Tested on the full 580-page PDF, iteratively fixing:
  - XML control character sanitization (PDF text contains invalid XML bytes)
  - Page header vs. paragraph number disambiguation
  - Numbered paragraph splitting across page boundaries
  - Sub-paragraph detection for both decimal (1.1, 1.2) and lettered (a, b, c) numbering

#### Phase 4: Validation

- Verified all 64 generated XML files are well-formed
- Compared extracted text against the original PDF for accuracy
- Validated structural completeness (preamble recitals, operative paragraphs, sub-paragraphs)

---

## Challenges and Limitations of Working with PDF

PDF is fundamentally a *presentation* format, not a *structural* format. This creates significant challenges when trying to extract semantic structure:

### 1. No semantic structure in PDF

PDF stores text as positioned character sequences on a canvas. There is no concept of "paragraph", "section", "heading", or "list item" in the PDF specification. What appears as a numbered paragraph to a human reader is just a collection of text spans at specific coordinates.

**Impact on this project**: Structure detection relies entirely on heuristics (font analysis, regex patterns, positioning). Any change in the PDF's visual formatting could break the parser.

### 2. Page-level fragmentation

PDF content is organized by pages, not by logical document structure. A single paragraph, list item, or even a word can be split across two pages.

**Impact on this project**: Text reassembly across page boundaries introduces errors. Page headers and footers must be surgically removed without accidentally stripping content. The "Res. 2 / 21" header on each page sits in the same text stream as the operative paragraphs below it.

### 3. Ambiguous standalone numbers

The number "1" appearing on a line by itself could be:
- A page number (header/footer)
- A paragraph number in an operative section
- A footnote reference
- Part of a list numbering

**Impact on this project**: The page header removal logic must use context (proximity to "Res. X" or "Dec. X" lines) to distinguish page numbers from paragraph numbers. Despite this, the first paragraph of each operative section is sometimes merged with introductory text because its "1" cannot be reliably distinguished from surrounding content.

### 4. Footnotes mixed with body text

PDF footnotes are simply text positioned at the bottom of a page. When extracting text linearly, footnote content gets interleaved with body text.

**Impact on this project**: Footnote text (e.g., "These include the least developed countries...") appears inline within the paragraph text rather than being separated into proper `<authorialNote>` elements.

### 5. Hyphenation and word breaks

PDF text extraction sometimes preserves end-of-line hyphenation (e.g., "Secretary-\nGeneral" becomes "Secretary- General"), and justified text can produce irregular spacing.

**Impact on this project**: Some words may appear with stray spaces or broken hyphenation in the XML output.

### 6. Tables and complex layouts

Tables, multi-column layouts, and embedded graphics in PDFs are extracted as jumbled text when using standard text extraction.

**Impact on this project**: Annexes containing financial tables (e.g., Decision 5's budget annexes) are extracted as flat text without table structure.

### 7. No reliable character semantics

Italic text (used for preamble keywords) is identified by font name ("Calibri-Italic") rather than by any semantic markup in the PDF. Bold, underline, and other formatting are similarly font-based.

**Impact on this project**: The parser must rely on keyword matching rather than italic detection, which works well for the standard ITU keywords but could miss non-standard formatting.

### Recommendation

For future iterations, **starting from a structured source format** (e.g., OOXML/DOCX from the ITU gDoc system, or the XML output from the Documents Proposals Manager) would eliminate most of these challenges. The ITU DPM system already produces structured document data that could be mapped directly to AKN4UN without the lossy PDF extraction step.

---

## Known Limitations of the Current Converter

| Limitation | Description | Severity |
|-----------|-------------|----------|
| **First paragraph merging** | Paragraph 1 of each operative section sometimes merges with introductory text | Medium |
| **Footnotes inline** | Footnote text appears within paragraph body rather than as `<authorialNote>` | Medium |
| **No table extraction** | Tables in annexes are extracted as plain text | Medium |
| **No cross-reference tagging** | References like "Resolution 77 (Rev. Dubai, 2018)" are not tagged with `<ref>` | Low |
| **No italic preservation** | Preamble keywords are tagged via `<i>` but inline italics in body text are not preserved | Low |
| **Annex structure** | Annex content is captured as flat text without internal structure | Medium |
| **Signatories/Declarations** | Parts VI and VII (Signatories, Declarations) are not parsed | Low |
| **Single conference** | Conference metadata (Dubai, 2018) is hardcoded; adapting to other conferences requires code changes | Low |

---

## Future Improvements

1. **DOCX/OOXML input**: Add a parser for Word documents from the ITU gDoc system, which preserves structural information lost in PDF.

2. **Cross-reference detection**: Use regex to identify references to other ITU documents (resolutions, recommendations, articles of the Constitution/Convention) and tag them with `<ref href="...">`.

3. **Footnote extraction**: Use PyMuPDF's position-based extraction to separate footnotes from body text based on their Y-coordinate on the page.

4. **Table extraction**: Use `pdfplumber` (already in dependencies) for table detection and convert to AKN `<table>` elements.

5. **Semantic annotation**: Tag named entities (Member States, organizations, dates, legal references) with appropriate AKN inline elements (`<organization>`, `<date>`, `<ref>`).

6. **Schema validation**: Validate generated XML against the `akomantoso30.xsd` schema (included in this project).

7. **Conference parameterization**: Make the converter configurable for any ITU conference (PP, WTSA, WCIT, WRC, WTDC) via a configuration file.

8. **Multilingual support**: Extend to process the French, Spanish, Arabic, Chinese, and Russian editions of the Final Acts.

---

## References

### AKN4UN Specification

- [UNSIF / AKN4UN Homepage](https://unsceb.org/unsif-akn4un) - UN CEB
- [AKN4UN Guidelines Part 1: Specifications](https://unsceb-hlcm.github.io/) - Content modelling, metadata, naming conventions
- [AKN4UN Guidelines Part 2: Document Modelling](https://unsceb-hlcm.github.io/part2/) - Document class definitions
- [GA Resolution Modelling (Part 3)](https://unsceb-hlcm.github.io/part3_ga/index-1.html) - Practical examples

### Akoma Ntoso Standard

- [Akoma Ntoso Version 1.0 (OASIS Standard)](https://www.oasis-open.org/standard/akn-v1-0/)
- [Akoma Ntoso Part 2: Specifications](https://docs.oasis-open.org/legaldocml/akn-core/v1.0/akn-core-v1.0-part2-specs.html)
- [Akoma Ntoso XSD Schema](https://docs.oasis-open.org/legaldocml/akn-core/v1.0/os/part2-specs/schemas/)
- [GitHub: OASIS LegalDocML](https://github.com/oasis-open/legaldocml-akomantoso)

### ITU Source Document

- [ITU Final Acts PP-18 (PDF)](https://www.itu.int/pub/S-CONF-ACTF-2018) - Plenipotentiary Conference, Dubai, 2018

---

## Project Files

### In the repository

```
akn4itu/
  itu_final_acts_to_akn.py      # Main converter script
  requirements.txt               # Python dependencies
  README.md                      # This documentation
  .gitignore                     # Git ignore rules
  akomantoso30.xsd               # Akoma Ntoso 3.0 XML Schema (for validation)
  otu_contribution.xml           # Sample AKN contribution template
  sample_output/                 # Example output for reference
    res_2.xml                    #   Sample: Resolution 2
    dec_5.xml                    #   Sample: Decision 5
```

### Downloaded separately (see Quick Start)

```
  S-CONF-ACTF-2018-R1-PDF-E.pdf  # Input: ITU Final Acts PP-18 (~25 MB)
                                  # Download from: https://www.itu.int/pub/S-CONF-ACTF-2018
```

### Generated by running the converter

```
  pp18_final_acts_akn.xml        # Full collection XML (all 64 documents)
  individual/                    # One XML file per document
    dec_5.xml
    dec_11.xml
    res_2.xml
    ...
    rec_7.xml
```

---

## License

This tool was developed for internal ITU use. The Akoma Ntoso standard is published by OASIS under CC-BY 4.0.

---

*Developed: February 2026 | ITU Innovation Hub*
