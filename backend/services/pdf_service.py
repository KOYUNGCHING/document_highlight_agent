"""Extract stable text blocks with normalized display coordinates."""
import fitz


class PDFService:
    def extract_text_from_pdf(self, file_path: str):
        pages = []
        with fitz.open(file_path) as doc:
            if doc.needs_pass:
                raise ValueError("請先解除 PDF 密碼保護。")
            for index, page in enumerate(doc):
                blocks = []
                for block in page.get_text("blocks", sort=True):
                    if block[6] != 0 or not block[4].strip():
                        continue
                    rect = fitz.Rect(block[:4]) * page.rotation_matrix
                    bounds = page.rect
                    coords = [rect.x0 / bounds.width, rect.y0 / bounds.height,
                              rect.x1 / bounds.width, rect.y1 / bounds.height]
                    text = block[4].strip()
                    # Oversized layout blocks share their source rectangle but have
                    # separate IDs, keeping each model input batch bounded.
                    for start in range(0, len(text), 4000):
                        blocks.append({"block_id": f"p{index + 1}-b{len(blocks)}",
                                       "page": index + 1, "text": text[start:start + 4000],
                                       "rect": [max(0, min(1, x)) for x in coords]})
                pages.append({"page_num": index + 1,
                              "text": "\n".join(b["text"] for b in blocks),
                              "blocks": blocks})
        return pages
