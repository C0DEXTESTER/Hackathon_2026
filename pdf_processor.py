"""
pdf_processor.py
================
This file handles everything related to reading PDF files and preparing text:

  1. Extract text from a PDF (page by page, keeping page numbers)
  2. Clean the text (normalize whitespace, remove junk)
  3. Split the text into small "chunks" (paragraph-sized pieces)
     that the AI model can compare later.

We use PyMuPDF (imported as "fitz") because it is fast and free.
"""

import re  # Python's built-in regular-expression module (used to split paragraphs)

import fitz  # PyMuPDF - the library that actually reads PDF files


# ---------------------------------------------------------------------------
# STEP 1: EXTRACT TEXT FROM A PDF
# ---------------------------------------------------------------------------

def extract_text_from_pdf(pdf_path):
    """
    Open a PDF file and pull out the text of every page.

    Returns a list of dictionaries, one per page, like this:

        [
            {"page": 1, "text": "...text of page 1..."},
            {"page": 2, "text": "...text of page 2..."},
            ...
        ]

    Page numbers start at 1 (more natural for humans than 0).

    If the file cannot be opened, the program stops with a clear error.
    If a page has no text at all, we warn the user that the PDF might be
    a scanned/image-based document (which would need OCR - not built yet).
    """

    # --- 1. Try to open the PDF -------------------------------------------
    try:
        pdf_document = fitz.open(pdf_path)
    except Exception as error:
        # "raise" stops the program here and shows the message below.
        raise FileNotFoundError(
            f"Could not open PDF file: '{pdf_path}'\n"
            f"Reason: {error}\n"
            f"Please check that the file exists and is a valid PDF."
        )

    pages = []  # this list will hold {"page": ..., "text": ...} dictionaries

    # --- 2. Read every page one by one ------------------------------------
    for page_number in range(len(pdf_document)):
        # fitz uses 0-based page indexes, so we add 1 to display 1-based pages
        #
        # We use get_text("blocks") instead of plain get_text():
        # "blocks" returns the text grouped into rectangular blocks, and in
        # most PDFs one block == one paragraph (or title, or table cell).
        # We join the blocks with a BLANK LINE ("\n\n") so that the chunking
        # step below can find the paragraph boundaries reliably.
        blocks = pdf_document[page_number].get_text("blocks")

        text_parts = []
        for block in blocks:
            # Each block is a tuple; index 4 holds its text and index 6
            # tells us its type: 0 = text block, 1 = image block.
            if block[6] == 0 and block[4].strip():
                text_parts.append(block[4].strip())

        raw_text = "\n\n".join(text_parts)

        # Skip completely empty pages early (saves work later)
        if raw_text.strip():
            pages.append(
                {
                    "page": page_number + 1,  # 1-based page number
                    "text": raw_text,
                }
            )
        else:
            # Page has no selectable text -> probably a scanned image.
            print(
                f"  Warning: page {page_number + 1} has no extractable text. "
                f"The PDF may be scanned/image-based (OCR is not supported yet)."
            )

    pdf_document.close()  # good habit: release the file

    # --- 3. Make sure we found at least SOMETHING --------------------------
    if not pages:
        raise ValueError(
            f"No text could be extracted from '{pdf_path}'.\n"
            f"This PDF is probably scanned/image-based.\n"
            f"Converting images to text requires OCR, which is not "
            f"implemented in this prototype yet."
        )

    return pages


# ---------------------------------------------------------------------------
# STEP 2: CLEAN THE TEXT
# ---------------------------------------------------------------------------

def clean_text(text):
    """
    Light, safe text cleaning.

    What it does:
      * removes hyphens that only exist because a word was split across
        two lines in the PDF (e.g. "com-\nputer" -> "computer")
      * converts every line break into a single space (we split into
        paragraphs using blank lines BEFORE calling this - see below)
      * collapses multiple spaces into one
      * trims spaces from the start and end

    What it deliberately does NOT do:
      * it does not remove words, punctuation or stop-words.
        We keep the text as close to the original as possible so the
        similarity comparison stays meaningful.
    """
    if not text:
        return ""

    # Join words that were hyphenated at a line break:
    # "com-" + newline + "puter"  becomes  "computer"
    fixed_text = text.replace("-\n", "")

    # Replace all remaining line breaks with a space
    fixed_text = fixed_text.replace("\n", " ")

    # Collapse runs of spaces/tabs into one single space
    while "  " in fixed_text:
        fixed_text = fixed_text.replace("  ", " ")

    return fixed_text.strip()


# ---------------------------------------------------------------------------
# STEP 3: SPLIT TEXT INTO CHUNKS
# ---------------------------------------------------------------------------

# Roughly how many words one chunk should contain.
# 100-200 words is a good size: big enough for meaning, small enough
# for a precise comparison.
TARGET_WORDS_PER_CHUNK = 150

# Never make chunks bigger than this many words - if a paragraph is longer,
# we slice it into several pieces (paragraph boundaries first, size second).
MAX_WORDS_PER_CHUNK = 250


def _split_into_sentences(paragraph):
    """
    Helper function: split a paragraph into sentences.

    We split AFTER a period, exclamation or question mark that is followed
    by whitespace + a capital-looking continuation. This is not a perfect
    grammar parser, but it is good enough for chunking purposes.
    """
    sentences = re.split(r"(?<=[.!?])\s+", paragraph)
    return [s.strip() for s in sentences if s.strip()]


