"""
ITU Final Acts PDF to AKN4UN (Akoma Ntoso for UN) Converter

Converts ITU Plenipotentiary Conference Final Acts PDF into AKN4UN XML markup.
Handles Decisions, Resolutions, and Recommendations following the AKN4UN specification
(https://unsceb-hlcm.github.io/).

Usage:
    python itu_final_acts_to_akn.py <input_pdf> [--output-dir <dir>]
"""

import re
import os
import sys
import argparse
from datetime import date
from dataclasses import dataclass, field
from typing import Optional
from lxml import etree
import fitz  # PyMuPDF


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

AKN_NS = "http://docs.oasis-open.org/legaldocml/ns/akn/3.0"
XML_NS = "http://www.w3.org/XML/1998/namespace"
NSMAP = {None: AKN_NS}


def _sanitize_xml_text(text: str) -> str:
    """Remove characters that are not valid in XML 1.0."""
    if text is None:
        return ""
    return re.sub(
        r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]",
        "",
        text,
    )

PREAMBLE_KEYWORDS = [
    "considering further",
    "considering",
    "noting with satisfaction",
    "noting with concern",
    "noting further",
    "noting",
    "recalling further",
    "recalling",
    "recognizing further",
    "recognizing",
    "bearing in mind",
    "having examined",
    "having considered",
    "having regard",
    "having reviewed",
    "taking into account",
    "taking note",
    "aware",
    "conscious",
    "convinced",
    "concerned",
    "deeply concerned",
    "emphasizing",
    "affirming",
    "reaffirming",
    "acknowledging",
    "appreciating",
    "welcoming",
    "mindful",
    "determined",
    "expressing",
    "stressing",
    "underlining",
    "observing",
    "encouraged",
]

OPERATIVE_KEYWORDS = [
    "resolves further",
    "resolves",
    "decides further",
    "decides",
    "instructs the Secretary-General",
    "instructs the Director",
    "instructs the ITU Council",
    "instructs the Council",
    "instructs the General Secretariat",
    "instructs",
    "further instructs the Secretary-General",
    "further instructs the Director",
    "further instructs the ITU Council",
    "further instructs the Council",
    "further instructs",
    "invites Member States",
    "invites Sector Members",
    "invites the Secretary-General",
    "invites the Director",
    "invites the ITU Council",
    "invites the Council",
    "invites",
    "requests the Secretary-General",
    "requests the Director",
    "requests the Council",
    "requests",
    "urges Member States",
    "urges",
    "encourages Member States",
    "encourages",
    "calls upon",
    "recommends",
    "authorizes the Secretary-General",
    "authorizes",
    "charges the Council",
    "charges",
    "appeals to",
]

# Sort keywords longest-first so greedy match picks the most specific form
PREAMBLE_KEYWORDS.sort(key=len, reverse=True)
OPERATIVE_KEYWORDS.sort(key=len, reverse=True)


# ---------------------------------------------------------------------------
# Data classes for parsed structure
# ---------------------------------------------------------------------------

@dataclass
class SubParagraph:
    label: str          # e.g. "a)", "1.1", "(i)"
    text: str = ""


@dataclass
class NumberedParagraph:
    num: str            # e.g. "1", "2"
    text: str = ""
    sub_paragraphs: list = field(default_factory=list)


@dataclass
class PreambleSection:
    keyword: str        # e.g. "considering", "noting"
    paragraphs: list = field(default_factory=list)  # list of SubParagraph or plain str


@dataclass
class OperativeSection:
    keyword: str        # e.g. "resolves", "decides"
    paragraphs: list = field(default_factory=list)  # list of NumberedParagraph


@dataclass
class DocumentItem:
    doc_type: str       # "RESOLUTION", "DECISION", "RECOMMENDATION"
    number: str         # e.g. "2", "5"
    revision: str       # e.g. "REV. DUBAI, 2018" or "DUBAI, 2018"
    title: str          # descriptive title
    enacting_formula: str = ""
    preamble_sections: list = field(default_factory=list)
    operative_sections: list = field(default_factory=list)
    annexes: list = field(default_factory=list)  # list of str (annex text blocks)
    footnotes: list = field(default_factory=list)


