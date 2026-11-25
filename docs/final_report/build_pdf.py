"""Builds zarojelentes.pdf from zarojelentes.md (A4, print layout).

No external Markdown package: a small converter for the subset the report uses
(headings, paragraphs, lists, tables, images with a caption line, bold/italic/code,
links, horizontal rules). The PDF is printed by headless Chrome.

    python build_pdf.py        # in docs/final_report/ -> zarojelentes.pdf
"""
import html
import re
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC, HTML, PDF = HERE / "zarojelentes.md", HERE / "zarojelentes.html", HERE / "zarojelentes.pdf"

CSS = """
@page { size: A4; margin: 22mm 20mm 20mm 20mm;
        @bottom-center { content: counter(page); font: 9pt 'Liberation Sans', sans-serif; color: #666; } }
@page :first { @bottom-center { content: none; } }
html { font: 10.5pt/1.45 'Liberation Serif', 'DejaVu Serif', serif; color: #111; }
body { margin: 0; }
p, li { text-align: justify; hyphens: auto; }
p { margin: 0 0 0.55em; orphans: 3; widows: 3; }
h1, h2, h3 { font-family: 'Liberation Sans', sans-serif; color: #111; break-after: avoid; line-height: 1.25; }
h1 { font-size: 20pt; margin: 0 0 4pt; }
h2 { font-size: 14pt; margin: 18pt 0 6pt; padding-bottom: 2pt; border-bottom: 0.6pt solid #999; }
h3 { font-size: 11.5pt; margin: 12pt 0 4pt; }
.byline { font-family: 'Liberation Sans', sans-serif; color: #444; margin-bottom: 10pt; }
hr { border: 0; border-top: 0.6pt solid #999; margin: 10pt 0; }
ul, ol { margin: 0 0 0.6em; padding-left: 1.4em; }
li { margin-bottom: 0.15em; }
code { font: 9pt 'Liberation Mono', monospace; background: #f2f2f0; padding: 0 2px; border-radius: 2px; }
figure { margin: 10pt 0 12pt; text-align: center; break-inside: avoid; }
figure img { max-width: 100%; max-height: 95mm; }
figure.photo img { max-height: 80mm; }
figcaption { font-size: 9pt; color: #333; margin-top: 4pt; text-align: center; font-style: italic; }
.tcap { font-size: 9pt; font-style: italic; color: #333; margin: 10pt 0 3pt; break-after: avoid; text-align: left; }
table { border-collapse: collapse; margin: 0 auto 12pt; font-size: 9pt; break-inside: avoid; }
th, td { border-top: 0.5pt solid #bbb; border-bottom: 0.5pt solid #bbb; padding: 3pt 7pt; text-align: left; }
th { background: #f0f0ee; font-family: 'Liberation Sans', sans-serif; font-weight: bold; }
.eq { text-align: center; margin: 8pt 0 10pt; font-size: 11.5pt; }
.refs p { text-align: left; font-size: 9pt; line-height: 1.3; padding-left: 2.2em; text-indent: -2.2em; margin-bottom: 0.25em; }
.footer-note { font-size: 8.5pt; color: #444; text-align: left; break-before: avoid; }
a { color: #1a4f9c; text-decoration: none; word-break: break-all; }
"""


def inline(t):
    t = html.escape(t, quote=False)
    t = re.sub(r"`([^`]+)`", r"<code>\1</code>", t)
    t = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(r"(?<![*\w])\*([^*]+)\*(?![*\w])", r"<em>\1</em>", t)
    t = re.sub(r"(?<![\"=])(https?://[^\s<]+)", r'<a href="\1">\1</a>', t)
    t = re.sub(r"\bR_F\b", "R<sub>F</sub>", t)
    return t


