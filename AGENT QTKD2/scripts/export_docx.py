"""Pure-Python Markdown-to-DOCX exporter for Task 1 & Task 2 submission reports."""

from __future__ import annotations

import re
import zipfile
from pathlib import Path
from typing import List, Tuple
from xml.sax.saxutils import escape


ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = ROOT / "docs"

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _parse_inline_runs(text: str) -> str:
    """Convert **bold** and `code` tokens into WordprocessingML <w:r> runs."""
    tokens = re.split(r"(\*\*.*?\*\*|`[^`]+`)", text)
    runs: List[str] = []
    for tok in tokens:
        if not tok:
            continue
        if tok.startswith("**") and tok.endswith("**") and len(tok) > 4:
            inner = escape(tok[2:-2])
            runs.append(f'<w:r><w:rPr><w:b/></w:rPr><w:t xml:space="preserve">{inner}</w:t></w:r>')
        elif tok.startswith("`") and tok.endswith("`") and len(tok) > 2:
            inner = escape(tok[1:-1])
            runs.append(
                f'<w:r><w:rPr><w:rFonts w:ascii="Courier New" w:hAnsi="Courier New"/>'
                f'<w:color w:val="0F2744"/></w:rPr><w:t xml:space="preserve">{inner}</w:t></w:r>'
            )
        else:
            # Strip markdown links [label](url) -> label
            cleaned = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", tok)
            runs.append(f'<w:r><w:t xml:space="preserve">{escape(cleaned)}</w:t></w:r>')
    return "".join(runs) if runs else '<w:r><w:t xml:space="preserve"></w:t></w:r>'


def _make_paragraph(text: str, style: str = "", indent_left: int = 0) -> str:
    ppr_parts = []
    if style:
        ppr_parts.append(f'<w:pStyle w:val="{style}"/>')
    if indent_left:
        ppr_parts.append(f'<w:ind w:left="{indent_left}"/>')
    ppr_parts.append('<w:spacing w:after="100" w:line="276" w:lineRule="auto"/>')
    ppr = f"<w:pPr>{''.join(ppr_parts)}</w:pPr>"
    return f"<w:p>{ppr}{_parse_inline_runs(text)}</w:p>"


def _make_table(rows: List[List[str]]) -> str:
    if not rows:
        return ""
    col_count = max(len(r) for r in rows)
    tbl_pr = (
        "<w:tblPr>"
        '<w:tblW w:w="9000" w:type="dxa"/>'
        "<w:tblBorders>"
        '<w:top w:val="single" w:sz="6" w:space="0" w:color="CBD5E1"/>'
        '<w:left w:val="single" w:sz="6" w:space="0" w:color="CBD5E1"/>'
        '<w:bottom w:val="single" w:sz="6" w:space="0" w:color="CBD5E1"/>'
        '<w:right w:val="single" w:sz="6" w:space="0" w:color="CBD5E1"/>'
        '<w:insideH w:val="single" w:sz="4" w:space="0" w:color="E2E8F0"/>'
        '<w:insideV w:val="single" w:sz="4" w:space="0" w:color="E2E8F0"/>'
        "</w:tblBorders>"
        "</w:tblPr>"
    )
    cell_w = max(1200, int(9000 / max(1, col_count)))
    tr_xmls: List[str] = []
    for r_idx, row in enumerate(rows):
        tc_xmls: List[str] = []
        for c_idx in range(col_count):
            cell_txt = row[c_idx] if c_idx < len(row) else ""
            shd = '<w:shd w:val="clear" w:color="auto" w:fill="E2E8F0"/>' if r_idx == 0 else ""
            txt_fmt = f"**{cell_txt}**" if r_idx == 0 and not cell_txt.startswith("**") else cell_txt
            tc_xmls.append(
                "<w:tc>"
                f'<w:tcPr><w:tcW w:w="{cell_w}" w:type="dxa"/>{shd}'
                '<w:tcMar><w:top w:w="80" w:type="dxa"/><w:bottom w:w="80" w:type="dxa"/>'
                '<w:left w:w="100" w:type="dxa"/><w:right w:w="100" w:type="dxa"/></w:tcMar></w:tcPr>'
                f"{_make_paragraph(txt_fmt)}"
                "</w:tc>"
            )
        tr_xmls.append(f"<w:tr>{''.join(tc_xmls)}</w:tr>")
    return f"<w:tbl>{tbl_pr}{''.join(tr_xmls)}</w:tbl>"


