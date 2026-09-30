#!/usr/bin/env python3
"""Extract text lines and images from a PDF in reading order.

Usage: extract_pdf.py input.pdf WORKDIR

Writes:
  WORKDIR/img/<prefix>_imgNNN.<ext>  every embedded image
  WORKDIR/items.json                  [["t", line] | ["i", filename, width, height, page], ...]
  WORKDIR/text.txt                    plain text with ===== PAGE n ===== markers (for reading)

Question dumps often use Turkish dotless 'ı' instead of 'i'; it is normalised here.
Images can then be attached to whichever question header precedes them in items.json.
"""
import json, os, sys
import pymupdf

pdf, work = sys.argv[1], sys.argv[2]
os.makedirs(os.path.join(work, "img"), exist_ok=True)
prefix = os.path.splitext(os.path.basename(pdf))[0][:20].replace(" ", "_")
doc = pymupdf.open(pdf)
items, pages, n = [], [], 0
for pi, page in enumerate(doc):
    pages.append(f"===== PAGE {pi+1} =====")
    for b in page.get_text("dict", sort=True)["blocks"]:
        if b["type"] == 0:
            for line in b["lines"]:
                s = "".join(sp["text"] for sp in line["spans"]).replace("ı", "i").strip()
                if s:
                    items.append(["t", s])
                    pages.append(s)
        else:
            n += 1
            fn = f"{prefix}_img{n:03d}.{b['ext']}"
            with open(os.path.join(work, "img", fn), "wb") as f:
                f.write(b["image"])
            items.append(["i", fn, b["width"], b["height"], pi + 1])
            pages.append(f"[IMAGE {fn}]")
json.dump(items, open(os.path.join(work, "items.json"), "w"), ensure_ascii=False, indent=0)
open(os.path.join(work, "text.txt"), "w").write("\n".join(pages))
print(f"{doc.page_count} pages, {sum(1 for i in items if i[0]=='t')} lines, {n} images")
