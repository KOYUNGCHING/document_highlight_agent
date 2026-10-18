"""Content-addressed PDF storage. Filenames never determine cache identity."""
import hashlib
import json
import re
from pathlib import Path
from uuid import uuid4

from services.pdf_service import PDFService


class DocumentStore:
    def __init__(self, root: Path):
        self.root = root
        root.mkdir(parents=True, exist_ok=True)
        self.parser = PDFService()

    def _path(self, document_id, suffix):
        if not re.fullmatch(r"[a-f0-9]{64}", document_id):
            raise ValueError("Invalid document ID")
        return self.root / f"{document_id}{suffix}"

    @staticmethod
    def _write_json(path, data):
        temp = path.with_name(f"{path.name}.{uuid4().hex}.tmp")
        try:
            temp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            temp.replace(path)
        finally:
            temp.unlink(missing_ok=True)

    def save(self, data: bytes, filename: str):
        if not data.startswith(b"%PDF-"):
            raise ValueError("請上傳有效的 PDF 文件。")
        document_id = hashlib.sha256(data).hexdigest()
        pdf_path = self._path(document_id, ".pdf")
        cache_path = self._path(document_id, ".json")
        if cache_path.exists():
            document = self.load(document_id)
        else:
            temp = self.root / f"{uuid4().hex}.tmp"
            try:
                temp.write_bytes(data)
                pages = self.parser.extract_text_from_pdf(str(temp))
                if not any(p["blocks"] for p in pages):
                    raise ValueError("PDF 沒有可讀取的文字，掃描文件需要先進行 OCR。")
                document = {"document_id": document_id,
                            "filename": Path(filename).name, "pages": pages}
                temp.replace(pdf_path)
                self._write_json(cache_path, document)
            finally:
                temp.unlink(missing_ok=True)
        self._write_json(self.root / "current.json", {"document_id": document_id})
        return document

    def load(self, document_id):
        return json.loads(self._path(document_id, ".json").read_text(encoding="utf-8"))

    def current(self):
        path = self.root / "current.json"
        if not path.exists():
            return None
        try:
            return self.load(json.loads(path.read_text())["document_id"])
        except (FileNotFoundError, ValueError, KeyError):
            return None

    def blocks(self, document_id):
        document = self.load(document_id)
        return [{**block, "document_id": document_id}
                for page in document["pages"] for block in page["blocks"]]
