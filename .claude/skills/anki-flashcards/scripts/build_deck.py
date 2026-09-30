#!/usr/bin/env python3
"""Build an interactive multiple-choice Anki deck (.apkg) for AnkiDroid.

Usage:
  build_deck.py questions.json --deck "Deck name" --label "SHORT" --img-dir img --out out/Deck.apkg

questions.json is a list of objects:
  {"num": 1, "stem": "Question text", "opts": ["opt A", "opt B", ...],
   "ans": [2] (1-based indexes of the correct options), "imgs": ["file.jpeg", ...],
   "note": "optional HTML shown on the back with a warning icon"}

Front: tap options to select (radio for one answer, capped multi-select for several).
Back: shows Correct/Incorrect and marks every option (correct, missed, wrong pick).
"""
import argparse, html, json, os, zlib
import genanki

ap = argparse.ArgumentParser()
ap.add_argument("questions")
ap.add_argument("--deck", required=True, help="Anki deck name")
ap.add_argument("--label", default="Q", help="short tag shown above each question, e.g. NSE4")
ap.add_argument("--img-dir", default="img")
ap.add_argument("--out", required=True)
ap.add_argument("--tag", action="append", default=[], help="extra tag(s) for every note")
args = ap.parse_args()

L = "ABCDEFGHIJ"
FRONT_JS = """
<script>
(function(){
  var box=document.getElementById('opts'); if(!box) return;
  var need=parseInt(box.getAttribute('data-count'))||1, key='mcqsel';
  var sel=[];
  function save(){ window[key]=sel.join(','); try{sessionStorage.setItem(key,sel.join(','));}catch(e){} }
  save();
  var hint=document.getElementById('hint');
  function upd(){ hint.textContent = need>1 ? ('Select '+need+' answers ('+sel.length+'/'+need+')') : 'Select one answer'; }
  upd();
  Array.prototype.forEach.call(box.querySelectorAll('.opt'),function(el){
    el.addEventListener('click',function(ev){
      ev.stopPropagation();
      var i=el.getAttribute('data-i'), p=sel.indexOf(i);
      if(p>=0){ sel.splice(p,1); el.classList.remove('sel'); }
      else{
        if(need===1){ sel=[]; Array.prototype.forEach.call(box.querySelectorAll('.opt'),function(o){o.classList.remove('sel');}); }
        else if(sel.length>=need){ var old=sel.shift(); box.querySelector('.opt[data-i="'+old+'"]').classList.remove('sel'); }
        sel.push(i); el.classList.add('sel');
      }
      save(); upd();
    });
  });
})();
</script>"""
BACK_JS = """
<script>
(function(){
  var box=document.getElementById('opts'); if(!box) return;
  var key='mcqsel', raw=window[key];
  if(raw===undefined){ try{raw=sessionStorage.getItem(key);}catch(e){} }
  var picked=(raw||'').split(',').filter(Boolean);
  var correct=box.getAttribute('data-correct').split(',');
  var allOk=picked.length===correct.length && correct.every(function(c){return picked.indexOf(c)>=0;});
  Array.prototype.forEach.call(box.querySelectorAll('.opt'),function(el){
    var i=el.getAttribute('data-i'), c=correct.indexOf(i)>=0, p=picked.indexOf(i)>=0;
    el.classList.add(c ? 'ok' : (p ? 'bad' : 'no'));
    if(c && picked.length && !p) el.classList.add('missed');
    var m=document.createElement('span'); m.className='mark';
    m.textContent = c ? (p||!picked.length ? ' ✔' : ' ✔ (missed)') : (p ? ' ✘ your pick' : '');
    el.appendChild(m);
  });
  var r=document.getElementById('result');
  if(!picked.length){ r.textContent='No answer selected'; r.className='result none'; }
  else if(allOk){ r.textContent='✅ Correct!'; r.className='result good'; }
  else { r.textContent='❌ Incorrect'; r.className='result wrong'; }
  window[key]=undefined; try{sessionStorage.removeItem(key);}catch(e){}
})();
</script>"""

HEAD = ('<div class="num">{{Label}} · Q{{Num}}</div><div class="q">{{Question}}</div>'
        '{{#Exhibit}}<div class="ex">{{Exhibit}}</div>{{/Exhibit}}')