@dataclass
class FinalActs:
    conference: str = "Plenipotentiary Conference"
    location: str = "Dubai"
    year: str = "2018"
    conference_date: str = "2018-11-15"
    parts: dict = field(default_factory=dict)  # part_name -> list of DocumentItem
    signatories_text: str = ""
    declarations_text: str = ""


# ---------------------------------------------------------------------------
# PDF Extraction
# ---------------------------------------------------------------------------

class PDFExtractor:
    """Extracts structured text from the ITU Final Acts PDF."""

    def __init__(self, pdf_path: str):
        self.doc = fitz.open(pdf_path)
        self.toc = self.doc.get_toc()

    def close(self):
        self.doc.close()

    def get_page_text(self, page_num: int) -> str:
        return self.doc[page_num].get_text("text")

    def get_page_spans(self, page_num: int) -> list:
        """Get font-aware spans for a page."""
        spans = []
        page = self.doc[page_num]
        blocks = page.get_text("dict")["blocks"]
        for block in blocks:
            if "lines" in block:
                for line in block["lines"]:
                    for span in line["spans"]:
                        spans.append({
                            "text": span["text"],
                            "font": span["font"],
                            "size": span["size"],
                            "flags": span["flags"],
                            "bbox": span["bbox"],
                        })
        return spans

    def extract_text_range(self, start_page: int, end_page: int) -> str:
        """Extract plain text for a range of pages (0-indexed, inclusive)."""
        parts = []
        for pg in range(start_page, min(end_page + 1, len(self.doc))):
            text = self.get_page_text(pg)
            text = self._clean_page_text(text, pg)
            parts.append(text)
        return "\n".join(parts)

    def _clean_page_text(self, text: str, page_num: int) -> str:
        """Remove page headers/footers from extracted text.

        The header block at the top of each page typically looks like:
            (blank) / "Res. 2" / "21" (page number)   -- or reversed order
        We identify the doc-reference line and the page-number line that is
        immediately adjacent to it (within 1 line). Lines separated from
        the doc-ref by a blank line are content (e.g. paragraph numbers)
        and must NOT be removed.
        """
        lines = text.split("\n")
        skip_indices = set()

        # Find the doc-reference line in the first 5 lines
        doc_ref_idx = None
        for i in range(min(5, len(lines))):
            if re.match(r"^\s*(Res|Dec|Rec)\.\s*\d+", lines[i]):
                doc_ref_idx = i
                skip_indices.add(i)
                break

        if doc_ref_idx is not None:
            # Remove blank lines before the doc-ref
            for j in range(doc_ref_idx):
                if lines[j].strip() == "":
                    skip_indices.add(j)

            # The page number is usually the line immediately before or after
            # the doc-ref (not separated by a blank line)
            for adj in [doc_ref_idx - 1, doc_ref_idx + 1]:
                if 0 <= adj < len(lines):
                    if re.match(r"^\s*\d{1,3}\s*$", lines[adj]):
                        skip_indices.add(adj)
                    elif lines[adj].strip() == "":
                        skip_indices.add(adj)

        cleaned = [line for i, line in enumerate(lines) if i not in skip_indices]
        return "\n".join(cleaned)


# ---------------------------------------------------------------------------
# Document Parser
# ---------------------------------------------------------------------------

