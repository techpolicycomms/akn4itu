#!/usr/bin/env python3
"""Generate browser-friendly HTML previews from AKN XML files."""

from __future__ import annotations

import argparse
import html
import re
import webbrowser
from pathlib import Path
from typing import List
from xml.etree import ElementTree as ET

AKN_NS = {"akn": "http://docs.oasis-open.org/legaldocml/ns/akn/3.0"}


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _node_text(node: ET.Element | None) -> str:
    if node is None:
        return ""
    return _clean_text("".join(node.itertext()))


def _statement_heading(statement: ET.Element, fallback: str) -> str:
    frbr_number = statement.find(
        ".//akn:identification/akn:FRBRWork/akn:FRBRnumber", AKN_NS
    )
    return (
        (frbr_number.get("showAs") if frbr_number is not None else None)
        or (frbr_number.get("value") if frbr_number is not None else None)
        or fallback
    )


def _statement_subtitle(statement: ET.Element) -> str:
    return _node_text(
        statement.find("./akn:preface/akn:container[@name='title']/akn:p", AKN_NS)
    )


def _render_paragraph(paragraph: ET.Element) -> str:
    number = _node_text(paragraph.find("akn:num", AKN_NS))
    content = _node_text(paragraph.find("akn:content", AKN_NS))
    if not content:
        content = _node_text(paragraph.find("akn:p", AKN_NS))

    list_items: List[str] = []
    for point in paragraph.findall("./akn:list/akn:point", AKN_NS):
        point_num = _node_text(point.find("akn:num", AKN_NS))
        point_text = _node_text(point.find("akn:content", AKN_NS))
        if not point_text:
            point_text = _node_text(point.find("akn:p", AKN_NS))
        label = f"<strong>{html.escape(point_num)}</strong> " if point_num else ""
        list_items.append(f"<li>{label}{html.escape(point_text)}</li>")

    label = f'<span class="num">{html.escape(number)}</span>' if number else ""
    rendered = [f"<p>{label}{html.escape(content)}</p>"]
    if list_items:
        rendered.append("<ul>")
        rendered.extend(list_items)
        rendered.append("</ul>")
    return "\n".join(rendered)


def _render_statement_sections(
    statement: ET.Element, section_heading_tag: str = "h3"
) -> tuple[str, str]:
    recitals_html: List[str] = []
    for recitals in statement.findall("./akn:preamble/akn:recitals", AKN_NS):
        intro = _node_text(recitals.find("akn:intro", AKN_NS))
        if intro:
            recitals_html.append(f"<{section_heading_tag}>{html.escape(intro)}</{section_heading_tag}>")
        recitals_html.append("<ul>")
        for recital in recitals.findall("akn:recital", AKN_NS):
            recital_num = _node_text(recital.find("akn:num", AKN_NS))
            recital_text = _node_text(recital.find("akn:p", AKN_NS))
            label = (
                f"<strong>{html.escape(recital_num)}</strong> " if recital_num else ""
            )
            recitals_html.append(f"<li>{label}{html.escape(recital_text)}</li>")
        recitals_html.append("</ul>")

    body_html: List[str] = []
    for section in statement.findall("./akn:mainBody/akn:hcontainer", AKN_NS):
        section_title = _node_text(section.find("akn:heading", AKN_NS))
        if section_title:
            body_html.append(f"<{section_heading_tag}>{html.escape(section_title)}</{section_heading_tag}>")
        for paragraph in section.findall("akn:paragraph", AKN_NS):
            body_html.append(_render_paragraph(paragraph))

    recitals_block = "".join(recitals_html) if recitals_html else "<p>(No preamble extracted)</p>"
    body_block = "".join(body_html) if body_html else "<p>(No operative content extracted)</p>"
    return recitals_block, body_block


def _base_style() -> str:
    return """
    :root { color-scheme: light dark; }
    body {
      font-family: Segoe UI, Arial, sans-serif;
      line-height: 1.55;
      max-width: 1050px;
      margin: 2rem auto;
      padding: 0 1rem;
    }
    h1, h2, h3, h4 { line-height: 1.3; }
    h2 { margin-top: 2rem; border-bottom: 1px solid #9994; padding-bottom: 0.35rem; }
    h3 { margin-top: 1.5rem; }
    .num {
      font-weight: 600;
      min-width: 2rem;
      display: inline-block;
      margin-right: 0.35rem;
    }
    ul { padding-left: 1.4rem; }
    li { margin-bottom: 0.35rem; }
    .source {
      margin-top: 2.25rem;
      padding-top: 1rem;
      border-top: 1px solid #9994;
      font-size: 0.92rem;
      opacity: 0.85;
    }
    .toc { border: 1px solid #9994; border-radius: 8px; padding: 1rem; margin: 1rem 0 1.5rem; }
    .doc-card { border-top: 1px solid #9994; padding-top: 1rem; margin-top: 1.5rem; }
    .back { font-size: 0.9rem; margin-bottom: 1rem; }
    """


def _render_statement_page(statement: ET.Element, source_label: str, fallback_title: str) -> tuple[str, str]:
    heading = _statement_heading(statement, fallback_title)
    subtitle = _statement_subtitle(statement)
    recitals_block, body_block = _render_statement_sections(statement, section_heading_tag="h3")

    page = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(heading)}</title>
  <style>{_base_style()}</style>
