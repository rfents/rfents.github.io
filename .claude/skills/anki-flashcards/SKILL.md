---
name: anki-flashcards
description: Turn a PDF, document or topic into an interactive multiple-choice Anki deck (.apkg) for AnkiDroid, where the learner taps answers on the front and the back grades them. Use whenever the user asks for flashcards, an Anki deck, or cards "like before".
---

# Interactive Anki flashcards (AnkiDroid)

The user studies with **AnkiDroid** on their phone. Every flashcard request gets this format by default. Don't ask which format to use.

- **Deliverable:** a single `.apkg` file with all images embedded, sent with SendUserFile (`display: attach`). Don't commit decks to the repository.
- **Front:** the question, any exhibit image(s), and options lettered A–E. Tapping an option selects it (blue).
  - One-answer questions work like radio buttons.
  - "Choose N" questions allow up to N picks, with a "Select N answers (k/N)" counter.
- **Back:** a banner showing ✅ Correct! / ❌ Incorrect / "No answer selected".
  - Correct options are green with ✔. Correct options the learner didn't pick are dashed and marked "(missed)".
  - Wrong picks are red and marked "✘ your pick". Other options are faded.
- Works in AnkiDroid night mode and at phone width. Tags: a short label (e.g. `NSE4`), `Exhibit`, and `Choose2`/`Choose3`.
- If the source's answer looks wrong, keep the source answer and add a `note` (shown with ⚠ on the back) giving the likely correct answer. Only do this when you're confident.

## Workflow

Scripts live in `.claude/skills/anki-flashcards/scripts/`. Put working files in the scratchpad.

1. **Set up:** `pip install genanki pymupdf playwright` (Chromium is preinstalled; never run `playwright install`).
2. **Extract** (PDF source): `python3 scripts/extract_pdf.py input.pdf WORK`.
   - This writes `WORK/items.json` (text lines and images in reading order), `WORK/text.txt` and `WORK/img/`.
   - It also converts dotless `ı` to `i`, which is common in exam dumps.
3. **Parse** the questions into `WORK/questions.json`: a list of `{num, stem, opts[], ans[1-based], imgs[], note}`.
   - Write a small parser for the source's layout. Typical layout: `Question #N`, numbered options `1.`, `2.`, …, then `Correct Answer(s): 1, 3`.
   - Attach each image to the question header that comes before it. Skip cover images before the first question.
   - Options continue across wrapped lines until the next number in sequence.
4. **Check** before building. Print every question with its options and its correct answers starred, then read the whole list. Look for:
   - Malformed answers like `32` or `43` (typos for a single option).
   - A question sentence parsed as option 1.
   - Garbled quotes (`˜`) and broken text across page breaks.
   - Questions that mention an exhibit but have no image, and images attached to a question that doesn't mention an exhibit.
   - Fix these in the questions JSON and list every fix for the user.
5. **Build:** `python3 scripts/build_deck.py WORK/questions.json --deck "Deck Name" --label SHORT --img-dir WORK/img --out WORK/out/Deck_Name.apkg`
6. **Test:** `python3 scripts/test_deck.py WORK/out/Deck_Name.apkg WORK --shots`.
   - All cases must print `OK`. Look at `WORK/front.png` and `WORK/back.png`.
7. **Deliver:** send the `.apkg` plus the two screenshots.
   - Summarize the card count, images, fixes made and ⚠ notes.
   - Remind the user: to replace an older version of the same deck, delete it in AnkiDroid first. If tapping an option flips the card, remove "Show answer" from the tap areas in AnkiDroid Settings → Controls.

## For non-PDF or non-MCQ sources

For notes, a topic or a Q&A list, write the multiple-choice questions yourself: 4 options, plausible distractors, and one or more correct answers. Build them with the same script, so every deck has the same tap-to-answer format.

## Implementation notes

- `build_deck.py` uses one fixed note-type ID ("MCQ (interactive)"), so all decks share a note type. The deck ID and note GUIDs come from the deck name, so rebuilding a deck updates its notes instead of duplicating them.
- The front and back pass the selection through `window.mcqsel` and `sessionStorage`. This works both when AnkiDroid swaps the content in place and when it loads the back as a new page. Option clicks call `stopPropagation`.
