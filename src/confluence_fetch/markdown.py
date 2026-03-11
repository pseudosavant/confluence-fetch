from __future__ import annotations

from pathlib import Path
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from markdownify import markdownify as html_to_markdown


def normalize_html_links(html: str, base_url: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag_name, attr_name in (("a", "href"), ("img", "src")):
        for tag in soup.find_all(tag_name):
            value = tag.get(attr_name)
            if not value:
                continue
            parsed = urlparse(value)
            if parsed.scheme or value.startswith("#"):
                continue
            tag[attr_name] = urljoin(base_url, value)
    return str(soup)


def collect_image_sources(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    return [src for img in soup.find_all("img") if (src := img.get("src"))]


def rewrite_image_sources(html: str, replacements: dict[str, str]) -> str:
    if not replacements:
        return html
    soup = BeautifulSoup(html, "html.parser")
    for img in soup.find_all("img"):
        src = img.get("src")
        if src and src in replacements:
            img["src"] = replacements[src]
    return str(soup)


def markdown_from_html(html: str) -> str:
    markdown = html_to_markdown(
        html,
        heading_style="ATX",
        bullets="-",
        strip=["span"],
    )
    return tidy_markdown(markdown)


def tidy_markdown(markdown: str) -> str:
    lines = markdown.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    output: list[str] = []
    blank_run = 0
    in_fence = False

    for raw_line in lines:
        line = raw_line
        if line.lstrip().startswith("```"):
            in_fence = not in_fence

        if not in_fence:
            line = line.rstrip()
            if not line:
                blank_run += 1
                if blank_run > 2:
                    continue
            else:
                blank_run = 0
        output.append(line)

    while output and not output[0]:
        output.pop(0)
    while output and not output[-1]:
        output.pop()

    return "\n".join(output)


def relative_markdown_path(path: Path, base_dir: Path) -> str:
    try:
        return path.relative_to(base_dir).as_posix()
    except ValueError:
        return path.as_posix()
