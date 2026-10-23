#!/usr/bin/env python3
"""Build a searchable, slide-linked static atlas from a .pptx without Office."""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import zipfile
from pathlib import Path, PurePosixPath
from xml.etree import ElementTree as ET

NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
}
SLIDE_RE = re.compile(r"ppt/slides/slide(\d+)\.xml$")


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def text_from_xml(raw: bytes) -> list[str]:
    root = ET.fromstring(raw)
    return [clean("".join(t.text or "" for t in para.findall(".//a:t", NS)))
            for para in root.findall(".//a:p", NS)
            if clean("".join(t.text or "" for t in para.findall(".//a:t", NS)))]

def text_values_from_xml(raw: bytes) -> list[str]:
    root = ET.fromstring(raw)
    values = []
    for node in root.iter():
        if node.tag.rsplit("}", 1)[-1] in {"t", "v"} and node.text:
            value = clean(node.text)
            if value and value not in values:
                values.append(value)
    return values


def relmap(zf: zipfile.ZipFile, relpath: str) -> dict[str, tuple[str, str]]:
    try:
        root = ET.fromstring(zf.read(relpath))
    except KeyError:
        return {}
    base = PurePosixPath(relpath).parent.parent
    result = {}
    for rel in root.findall("rel:Relationship", NS):
        target = rel.attrib.get("Target", "")
        mode = rel.attrib.get("TargetMode", "")
        if mode != "External":
            target = str((base / target).as_posix())
            while "/../" in target:
                target = re.sub(r"[^/]+/\.\./", "", target, count=1)
        result[rel.attrib.get("Id", "")] = (target, mode)
    return result


def category_for(text: str) -> str:
    s = text.lower()
    buckets = [
        ("AI & Automation", ("now assist", "generative ai", "agentic", "ai agent", "artificial intelligence", "machine learning", "llm", "copilot")),
        ("IT Workflows", ("itsm", "it service", "it operations", "itom", "it asset", "cmdb", "change management", "incident management")),
        ("Employee Workflows", ("hr service", "employee center", "workplace service", "employee experience", "people")),
        ("Customer & Industry", ("customer service", "csm", "field service", "industry", "financial services", "telecommunications", "healthcare")),
        ("Creator & Platform", ("app engine", "creator", "automation engine", "integration hub", "flow designer", "developer")),
        ("Risk & Security", ("security operations", "secops", "grc", "risk", "vulnerability", "zero trust")),
        ("Data & Integration", ("data fabric", "data foundation", "integration", "workflow data", "common service data model", "c s d m")),
        ("Operations & Assets", ("enterprise asset", "hardware asset", "software asset", "supply chain", "workplace")),
    ]
    for name, words in buckets:
        if any(word in s for word in words):
            return name
    return "Platform & Portfolio"


PRODUCT_TERMS = ["ITSM", "ITOM", "ITAM", "CSM", "HRSD", "FSM", "SecOps", "GRC", "App Engine", "Integration Hub", "Now Assist", "AI Control Tower", "Service Graph", "CMDB", "Strategic Portfolio Management", "Field Service Management", "Enterprise Asset Management", "Workplace Service Delivery", "Customer Service Management", "Employee Center", "Automation Engine"]

def products_for(text: str) -> list[str]:
    low = text.lower()
    return [name for name in PRODUCT_TERMS if name.lower() in low]


