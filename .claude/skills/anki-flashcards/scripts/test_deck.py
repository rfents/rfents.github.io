#!/usr/bin/env python3
"""Smoke-test an .apkg built by build_deck.py in headless Chromium.

Usage: test_deck.py deck.apkg WORKDIR [--shots]

For a few notes it renders the front, taps options, loads the back as a new page
(as AnkiDroid does) and checks the Correct/Incorrect grading. With --shots it also
saves front.png / back.png in WORKDIR so the layout can be checked by eye.
"""
import json, re, sqlite3, sys, zipfile, os
from playwright.sync_api import sync_playwright

apkg, work = sys.argv[1], sys.argv[2]
shots = "--shots" in sys.argv
x = os.path.join(work, "apkg_check")
zipfile.ZipFile(apkg).extractall(x)
media = json.load(open(os.path.join(x, "media")))
for k, name in media.items():  # restore media file names so <img src> resolves
    os.replace(os.path.join(x, k), os.path.join(x, name))
db = sqlite3.connect(os.path.join(x, "collection.anki2"))
m = list(json.loads(db.execute("select models from col").fetchone()[0]).values())[0]
names = [f["name"] for f in m["flds"]]
t = m["tmpls"][0]

def render(tpl, f):
    tpl = re.sub(r"\{\{#(\w+)\}\}(.*?)\{\{/\1\}\}", lambda g: g.group(2) if f[g.group(1)] else "", tpl, flags=re.S)
    return re.sub(r"\{\{(\w+)\}\}", lambda g: f[g.group(1)], tpl)

def page(body):
    return ('<html><head><meta name="viewport" content="width=device-width"><style>' + m["css"]
            + '</style></head><body class="card">' + body + "</body></html>")

notes = [dict(zip(names, r[0].split("\x1f"))) for r in db.execute("select flds from notes")]
single = next(n for n in notes if n["Count"] == "1")
multi = next((n for n in notes if n["Count"] != "1"), None)
cases = []
for n in [single, multi]:
    if not n:
        continue
    right = n["Correct"].split(",")
    wrong = [str(i) for i in range(1, n["Options"].count('class="opt"') + 1) if str(i) not in right]
    cases += [(n, right, "✅ Correct!"), (n, wrong[:len(right)], "❌ Incorrect"), (n, [], "No answer selected")]

ok = True
with sync_playwright() as p:
    b = p.chromium.launch(executable_path="/opt/pw-browsers/chromium-1194/chrome-linux/chrome")
    pg = b.new_page(viewport={"width": 400, "height": 900})
    for i, (n, clicks, expect) in enumerate(cases):
        open(os.path.join(x, "front.html"), "w").write(page(render(t["qfmt"], n)))
        pg.goto("file://" + os.path.join(x, "front.html"))
        for c in clicks:
            pg.click(f'.opt[data-i="{c}"]')
        if shots and i == 0:
            pg.screenshot(path=os.path.join(work, "front.png"), full_page=True)
        open(os.path.join(x, "back.html"), "w").write(page(render(t["afmt"], n)))
        pg.goto("file://" + os.path.join(x, "back.html"))
        got = pg.inner_text("#result")
        if shots and i == 1:
            pg.screenshot(path=os.path.join(work, "back.png"), full_page=True)
        status = "OK " if got == expect else "FAIL"
        ok &= got == expect
        print(f"{status} Q{n['Num']} picks={clicks} -> {got!r}")
    b.close()
print(f"{len(notes)} notes, {len(media)} media files")
sys.exit(0 if ok else 1)
