"""
main.py
=======
The entry point of the prototype.

Run it with:

    python main.py            -> full PDF vs PDF analysis
    python main.py --test     -> quick self-test with 3 small text examples

What it does (the pipeline):

    Reference PDF + Student PDF
            |
      Extract Text (PyMuPDF)
            |
      Split into Chunks
            |
      Generate Embeddings (all-MiniLM-L6-v2)
            |
      Compare chunks (cosine + SequenceMatcher)
            |
      Find best matches + combined score
            |
      Flag similar content + save results to results/analysis.json
"""

import json
import os
import sys

import pdf_processor
import similarity

# ---------------------------------------------------------------------------
# SETTINGS
# ---------------------------------------------------------------------------

# Default locations of the two PDFs (relative to this folder)
REFERENCE_PDF_PATH = os.path.join("papers", "reference.pdf")
STUDENT_PDF_PATH = os.path.join("papers", "student.pdf")

# Where the JSON report is written
RESULTS_FOLDER = "results"
RESULTS_FILE = os.path.join(RESULTS_FOLDER, "analysis.json")

# How many best matches to show in the terminal
TOP_MATCHES_TO_SHOW = 10


# ---------------------------------------------------------------------------
# SMALL HELPER FOR NICE TERMINAL OUTPUT
# ---------------------------------------------------------------------------

def print_step_done():
    print("  âœ“ Complete")


def print_short_text(label, text, max_chars=220):
    """Print a text preview trimmed to max_chars characters."""
    text = text.replace("\n", " ").strip()
    if len(text) > max_chars:
        text = text[:max_chars].rstrip() + "..."
    print(f'{label}: "{text}"')


# ---------------------------------------------------------------------------
# THE MAIN PIPELINE
# ---------------------------------------------------------------------------