class FinalActsParser:
    """Parses extracted text into structured DocumentItem objects."""

    DOC_HEADER_RE = re.compile(
        r"^(RESOLUTION|DECISION|RECOMMENDATION)\s+"
        r"(\d+(?:\s*\([^)]+\))?)\s*"
        r"(?:\(([^)]+)\))?\s*$",
        re.MULTILINE,
    )

    DOC_HEADER_WITH_TITLE_RE = re.compile(
        r"(RESOLUTION|DECISION|RECOMMENDATION)\s+"
        r"(\d+)\s*"
        r"\(([^)]+)\)\s*"
        r"(?:\-\s*)?"
    )

    def __init__(self, extractor: PDFExtractor):
        self.extractor = extractor
        self.toc = extractor.toc

    def parse(self) -> FinalActs:
        acts = FinalActs()
        doc_entries = self._find_document_entries()

        for i, entry in enumerate(doc_entries):
            end_page = (doc_entries[i + 1]["page"] - 1
                        if i + 1 < len(doc_entries)
                        else len(self.extractor.doc) - 1)

            text = self.extractor.extract_text_range(entry["page"], end_page)
            doc_item = self._parse_document_text(text, entry)

            if doc_item:
                part = entry.get("part", "other")
                if part not in acts.parts:
                    acts.parts[part] = []
                acts.parts[part].append(doc_item)

        return acts

    def _find_document_entries(self) -> list:
        """Use the PDF TOC to find each document entry."""
        entries = []
        current_part = "other"

        for level, title, page in self.toc:
            page_idx = page - 1

            part_match = re.match(r"PART\s+([IVXLC]+)\s*[–—-]\s*(.*)", title.strip())
            if part_match:
                current_part = part_match.group(2).strip()
                continue

            doc_match = re.match(
                r"(RESOLUTION|DECISION|RECOMMENDATION)\s+(\d+)\s*\(([^)]+)\)\s*(?:-\s*)?(.*)",
                title.strip(),
            )
            if doc_match:
                entries.append({
                    "type": doc_match.group(1),
                    "number": doc_match.group(2),
                    "revision": doc_match.group(3).strip(),
                    "title": doc_match.group(4).strip(),
                    "page": page_idx,
                    "part": current_part,
                })

        return entries

    def _parse_document_text(self, raw_text: str, entry: dict) -> Optional[DocumentItem]:
        """Parse the full text of a single document (resolution/decision/recommendation)."""
        doc = DocumentItem(
            doc_type=entry["type"],
            number=entry["number"],
            revision=entry["revision"],
            title=entry["title"],
        )

        text = self._normalize_text(raw_text)

        # Extract the enacting formula
        enact_match = re.search(
            r"(The Plenipotentiary Conference.*?(?:Dubai,\s*2018\)),?)",
            text, re.DOTALL,
        )
        if enact_match:
            doc.enacting_formula = self._clean_whitespace(enact_match.group(1))
            text_after_enact = text[enact_match.end():]
        else:
            text_after_enact = text

        # Split into preamble and operative sections
        self._parse_sections(text_after_enact, doc)
        return doc

    def _normalize_text(self, text: str) -> str:
        """Normalize whitespace and fix common PDF extraction artifacts."""
        text = re.sub(r"\u2013|\u2014", "-", text)
        text = re.sub(r"\u201c|\u201d", '"', text)
        text = re.sub(r"\u2018|\u2019", "'", text)
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = _sanitize_xml_text(text)
        return text.strip()

    def _clean_whitespace(self, text: str) -> str:
        return re.sub(r"\s+", " ", text).strip()

    def _parse_sections(self, text: str, doc: DocumentItem):
        """Split text into preamble and operative sections based on keywords."""
        all_keywords = (
            [(kw, "preamble") for kw in PREAMBLE_KEYWORDS]
            + [(kw, "operative") for kw in OPERATIVE_KEYWORDS]
        )

        # Find positions of all keyword occurrences
        section_positions = []
        for kw, kw_type in all_keywords:
            pattern = re.compile(r"(?:^|\n)\s*" + re.escape(kw) + r"\s*\n", re.IGNORECASE)
            for m in pattern.finditer(text):
                section_positions.append((m.start(), kw, kw_type))

        section_positions.sort(key=lambda x: x[0])

        # Remove overlapping matches (keep longer/earlier)
        filtered = []
        for pos, kw, kw_type in section_positions:
            if not filtered or pos > filtered[-1][0] + len(filtered[-1][1]) + 5:
                filtered.append((pos, kw, kw_type))
        section_positions = filtered

        # Extract text for each section
        for i, (pos, kw, kw_type) in enumerate(section_positions):
            start = pos
            end = section_positions[i + 1][0] if i + 1 < len(section_positions) else len(text)
            section_text = text[start:end].strip()

            # Remove the keyword line itself
            section_text = re.sub(
                r"^\s*" + re.escape(kw) + r"\s*",
                "",
                section_text,
                count=1,
                flags=re.IGNORECASE,
            ).strip()

            if kw_type == "preamble":
                preamble_sec = self._parse_preamble_section(kw, section_text)
                doc.preamble_sections.append(preamble_sec)
            else:
                operative_sec = self._parse_operative_section(kw, section_text)
                doc.operative_sections.append(operative_sec)

    def _parse_preamble_section(self, keyword: str, text: str) -> PreambleSection:
        """Parse a preamble section into lettered paragraphs."""
        section = PreambleSection(keyword=keyword)

        # Try to split by letter labels: a), b), c) ...
        parts = re.split(r"\n\s*([a-z]\))\s*", text)

        if len(parts) > 1:
            # First part may be intro text before a)
            if parts[0].strip():
                section.paragraphs.append(
                    SubParagraph(label="", text=self._clean_whitespace(parts[0]))
                )
            for j in range(1, len(parts), 2):
                label = parts[j]
                body = parts[j + 1] if j + 1 < len(parts) else ""
                section.paragraphs.append(
                    SubParagraph(label=label, text=self._clean_whitespace(body))
                )
        else:
            section.paragraphs.append(
                SubParagraph(label="", text=self._clean_whitespace(text))
            )

        return section

    def _parse_operative_section(self, keyword: str, text: str) -> OperativeSection:
        """Parse an operative section into numbered paragraphs."""
        section = OperativeSection(keyword=keyword)

        # Numbers appear on their own line in the PDF extraction.
        # Match: newline, optional whitespace, one or more digits (possibly with
        # a decimal sub-number like 1.1), followed by whitespace/newline.
        # The number must NOT look like a year (4 digits >= 1900).
        parts = re.split(r"\n\s*(\d{1,2}(?:\.\d+)?)\s*\n", text)

        if len(parts) > 1:
            if parts[0].strip():
                section.paragraphs.append(
                    NumberedParagraph(num="", text=self._clean_whitespace(parts[0]))
                )
            for j in range(1, len(parts), 2):
                num = parts[j]
                body = parts[j + 1] if j + 1 < len(parts) else ""
                para = NumberedParagraph(
                    num=num,
                    text=self._clean_whitespace(body),
                )
                self._parse_sub_paragraphs(body, para)
                section.paragraphs.append(para)
        else:
            # Fallback: try "10 that..." pattern (number at start of line
            # followed directly by text, as seen for paragraph 10+)
            parts2 = re.split(r"\n\s*(\d{1,2})\s+(?=that |to )", text)
            if len(parts2) > 2:
                if parts2[0].strip():
                    section.paragraphs.append(
                        NumberedParagraph(num="", text=self._clean_whitespace(parts2[0]))
                    )
                for j in range(1, len(parts2), 2):
                    num = parts2[j]
                    body = parts2[j + 1] if j + 1 < len(parts2) else ""
                    para = NumberedParagraph(
                        num=num,
                        text=self._clean_whitespace(body),
                    )
                    self._parse_sub_paragraphs(body, para)
                    section.paragraphs.append(para)
            else:
                section.paragraphs.append(
                    NumberedParagraph(num="", text=self._clean_whitespace(text))
                )

        return section

    def _parse_sub_paragraphs(self, text: str, para: NumberedParagraph):
        """Extract sub-numbered items like 1.1, 1.2, or a), b) within a paragraph."""
        # Sub-numbers like 1.1, 1.2
        sub_parts = re.split(r"\n\s*(\d+\.\d+)\s+", text)
        if len(sub_parts) > 2:
            para.text = self._clean_whitespace(sub_parts[0])
            for j in range(1, len(sub_parts), 2):
                label = sub_parts[j]
                body = sub_parts[j + 1] if j + 1 < len(sub_parts) else ""
                para.sub_paragraphs.append(
                    SubParagraph(label=label, text=self._clean_whitespace(body))
                )
            return

        # Letter sub-paragraphs: a), b)
        sub_parts = re.split(r"\n\s*([a-z]\))\s*", text)
        if len(sub_parts) > 2:
            para.text = self._clean_whitespace(sub_parts[0])
            for j in range(1, len(sub_parts), 2):
                label = sub_parts[j]
                body = sub_parts[j + 1] if j + 1 < len(sub_parts) else ""
                para.sub_paragraphs.append(
                    SubParagraph(label=label, text=self._clean_whitespace(body))
                )