def _split_long_paragraph(paragraph):
    """
    Helper function (the underscore means "internal, not used outside").

    If a single paragraph is longer than MAX_WORDS_PER_CHUNK words,
    split it at SENTENCE boundaries and pack whole sentences together
    until we reach ~TARGET_WORDS_PER_CHUNK words. Splitting at sentences
    (instead of cutting mid-word-window) keeps every chunk readable
    and keeps its meaning intact for the embedding model.
    """
    sentences = _split_into_sentences(paragraph)

    pieces = []
    current_words = []  # words collected for the piece being built

    for sentence in sentences:
        sentence_words = sentence.split()

        # A single monster sentence longer than the limit: hard-slice it.
        if len(sentence_words) > MAX_WORDS_PER_CHUNK:
            if current_words:
                pieces.append(" ".join(current_words))
                current_words = []
            for start in range(0, len(sentence_words), TARGET_WORDS_PER_CHUNK):
                window = sentence_words[start:start + TARGET_WORDS_PER_CHUNK]
                pieces.append(" ".join(window))
            continue

        # Would adding this sentence overflow the target size?
        if len(current_words) + len(sentence_words) > TARGET_WORDS_PER_CHUNK \
                and current_words:
            pieces.append(" ".join(current_words))
            current_words = []

        current_words.extend(sentence_words)

    # Don't forget the last partially-filled piece
    if current_words:
        pieces.append(" ".join(current_words))

    return pieces


def create_chunks(pages):
    """
    Turn the list of page dictionaries (from extract_text_from_pdf)
    into a list of chunk dictionaries:

        [
            {"chunk_id": 1, "text": "...", "page": 1},
            {"chunk_id": 2, "text": "...", "page": 2},
            ...
        ]

    Strategy (kept simple on purpose):
      1. Paragraphs inside a page are separated by blank lines.
      2. Every paragraph becomes its own chunk (page number is remembered).
      3. Very long paragraphs are sliced into ~150-word pieces.
      4. Very short fragments (< 20 words) are NOT blindly thrown away.
         Some PDF generators export text as ONE LINE PER BLOCK, so a real
         paragraph arrives as many tiny pieces. If we dropped them all,
         a perfectly good PDF would produce ZERO chunks. Instead, the
         small pieces of each page are collected and MERGED back into
         normal-size chunks.
    """
    MIN_WORDS_PER_CHUNK = 20  # shorter than this -> not meaningful for AI

    chunks = []
    chunk_id = 1

    for page in pages:
        raw_text = page["text"]

        # Paragraphs in PDF text are separated by blank lines (one or more
        # newlines possibly with spaces between them). The regex below
        # splits on ANY blank line, e.g. "\n\n", "\n \n", "\n  \n", ...
        paragraphs = re.split(r"\n\s*\n", raw_text)

        # Small pieces found on this page; merged into chunks afterwards.
        leftover_words = []

        for paragraph in paragraphs:
            # Clean whitespace but keep the words themselves untouched
            cleaned = clean_text(paragraph)

            word_count = len(cleaned.split())

            # Empty paragraph -> nothing to do
            if word_count == 0:
                continue

            # Piece too small to be a chunk on its own -> keep its WORDS
            # so they can be merged later (see docstring point 4).
            if word_count < MIN_WORDS_PER_CHUNK:
                leftover_words.extend(cleaned.split())
                continue

            # Normal-size paragraph -> one chunk
            if word_count <= MAX_WORDS_PER_CHUNK:
                chunks.append(
                    {
                        "chunk_id": chunk_id,
                        "text": cleaned,
                        "page": page["page"],
                    }
                )
                chunk_id += 1
            else:
                # Huge paragraph -> cut into ~150-word pieces
                for piece in _split_long_paragraph(cleaned):
                    chunks.append(
                        {
                            "chunk_id": chunk_id,
                            "text": piece,
                            "page": page["page"],
                        }
                    )
                    chunk_id += 1

        # Merge this page's small leftover pieces into real chunks.
        if len(leftover_words) >= MIN_WORDS_PER_CHUNK:
            merged_text = " ".join(leftover_words)
            if len(leftover_words) <= MAX_WORDS_PER_CHUNK:
                chunks.append(
                    {
                        "chunk_id": chunk_id,
                        "text": merged_text,
                        "page": page["page"],
                    }
                )
                chunk_id += 1
            else:
                # Leftovers together are long -> slice into ~150-word pieces
                for piece in _split_long_paragraph(merged_text):
                    chunks.append(
                        {
                            "chunk_id": chunk_id,
                            "text": piece,
                            "page": page["page"],
                        }
                    )
                    chunk_id += 1

    return chunks


# ---------------------------------------------------------------------------
# ALLOW RUNNING THIS FILE DIRECTLY FOR A QUICK TEST:  python pdf_processor.py
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Quick manual test: try to extract and chunk a PDF given on the command line
    import sys

    if len(sys.argv) < 2:
        print("Usage: python pdf_processor.py <path-to-pdf>")
    else:
        print(f"Extracting text from: {sys.argv[1]}")
        extracted_pages = extract_text_from_pdf(sys.argv[1])
        print(f"  Pages with text: {len(extracted_pages)}")
        for p in extracted_pages[:3]:  # show first 3 pages briefly
            print(f"  Page {p['page']} preview: {p['text'][:80]}...")
        created_chunks = create_chunks(extracted_pages)
        print(f"  Chunks created: {len(created_chunks)}")
        if created_chunks:
            print(f"  First chunk: {created_chunks[0]['text'][:80]}...")