def markdown_to_docx(md_path: Path, docx_path: Path) -> None:
    """Convert a Markdown file into a styled Word .docx document."""
    lines = md_path.read_text(encoding="utf-8").splitlines()
    body_blocks: List[str] = []
    i = 0
    in_code_block = False

    while i < len(lines):
        raw = lines[i]
        stripped = raw.strip()

        if stripped.startswith("```"):
            in_code_block = not in_code_block
            i += 1
            continue
        if in_code_block:
            body_blocks.append(_make_paragraph(f"`{raw}`", indent_left=360))
            i += 1
            continue

        if not stripped or stripped == "---":
            i += 1
            continue

        # Markdown table block
        if stripped.startswith("|"):
            table_rows: List[List[str]] = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                tline = lines[i].strip()
                if re.fullmatch(r"[\|\-:\s]+", tline):
                    i += 1
                    continue
                cells = [c.strip() for c in tline.split("|")[1:-1]]
                table_rows.append(cells)
                i += 1
            body_blocks.append(_make_table(table_rows))
            body_blocks.append(_make_paragraph(""))
            continue

        if stripped.startswith("### "):
            body_blocks.append(_make_paragraph(stripped[4:], style="Heading3"))
        elif stripped.startswith("## "):
            body_blocks.append(_make_paragraph(stripped[3:], style="Heading2"))
        elif stripped.startswith("# "):
            body_blocks.append(_make_paragraph(stripped[2:], style="Heading1"))
        elif stripped.startswith("- ") or stripped.startswith("* "):
            indent = 720 if raw.startswith("  ") else 360
            body_blocks.append(_make_paragraph(f"• {stripped[2:]}", indent_left=indent))
        elif re.match(r"^\d+\.\s+", stripped):
            indent = 720 if raw.startswith("  ") else 360
            body_blocks.append(_make_paragraph(stripped, indent_left=indent))
        else:
            body_blocks.append(_make_paragraph(stripped))
        i += 1

    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:document xmlns:w="{W_NS}">'
        "<w:body>"
        f"{''.join(body_blocks)}"
        "<w:sectPr>"
        '<w:pgSz w:w="11906" w:h="16838"/>'
        '<w:pgMar w:top="1134" w:right="1134" w:bottom="1134" w:left="1134"/>'
        "</w:sectPr>"
        "</w:body>"
        "</w:document>"
    )

    styles_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:styles xmlns:w="{W_NS}">'
        '<w:style w:type="paragraph" w:default="1" w:styleId="Normal">'
        '<w:name w:val="Normal"/>'
        '<w:rPr><w:rFonts w:ascii="Arial" w:hAnsi="Arial" w:cs="Arial"/><w:sz w:val="22"/></w:rPr>'
        "</w:style>"
        '<w:style w:type="paragraph" w:styleId="Heading1">'
        '<w:name w:val="heading 1"/><w:basedOn w:val="Normal"/>'
        '<w:pPr><w:spacing w:before="200" w:after="120"/></w:pPr>'
        '<w:rPr><w:b/><w:color w:val="0F2744"/><w:sz w:val="32"/></w:rPr>'
        "</w:style>"
        '<w:style w:type="paragraph" w:styleId="Heading2">'
        '<w:name w:val="heading 2"/><w:basedOn w:val="Normal"/>'
        '<w:pPr><w:spacing w:before="180" w:after="80"/></w:pPr>'
        '<w:rPr><w:b/><w:color w:val="1B3B64"/><w:sz w:val="26"/></w:rPr>'
        "</w:style>"
        '<w:style w:type="paragraph" w:styleId="Heading3">'
        '<w:name w:val="heading 3"/><w:basedOn w:val="Normal"/>'
        '<w:pPr><w:spacing w:before="120" w:after="60"/></w:pPr>'
        '<w:rPr><w:b/><w:color w:val="0F766E"/><w:sz w:val="23"/></w:rPr>'
        "</w:style>"
        "</w:styles>"
    )

    content_types_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
        "</Types>"
    )

    root_rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
        "</Relationships>"
    )

    doc_rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
        "</Relationships>"
    )

    docx_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(docx_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types_xml)
        zf.writestr("_rels/.rels", root_rels_xml)
        zf.writestr("word/_rels/document.xml.rels", doc_rels_xml)
        zf.writestr("word/styles.xml", styles_xml)
        zf.writestr("word/document.xml", document_xml)


def main() -> None:
    pairs: List[Tuple[str, str]] = [
        ("BaoCao_Task1_PhanTich_ThietKe.md", "BaoCao_Task1_PhanTich_ThietKe.docx"),
        ("BaoCao_Task2_GiaiPhap_KiemThu.md", "BaoCao_Task2_GiaiPhap_KiemThu.docx"),
    ]
    for md_name, docx_name in pairs:
        markdown_to_docx(DOCS_DIR / md_name, DOCS_DIR / docx_name)
        print(f"Exported: {DOCS_DIR / docx_name}")


if __name__ == "__main__":
    main()

