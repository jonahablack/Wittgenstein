import os
import nltk
from nltk import sent_tokenize
import PyPDF2
from ebooklib import epub
from bs4 import BeautifulSoup

def extract_text_from_pdf(pdf_path):
    text = ""
    with open(pdf_path, 'rb') as f:
        reader = PyPDF2.PdfReader(f)
        for page in reader.pages:
            text += page.extract_text() + "\n"
    return text.strip()

def extract_text_from_epub(epub_path):
    book = epub.read_epub(epub_path)
    text_content = []
    for item in book.get_items():
        if item.get_type() == epub.ITEM_DOCUMENT:
            soup = BeautifulSoup(item.get_content(), 'html.parser')
            text_content.append(soup.get_text(separator=' ').strip())
    return "\n".join(text_content).strip()

def segment_text(text):
    # ensure NLTK is set up: python -m nltk.downloader punkt
    sentences = sent_tokenize(text)
    return list(enumerate(sentences))