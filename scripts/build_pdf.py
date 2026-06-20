"""
Build a project PDF from a Markdown source.

Pipeline:  Markdown --(python-markdown)--> styled HTML --(headless Chrome)--> PDF

Usage:
    python scripts/build_pdf.py                       # builds both project PDFs
    python scripts/build_pdf.py DOCUMENTATION.md out.pdf   # build one explicitly
"""
import pathlib
import subprocess
import sys

import markdown

ROOT = pathlib.Path(__file__).resolve().parents[1]
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

# (markdown source, output PDF) pairs built when no CLI args are given.
DEFAULT_TARGETS = [
    ("DOCUMENTATION.md", "KnowledgeHub_Documentation.pdf"),
    ("EXPLANATION_GUIDE.md", "KnowledgeHub_Explanation_Guide.pdf"),
    ("CODE_WALKTHROUGH.md", "KnowledgeHub_Code_Walkthrough.pdf"),
]

CSS = """
@page { size: A4; margin: 18mm 16mm; }
* { box-sizing: border-box; }
body { font-family: -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
       color: #1b1f23; line-height: 1.55; font-size: 12px; max-width: 100%; }
h1 { font-size: 26px; color: #0d47a1; border-bottom: 3px solid #0d47a1; padding-bottom: 6px; }
h2 { font-size: 19px; color: #11508a; margin-top: 26px; border-bottom: 1px solid #d0d7de; padding-bottom: 4px; page-break-after: avoid; }
h3 { font-size: 15px; color: #24292f; margin-top: 18px; page-break-after: avoid; }
p, li { font-size: 12px; }
code { background: #f0f3f6; padding: 1px 5px; border-radius: 4px;
       font-family: "SF Mono", Menlo, Consolas, monospace; font-size: 11px; color: #b3245f; }
pre { background: #0d1117; color: #c9d1d9; padding: 12px 14px; border-radius: 8px;
      overflow-x: auto; font-size: 10.5px; line-height: 1.45; page-break-inside: avoid; }
pre code { background: transparent; color: inherit; padding: 0; }
table { border-collapse: collapse; width: 100%; margin: 10px 0; font-size: 11px; page-break-inside: avoid; }
th, td { border: 1px solid #d0d7de; padding: 6px 9px; text-align: left; vertical-align: top; }
th { background: #eef3f8; }
img { max-width: 100%; height: auto; display: block; margin: 10px auto;
      border: 1px solid #e1e4e8; border-radius: 6px; page-break-inside: avoid; }
em { color: #57606a; }
blockquote { border-left: 4px solid #d0d7de; margin: 10px 0; padding: 2px 14px; color: #57606a; background: #f6f8fa; }
hr { border: none; border-top: 1px solid #d0d7de; margin: 22px 0; }
a { color: #0969da; text-decoration: none; }
h2 { page-break-before: auto; }
"""

def main() -> None:
    text = SRC.read_text(encoding="utf-8")
    body = markdown.markdown(
        text,
        extensions=["tables", "fenced_code", "codehilite", "toc", "sane_lists", "attr_list"],
        extension_configs={"codehilite": {"guess_lang": False, "noclasses": True}},
    )
    # base href lets relative image paths (docs/diagrams/..., docs/screenshots/...) resolve.
    html = f"""<!doctype html>
<html><head><meta charset="utf-8">
<base href="file://{ROOT}/">
<style>{CSS}</style></head>
<body>{body}</body></html>"""
    HTML_OUT.write_text(html, encoding="utf-8")
    print(f"HTML written: {HTML_OUT}")

    subprocess.run(
        [CHROME, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
         f"--print-to-pdf={PDF_OUT}", "--virtual-time-budget=10000",
         f"file://{HTML_OUT}"],
        check=True, capture_output=True,
    )
    print(f"PDF written:  {PDF_OUT}  ({PDF_OUT.stat().st_size // 1024} KB)")


def build(src_name: str, pdf_name: str) -> None:
    global SRC, HTML_OUT, PDF_OUT
    SRC = ROOT / src_name
    HTML_OUT = ROOT / "docs" / ("_build_" + pathlib.Path(src_name).stem + ".html")
    PDF_OUT = ROOT / pdf_name
    main()


if __name__ == "__main__":
    if len(sys.argv) == 3:
        build(sys.argv[1], sys.argv[2])
    else:
        for src_name, pdf_name in DEFAULT_TARGETS:
            build(src_name, pdf_name)
