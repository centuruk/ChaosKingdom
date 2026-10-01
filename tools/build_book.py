"""A dependency-free compiler for the deliberately small Markdown dialect of this book."""
from __future__ import annotations

import base64
import html
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
CHAPTERS = ROOT / "docs" / "book"


def anchor(path: Path) -> str:
    return "chapter-" + path.stem


def inline(value: str, origin: Path) -> str:
    tokens = []
    def reserve(markup: str) -> str:
        tokens.append(markup)
        return f"\x00{len(tokens) - 1}\x00"
    def image(match) -> str:
        alt, name = match.group(1), match.group(2)
        path = (origin.parent / name).resolve()
        if not path.is_relative_to(ROOT / "docs") or not path.is_file():
            raise ValueError(f"책 이미지가 없거나 허용 범위 밖입니다: {name}")
        mime = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}.get(path.suffix.lower())
        if not mime:
            raise ValueError(f"지원하지 않는 그림 형식: {path}")
        encoded = base64.b64encode(path.read_bytes()).decode()
        return reserve(f'<figure><img src="data:{mime};base64,{encoded}" alt="{html.escape(alt)}"><figcaption>{html.escape(alt)}</figcaption></figure>')
    value = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", image, value)
    value = re.sub(r"`([^`]+)`", lambda m: reserve("<code>" + html.escape(m.group(1)) + "</code>"), value)
    def link(match) -> str:
        label, target = match.group(1), match.group(2)
        path = (origin.parent / target).resolve()
        if path.parent == CHAPTERS and path.suffix == ".md":
            target = "#" + anchor(path)
        return reserve(f'<a href="{html.escape(target, quote=True)}">{html.escape(label)}</a>')
    value = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", link, value)
    value = html.escape(value)
    value = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", value)
    for i, token in enumerate(tokens):
        value = value.replace(f"\x00{i}\x00", token)
    return value


def render_markdown(source: str, origin: Path) -> str:
    lines, output, index = source.splitlines(), [], 0
    while index < len(lines):
        line = lines[index]
        if not line.strip():
            index += 1
            continue
        if line.startswith("```"):
            language = line[3:].strip()
            body = []
            index += 1
            while index < len(lines) and not lines[index].startswith("```"):
                body.append(lines[index])
                index += 1
            output.append(f'<pre data-language="{html.escape(language)}"><code>{html.escape(chr(10).join(body))}</code></pre>')
            index += 1
            continue
        if heading := re.match(r"^(#{1,6}) (.+)", line):
            level = len(heading.group(1))
            output.append(f"<h{level}>{inline(heading.group(2), origin)}</h{level}>")
            index += 1
            continue
        if line.startswith("|") and index + 1 < len(lines) and re.match(r"^\|[\s:|\-]+\|$", lines[index + 1]):
            headers = [c.strip() for c in line.strip("|").split("|")]
            output.append("<div class='table-wrap'><table><thead><tr>" + "".join(f"<th>{inline(c, origin)}</th>" for c in headers) + "</tr></thead><tbody>")
            index += 2
            while index < len(lines) and lines[index].startswith("|"):
                cells = [c.strip() for c in lines[index].strip("|").split("|")]
                output.append("<tr>" + "".join(f"<td>{inline(c, origin)}</td>" for c in cells) + "</tr>")
                index += 1
            output.append("</tbody></table></div>")
            continue
        if re.match(r"^(?:- |\d+\. )", line):
            ordered = bool(re.match(r"^\d+\. ", line))
            tag = "ol" if ordered else "ul"
            output.append(f"<{tag}>")
            while index < len(lines) and re.match(r"^(?:- |\d+\. )", lines[index]):
                value = re.sub(r"^(?:- |\d+\. )", "", lines[index])
                output.append(f"<li>{inline(value, origin)}</li>")
                index += 1
            output.append(f"</{tag}>")
            continue
        paragraph = [line]
        index += 1
        while index < len(lines) and lines[index].strip() and not re.match(r"^(?:#|```|\||- |\d+\. )", lines[index]):
            paragraph.append(lines[index])
            index += 1
        value = inline(" ".join(paragraph), origin)
        output.append(value if value.startswith("<figure>") else "<p>" + value + "</p>")
    return "\n".join(output)


