import os
import sys
import json
from dotenv import load_dotenv

# Ensure stdout uses UTF-8 to display Chinese characters properly
sys.stdout.reconfigure(encoding='utf-8')

# Load backend environment variables
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(dotenv_path=os.path.join(BACKEND_DIR, ".env"))

# Import services
from services.pdf_service import PDFService
from services.llm_service import LLMService

def main():
    print("=" * 60)
    print("🤖 PDF 智慧搜尋問答 & Highlight 終端機偵錯工具 🤖")
    print("=" * 60)
    
    # 1. Check active file
    state_path = os.path.join(BACKEND_DIR, "uploads", "state.json")
    if not os.path.exists(state_path):
        print("❌ 找不到活動檔案狀態。請先在前端上傳一個 PDF 檔案。")
        return
        
    try:
        with open(state_path, "r", encoding="utf-8") as f:
            state = json.load(f)
            active_file = state.get("active_file")
    except Exception as e:
        print(f"❌ 讀取 state.json 失敗: {e}")
        return
        
    if not active_file:
        print("❌ 目前沒有設定任何活動的 PDF 檔案。")
        return
        
    print(f"📄 當前載入的文件: {active_file}")
    
    # 2. Load text cache
    cache_path = os.path.join(BACKEND_DIR, "uploads", active_file + ".json")
    if not os.path.exists(cache_path):
        print(f"❌ 找不到該檔案的文字快取 ({cache_path})，請先重新上傳。")
        return
        
    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            pages_text = json.load(f)
    except Exception as e:
        print(f"❌ 載入快取失敗: {e}")
        return
        
    print(f"📦 已載入快取文字。總頁數: {len(pages_text)} 頁。")
    print("-" * 60)
    
    # Initialize LLM
    print("⚙️ 正在初始化 Gemini LLM 服務...")
    try:
        llm_service = LLMService()
    except Exception as e:
        print(f"❌ 初始化 LLM 失敗 (請確認 GEMINI_API_KEY 設定): {e}")
        return
    print("✅ LLM 服務就緒！")
    print("=" * 60)
    
    # Helper function to check loose match (similar to frontend)
    def normalize_string(str_val):
        return str_val.replace(" ", "").replace("\n", "").replace("\r", "").replace("\t", "").lower()
        
    # Build context
    context_texts = []
    for page in pages_text:
        context_texts.append(f"[Page {page['page_num']}]\n{page['text']}")
    context = "\n\n".join(context_texts)
    
    while True:
        try:
            print("\n" + "?" * 10 + " 請輸入您的問答問題 (輸入 'q' 結束) " + "?" * 10)
            question = input("問題: ").strip()
            
            if not question:
                continue
            if question.lower() == 'q':
                print("👋 偵錯結束！")
                break
                
            print("\n⌛ 正在向 Gemini 提問，請稍候...")
            res = llm_service.generate_response(question, context)
            
            answer = res.get("answer", "無回答欄位")
            raw_highlights = res.get("highlights", [])
            
            # Local copy of filter_highlights for printing debug info
            def filter_highlights_local(highlights_list, pages):
                valid = []
                def normalize(s):
                    return s.replace(" ", "").replace("\n", "").replace("\r", "").replace("\t", "").lower()
                for hl in highlights_list:
                    cleaned = hl.strip()
                    if len(cleaned) < 4:
                        print(f"   ⚠️ [過濾過短] 捨棄 \"{hl}\" (< 4 字)")
                        continue
                    norm_hl = normalize(cleaned)
                    matched_pages = []
                    for page in pages:
                        norm_page_text = normalize(page["text"])
                        if norm_hl in norm_page_text:
                            matched_pages.append(page["page_num"])
                    if len(matched_pages) > 2:
                        print(f"   ⚠️ [過濾過於普遍] 捨棄 \"{hl}\" (匹配多達 {len(matched_pages)} 頁: {matched_pages})")
                        continue
                    elif len(matched_pages) == 0:
                        print(f"   ⚠️ [過濾找不到] 捨棄 \"{hl}\" (在原文中不存在)")
                        continue
                    valid.append(hl)
                return valid

            highlights = filter_highlights_local(raw_highlights, pages_text)
            
            print("\n" + "=" * 20 + " AI 回答內容 " + "=" * 20)
            print(answer)
            print("=" * 53)
            
            # Process sub-phrases exactly like the frontend to verify matches
            sub_phrases = []
            import re
            for hl in highlights:
                # Split by newlines, periods, semicolons, colons, commas
                parts = re.split(r'[\n\r。；：，]', hl)
                for part in parts:
                    # Strip list numbering prefixes like "一、", "1."
                    cleaned = re.sub(r'^([一二三四五六七八九十百]+[、.．])|^(\d+[、.．])', '', part.strip()).strip()
                    if len(cleaned) >= 4:
                        sub_phrases.append(cleaned)
            
            unique_sub_phrases = list(set(sub_phrases))
            
            print("\n🎯 最終採用的原文標記片段 (Highlights):")
            if not unique_sub_phrases:
                print("   (無有效標記片段)")
            else:
                for idx, phrase_text in enumerate(unique_sub_phrases):
                    print(f"   [{idx + 1}] \"{phrase_text}\"")
                    
                    norm_hl = normalize_string(phrase_text)
                    for page in pages_text:
                        page_text = page["text"]
                        norm_page_text = normalize_string(page_text)
                        
                        if norm_hl in norm_page_text:
                            if phrase_text in page_text:
                                print(f"       ✅ 在第 {page['page_num']} 頁: 完全精確匹配")
                            else:
                                print(f"       ✅ 在第 {page['page_num']} 頁: 空白/換行標點容錯匹配")
            
        except KeyboardInterrupt:
            print("\n👋 偵錯結束！")
            break
        except Exception as e:
            print(f"\n❌ 問答出錯: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    main()