def convert(md):
    lines = md.splitlines()
    out, i, in_refs, title_done = [], 0, False, False
    para = []

    def flush():
        if para:
            text = " ".join(s.strip() for s in para)
            out.append(f"<p>{inline(text)}</p>")
            para.clear()

    while i < len(lines):
        ln = lines[i]
        s = ln.strip()
        if not s:
            flush(); i += 1; continue
        m = re.match(r"^(#{1,3}) (.*)", ln)
        if m:
            flush()
            lvl, txt = len(m.group(1)), m.group(2)
            if lvl == 2 and in_refs:
                out.append("</div>"); in_refs = False
            out.append(f"<h{lvl}>{inline(txt)}</h{lvl}>")
            if lvl == 2 and txt.strip() == "Hivatkozások":
                out.append('<div class="refs">'); in_refs = True
            i += 1
            if lvl == 1 and not title_done:   # byline right below the title
                while i < len(lines) and not lines[i].strip():
                    i += 1
                out.append(f'<div class="byline">{inline(lines[i].strip())}</div>')
                title_done = True
                i += 1
            continue
        if s == "---":
            flush()
            if in_refs:
                out.append("</div>"); in_refs = False
            out.append("<hr>"); i += 1; continue
        m = re.match(r"^!\[([^\]]*)\]\(([^)]+)\)", s)
        if m:
            flush()
            alt, src = m.groups()
            cap = ""
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            if j < len(lines) and re.match(r"^\*[^*].*\*$", lines[j].strip()):
                cap = lines[j].strip()[1:-1]
                i = j
            cls = ' class="photo"' if src.endswith((".jpeg", ".jpg")) else ""
            out.append(f'<figure{cls}><img src="{src}" alt="{html.escape(alt)}">'
                       + (f"<figcaption>{inline(cap)}</figcaption>" if cap else "") + "</figure>")
            i += 1; continue
        if re.match(r"^\*\d+\. táblázat", s) or (s.startswith("*") and s.endswith("*") and "táblázat" in s[:20]):
            flush(); out.append(f'<div class="tcap">{inline(s[1:-1])}</div>'); i += 1; continue
        if s.startswith("|"):
            flush()
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            head, body = rows[0], [r for r in rows[1:] if not all(re.match(r"^:?-+:?$", c) for c in r)]
            out.append("<table><thead><tr>" + "".join(f"<th>{inline(c)}</th>" for c in head) + "</tr></thead><tbody>"
                       + "".join("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>" for r in body)
                       + "</tbody></table>")
            continue
        if re.match(r"^[-*] ", s) or re.match(r"^\d+\. ", s):
            flush()
            ordered = bool(re.match(r"^\d+\. ", s))
            tag = "ol" if ordered else "ul"
            items = []
            while i < len(lines):
                t = lines[i].strip()
                mm = re.match(r"^\d+\. (.*)", t) if ordered else re.match(r"^[-*] (.*)", t)
                if mm:
                    items.append(mm.group(1))
                elif t and items and lines[i].startswith("  "):
                    items[-1] += " " + t          # continuation line
                else:
                    break
                i += 1
            out.append(f"<{tag}>" + "".join(f"<li>{inline(x)}</li>" for x in items) + f"</{tag}>")
            continue
        if ln.startswith("  ") and s.startswith("**") and s.endswith("**"):
            flush(); out.append(f'<div class="eq">{inline(s)}</div>'); i += 1; continue
        if s.startswith("**Adat és kód:**"):
            flush(); out.append(f'<p class="footer-note">{inline(s)}</p>'); i += 1; continue
        para.append(ln)
        i += 1
    flush()
    if in_refs:
        out.append("</div>")
    return "\n".join(out)


def main():
    body = convert(SRC.read_text(encoding="utf-8"))
    title = re.search(r"^# (.*)", SRC.read_text(encoding="utf-8"), re.M).group(1)
    HTML.write_text(f'<!doctype html><html lang="hu"><head><meta charset="utf-8"><title>{html.escape(title)}</title>'
                    f"<style>{CSS}</style></head><body>{body}</body></html>", encoding="utf-8")
    subprocess.run(["google-chrome", "--headless=new", "--no-pdf-header-footer", "--disable-gpu",
                    f"--print-to-pdf={PDF}", HTML.as_uri()], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
    print(PDF)


if __name__ == "__main__":
    main()