def read_slide(zf: zipfile.ZipFile, slide_path: str, number: int, out_media: Path) -> dict:
    rel_path = str(PurePosixPath(slide_path).parent / "_rels" / (PurePosixPath(slide_path).name + ".rels"))
    rels = relmap(zf, rel_path)
    root = ET.fromstring(zf.read(slide_path))
    paragraphs = text_from_xml(zf.read(slide_path))
    media, links, supplemental = [], [], []
    for element in root.iter():
        rid = element.attrib.get("{%s}embed" % NS["r"]) or element.attrib.get("{%s}link" % NS["r"])
        if rid and rid in rels:
            target, mode = rels[rid]
            if mode == "External":
                links.append(target)
            elif target.startswith("ppt/media/") and target in zf.namelist():
                out = out_media / PurePosixPath(target).name
                if not out.exists():
                    out.parent.mkdir(parents=True, exist_ok=True)
                    out.write_bytes(zf.read(target))
                media.append({"src": "media/" + out.name, "name": out.name,
                              "type": out.suffix.lower().lstrip(".")})
    # Include chart data labels and SmartArt labels; many are separate XML parts.
    for target, mode in rels.values():
        if mode == "External" or target not in zf.namelist():
            continue
        if target.startswith("ppt/charts/"):
            supplemental.extend(text_values_from_xml(zf.read(target)))
        elif target.startswith("ppt/diagrams/"):
            supplemental.extend(text_from_xml(zf.read(target)))
        elif target.startswith("ppt/notesSlides/") and target.endswith(".xml"):
            notes = text_from_xml(zf.read(target))
            supplemental.extend(t for t in notes if t not in {str(number), "Slide image"})
    all_text = paragraphs + supplemental
    title = ""
    for shape in root.findall(".//p:sp", NS):
        placeholder = shape.find(".//p:ph", NS)
        if placeholder is not None and placeholder.attrib.get("type") in {"title", "ctrTitle"}:
            title = clean(" ".join(t.text or "" for t in shape.findall(".//a:t", NS)))
            if title: break
    if not title:
        title = next((p for p in paragraphs if len(p) > 2), f"Slide {number}")
    text = "\n".join(dict.fromkeys(all_text))
    return {"slide": number, "title": title[:180], "domain": category_for(title + " " + text), "products": products_for(title + " " + text),
            "text": text, "media": list({m["src"]: m for m in media}.values()),
            "links": list(dict.fromkeys(links))}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("deck", nargs="?", type=Path, default=Path(__file__).resolve().parents[2] / "servicenow-overview-and-interactive-capability-map.pptx")
    parser.add_argument("--out", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    deck, out = args.deck.resolve(), args.out.resolve()
    if not deck.is_file():
        print(f"Deck not found: {deck}", file=sys.stderr); return 2
    data_dir, media_dir = out / "data", out / "media"
    data_dir.mkdir(parents=True, exist_ok=True); media_dir.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(deck) as zf:
            # Preserve the complete embedded media folder, including assets placed on layouts/masters.
            for member in zf.namelist():
                if member.startswith("ppt/media/") and not member.endswith("/"):
                    target = media_dir / PurePosixPath(member).name
                    if not target.exists():
                        target.write_bytes(zf.read(member))
            slides = []
            for member in sorted((n for n in zf.namelist() if SLIDE_RE.match(n)), key=lambda n: int(SLIDE_RE.match(n).group(1))):
                n = int(SLIDE_RE.match(member).group(1))
                slides.append(read_slide(zf, member, n, media_dir))
    except (PermissionError, OSError) as exc:
        print(f"Cannot read deck (it may be locked by PowerPoint or OneDrive): {exc}", file=sys.stderr); return 3
    references = {}
    for slide in slides:
        for media in slide["media"]:
            references.setdefault(media["src"], []).append(slide["slide"])
    with zipfile.ZipFile(deck) as zf:
        all_media = [{"src": "media/" + PurePosixPath(n).name,
                      "name": PurePosixPath(n).name,
                      "type": PurePosixPath(n).suffix.lower().lstrip("."),
                      "slides": references.get("media/" + PurePosixPath(n).name, [])}
                     for n in zf.namelist() if n.startswith("ppt/media/") and not n.endswith("/")]
    all_media.sort(key=lambda item: item["name"].lower())
    (data_dir / "slides.json").write_text(json.dumps({"source": deck.name, "builtAt": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(), "slides": slides, "mediaAssets": all_media}, ensure_ascii=False), encoding="utf-8")
    print(f"Indexed {len(slides)} slides, {len(all_media)} embedded media assets, and copied the complete embedded media folder to {media_dir}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
