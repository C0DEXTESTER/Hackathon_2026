# AI Research Paper Similarity Prototype

A small command-line Python prototype that compares a **student research paper** against a **reference academic paper** and flags duplicate or semantically similar content — using only free, open-source tools that run completely locally.

This is **Stage 1** of a hackathon project: first prove the core AI similarity detection works, then (later) build a website on top of it.

---

## What this project does

You give it two PDFs:

```text
papers/reference.pdf   (the original/source paper)
papers/student.pdf     (the submission to check)
```

The program:

1. Extracts text from both PDFs (page by page)
2. Splits the text into paragraph-sized **chunks**
3. Converts every chunk into an **embedding** (a numerical representation of its meaning)
4. Compares every student chunk against every reference chunk using:
   - **semantic similarity** (meaning — catches paraphrasing)
   - **lexical similarity** (exact wording — catches copy-paste)
5. Combines both into one score, classifies risk (LOW / MEDIUM / HIGH)
6. Prints the top matches with page numbers and text previews
7. Saves the full analysis to `results/analysis.json`

> ⚠️ **Important:** A HIGH similarity flag means "high similarity — review recommended". It is **not** proof of plagiarism. A human must always make the final judgment.

---

## How it works

```text
PDF
 ↓
Text (PyMuPDF)
 ↓
Chunks (paragraphs, ~150 words)
 ↓
Embeddings (all-MiniLM-L6-v2)
 ↓
Cosine Similarity (semantic)
 ↓
SequenceMatcher (lexical)
 ↓
Combined Score (0.7 × semantic + 0.3 × lexical)
 ↓
Flag similar content (LOW / MEDIUM / HIGH)
```

---

## What is an embedding?

An embedding is a **list of numbers that describes the meaning of a piece of text**.

```text
"AI is used in healthcare"  →  [0.12, -0.45, 0.88, ..., 0.03]
```

Think of it as coordinates on a map of meanings. Texts with similar meanings end up close together on that map, even if they use different words:

- "Machine learning helps doctors" → point A
- "ML assists physicians" → point B (very close to A)
- "The football team won" → point C (far away from A)

We use the free model `all-MiniLM-L6-v2` (only ~80 MB, runs fine on CPU) from the `sentence-transformers` library.

---

## What is cosine similarity?

Cosine similarity measures the **angle** between two embedding vectors:

- **1.0** — vectors point the same way → texts mean the same thing
- **0.0** — vectors are perpendicular → meanings are unrelated

It ignores how long the vectors are and only looks at direction, which is exactly what we want when comparing meaning. We compute it with `sklearn.metrics.pairwise.cosine_similarity`.

---

## What is semantic similarity?

Semantic similarity = how close the **meanings** of two texts are, regardless of wording.

Example:

```text
Student:   "AI technologies are increasingly used for medical diagnosis."
Reference: "Artificial intelligence is increasingly being used to diagnose diseases."
```

These share few words, but mean almost the same thing → **high semantic similarity**. Copy-paste checkers that only compare strings would miss this; embeddings catch it.

---

## Installation

Make sure you have Python 3.10+ installed, then run:

```bash
pip install -r requirements.txt
```

This installs:

- `pymupdf` — PDF text extraction
- `sentence-transformers` — embedding model (also installs PyTorch)
- `scikit-learn` — cosine similarity

> The **first run** downloads the `all-MiniLM-L6-v2` model (~80 MB) from Hugging Face and caches it locally. After that everything works **offline**.

---

## How to run

Put your two PDFs here (exact names):

```text
papers/reference.pdf
papers/student.pdf
```

Then run:

```bash
python main.py
```

**Easiest way (Windows):** just **double-click `run.bat`** inside the project folder — it runs the program and keeps the window open so you can read the results.

**From VS Code:** right-click `main.py` → *Run Python File in Terminal* (make sure the terminal is inside the `research_similarity_prototype` folder).

Optional quick self-test (no PDFs needed) — compares three small text pairs (exact duplicate / paraphrase / unrelated):

```bash
python main.py --test
```

---

## Optional: local web interface

The **same engine** also powers a small local website (Flask backend + plain HTML/CSS/JS frontend — no frameworks):

```bash
python app.py
```

Then open <http://127.0.0.1:5000> (or double-click `start_website.bat` on Windows).

- Upload the two PDFs in the browser (drag & drop supported)
- Watch the **real** analysis progress (the same steps as the command line)
- View the similarity report on the Results dashboard (donut chart, breakdown bars, match cards with page numbers, detail modal with shared-word highlighting)
- Past analyses are listed on the History page (stored in `results/history/`)

The website adds **no new AI logic** — `app.py` simply calls the same `analyze_papers()` pipeline used by `python main.py`.

---

## Output

The terminal shows:

- Overall similarity (experimental, average of best-match combined scores)
- Counts of HIGH / MEDIUM / LOW similarity chunks
- Top 10 most similar chunk pairs with:
  - semantic / lexical / combined percentages
  - student page number & reference page number
  - the actual matched text (so you can see **why** it was flagged)

A machine-readable copy of everything is saved to:

```text
results/analysis.json
```

This JSON will later be consumed by the web version of the tool.

---

## Project structure

```text
research_similarity_prototype/
├── main.py              # entry point + pipeline + report + JSON saving
├── app.py               # optional Flask backend + local website server
├── pdf_processor.py     # PDF extraction, text cleaning, chunking
├── similarity.py        # embeddings + semantic/lexical/combined scoring
├── requirements.txt
├── README.md
├── start_website.bat    # double-click to launch the website (Windows)
├── run.bat              # double-click to run the CLI version (Windows)
├── papers/              # put reference.pdf and student.pdf here
├── results/             # analysis.json + history/ (web analyses)
├── website/             # HTML/CSS/JS frontend (no build tools)
└── tests/               # (optional) extra test material
```

---

## Limitations

- Similarity is **not proof of plagiarism** — always human-review flagged passages
- Scanned / image-based PDFs are **not supported** (no OCR yet)
- Thresholds (0.50 / 0.75) and weights (0.7 / 0.3) are **preliminary guesses**, not calibrated on a dataset
- Common academic phrases ("in this paper we propose...") may cause **false positives**
- Only **one reference paper** can be compared at a time
- Short/generic sentences can score oddly high with embedding models

---

## Future Improvements

- Improve the local web interface (multi-user, accounts, better charts)
- Section-wise analysis (compare only Methodology vs Methodology)
- Dataset-based evaluation and threshold calibration
- OCR support for scanned PDFs
- Academic-domain-specific embedding models (e.g. SPECTER)
- Batch comparison against multiple reference papers
- Downloadable PDF/HTML reports