def analyze_papers(reference_pdf_path=REFERENCE_PDF_PATH,
                   student_pdf_path=STUDENT_PDF_PATH,
                   progress_callback=None):
    """
    Run the complete analysis:

      1. Extract text from both PDFs
      2. Split into chunks
      3. Generate embeddings
      4. Compare and find best matches
      5. Compute overall similarity
      6. Print report + save JSON

    Returns the full results dictionary (also saved to results/analysis.json).

    progress_callback (optional): a function(step_name, percent) that gets
    called at each stage. The website backend uses this to show REAL
    progress to the user. If None (command-line use), nothing changes.
    """

    def report_progress(step_name, percent):
        """Tell the caller (e.g. the web backend) which stage we are on."""
        if progress_callback:
            progress_callback(step_name, percent)

    print("===========================================")
    print(" AI RESEARCH PAPER SIMILARITY PROTOTYPE")
    print("===========================================")
    print()
    print(f"Reference Paper:\n{reference_pdf_path}")
    print()
    print(f"Student Paper:\n{student_pdf_path}")
    print()

    # ------------------------------------------------------------------ 1/5
    print("[1/5] Extracting reference paper...")
    report_progress("extracting_reference_text", 15)
    reference_pages = pdf_processor.extract_text_from_pdf(reference_pdf_path)
    print(f"  Pages with text: {len(reference_pages)}")
    print_step_done()
    print()

    # ------------------------------------------------------------------ 2/5
    print("[2/5] Extracting student paper...")
    report_progress("extracting_student_text", 30)
    student_pages = pdf_processor.extract_text_from_pdf(student_pdf_path)
    print(f"  Pages with text: {len(student_pages)}")
    print_step_done()
    print()

    # ------------------------------------------------------------------ 3/5
    print("[3/5] Creating text chunks...")
    report_progress("creating_text_chunks", 45)
    reference_chunks = pdf_processor.create_chunks(reference_pages)
    student_chunks = pdf_processor.create_chunks(student_pages)
    print(f"  âœ“ Reference chunks: {len(reference_chunks)}")
    print(f"  âœ“ Student chunks: {len(student_chunks)}")
    print()

    if not reference_chunks or not student_chunks:
        # Name the exact problem PDF so the user knows which one to fix
        if not reference_chunks and not student_chunks:
            problem = "both the reference and the student paper"
        elif not reference_chunks:
            problem = "the REFERENCE paper"
        else:
            problem = "the STUDENT paper"
        print(
            f"ERROR: Could not build text chunks from {problem}.\n"
            f"The PDF may be scanned/image-based, or too short to analyze.\n"
            f"Scanned PDFs need OCR, which this prototype does not include yet."
        )
        return None
    print_step_done()
    print()

    # ------------------------------------------------------------------ 4/5
    print("[4/5] Generating embeddings...")
    report_progress("generating_embeddings", 60)
    model = similarity.load_embedding_model()
    reference_embeddings = similarity.generate_embeddings(model, reference_chunks)
    student_embeddings = similarity.generate_embeddings(model, student_chunks)
    print_step_done()
    print()

    # ------------------------------------------------------------------ 5/5
    print("[5/5] Comparing content...")
    report_progress("comparing_content", 85)
    match_results = similarity.find_best_matches(
        reference_chunks, student_chunks,
        reference_embeddings, student_embeddings,
    )
    overall_similarity = similarity.calculate_overall_similarity(match_results)
    print_step_done()

    # Average of each individual score across all student chunks —
    # the website dashboard shows these three numbers as bars.
    if match_results:
        avg_semantic = sum(m["semantic_similarity"] for m in match_results) / len(match_results)
        avg_lexical = sum(m["lexical_similarity"] for m in match_results) / len(match_results)
        avg_combined = sum(m["combined_similarity"] for m in match_results) / len(match_results)
    else:
        avg_semantic = avg_lexical = avg_combined = 0.0
    print()

    # ---------------------------------------------------------------- Report
    high_matches = [m for m in match_results if m["risk"] == "HIGH"]
    medium_matches = [m for m in match_results if m["risk"] == "MEDIUM"]
    low_matches = [m for m in match_results if m["risk"] == "LOW"]

    # Sort all matches by combined similarity (highest first) for the top list
    top_matches = sorted(
        match_results, key=lambda m: m["combined_similarity"], reverse=True
    )[:TOP_MATCHES_TO_SHOW]

    print("===========================================")
    print(" RESULTS")
    print("===========================================")
    print()
    print(f"Overall Similarity: {overall_similarity * 100:.1f}%")
    print("(experimental semantic + lexical similarity - NOT a plagiarism score)")
    print()
    print(f"High Similarity Matches:   {len(high_matches)}")
    print(f"Medium Similarity Matches: {len(medium_matches)}")
    print(f"Low Similarity Matches:    {len(low_matches)}")
    print()

    print("===========================================")
    print(" TOP SIMILAR CONTENT")
    print("===========================================")
    print()

    for rank, match in enumerate(top_matches, start=1):
        print(f"Match #{rank}")
        print(f"Combined Similarity: {match['combined_similarity'] * 100:.1f}%")
        print(f"Risk: {match['risk']}")
        if match["risk"] == "HIGH":
            print("(HIGH SIMILARITY - REVIEW RECOMMENDED)")
        print()
        print(f"Semantic Similarity: {match['semantic_similarity'] * 100:.1f}%")
        print(f"Lexical Similarity:  {match['lexical_similarity'] * 100:.1f}%")
        print()
        print(f"Student Page:   {match['student_page']}")
        print(f"Reference Page: {match['reference_page']}")
        print()
        print_short_text("Student", match["student_text"])
        print_short_text("Reference", match["reference_text"])
        print()
        print("-------------------------------------------")
        print()

    # ------------------------------------------------------------------ JSON
    results_for_json = {
        "reference_paper": reference_pdf_path,
        "student_paper": student_pdf_path,
        "reference_chunk_count": len(reference_chunks),
        "student_chunk_count": len(student_chunks),
        "overall_similarity": overall_similarity,
        "semantic_similarity": round(avg_semantic, 4),
        "lexical_similarity": round(avg_lexical, 4),
        "combined_similarity": round(avg_combined, 4),
        "high_similarity_matches": len(high_matches),
        "medium_similarity_matches": len(medium_matches),
        "low_similarity_matches": len(low_matches),
        "weights": {
            "semantic_weight": similarity.SEMANTIC_WEIGHT,
            "lexical_weight": similarity.LEXICAL_WEIGHT,
        },
        "thresholds": {
            "low_below": similarity.LOW_THRESHOLD,
            "high_above": similarity.HIGH_THRESHOLD,
        },
        "top_matches": top_matches,
        "all_matches": match_results,
    }

    save_results_to_json(results_for_json)

    print(f"Full results saved to: {RESULTS_FILE}")
    print("===========================================")

    report_progress("generating_report", 95)
    return results_for_json


