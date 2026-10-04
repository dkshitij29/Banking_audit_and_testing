"""Turning facts into a page: surface style, formatting, HTML helpers, and PDF.

Every fact printed in a document is formatted here, by code, from the case. The
LLM never writes a date, an amount or a name (render/documents.py explains how
its prose is kept free of them), so a document cannot contradict the case by
formatting alone.

Surface form varies so an agent cannot overfit to one layout (CLAUDE.md):

- Hospital documents take a style drawn from the case: a hospital in Pune and
  one in Kochi write dates, money and letterheads differently, and a case's own
  hospital documents agree with each other.
- Insurer documents take a style drawn from the product: one insurer's forms
  look the same across its cases, as real ones do. Variation across insurers
  comes from having several products.

A style is drawn from a seed, so it is the same on every regeneration.
"""

from __future__ import annotations

import datetime as dt
import html
import os
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from sampler.rng import Rng

MONTHS_SHORT = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
MONTHS_LONG = ("January", "February", "March", "April", "May", "June", "July",
               "August", "September", "October", "November", "December")


class Issuer(StrEnum):
    HOSPITAL = "HOSPITAL"
    INSURER = "INSURER"


@dataclass(frozen=True)
class Style:
    """How one issuer prints things. Drawn from a seed; never affects any fact."""

    date: str
    """slashes 04/08/2025, dashes 04-Aug-2025, long 4 August 2025, dots 04.08.2025"""
    clock_24h: bool
    money: str
    """symbol ₹1,05,000, rs Rs. 1,05,000, inr INR 1,05,000, suffix 1,05,000/-"""
    grouping: str
    """indian 1,05,000 or western 105,000"""
    paise: bool
    """Whether whole amounts are printed with .00"""
    serif: bool
    accent: str
    letterhead: str
    """left, centred or banded"""
    headings: str
    """upper SECTION or title Section"""


FONTS = {
    True: '"Liberation Serif", "DejaVu Serif", "FreeSerif", serif',
    False: '"Liberation Sans", "DejaVu Sans", "FreeSans", sans-serif',
}
ACCENTS = ("#1f3864", "#7b2d26", "#14532d", "#4a148c", "#0b4f6c", "#8a5a00", "#333333")


def style_for(*seed_parts: object, issuer: Issuer) -> Style:
    """The style an issuer uses. Same parts, same style, always."""
    rng = Rng(0, "style", issuer.value, *(str(part) for part in seed_parts))
    return Style(
        date=rng.choice(("slashes", "dashes", "long", "dots")),
        clock_24h=rng.chance(60),
        money=rng.choice(("symbol", "rs", "inr", "suffix")),
        grouping="western" if rng.chance(20) else "indian",
        paise=rng.chance(35),
        serif=rng.chance(55),
        accent=rng.choice(ACCENTS),
        letterhead=rng.choice(("left", "centred", "banded")),
        headings="upper" if rng.chance(55) else "title",
    )


# ---------------------------------------------------------------- formatting facts


def format_date(date: dt.date, style: Style) -> str:
    if style.date == "slashes":
        return f"{date.day:02d}/{date.month:02d}/{date.year}"
    if style.date == "dashes":
        return f"{date.day:02d}-{MONTHS_SHORT[date.month - 1]}-{date.year}"
    if style.date == "dots":
        return f"{date.day:02d}.{date.month:02d}.{date.year}"
    return f"{date.day} {MONTHS_LONG[date.month - 1]} {date.year}"


def format_time(moment: dt.datetime, style: Style) -> str:
    if style.clock_24h:
        return f"{moment.hour:02d}:{moment.minute:02d} hrs"
    hour = moment.hour % 12 or 12
    return f"{hour}:{moment.minute:02d} {'AM' if moment.hour < 12 else 'PM'}"


def format_datetime(moment: dt.datetime, style: Style) -> str:
    return f"{format_date(moment.date(), style)} {format_time(moment, style)}"