# Fixed model ID: every deck built with this script shares one note type.
model = genanki.Model(1607392321, "MCQ (interactive)",
 fields=[{"name": n} for n in ("Num", "Label", "Question", "Exhibit", "Options", "Count", "Correct", "Explanation")],
 templates=[{"name": "Card 1",
  "qfmt": HEAD + '<div id="hint" class="hint"></div><div id="opts" class="opts" data-count="{{Count}}">{{Options}}</div>' + FRONT_JS,
  "afmt": HEAD + '<div id="result" class="result"></div><div id="opts" class="opts" data-correct="{{Correct}}">{{Options}}</div>'
          '{{#Explanation}}<div class="note">⚠ {{Explanation}}</div>{{/Explanation}}' + BACK_JS}],
 css='''.card{font-family:-apple-system,Roboto,"Segoe UI",sans-serif;font-size:17px;line-height:1.45;text-align:left;color:#1d1d1f;background:#fff;padding:4px}
.num{font-size:12px;color:#888;margin-bottom:6px}
.q{font-weight:600;margin-bottom:10px;white-space:pre-line}
.ex img{max-width:100%;height:auto;border:1px solid #ccc;border-radius:4px;margin:4px 0}
.hint{font-size:13px;color:#1565c0;margin:8px 0 2px}
.opt{padding:10px 11px;margin:7px 0;border:2px solid #d0d0d0;border-radius:10px;cursor:pointer;-webkit-tap-highlight-color:transparent;user-select:none}
.opt b{margin-right:6px}
.sel{border-color:#1565c0;background:#e3f2fd}
.ok{border-color:#2e7d32;background:#e8f5e9;color:#1b5e20;font-weight:600}
.missed{border-style:dashed}
.bad{border-color:#c62828;background:#ffebee;color:#b71c1c}
.no{opacity:.5}
.mark{font-weight:700}
.result{font-size:20px;font-weight:700;margin:10px 0 4px}
.good{color:#2e7d32}.wrong{color:#c62828}.none{color:#888;font-size:15px}
.note{margin-top:12px;padding:8px 10px;border-left:4px solid #f9a825;background:#fff8e1;font-size:15px}
.nightMode .card,.night_mode .card,.card.nightMode{color:#e6e6e6;background:#1e1e1e}
.nightMode .opt,.night_mode .opt{border-color:#555}
.nightMode .sel,.night_mode .sel{background:#0d2a45;border-color:#64b5f6}
.nightMode .hint,.night_mode .hint{color:#90caf9}
.nightMode .ok,.night_mode .ok{background:#1b3a1e;color:#a5d6a7;border-color:#66bb6a}
.nightMode .bad,.night_mode .bad{background:#3d1717;color:#ef9a9a;border-color:#e57373}
.nightMode .good,.night_mode .good{color:#81c784}.nightMode .wrong,.night_mode .wrong{color:#e57373}
.nightMode .note,.night_mode .note{background:#3a3218;color:#ffe082}
.nightMode .ex img,.night_mode .ex img{background:#fff}''')

deck = genanki.Deck(zlib.crc32(args.deck.encode()) | (1 << 30), args.deck)
e = html.escape
media = []
for q in json.load(open(args.questions)):
    assert q["ans"] and all(1 <= a <= len(q["opts"]) for a in q["ans"]), f"bad answer in Q{q['num']}: {q['ans']}"
    opts = "".join(f'<div class="opt" data-i="{i+1}"><b>{L[i]}.</b>{e(o)}</div>' for i, o in enumerate(q["opts"]))
    imgs = q.get("imgs", [])
    ex = "".join(f'<img src="{f}">' for f in imgs)
    media += [os.path.join(args.img_dir, f) for f in imgs]
    k = len(q["ans"])
    tags = [t.replace(" ", "_") for t in [args.label] + args.tag] + (["Exhibit"] if imgs else []) + ([f"Choose{k}"] if k > 1 else [])
    deck.add_note(genanki.Note(model=model, tags=tags, guid=genanki.guid_for(args.deck, q["num"]),
        fields=[str(q["num"]), e(args.label), e(q["stem"]), ex, opts, str(k),
                ",".join(map(str, q["ans"])), q.get("note", "")]))
pkg = genanki.Package(deck)
pkg.media_files = media
os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
pkg.write_to_file(args.out)
print(f"{len(deck.notes)} notes, {len(media)} images -> {args.out}")