CSS = """
:root{--ink:#253834;--muted:#61716b;--paper:#faf6ed;--accent:#3e796b;--gold:#ad8343}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:var(--paper);color:var(--ink);font-family:'Apple SD Gothic Neo','Malgun Gothic','Noto Sans KR',sans-serif;font-size:17px;line-height:1.95;word-break:keep-all}
aside{position:fixed;inset:0 auto 0 0;width:270px;background:#1b302d;color:#dce5df;padding:36px 25px;overflow:auto}aside .brand{font-size:21px;font-weight:800;line-height:1.5;margin-bottom:28px}aside a{display:block;color:#bdcbc4;text-decoration:none;font-size:14px;line-height:1.6;padding:8px 0;border-bottom:1px solid #304640}aside a:hover{color:#e6c891}
main{margin-left:270px;max-width:1210px;padding:0 64px 80px}.cover{padding:90px 0 70px;border-bottom:2px solid var(--accent);margin-bottom:50px}.eyebrow{font-size:14px;letter-spacing:3px;color:var(--gold)}.cover h1{font-size:58px;letter-spacing:-2px;line-height:1.35;margin:28px 0}.cover .sub{font-size:23px;color:var(--muted)}.meta{margin-top:35px;font-size:14px;color:var(--muted)}
article{padding:24px 0 54px;scroll-margin-top:25px;border-bottom:1px solid #d5ddd3}h1{font-size:35px;line-height:1.5;letter-spacing:-1px}h2{font-size:24px;margin:45px 0 18px}p{margin:0 0 20px}a{color:var(--accent)}code{background:#e8eee4;padding:2px 6px;border-radius:4px;font-family:Menlo,Consolas,monospace;font-size:14px;word-break:break-word}pre{background:#203632;color:#e0e8df;padding:25px;border-radius:8px;overflow:auto;line-height:1.75}pre code{background:none;color:inherit;padding:0;font-size:13px;white-space:pre-wrap}table{width:100%;border-collapse:collapse;font-size:15px;line-height:1.7;margin:15px 0 28px}th{text-align:left;background:#e5ebe0}th,td{padding:12px 14px;border-bottom:1px solid #d2dacc}.table-wrap{overflow:auto}figure{margin:35px 0}figure img{width:100%;border-radius:7px}figcaption{text-align:center;font-size:14px;color:var(--muted);margin-top:10px}li{margin-bottom:9px}footer{font-size:14px;padding-top:30px;color:var(--muted)}
@media(max-width:980px){aside{position:static;width:auto;padding:25px}aside a{display:inline-block;margin-right:18px}main{margin:0;padding:0 25px 50px}.cover{padding:50px 0}.cover h1{font-size:40px}}
@page{size:A4;margin:20mm 18mm}@media print{aside{display:none}main{margin:0;padding:0;max-width:none}body{font-size:10.5pt;line-height:1.85}.cover{height:230mm;padding-top:55mm;break-after:page;border:0}.cover h1{font-size:37pt}article{break-before:page;border:0;padding:0}h1{font-size:22pt}h2{font-size:15pt;break-after:avoid}pre,figure,tr{break-inside:avoid}code{font-size:8.5pt}pre code{font-size:8pt}table{font-size:9pt}a{text-decoration:none;color:inherit}footer{display:none}}
"""


def main() -> int:
    chapters = sorted(p for p in CHAPTERS.glob("[0-9][0-9]-*.md"))
    if not chapters:
        raise ValueError("편찬할 원고가 없습니다.")
    titles = [p.read_text(encoding="utf-8").splitlines()[0].removeprefix("# ") for p in chapters]
    toc = "".join(f'<a href="#{anchor(p)}">{html.escape(t)}</a>' for p, t in zip(chapters, titles))
    articles = "".join(f'<article id="{anchor(p)}">{render_markdown(p.read_text(encoding="utf-8"), p)}</article>' for p in chapters)
    book = f'''<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>200명의 의지를 설계하다</title><style>{CSS}</style></head><body>
<aside><a class="brand" href="#cover">200명의 의지를<br>설계하다</a>{toc}</aside><main><section class="cover" id="cover"><div class="eyebrow">CHAOS KINGDOM · DEVELOPMENT BOOK</div><h1>200명의 의지를<br>설계하다</h1><div class="sub">PyGame으로 만드는 장수제 전략 게임과 자율 역사 엔진</div><p class="meta">설계 · 구현 · 실험 · 검증<br>기준 구현 0.3.0-beta.1 · 2026년 10월 1일 · 개발·AI 제작 원고</p></section>{articles}<footer>원고: docs/book/ · 편찬: tools/build_book.py · 실제 검증: docs/evidence/verification.md</footer></main></body></html>'''
    output = ROOT / "docs" / "book.html"
    output.write_text(book, encoding="utf-8")
    print(f"편찬 완료: {len(chapters)}개 장 · {output} · {output.stat().st_size:,} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