# ---------------------------------------------------------------------------
# AKN4UN XML Generator
# ---------------------------------------------------------------------------

class AKNGenerator:
    """Generates AKN4UN XML from parsed document structures."""

    def __init__(self, final_acts: FinalActs):
        self.acts = final_acts
        self.today = date.today().isoformat()

    def _el(self, tag: str, parent=None, text=None, **attribs) -> etree._Element:
        """Create an AKN element."""
        el = etree.SubElement(parent, f"{{{AKN_NS}}}{tag}") if parent is not None else etree.Element(f"{{{AKN_NS}}}{tag}", nsmap=NSMAP)
        for k, v in attribs.items():
            if k == "xml_lang":
                el.set(f"{{{XML_NS}}}lang", v)
            elif k == "eId":
                el.set("eId", v)
            elif k == "wId":
                el.set("wId", v)
            else:
                el.set(k.replace("_", ""), v)
        if text:
            el.text = _sanitize_xml_text(text)
        return el

    def generate_collection(self) -> etree._Element:
        """Generate the top-level documentCollection for the entire Final Acts."""
        root = self._el("akomaNtoso")
        doc_collection = self._el("documentCollection", root, name="finalActs")
        doc_collection.set(f"{{{XML_NS}}}lang", "en")

        self._add_collection_meta(doc_collection)
        self._add_collection_preface(doc_collection)

        coll_body = self._el("collectionBody", doc_collection)

        for part_name, documents in self.acts.parts.items():
            part_eid = self._make_eid(part_name)
            part_el = self._el("component", coll_body, eId=f"cmp_{part_eid}")
            self._el("componentRef",
                      part_el,
                      src=f"#cmp_{part_eid}",
                      showAs=part_name)

        self._add_components_section(doc_collection)

        return root

    def _add_collection_meta(self, parent):
        """Add metadata block for the collection."""
        meta = self._el("meta", parent)
        ident = self._el("identification", meta, source="#itu")

        work_iri_base = "/akn/un/officialGazette/publication/itu-pp/2018-11-15/pp-18-final-acts"

        work = self._el("FRBRWork", ident)
        self._el("FRBRthis", work, value=f"{work_iri_base}/!main")
        self._el("FRBRuri", work, value=work_iri_base)
        self._el("FRBRdate", work, date="2018-11-15", name="publication")
        self._el("FRBRauthor", work, href="#itu-pp")
        self._el("FRBRcountry", work, value="un")
        self._el("FRBRsubtype", work, value="publication")
        self._el("FRBRnumber", work, value="pp-18-final-acts", showAs="Final Acts PP-18")

        expr = self._el("FRBRExpression", ident)
        self._el("FRBRthis", expr, value=f"{work_iri_base}/eng@2018-11-15/!main")
        self._el("FRBRuri", expr, value=f"{work_iri_base}/eng@2018-11-15")
        self._el("FRBRdate", expr, date="2018-11-15", name="publication")
        self._el("FRBRauthor", expr, href="#itu-pp")
        self._el("FRBRlanguage", expr, language="eng")

        manif = self._el("FRBRManifestation", ident)
        self._el("FRBRthis", manif, value=f"{work_iri_base}/eng@2018-11-15/.xml")
        self._el("FRBRuri", manif, value=f"{work_iri_base}/eng@2018-11-15/.xml")
        self._el("FRBRdate", manif, date=self.today, name="XMLMarkup")
        self._el("FRBRauthor", manif, href="#converter")

        refs = self._el("references", meta, source="#converter")
        self._el("TLCOrganization",
                 refs,
                 eId="itu",
                 href="/ontology/organizations/itu",
                 showAs="International Telecommunication Union")
        self._el("TLCOrganization",
                 refs,
                 eId="itu-pp",
                 href="/ontology/organizations/itu-pp",
                 showAs="ITU Plenipotentiary Conference (Dubai, 2018)")
        self._el("TLCOrganization",
                 refs,
                 eId="converter",
                 href="/ontology/software/akn4itu-converter",
                 showAs="AKN4ITU PDF Converter")

    def _add_collection_preface(self, parent):
        """Add preface block for the collection."""
        preface = self._el("preface", parent)
        long_title = self._el("longTitle", preface)
        p = self._el("p", long_title)
        doc_type = self._el("docType", p, text="FINAL ACTS")
        p_text = self._el("docTitle", p,
                          text=f"of the {self.acts.conference} ({self.acts.location}, {self.acts.year})")

    def _add_components_section(self, doc_collection):
        """Add the <components> section with each individual document."""
        components = self._el("components", doc_collection)

        for part_name, documents in self.acts.parts.items():
            for doc_item in documents:
                comp_eid = self._doc_eid(doc_item)
                comp_el = self._el("component", components, eId=f"cmp_{comp_eid}")
                doc_xml = self._generate_single_document(doc_item)
                comp_el.append(doc_xml)

    def _generate_single_document(self, doc_item: DocumentItem) -> etree._Element:
        """Generate AKN4UN XML for a single Resolution/Decision/Recommendation."""
        doc_type_akn = "statement"
        subtype = "deliberation"
        name = doc_item.doc_type.lower()

        statement = self._el(doc_type_akn, name=name)
        statement.set(f"{{{XML_NS}}}lang", "en")

        self._add_document_meta(statement, doc_item)
        self._add_document_preface(statement, doc_item)

        if doc_item.preamble_sections:
            self._add_document_preamble(statement, doc_item)

        self._add_document_body(statement, doc_item)

        if doc_item.annexes:
            self._add_document_attachments(statement, doc_item)

        return statement

    def _add_document_meta(self, parent, doc_item: DocumentItem):
        """Add FRBR metadata for a single document."""
        meta = self._el("meta", parent)
        ident = self._el("identification", meta, source="#itu")

        num_slug = doc_item.number.replace("/", "-").replace(" ", "_")
        doc_prefix = doc_item.doc_type.lower()[:3]
        work_iri = f"/akn/un/statement/deliberation/itu-pp/2018-11-15/{doc_prefix}-{num_slug}"

        work = self._el("FRBRWork", ident)
        self._el("FRBRthis", work, value=f"{work_iri}/!main")
        self._el("FRBRuri", work, value=work_iri)
        self._el("FRBRdate", work, date="2018-11-15", name="adoption")
        self._el("FRBRauthor", work, href="#itu-pp")
        self._el("FRBRcountry", work, value="un")
        self._el("FRBRsubtype", work, value="deliberation")
        num_el = self._el("FRBRnumber", work, value=f"{doc_prefix}-{num_slug}")
        num_el.set("showAs", f"{doc_item.doc_type} {doc_item.number} ({doc_item.revision})")

        expr = self._el("FRBRExpression", ident)
        self._el("FRBRthis", expr, value=f"{work_iri}/eng@2018-11-15/!main")
        self._el("FRBRuri", expr, value=f"{work_iri}/eng@2018-11-15")
        self._el("FRBRdate", expr, date="2018-11-15", name="adoption")
        self._el("FRBRauthor", expr, href="#itu-pp")
        self._el("FRBRlanguage", expr, language="eng")

        manif = self._el("FRBRManifestation", ident)
        self._el("FRBRthis", manif, value=f"{work_iri}/eng@2018-11-15/.xml")
        self._el("FRBRuri", manif, value=f"{work_iri}/eng@2018-11-15/.xml")
        self._el("FRBRdate", manif, date=self.today, name="XMLMarkup")
        self._el("FRBRauthor", manif, href="#converter")

        refs = self._el("references", meta, source="#converter")
        self._el("TLCOrganization",
                 refs,
                 eId="itu",
                 href="/ontology/organizations/itu",
                 showAs="International Telecommunication Union")
        self._el("TLCOrganization",
                 refs,
                 eId="itu-pp",
                 href="/ontology/organizations/itu-pp",
                 showAs="ITU Plenipotentiary Conference")

    def _add_document_preface(self, parent, doc_item: DocumentItem):
        """Add the identification/title block."""
        preface = self._el("preface", parent)
        long_title = self._el("longTitle", preface, eId="longTitle_1")
        p = self._el("p", long_title)

        self._el("docType", p, text=doc_item.doc_type)
        self._el("docNumber", p, text=f"{doc_item.number} ({doc_item.revision})")

        title_block = self._el("container", preface, name="title", eId="container_title")
        self._el("p", title_block, text=doc_item.title)

    def _add_document_preamble(self, parent, doc_item: DocumentItem):
        """Add the preamble with recitals/considering clauses."""
        preamble = self._el("preamble", parent, eId="preamble")

        if doc_item.enacting_formula:
            formula = self._el("formula", preamble, name="enactingFormula", eId="formula_1")
            self._el("p", formula, text=doc_item.enacting_formula)

        recital_counter = 0
        for sec in doc_item.preamble_sections:
            recitals = self._el("recitals", preamble, eId=f"recs_{self._make_eid(sec.keyword)}")

            intro = self._el("intro", recitals)
            p_intro = self._el("p", intro)
            i_el = etree.SubElement(p_intro, f"{{{AKN_NS}}}i")
            i_el.text = sec.keyword

            for para in sec.paragraphs:
                recital_counter += 1
                rec_eid = f"rec_{recital_counter}"

                if para.label:
                    recital = self._el("recital", recitals, eId=rec_eid)
                    self._el("num", recital, text=para.label)
                    self._el("p", recital, text=para.text)
                else:
                    recital = self._el("recital", recitals, eId=rec_eid)
                    self._el("p", recital, text=para.text)

    def _add_document_body(self, parent, doc_item: DocumentItem):
        """Add the main body with operative sections."""
        main_body = self._el("mainBody", parent, eId="body")

        para_counter = 0

        for sec in doc_item.operative_sections:
            sec_eid = self._make_eid(sec.keyword)
            section = self._el("hcontainer", main_body, name=sec_eid, eId=f"hcont_{sec_eid}")

            heading = self._el("heading", section)
            i_el = etree.SubElement(heading, f"{{{AKN_NS}}}i")
            i_el.text = sec.keyword

            for para in sec.paragraphs:
                para_counter += 1

                if para.num:
                    para_el = self._el("paragraph", section, eId=f"para_{para.num}")
                    self._el("num", para_el, text=para.num)

                    if para.sub_paragraphs:
                        content = self._el("content", para_el)
                        if para.text:
                            self._el("p", content, text=para.text)
                        lst = self._el("list", para_el, eId=f"para_{para.num}__list_1")

                        for sp in para.sub_paragraphs:
                            point_eid = f"para_{para.num}__point_{sp.label.replace(')', '').replace('.', '-')}"
                            point = self._el("point", lst, eId=point_eid)
                            self._el("num", point, text=sp.label)
                            content_sp = self._el("content", point)
                            self._el("p", content_sp, text=sp.text)
                    else:
                        content = self._el("content", para_el)
                        self._el("p", content, text=para.text)
                else:
                    block = self._el("paragraph", section, eId=f"para_unnumbered_{para_counter}")
                    content = self._el("content", block)
                    self._el("p", content, text=para.text)

    def _add_document_attachments(self, parent, doc_item: DocumentItem):
        """Add annexes/attachments if present."""
        attachments = self._el("attachments", parent)
        for i, annex_text in enumerate(doc_item.annexes, 1):
            att = self._el("attachment", attachments, eId=f"att_{i}")
            heading = self._el("heading", att, text=f"Annex {i}")
            doc_el = self._el("doc", att, name="annex")
            meta = self._el("meta", doc_el)
            ident = self._el("identification", meta, source="#itu")
            main_body = self._el("mainBody", doc_el)
            p = self._el("p", main_body, text=annex_text[:500])

    def _make_eid(self, text: str) -> str:
        """Convert text to a valid eId."""
        eid = re.sub(r"[^a-zA-Z0-9]", "_", text.lower())
        eid = re.sub(r"_+", "_", eid).strip("_")
        return eid[:50]

    def _doc_eid(self, doc_item: DocumentItem) -> str:
        """Create eId for a document item."""
        prefix = doc_item.doc_type.lower()[:3]
        return f"{prefix}_{doc_item.number}"


