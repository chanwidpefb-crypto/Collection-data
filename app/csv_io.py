"""Small CSV helpers shared by the register/node import-export endpoints.

Import is an upsert: rows matching an existing register/node (by whatever
natural key that type uses -- tag_name, or area+address, etc.) update it in
place; unmatched rows create a new one. This also serves as a lightweight
"template" mechanism -- export one connector's registers, edit the file in a
spreadsheet, then import it into another connector.
"""
from __future__ import annotations

import csv
import io


def write_csv(fieldnames: list[str], rows: list[dict]) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return buf.getvalue()


def read_csv(content: str) -> list[dict]:
    # utf-8-sig transparently strips the BOM Excel prepends when saving CSV.
    buf = io.StringIO(content)
    reader = csv.DictReader(buf)
    return list(reader)


def parse_bool(value, default: bool = True) -> bool:
    if value is None or str(value).strip() == "":
        return default
    return str(value).strip().lower() in ("1", "true", "yes", "y", "on")


def parse_float(value, default: float = 0.0) -> float:
    value = "" if value is None else str(value).strip()
    return float(value) if value else default
