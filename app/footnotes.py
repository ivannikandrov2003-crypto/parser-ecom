"""Примечания со звёздочками из оригинальных публикаций."""

import re
from collections import defaultdict
from typing_extensions import TypedDict

from bs4 import BeautifulSoup, Tag

WORD = r"[^\W\d_][\w]*(?:[.-][^\W_]+)*"
MARKER = r"\*{1,5}"
REFERENCE = re.compile(rf"(?<![\w*])(?P<term>{WORD})[^\S\n]*(?P<marker>{MARKER})(?![\w*])")
WORD_OR_REFERENCE = re.compile(
    rf"(?<![\w*])(?P<term>{WORD})(?!\w)(?P<reference>[^\S\n]*(?P<marker>{MARKER})(?![\w*]))?"
)
DEFINITION = re.compile(rf"^\s*(?:\((?P<paren>{MARKER})\)|(?P<plain>{MARKER})(?!\*))\s*[-—–:]?\s*(?P<text>.+)$")
BLOCKS = ["p", "li", "div", "aside", "small", "blockquote", "section", "footer"]


class SourceFootnote(TypedDict):
    marker: str
    text: str
    terms: list[str]


class Footnote(TypedDict):
    marker: str
    text: str


def _definition(line: str) -> tuple[str, str] | None:
    match = DEFINITION.match(line)
    if match is None:
        return None
    marker, text = match["paren"] or match["plain"], match["text"].strip()
    if not text or text.endswith(marker) or not any(letter.isalpha() for letter in text):
        return None
    return marker, text


def _plain_parts(text: str) -> tuple[str, dict[str, set[str]]]:
    definitions = defaultdict(set)
    body = []
    current_marker = None
    paragraphs = []
    for line in [*text.splitlines(), ""]:
        note = _definition(line)
        if current_marker and (note or not line.strip()):
            definitions[current_marker].add(" ".join(paragraphs))
            current_marker = None
        if note:
            current_marker, first_line = note
            paragraphs = [first_line]
        elif current_marker:
            paragraphs.append(line.strip())
        else:
            body.append(line)
    return "\n".join(body), definitions


def _html_parts(html: bytes) -> tuple[str, dict[str, set[str]]]:
    soup = BeautifulSoup(html, "html.parser")
    article = soup.find(itemprop="articleBody") or soup.find("article") or soup.find("main") or soup.body or soup
    for br in article.find_all("br"):
        br.replace_with("\n")

    definitions = defaultdict(set)
    article_lines = []
    for block in article.find_all(BLOCKS):
        if block.find(BLOCKS):
            continue
        for line in block.get_text(" ").splitlines():
            line = " ".join(line.split())
            note = _definition(line)
            if note:
                marker, text = note
                definitions[marker].add(text)
            else:
                article_lines.append(line)

    for sibling in article.next_siblings:
        if not isinstance(sibling, Tag):
            continue
        adjacent_notes = [
            note for line in sibling.get_text(" ").splitlines()
            if (note := _definition(" ".join(line.split())))
        ]
        if not adjacent_notes:
            break
        for marker, text in adjacent_notes:
            definitions[marker].add(text)

    for ref in article.find_all("a", href=True):
        marker = ref.get_text(strip=True)
        href = ref["href"]
        if not re.fullmatch(MARKER, marker) or not href.startswith("#"):
            continue
        target = soup.find(id=href[1:])
        if isinstance(target, Tag) and target is not ref:
            target_text = " ".join(target.stripped_strings)
            note = _definition(target_text)
            if note and note[0] == marker:
                target_text = note[1]
            if target_text and any(letter.isalpha() for letter in target_text):
                definitions[marker].add(target_text)

    return "\n".join(article_lines), definitions


def extract_footnotes(text: str, title: str = "", html: bytes = b"") -> list[SourceFootnote]:
    has_marked_text = "*" in text or "*" in title
    has_marked_html = bool(re.search(rb"\*|&#0*42;|&#x0*2a;|&ast;", html, re.IGNORECASE))
    if not (has_marked_text or has_marked_html):
        return []

    body, plain_definitions = _plain_parts(text)
    if has_marked_html:
        html_body, html_definitions = _html_parts(html)
    else:
        html_body, html_definitions = "", {}

    terms = defaultdict(dict)
    for ref in REFERENCE.finditer("\n".join((title, body, html_body))):
        terms[ref["marker"]].setdefault(ref["term"].casefold(), ref["term"])

    notes = []
    for marker, words in terms.items():
        definitions = html_definitions.get(marker) or plain_definitions.get(marker, ())
        if len(definitions) == 1:
            notes.append({"marker": marker, "text": next(iter(definitions)), "terms": list(words.values())})
    return notes


def attach_footnotes(summary: str, source_notes: list[SourceFootnote]) -> tuple[str, list[Footnote]]:
    if not source_notes:
        return summary, []

    by_marker = {note["marker"]: note["text"] for note in source_notes}
    by_term = defaultdict(set)
    for note in source_notes:
        for term in note["terms"]:
            by_term[term.casefold()].add(note["marker"])

    used = {}

    def mark(match: re.Match) -> str:
        term = match["term"]
        markers = by_term.get(term.casefold(), ())
        marker = match["marker"] or (next(iter(markers)) if len(markers) == 1 else None)
        if marker in by_marker:
            used[marker] = by_marker[marker]
            return term + marker
        return match[0]

    summary = WORD_OR_REFERENCE.sub(mark, summary)
    return summary, [{"marker": marker, "text": text} for marker, text in used.items()]
