import fitz  # PyMuPDF

class PDFService:
    def __init__(self):
        pass

    def extract_text_from_pdf(self, file_path: str):
        """Extract text from a PDF file page by page."""
        doc = fitz.open(file_path)
        pages_text = []
        for page_num in range(len(doc)):
            page = doc[page_num]
            text = page.get_text("text")
            pages_text.append({"text": text, "page_num": page_num + 1})
        return pages_text

