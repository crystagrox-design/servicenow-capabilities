#!/usr/bin/env python3
"""Fetch public ServiceNow release and model documentation into a small feed."""
from __future__ import annotations
import json, re, sys
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.request import Request, urlopen

SOURCES = [
    ("Release notes", "https://www.servicenow.com/docs/r/release-notes/new-features-changes.html"),
    ("Now LLM model updates", "https://www.servicenow.com/docs/r/intelligent-experiences/servicenow-large-language-model-now-llm/now-llm-model-updates.html"),
    ("Build Agent release notes", "https://www.servicenow.com/docs/r/store-release-notes/store-platcap-rn-build-agent-trial.html"),
]

class PageText(HTMLParser):
    def __init__(self):
        super().__init__(); self.parts=[]; self.title=[]; self.in_title=False; self.skip=0; self.block=None
    def handle_starttag(self, tag, attrs):
        if tag in ("script","style","noscript","svg"): self.skip+=1
        if tag=="title": self.in_title=True
        if tag in ("p","li","h1","h2","h3","h4"):
            self.flush(); self.block=[]
    def handle_endtag(self, tag):
        if tag in ("script","style","noscript","svg") and self.skip: self.skip-=1
        if tag=="title": self.in_title=False
        if tag in ("p","li","h1","h2","h3","h4"):self.flush()
    def handle_data(self, data):
        value=re.sub(r"\s+"," ",data).strip()
        if value and not self.skip:
            if self.block is not None:self.block.append(value)
            else:self.parts.append(value)
            if self.in_title:self.title.append(value)
    def flush(self):
        if self.block is not None:
            value=re.sub(r"\s+"," "," ".join(self.block)).strip()
            if value:self.parts.append(value)
            self.block=None

def summarize(items, limit=600):
    # Prefer the newest dated section; docs pages often repeat that section in navigation.
    months = {name: i for i, name in enumerate(("January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"), 1)}
    dated=[]
    for i, item in enumerate(items):
        match=re.search(r"\b("+"|".join(months)+r")\s+(20\d{2})\b", item)
        if match:dated.append((int(match.group(2)),months[match.group(1)],i))
    if dated:
        newest=max(dated)
        start=newest[2]
        # Gather nearby explanatory blocks, stopping before another dated section.
        source=[]
        for item in items[start:start+12]:
            if source and re.search(r"\b("+"|".join(months)+r")\s+20\d{2}\b",item):break
            source.append(item)
        result=" ".join(re.sub(r"\s+"," ",x).strip() for x in source if len(x.strip())>25)
        if result:return result[:limit].strip()
    # Otherwise keep the first meaningful paragraphs, avoiding cookie and navigation chrome.
    chosen=[]; seen=set()
    for item in items:
        t=re.sub(r"\s+"," ",item).strip()
        low=t.lower()
        if len(t)<45 or low in seen or any(x in low for x in ("cookie preferences","privacy statement","legal notice","skip to content","table of contents")): continue
        seen.add(low); chosen.append(t)
        if sum(len(x) for x in chosen)>limit:break
    return " ".join(chosen)[:limit].strip()

def fetch(source, url):
    req=Request(url,headers={"User-Agent":"ServiceNowCapabilityAtlas/1.0 (documentation refresh; contact site owner)"})
    with urlopen(req,timeout=35) as response:
        html=response.read().decode("utf-8","replace")
    modified=response.headers.get("Last-Modified","")
    parser=PageText(); parser.feed(html)
    # Prefer first page heading over a templated title, otherwise use source label.
    title=" ".join(parser.title).strip() or next((x for x in parser.parts if x and x.lower() not in {"servicenow documentation"}),source)
    text=summarize(parser.parts)
    page_date=next((re.sub(r"^Updated\s*", "", x, flags=re.I) for x in parser.parts if re.match(r"^Updated\s+",x,re.I)),"")
    return {"source":source,"title":title[:180],"summary":text or "Open the official documentation for the latest release-specific changes.","url":url,"updated":page_date or modified or "Page checked on refresh","fetchedAt":datetime.now(timezone.utc).isoformat()}

def main():
    path=Path(__file__).resolve().parents[1]/"data"/"official-updates.json"
    path.parent.mkdir(parents=True,exist_ok=True)
    previous={}
    if path.exists():
        try: previous=json.loads(path.read_text(encoding="utf-8"))
        except Exception: previous={}
    items=[]; errors=[]
    for source,url in SOURCES:
        try: items.append(fetch(source,url))
        except Exception as e:
            errors.append(f"{source}: {e}")
            old=next((x for x in previous.get("items",[]) if x.get("url")==url),None)
            if old:items.append(old)
    payload={"checkedAt":datetime.now(timezone.utc).isoformat(),"items":items,"errors":errors}
    path.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(f"Wrote {len(items)} official update records; failures: {len(errors)}")
    if not items:return 1
    return 0
if __name__=="__main__":raise SystemExit(main())
