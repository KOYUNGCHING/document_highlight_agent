import os
import shutil
import json
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv

from services.pdf_service import PDFService
from services.llm_service import LLMService

load_dotenv()

app = FastAPI(title="PDF Smart Search API")

# Allow CORS for React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Mount uploads directory as static files so frontend can load PDF files directly
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

# Initialize Services
pdf_service = PDFService()
llm_service = LLMService()

STATE_FILE = os.path.join(UPLOAD_DIR, "state.json")

def get_active_file():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("active_file")
        except Exception:
            pass
    return None

def set_active_file(filename: str):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump({"active_file": filename}, f, ensure_ascii=False)
    except Exception as e:
        print(f"Error writing state file: {e}")

def filter_highlights(highlights: list[str], pages_text: list[dict]) -> list[str]:
    """Filters highlights to exclude terms that are too short or match too many pages."""
    valid_highlights = []
    
    def normalize(s):
        return s.replace(" ", "").replace("\n", "").replace("\r", "").replace("\t", "").lower()
        
    for hl in highlights:
        cleaned = hl.strip()
        # 1. Skip if too short (less than 4 characters)
        if len(cleaned) < 4:
            print(f"[FILTER] SKIP (too short): '{hl}'")
            continue
            
        norm_hl = normalize(cleaned)
        
        # 2. Find pages containing this highlight
        matched_pages = []
        for page in pages_text:
            norm_page_text = normalize(page["text"])
            if norm_hl in norm_page_text:
                matched_pages.append(page["page_num"])
                
        # 3. Discard if it matches more than 5 pages (truly generic noise)
        if len(matched_pages) > 5:
            print(f"[FILTER] SKIP (matches {len(matched_pages)} pages): '{hl[:40]}...'")
            continue
        elif len(matched_pages) == 0:
            print(f"[FILTER] SKIP (not found in text): '{hl[:40]}'")
            continue
            
        print(f"[FILTER] PASS (pages {matched_pages}): '{hl[:60]}'")
        valid_highlights.append(hl)
        
    return valid_highlights

class ChatRequest(BaseModel):
    question: str

@app.post("/api/upload")
async def upload_pdf(file: UploadFile = File(...)):
    """Uploads a PDF, extracts text (with caching), and sets as active document."""
    
    file_path = os.path.join(UPLOAD_DIR, file.filename)
    cache_path = file_path + ".json"
    
    # Save the file locally if it doesn't exist or is uploaded fresh
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    # Check cache
    if os.path.exists(cache_path):
        print(f"[CACHE] Found text cache for {file.filename}. Skipping PDF extraction.")
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                pages_text = json.load(f)
        except Exception as e:
            print(f"[CACHE] Failed to load cache: {e}. Re-parsing...")
            pages_text = pdf_service.extract_text_from_pdf(file_path)
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(pages_text, f, ensure_ascii=False)
    else:
        print(f"[PARSER] No cache found for {file.filename}. Extracting PDF text...")
        pages_text = pdf_service.extract_text_from_pdf(file_path)
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(pages_text, f, ensure_ascii=False)
            
    # Set this file as the active document
    set_active_file(file.filename)
    
    return {
        "filename": file.filename,
        "url": f"http://localhost:8000/uploads/{file.filename}",
        "message": f"Successfully processed {file.filename}. Total pages: {len(pages_text)}"
    }

@app.get("/api/current-file")
async def get_current_file():
    """Retrieves the active PDF file details."""
    active_file = get_active_file()
    if active_file and os.path.exists(os.path.join(UPLOAD_DIR, active_file)):
        return {
            "filename": active_file,
            "url": f"http://localhost:8000/uploads/{active_file}"
        }
    return {"filename": None, "url": None}

@app.post("/api/chat")
async def chat_with_pdf(request: ChatRequest):
    """Answers a question based on the PDF content from cache."""
    
    question = request.question
    active_file = get_active_file()
    
    if not active_file:
        return {"answer": "請先上傳 PDF 文件再開始提問。", "highlights": []}
        
    cache_path = os.path.join(UPLOAD_DIR, active_file + ".json")
    if not os.path.exists(cache_path):
        return {"answer": "快取資料不存在，請重新上傳 PDF 文件。", "highlights": []}
        
    # Load document text from cache
    with open(cache_path, "r", encoding="utf-8") as f:
        pages_text = json.load(f)
        
    # Construct context from entire text
    context_texts = []
    for page in pages_text:
        context_texts.append(f"[Page {page['page_num']}]\n{page['text']}")
    
    context = "\n\n".join(context_texts)
    
    # Call LLM
    response = llm_service.generate_response(question, context)
    
    # Filter highlights to prevent generic matching issues
    if "highlights" in response and isinstance(response["highlights"], list):
        response["highlights"] = filter_highlights(response["highlights"], pages_text)
        
        # Calculate target_page based on highlight matches
        target_page = None
        if len(response["highlights"]) > 0:
            page_counts = {}
            for hl in response["highlights"]:
                norm_hl = hl.strip().replace(" ", "").replace("\n", "").replace("\r", "").replace("\t", "").lower()
                for page in pages_text:
                    norm_page_text = page["text"].replace(" ", "").replace("\n", "").replace("\r", "").replace("\t", "").lower()
                    if norm_hl in norm_page_text:
                        p_num = page["page_num"]
                        page_counts[p_num] = page_counts.get(p_num, 0) + 1
            
            if page_counts:
                # Sort by count descending, then by page number ascending
                sorted_pages = sorted(page_counts.items(), key=lambda x: (-x[1], x[0]))
                target_page = sorted_pages[0][0]
                print(f"[CHAT] Determined target_page={target_page} (counts: {page_counts})")

        response["target_page"] = target_page
    else:
        response["target_page"] = None
        
    return response

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

