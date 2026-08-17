"""
tests/make_sample_pdfs.py
=========================
Creates two SMALL SAMPLE PDFs for end-to-end testing of the prototype:

    papers/reference.pdf  -> a fake "original research paper"
    papers/student.pdf    -> a fake "student submission" that copies
                             some paragraphs, paraphrases others, and
                             also contains original content

This lets you test the whole pipeline without hunting for real papers.
The generator needs PyMuPDF installed:

    pip install pymupdf

Run from inside the research_similarity_prototype folder:

    python tests/make_sample_pdfs.py
"""

import os

import fitz  # PyMuPDF


# --------------------------------------------------------------------------
# The fake "original" reference paper
# --------------------------------------------------------------------------

REFERENCE_PAGE_1 = [
    """Deep learning has emerged as one of the most powerful machine learning
techniques of the last decade. Neural networks with many layers can now learn
complex patterns directly from raw data such as images, audio and text. In the
medical domain, deep learning models have achieved expert-level performance on
tasks like classifying skin conditions, detecting diabetic retinopathy in eye
scans, and predicting patient deterioration from electronic health records.""",
    """Despite this progress, the adoption of deep learning in clinical practice
remains limited. A key obstacle is the lack of interpretability: clinicians
hesitate to trust predictions from models that cannot explain their reasoning.
Consequently, research on explainable artificial intelligence for healthcare
has grown rapidly in recent years, producing techniques such as attention
maps, saliency methods and concept activation vectors.""",
]

REFERENCE_PAGE_2 = [
    """In this work we propose an interpretable pipeline for hospital mortality
prediction. Our approach combines a gradient boosted tree ensemble with
post-hoc explanation via SHAP values. We evaluate the pipeline on the MIMIC-IV
intensive care database, which contains de-identified records of more than
fifty thousand ICU admissions. Our model achieves an area under the ROC curve
of 0.85, exceeding previously reported baselines while remaining fully
explainable at the patient level.""",
    """Our results suggest that interpretable machine learning can match the
accuracy of black-box deep networks on tabular clinical data. We argue that
future work should focus on human-in-the-loop evaluation, where explanations
are assessed not only by fidelity metrics but by whether they help clinicians
make better and faster decisions at the bedside.""",
]


# --------------------------------------------------------------------------
# The fake "student" paper: copies some parts, paraphrases others, adds original content
# --------------------------------------------------------------------------

STUDENT_PAGE_1 = [
    """Climate change poses a serious threat to global agriculture. Rising
temperatures, changing rainfall patterns and the increased frequency of
extreme weather events reduce crop yields and threaten food security in many
regions. This thesis investigates how machine learning can support farmers
and policymakers in adapting to these challenges.""",  # original, unrelated
    """Despite this progress, the adoption of deep learning in clinical practice
remains limited. A key obstacle is the lack of interpretability: clinicians
hesitate to trust predictions from models that cannot explain their reasoning.""",  # COPIED
]

STUDENT_PAGE_2 = [
    """Machine learning methods based on layered neural representations have
become the dominant artificial intelligence approach of recent years. Such
models automatically discover intricate structure in large datasets including
medical images, speech and natural language, and they now rival human experts
on several diagnostic tasks.""",  # PARAPHRASE of reference page 1, para 1
    """Football analytics is a growing field in sports science. Coaches use
tracking data to evaluate player fitness, optimize training loads and reduce
injury risk across a long competitive season. Statistical models of passing
networks can even quantify a team's playing style.""",  # original, unrelated
    """We propose an explainable pipeline for predicting mortality in
intensive care units, combining gradient boosted trees with SHAP value
explanations, and we validate it on the public MIMIC-IV database of critical
care records.""",  # PARAPHRASE of reference page 2, para 1
]


def write_pdf(file_path, pages_content, title):
    """Create a simple multi-page PDF where each list item becomes a paragraph."""
    document = fitz.open()  # new empty PDF

    paragraphs_on_page = 2  # split content across pages, 2 paragraphs each

    # Chunk the list of paragraphs into groups -> one PDF page per group
    for start in range(0, len(pages_content), paragraphs_on_page):
        group = pages_content[start:start + paragraphs_on_page]
        page = document.new_page()  # A4 by default
        y_position = 72  # start a bit below the top margin

        page.insert_text(
            (72, y_position), title, fontsize=14, fontname="hebo"
        )
        y_position += 28

        for paragraph in group:
            # insert_textbox wraps the text automatically inside the rectangle
            rectangle = fitz.Rect(72, y_position, 523, y_position + 400)
            inserted_height = page.insert_textbox(
                rectangle, paragraph, fontsize=11, fontname="helv", align=3
            )
            # if inserted_height < 0 the text did not fit (not expected here)
            y_position += 160  # move down for the next paragraph

        print(f"  page written ({len(group)} paragraphs)")

    document.save(file_path)
    document.close()
    print(f"  saved -> {file_path}")


if __name__ == "__main__":
    papers_folder = os.path.join(os.path.dirname(__file__), "..", "papers")
    os.makedirs(papers_folder, exist_ok=True)

    reference_path = os.path.join(papers_folder, "reference.pdf")
    student_path = os.path.join(papers_folder, "student.pdf")

    print("Creating sample reference.pdf ...")
    write_pdf(reference_path, REFERENCE_PAGE_1 + REFERENCE_PAGE_2,
              "Interpretable Machine Learning for ICU Mortality Prediction")

    print("Creating sample student.pdf ...")
    write_pdf(student_path, STUDENT_PAGE_1 + STUDENT_PAGE_2,
              "Machine Learning for Climate-Resilient Agriculture")

    print("Done. You can now run:  python main.py")