</head>
<body>
  <h1>{html.escape(heading)}</h1>
  <p>{html.escape(subtitle)}</p>
  <h2>Preamble</h2>
  {recitals_block}
  <h2>Main Body</h2>
  {body_block}
  <p class="source">Source XML: {html.escape(source_label)}</p>
</body>
</html>
"""
    return heading, page


def _render_collection_page(collection: ET.Element, xml_path: Path) -> tuple[str, str]:
    frbr_number = collection.find(
        ".//akn:identification/akn:FRBRWork/akn:FRBRnumber", AKN_NS
    )
    heading = (
        (frbr_number.get("showAs") if frbr_number is not None else None)
        or (frbr_number.get("value") if frbr_number is not None else None)
        or xml_path.stem
    )
    collection_subtitle = _node_text(
        collection.find("./akn:preface/akn:longTitle", AKN_NS)
    )

    blocks: List[str] = []
    toc_entries: List[str] = []
    statements = collection.findall("./akn:components/akn:component/akn:statement", AKN_NS)
    for idx, statement in enumerate(statements, start=1):
        title = _statement_heading(statement, f"Document {idx}")
        subtitle = _statement_subtitle(statement)
        anchor = f"doc-{idx}"
        toc_entries.append(f'<li><a href="#{anchor}">{html.escape(title)}</a></li>')

        recitals_block, body_block = _render_statement_sections(statement, section_heading_tag="h4")
        blocks.append(
            f"""
<article id="{anchor}" class="doc-card">
  <h3>{html.escape(title)}</h3>
  <p>{html.escape(subtitle)}</p>
  <h4>Preamble</h4>
  {recitals_block}
  <h4>Main Body</h4>
  {body_block}
  <p class="back"><a href="#top">Back to documents list</a></p>
</article>
"""
        )

    toc = "".join(toc_entries) if toc_entries else "<li>(No embedded statements found)</li>"
    body = "".join(blocks) if blocks else "<p>(No embedded statements found)</p>"

    page = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(heading)}</title>
  <style>{_base_style()}</style>
</head>
<body>
  <div id="top"></div>
  <h1>{html.escape(heading)}</h1>
  <p>{html.escape(collection_subtitle)}</p>
  <section class="toc">
    <h2>Documents in this collection</h2>
    <ul>{toc}</ul>
  </section>
  {body}
  <p class="source">Source XML: {html.escape(xml_path.name)}</p>
</body>
</html>
"""
    return heading, page


def _render_xml_file(xml_path: Path) -> tuple[str, str]:
    root = ET.parse(xml_path).getroot()
    statement = root.find("akn:statement", AKN_NS)
    if statement is not None:
        return _render_statement_page(
            statement=statement, source_label=xml_path.name, fallback_title=xml_path.stem
        )

    collection = root.find("akn:documentCollection", AKN_NS)
    if collection is not None:
        return _render_collection_page(collection, xml_path)

    raise ValueError(
        f"{xml_path.name} is not supported. Expected <statement> or <documentCollection>."
    )


def _write_index(items: List[tuple[str, str]], output_dir: Path) -> Path:
    rows = "\n".join(
        f'<li><a href="{html.escape(filename)}">{html.escape(title)}</a></li>'
        for title, filename in items
    )
    index_path = output_dir / "index.html"
    index_html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AKN Preview</title>
  <style>
    body {{
      font-family: Segoe UI, Arial, sans-serif;
      line-height: 1.5;
      max-width: 900px;
      margin: 2rem auto;
      padding: 0 1rem;
    }}
    li {{ margin-bottom: 0.45rem; }}
  </style>
</head>
<body>
  <h1>AKN Preview</h1>
  <p>Generated previews for XML files.</p>
  <ul>
    {rows}
  </ul>
</body>
</html>
"""
    index_path.write_text(index_html, encoding="utf-8")
    return index_path


def _collect_xml_files(input_dir: Path, input_file: Path | None) -> List[Path]:
    if input_file is not None:
        return [input_file.resolve()]
    return sorted(input_dir.resolve().glob("*.xml"))


def main() -> None:
    script_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(
        description="Generate browser preview pages for AKN XML files."
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=script_dir,
        help="Directory containing XML files (default: current script directory).",
    )
    parser.add_argument(
        "--input-file",
        type=Path,
        default=None,
        help="Single XML file to render (overrides --input-dir when set).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=script_dir / "preview_html",
        help="Directory where HTML files are written (default: preview_html).",
    )
    parser.add_argument(
        "--open",
        action="store_true",
        help="Open the generated index page in the default browser.",
    )
    args = parser.parse_args()

    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    xml_files = _collect_xml_files(args.input_dir, args.input_file)
    if not xml_files:
        raise SystemExit(f"No XML files found in: {args.input_dir.resolve()}")

    index_items: List[tuple[str, str]] = []
    for xml_file in xml_files:
        try:
            title, page = _render_xml_file(xml_file)
        except (ET.ParseError, ValueError) as exc:
            print(f"Skipped: {xml_file.name} ({exc})")
            continue
        out_name = f"{xml_file.stem}.html"
        (output_dir / out_name).write_text(page, encoding="utf-8")
        index_items.append((title, out_name))
        print(f"Written: {output_dir / out_name}")

    if not index_items:
        raise SystemExit(
            "No preview pages generated. Use --input-file for a specific document "
            "or provide a directory with AKN XML files."
        )

    index_path = _write_index(index_items, output_dir)
    print(f"Written: {index_path}")
    if args.open:
        webbrowser.open(index_path.as_uri())


if __name__ == "__main__":
    main()
