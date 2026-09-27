#!/usr/bin/env python3
"""Generate an interactive MCQ / True-False Anki deck (.apkg) for Fortinet NSE 4
(FortiGate Administrator, FortiOS 7.x). Questions live in nse4_questions.py.

On the front, tap the option(s) you think are right, then show the answer:
the back highlights the correct options, marks your wrong picks and shows an explanation.

Usage: pip install genanki && python3 generate_nse4.py
"""
import html
import random

import genanki

from nse4_questions import MODULES

DECK_ID = 1727460101
MODEL_ID = 1727460102
SEP = "|||"

CSS = """
.card { font-family: Arial, sans-serif; font-size: 18px; text-align: left;
        color: #1d1d1f; background: #fff; padding: 6px; }
.module { font-size: 12px; color: #fff; background: #da291c; display: inline-block;
          padding: 2px 8px; border-radius: 10px; margin-bottom: 10px; }
.type { background: #555; }
.q { font-weight: bold; margin-bottom: 10px; }
.opt { display: flex; align-items: flex-start; gap: 10px; margin: 8px 0; padding: 10px 12px;
       border: 2px solid #ccc; border-radius: 10px; cursor: pointer; user-select: none; }
.opt .letter { font-weight: bold; min-width: 18px; }
.opt.picked { border-color: #1a73e8; background: #e8f0fe; }
.opt.right { border-color: #1e8e3e; background: #e6f4ea; }
.opt.wrong { border-color: #d93025; background: #fce8e6; }
.opt.right.picked::after { content: "✔"; margin-left: auto; color: #1e8e3e; font-weight: bold; }
.opt.wrong::after { content: "✘"; margin-left: auto; color: #d93025; font-weight: bold; }
.verdict { font-size: 20px; font-weight: bold; margin: 6px 0; }
.verdict.ok { color: #1e8e3e; } .verdict.ko { color: #d93025; } .verdict.none { color: #777; font-size: 15px; }
.expl { line-height: 1.45; }
code { background: #f2f2f2; padding: 1px 4px; border-radius: 3px; font-size: 15px; }
.nightMode .card, .night_mode .card { color: #eee; background: #1e1e1e; }
.nightMode .opt, .night_mode .opt { border-color: #555; }
.nightMode .opt.picked, .night_mode .opt.picked { background: #1c2b45; border-color: #8ab4f8; }
.nightMode .opt.right, .night_mode .opt.right { background: #173a24; border-color: #81c995; }
.nightMode .opt.wrong, .night_mode .opt.wrong { background: #4a1f1c; border-color: #f28b82; }
.nightMode code, .night_mode code { background: #333; }
"""

# Selection is kept in sessionStorage (AnkiDroid reloads the page between sides)
# with a window variable as fallback (Anki desktop keeps the same page).
JS = r"""
function nse4Render(back) {
  var box = document.getElementById('opts');
  var opts = document.getElementById('src').innerHTML.split('""" + SEP + r"""');
  var right = document.getElementById('key').textContent.trim().split(/\s+/).map(Number);
  var qid = document.querySelector('.q').textContent;
  var multi = right.length > 1;
  function load() {
    var s = null;
    try { s = JSON.parse(sessionStorage.getItem('nse4sel') || 'null'); } catch (e) {}
    if (!s) s = window.__nse4sel;
    return (s && s.q === qid) ? s.sel : [];
  }
  function save(sel) {
    var s = {q: qid, sel: sel};
    window.__nse4sel = s;
    try { sessionStorage.setItem('nse4sel', JSON.stringify(s)); } catch (e) {}
  }
  var sel = back ? load() : [];
  if (!back) save([]);
  box.innerHTML = '';
  opts.forEach(function (t, i) {
    var d = document.createElement('div');
    d.className = 'opt';
    d.innerHTML = '<span class="letter">' + String.fromCharCode(65 + i) + '</span><span>' + t + '</span>';
    if (back) {
      var isRight = right.indexOf(i) >= 0, isPicked = sel.indexOf(i) >= 0;
      if (isRight) d.classList.add('right');
      if (isPicked) d.classList.add(isRight ? 'picked' : 'wrong');
    } else {
      d.addEventListener('click', function (ev) {
        ev.stopPropagation();
        var k = sel.indexOf(i);
        if (multi) { if (k >= 0) sel.splice(k, 1); else sel.push(i); }
        else sel = [i];
        for (var j = 0; j < box.children.length; j++)
          box.children[j].classList.toggle('picked', sel.indexOf(j) >= 0);
        save(sel.slice());
      });
    }
    box.appendChild(d);
  });
  if (back) {
    var v = document.getElementById('verdict');
    if (!sel.length) { v.textContent = 'No answer selected'; v.className = 'verdict none'; return; }
    var ok = sel.length === right.length && sel.every(function (x) { return right.indexOf(x) >= 0; });
    v.textContent = ok ? '✔ Correct' : '✘ Incorrect';
    v.className = 'verdict ' + (ok ? 'ok' : 'ko');
  }
}
"""

