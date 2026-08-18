<h1>ResearchGuard AI</h1>

A small web app for comparing a student paper against a reference paper and flagging text that looks copied or paraphrased. It combines AI embeddings with plain lexical comparison so it catches both direct copy-paste and reworded content.

Note: a high score is a flag for a human to look at, not proof of plagiarism. This is a screening tool, not a verdict.

What it does
Takes two PDFs — a reference paper and a student paper
Pulls text out with PyMuPDF and breaks it into chunks
Embeds the chunks with FastEmbed
Scores each student chunk against the closest reference chunk, two ways:
semantic similarity (meaning)
lexical similarity (actual wording)
Blends the two into one score and buckets it into LOW / MEDIUM / HIGH
Shows you the matching passages side by side, with page numbers, so you can actually check the match instead of trusting a number
Why semantic + lexical

Straight text matching misses paraphrasing. If a student writes:

"AI technologies are increasingly used for medical diagnosis."

and the reference says:

"Artificial intelligence is increasingly being used to diagnose diseases."

a word-for-word diff won't catch that these are basically the same sentence. Embeddings do, because they compare meaning rather than exact characters.

The embedding model is sentence-transformers/all-MiniLM-L6-v2, run through FastEmbed on ONNX Runtime — open source, no external API key needed, runs locally.

Lexical similarity is simpler: lowercase, strip punctuation, normalize whitespace, then run Python's SequenceMatcher over it. This is what catches near-identical or copy-pasted sentences that semantic similarity alone might rate lower than it should.

How the score is calculated
combined_similarity = 0.7 * semantic_similarity + 0.3 * lexical_similarity

Semantic gets the higher weight since paraphrase detection is the main point here — a purely lexical check would miss it.

Risk buckets:

Score	Risk
< 0.50	LOW
0.50 – 0.75	MEDIUM
>= 0.75	HIGH

These thresholds are preliminary — they haven't been calibrated against a real academic dataset yet, so treat HIGH as "worth a closer look," not "guilty."

Pipeline
Reference PDF ──┐
                ├──> extract text ──> chunk ──> embed ──┐
Student PDF ────┘                                       │
                                                          ▼
                                       semantic similarity + lexical similarity
                                                          │
                                                          ▼
                                              combined score → risk label
                                                          │
                                                          ▼
                                                  analysis report
Running it

Requires Python 3.10+.

bash
pip install -r requirements.txt
python app.py

Windows users can just double-click start_website.bat. Either way, it comes up at http://127.0.0.1:5000.

You'll see something like:

=======================================================
 ResearchGuard AI - Web Backend
=======================================================
 Website: http://127.0.0.1:5000
 Health:  http://127.0.0.1:5000/api/health
=======================================================

There's also a CLI path if you don't want the web UI:

bash
python main.py

Same pipeline underneath (PDF processing → chunking → FastEmbed → semantic/lexical scoring → risk classification), just no browser involved.

Uploading papers

The web app takes two PDFs — reference and student. Max request size is 30MB. Once uploaded, the backend validates the files, generates a job ID, and kicks off analysis in a background thread so the server doesn't lock up while the model loads and runs. Only one analysis runs at a time, mostly to keep memory use sane.

You can poll GET /api/progress while it's running to get the current stage — extracting text, chunking, loading the model, generating embeddings, scoring, and so on — if you want to show a progress bar or just watch it work.

API
Method	Endpoint	What it does
GET	/api/health	Reports starting until the model has loaded, then ok
POST	/api/analyze	Takes reference_pdf + student_pdf, returns a job_id
GET	/api/progress	Current status of the running job
GET	/api/results	Most recent completed analysis
GET	/api/results/<job_id>	A specific analysis by job ID
GET	/api/history	List of past analyses
DELETE	/api/history/<job_id>	Removes one analysis + its uploaded PDFs
DELETE	/api/history	Wipes all stored history and uploads

Example /api/analyze response:

json
{
  "job_id": "20260818_123456_a1b2c3",
  "status": "started"
}

Example chunk-level match from a report:

json
{
  "student_chunk_id": 12,
  "reference_chunk_id": 8,
  "semantic_similarity": 0.8421,
  "lexical_similarity": 0.7315,
  "combined_similarity": 0.8089,
  "risk": "HIGH",
  "student_page": 4,
  "reference_page": 3
}

Completed analyses get saved under results/history/, each with its own job ID, similarity breakdown, timestamps, and the matched chunks with page numbers.

Frontend

Plain HTML/CSS/JS, no framework or build step. Handles the usual stuff — responsive nav, dark/light theme (persisted in localStorage), toast notifications, scroll animations, a typing effect on the hero, shared-word highlighting on matches, and JSON export of results.

Project layout
research_similarity_prototype/
├── app.py              # Flask backend + API routes
├── main.py              # CLI analysis pipeline
├── similarity.py         # embeddings + similarity math
├── pdf_processor.py       # PDF extraction and chunking
├── requirements.txt
├── start_website.bat
├── run.bat
├── papers/               # test/reference PDFs
├── uploads/               # uploaded PDFs
├── results/
│   ├── analysis.json
│   └── history/
├── website/               # HTML/CSS/JS
└── tests/
Stack

Python, Flask, PyMuPDF for PDF extraction, FastEmbed (all-MiniLM-L6-v2 on ONNX Runtime) for embeddings, NumPy for the math, SequenceMatcher for lexical comparison, Gunicorn for production, and a no-framework HTML/CSS/JS frontend.

Known limitations
One student paper vs. one reference paper at a time — no batch mode yet
Scanned/image PDFs aren't supported, no OCR
Thresholds are provisional, not validated against a large academic corpus
Generic or boilerplate academic phrasing can trigger false positives
Short sentences sometimes get inflated semantic scores
The embedding model is general-purpose, not trained specifically on academic writing
Doesn't check citations or references at all
Similarity ≠ plagiarism — full stop
Single analysis job at a time
This is a prototype, not a production-grade system
Where this could go

Batch comparison against multiple references, an academic-tuned embedding model, section-by-section comparison, citation checking, OCR for scanned documents, better visualizations, downloadable PDF/HTML reports, proper threshold calibration against real data, multi-user support with auth, and general performance/memory work.

The point of it

Plain text-matching tools break down the moment someone paraphrases instead of copying. This combines semantic understanding with lexical comparison to catch both, and gives you a risk label plus the actual matched text so you can make the call yourself — it's a first pass, not a verdict.

Disclaimer: ResearchGuard AI is a screening tool. Its output is meant to guide further human review, not serve as proof of academic misconduct. The final call always belongs to a qualified reviewer.
