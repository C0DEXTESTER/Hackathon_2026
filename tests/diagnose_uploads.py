"""Temporary diagnostic: check the user's uploaded PDFs."""
import sys
sys.path.insert(0, 'research_similarity_prototype')
from pdf_processor import extract_text_from_pdf, create_chunks

files = [
    ('REFERENCE', 'research_similarity_prototype/uploads/20260815_170623_ccc6ee_reference.pdf'),
    ('STUDENT', 'research_similarity_prototype/uploads/20260815_170623_ccc6ee_student.pdf'),
]

for label, path in files:
    print('=' * 30, label)
    try:
        pages = extract_text_from_pdf(path)
        total_chars = sum(len(p['text']) for p in pages)
        print('pages with text:', len(pages), '| total chars:', total_chars)
        chunks = create_chunks(pages)
        print('chunks:', len(chunks))
        for p in pages[:4]:
            words = len(p['text'].split())
            preview = p['text'][:60].replace('\n', ' ')
            print('  page', p['page'], ':', words, 'words |', repr(preview))
    except Exception as e:
        print('ERROR:', e)