COMMON = """<div class="module">{{Module}}</div> <div class="module type">{{Type}}</div>
<div class="q">{{Question}}</div>
<div id="opts"></div>
<div id="src" style="display:none">{{Options}}</div>
<div id="key" style="display:none">{{Answer}}</div>
"""

MODEL = genanki.Model(
    MODEL_ID,
    "NSE4 MCQ / True-False",
    fields=[{"name": f} for f in ("Question", "Options", "Answer", "Explanation", "Type", "Module")],
    templates=[{
        "name": "Practice",
        "qfmt": COMMON + "<script>" + JS + "nse4Render(false);</script>",
        "afmt": COMMON + '<div id="verdict" class="verdict"></div><hr id="answer">'
                '<div class="expl">{{Explanation}}</div>'
                "<script>" + JS + "nse4Render(true);</script>",
    }],
    css=CSS,
)


def fmt(text):
    """Escape HTML, then turn `x` into <code>x</code>."""
    parts = html.escape(text).split("`")
    return "".join(f"<code>{p}</code>" if i % 2 else p for i, p in enumerate(parts))


def build_note(module, entry):
    q, choices, expl = entry
    if isinstance(choices, bool):  # True/False statement
        options, right, kind = ["True", "False"], [0 if choices else 1], "True / False"
        question = q
    else:
        items = [(c.lstrip("*"), c.startswith("*")) for c in choices]
        random.Random(q).shuffle(items)  # deterministic shuffle so the answer isn't always A
        options = [t for t, _ in items]
        right = [i for i, (_, ok) in enumerate(items) if ok]
        kind = "MCQ"
        question = q
    return genanki.Note(
        model=MODEL,
        fields=[fmt(question), SEP.join(fmt(o) for o in options), " ".join(map(str, right)),
                fmt(expl), kind, html.escape(module)],
        tags=["NSE4", "".join(c for c in module.title() if c.isalnum()),
              "TrueFalse" if kind != "MCQ" else "MCQ"],
        guid=genanki.guid_for("nse4-practice", q),
    )


def main():
    decks, counts = [], {"MCQ": 0, "True / False": 0}
    for n, (module, entries) in enumerate(MODULES, 1):
        deck = genanki.Deck(DECK_ID + n, f"NSE 4 Practice::{n:02d} {module}")
        for e in entries:
            note = build_note(module, e)
            counts[note.fields[4]] += 1
            deck.add_note(note)
        decks.append(deck)
    out = "NSE4_Practice_MCQ_TrueFalse.apkg"
    genanki.Package(decks).write_to_file(out)
    print(f"{out}: {sum(counts.values())} cards ({counts['MCQ']} MCQ, "
          f"{counts['True / False']} True/False) in {len(decks)} modules")


if __name__ == "__main__":
    main()