def group_digits(whole: int, grouping: str) -> str:
    """1,05,000 the Indian way; 105,000 the western way."""
    digits = str(whole)
    if grouping == "western" or len(digits) <= 3:
        return f"{whole:,}"
    head, groups = digits[:-3], [digits[-3:]]
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    return ",".join(groups)


def format_money(rupees: int, style: Style) -> str:
    """The same amount, printed as this issuer prints it."""
    amount = group_digits(rupees, style.grouping) + (".00" if style.paise else "")
    return {
        "symbol": f"₹{amount}",
        "rs": f"Rs. {amount}",
        "inr": f"INR {amount}",
        "suffix": f"{amount}/-",
    }[style.money]


def format_stay(admitted: dt.datetime, discharged: dt.datetime) -> str:
    """'3 days' / '7 hours 15 minutes', as a hospital would write the length of stay."""
    stay = discharged - admitted
    hours, minutes = divmod(stay // dt.timedelta(minutes=1), 60)
    if hours >= 24:
        days, rest = divmod(hours, 24)
        tail = f" {rest} hour{'s' if rest != 1 else ''}" if rest else ""
        return f"{days} day{'s' if days != 1 else ''}{tail}"
    parts = [f"{hours} hour{'s' if hours != 1 else ''}"]
    if minutes:
        parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
    return " ".join(parts)


def heading(text: str, style: Style) -> str:
    return text.upper() if style.headings == "upper" else text


# ---------------------------------------------------------------- HTML helpers


def esc(value: object) -> str:
    """Everything placed in a document goes through here."""
    return html.escape(str(value), quote=True)


def tag(name: str, content: str, **attrs: str) -> str:
    rendered = "".join(f' {key.rstrip("_").replace("_", "-")}="{esc(value)}"' for key, value in attrs.items())
    return f"<{name}{rendered}>{content}</{name}>"


def fields(pairs: list[tuple[str, str]], *, columns: int = 1) -> str:
    """A label/value block, in one or two columns. Values are already escaped.

    A two-column block is padded to a whole number of rows, so the grid stays
    square whatever facts a case happens to have.
    """
    pairs = list(pairs)
    if columns == 2 and len(pairs) % 2:
        pairs.append(("", ""))
    cells = [(tag("th", esc(label)) + tag("td", value)) for label, value in pairs]
    lines = [cells[i:i + columns] for i in range(0, len(cells), columns)]
    body = "".join(tag("tr", "".join(row)) for row in lines)
    return tag("table", body, class_=f"fields {'two' if columns == 2 else 'one'}")


def table(head: list[str], body: list[list[str]], style: Style, *, right: tuple[int, ...] = ()) -> str:
    """A bordered table; `right` names the columns to right-align."""

    def cell(name: str, index: int, value: str) -> str:
        return tag(name, value, class_="num") if index in right else tag(name, value)

    header = tag("tr", "".join(cell("th", n, esc(text)) for n, text in enumerate(head)))
    lines = "".join(tag("tr", "".join(cell("td", n, value) for n, value in enumerate(row))) for row in body)
    return tag("table", tag("thead", header) + tag("tbody", lines), class_="grid")


def section(title: str, content: str, style: Style) -> str:
    return tag("h2", esc(heading(title, style))) + content


def paragraphs(text: str) -> str:
    """LLM prose, already checked and substituted, as escaped paragraphs."""
    return "".join(tag("p", esc(block.strip())) for block in text.split("\n") if block.strip())


# ---------------------------------------------------------------- the page


def css(style: Style) -> str:
    banded = style.letterhead == "banded"
    return f"""
@page {{
  size: A4;
  margin: 16mm 15mm 15mm 15mm;
  @bottom-right {{ content: "Page " counter(page) " of " counter(pages); font-size: 7.5pt; color: #777; }}
}}
body {{ font-family: {FONTS[style.serif]}; font-size: 9.8pt; line-height: 1.42; color: #111; }}
h1 {{ font-size: 15pt; margin: 0; color: {"#fff" if banded else style.accent}; letter-spacing: .3px; }}
h2 {{ font-size: 10pt; margin: 11pt 0 4pt; color: {style.accent};
      border-bottom: 1px solid {style.accent}; padding-bottom: 2px; page-break-after: avoid; }}
table.grid tr {{ page-break-inside: avoid; }}
p {{ margin: 0 0 5pt; text-align: justify; }}
.letterhead {{ margin-bottom: 8pt; {"background: " + style.accent + "; padding: 7pt 9pt;" if banded else ""}
               {"text-align: center;" if style.letterhead == "centred" else ""} }}
.letterhead .addr {{ font-size: 8.2pt; color: {"#eee" if banded else "#555"}; margin-top: 2pt; }}
.rule {{ border-top: 2px solid {style.accent}; margin: 6pt 0 9pt; }}
.title {{ text-align: center; font-weight: bold; font-size: 11pt; margin: 4pt 0 8pt;
          text-transform: {"uppercase" if style.headings == "upper" else "none"}; }}
table {{ border-collapse: collapse; width: 100%; font-size: 9.4pt; }}
table.fields th {{ text-align: left; font-weight: normal; color: #555;
                   padding: 2.4pt 6pt 2.4pt 0; vertical-align: top; }}
table.fields td {{ padding: 2.4pt 12pt 2.4pt 0; vertical-align: top; }}
table.fields.one th {{ width: 24%; }}
table.fields.two th {{ width: 15%; }}
table.fields.two td {{ width: 35%; }}
table.grid {{ margin: 3pt 0 6pt; }}
table.grid th {{ background: #f0f0f0; border: 1px solid #bbb; padding: 3.4pt 5pt; text-align: left; }}
table.grid td {{ border: 1px solid #bbb; padding: 3.4pt 5pt; }}
.num {{ text-align: right; white-space: nowrap; }}
table.totals {{ margin-top: 5pt; page-break-inside: avoid; }}
table.totals th {{ width: 62%; text-align: right; padding-right: 10pt; color: #222; }}
table.totals tr:last-child th, table.totals tr:last-child td {{ font-weight: bold;
    border-top: 1px solid #999; padding-top: 4pt; }}
.foot {{ margin-top: 14pt; font-size: 8.6pt; color: #444; }}
.sign {{ margin-top: 22pt; }}
""".strip()


def letterhead(name: str, address: str, style: Style, *, tagline: str = "") -> str:
    lines = tag("h1", esc(name)) + tag("div", esc(address), class_="addr")
    if tagline:
        lines += tag("div", esc(tagline), class_="addr")
    head = tag("div", lines, class_="letterhead")
    return head if style.letterhead == "banded" else head + '<div class="rule"></div>'


def page(title: str, body: str, style: Style) -> str:
    """A whole document as HTML. `title` is the PDF's metadata title, not printed."""
    return (
        "<!DOCTYPE html><html><head><meta charset=\"utf-8\">"
        f"{tag('title', esc(title))}{tag('style', css(style))}</head>"
        f"{tag('body', body)}</html>"
    )


def to_pdf(document: str, path: Path, *, created: dt.date) -> Path:
    """Write HTML to a text PDF, stamped as made on `created`.

    A PDF carries a creation time, so without this the same document would give
    different bytes on every run. `created` is the day the issuer would have
    printed it, which keeps the metadata honest as well as stable. WeasyPrint
    takes it from SOURCE_DATE_EPOCH, the usual convention for reproducible builds.
    """
    from weasyprint import HTML

    path.parent.mkdir(parents=True, exist_ok=True)
    stamp = int(dt.datetime.combine(created, dt.time(9, 0), tzinfo=dt.UTC).timestamp())
    was = os.environ.get("SOURCE_DATE_EPOCH")
    os.environ["SOURCE_DATE_EPOCH"] = str(stamp)
    try:
        HTML(string=document).write_pdf(path, uncompressed_pdf=False)
    finally:
        if was is None:
            os.environ.pop("SOURCE_DATE_EPOCH", None)
        else:
            os.environ["SOURCE_DATE_EPOCH"] = was
    return path