def save_results_to_json(results):
    """Write the results dictionary into results/analysis.json."""
    os.makedirs(RESULTS_FOLDER, exist_ok=True)
    with open(RESULTS_FILE, "w", encoding="utf-8") as json_file:
        json.dump(results, json_file, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# OPTIONAL SELF-TEST MODE (no PDFs needed)
# ---------------------------------------------------------------------------

def run_simple_tests():
    """
    Quick sanity check of the similarity logic using three tiny examples:

      1. Exact duplicate  -> very high lexical + high semantic
      2. Paraphrase       -> high semantic, lower lexical
      3. Unrelated texts  -> low similarity everywhere

    Run with:  python main.py --test
    """
    print("===========================================")
    print(" SIMPLE TEXT SIMILARITY TESTS")
    print("===========================================")
    print()

    text_a = "Artificial intelligence is widely used in healthcare."

    examples = [
        ("Exact duplicate",
         "Artificial intelligence is widely used in healthcare."),
        ("Paraphrase",
         "AI technologies are commonly applied in the healthcare sector."),
        ("Unrelated",
         "The football team won the championship yesterday."),
    ]

    model = similarity.load_embedding_model()

    for label, text_b in examples:
        # Embeddings need a list of texts; we encode the pair together
        embeddings = model.encode(
            [text_a, text_b], normalize_embeddings=True
        )

        semantic = similarity.calculate_semantic_similarity_matrix(
            embeddings[:1], embeddings[1:]
        )[0][0]

        lexical = similarity.calculate_lexical_similarity(text_a, text_b)
        combined = similarity.calculate_combined_score(semantic, lexical)
        risk = similarity.classify_risk(combined)

        print(f"Example: {label}")
        print(f'  A: "{text_a}"')
        print(f'  B: "{text_b}"')
        print(f"  Semantic Similarity: {semantic * 100:.1f}%")
        print(f"  Lexical Similarity:  {lexical * 100:.1f}%")
        print(f"  Combined Similarity: {combined * 100:.1f}%")
        print(f"  Risk: {risk}")
        print()


# ---------------------------------------------------------------------------
# ENTRY POINT
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if "--test" in sys.argv:
        run_simple_tests()
    else:
        # Normal mode: compare the two PDFs in the papers/ folder
        if not os.path.exists(REFERENCE_PDF_PATH):
            print(f"ERROR: Reference paper not found at '{REFERENCE_PDF_PATH}'.")
            print("Please place your PDFs as papers/reference.pdf and papers/student.pdf,")
            print("or run 'python main.py --test' for the quick text-only self-test.")
        elif not os.path.exists(STUDENT_PDF_PATH):
            print(f"ERROR: Student paper not found at '{STUDENT_PDF_PATH}'.")
            print("Please place your PDFs as papers/reference.pdf and papers/student.pdf,")
            print("or run 'python main.py --test' for the quick text-only self-test.")
        else:
            analyze_papers()