# ---------------------------------------------------------------------------
# XML Writer
# ---------------------------------------------------------------------------

def write_xml(root: etree._Element, output_path: str):
    """Write the XML tree to file with proper formatting."""
    tree = etree.ElementTree(root)
    etree.indent(tree, space="  ")
    with open(output_path, "wb") as f:
        tree.write(
            f,
            xml_declaration=True,
            encoding="UTF-8",
            pretty_print=True,
        )
    print(f"Written: {output_path}")


def write_individual_documents(final_acts: FinalActs, output_dir: str):
    """Write each document as a separate AKN4UN XML file."""
    generator = AKNGenerator(final_acts)

    for part_name, documents in final_acts.parts.items():
        for doc_item in documents:
            prefix = doc_item.doc_type.lower()[:3]
            filename = f"{prefix}_{doc_item.number}.xml"
            filepath = os.path.join(output_dir, filename)

            root = etree.Element(f"{{{AKN_NS}}}akomaNtoso", nsmap=NSMAP)
            doc_xml = generator._generate_single_document(doc_item)
            root.append(doc_xml)
            write_xml(root, filepath)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Convert ITU Final Acts PDF to AKN4UN XML"
    )
    parser.add_argument("input_pdf", help="Path to the Final Acts PDF file")
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Output directory (default: same as input PDF)",
    )
    parser.add_argument(
        "--individual",
        action="store_true",
        help="Also write each document as a separate XML file",
    )
    args = parser.parse_args()

    if not os.path.exists(args.input_pdf):
        print(f"Error: File not found: {args.input_pdf}")
        sys.exit(1)

    output_dir = args.output_dir or os.path.dirname(os.path.abspath(args.input_pdf))
    os.makedirs(output_dir, exist_ok=True)

    print(f"Reading PDF: {args.input_pdf}")
    extractor = PDFExtractor(args.input_pdf)

    print("Parsing document structure...")
    doc_parser = FinalActsParser(extractor)
    final_acts = doc_parser.parse()

    total_docs = sum(len(docs) for docs in final_acts.parts.values())
    print(f"Found {total_docs} documents across {len(final_acts.parts)} parts:")
    for part_name, docs in final_acts.parts.items():
        print(f"  {part_name}: {len(docs)} documents")
        for d in docs[:3]:
            print(f"    - {d.doc_type} {d.number}: {d.title[:60]}")
        if len(docs) > 3:
            print(f"    ... and {len(docs) - 3} more")

    # Generate the collection XML
    print("\nGenerating AKN4UN XML...")
    generator = AKNGenerator(final_acts)
    root = generator.generate_collection()

    collection_path = os.path.join(output_dir, "pp18_final_acts_akn.xml")
    write_xml(root, collection_path)

    # Optionally write individual files
    if args.individual:
        individual_dir = os.path.join(output_dir, "individual")
        os.makedirs(individual_dir, exist_ok=True)
        print(f"\nWriting individual documents to: {individual_dir}")
        write_individual_documents(final_acts, individual_dir)

    extractor.close()

    print("\nConversion complete!")
    print(f"Collection file: {collection_path}")

    # Print a sample of the generated XML
    xml_str = etree.tostring(root, pretty_print=True, encoding="unicode")
    lines = xml_str.split("\n")
    print(f"\nXML preview (first 50 lines of {len(lines)} total):")
    for line in lines[:50]:
        print(line)
    if len(lines) > 50:
        print(f"... ({len(lines) - 50} more lines)")


if __name__ == "__main__":
    main()
