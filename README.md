# PDF 智慧搜尋與高光定位系統 - 專案交接與部署說明 (README.md)

## 1. 開發環境與版本需求

接收專案的同仁在啟動前，請先確認本地端安裝了以下環境：

* **Python 版本**：建議 **Python 3.10 或 3.11** (必須高於 3.10，以支援最新的型態註解與套件相容性)。
* **Node.js 版本**：建議 **Node.js 18.x 或 20.x (LTS)**，並自帶 **npm 9.x+**。

---

## 2. 安裝與啟動步驟

交接同仁取得專案壓縮檔並解壓縮後，請依照以下步驟啟動服務：

### 第一步：設定後端 (FastAPI)

1. **開啟終端機並進入後端目錄**：
   ```bash
   cd backend
   ```

2. **建立 Python 虛擬環境**：
   ```bash
   python -m venv venv
   ```

3. **啟動虛擬環境**：
   * **Windows (PowerShell)**:
     ```powershell
     .\venv\Scripts\Activate.ps1
     ```
   * **Windows (CMD)**:
     ```cmd
     .\venv\Scripts\activate.bat
     ```
   * **macOS / Linux**:
     ```bash
     source venv/bin/activate
     ```

4. **安裝後端套件**：
   ```bash
   pip install -r requirements.txt
   ```

5. **設定 `.env` 環境變數**：
   請確認 `backend/.env` 檔案存在，並且填寫了有效的 **Gemini API Key**：
   ```env
   LLM_PROVIDER=gemini
   GEMINI_API_KEY=您的_GEMINI_API_KEY
   ```

6. **啟動後端服務**：
   ```bash
   uvicorn main:app --reload
   ```
   * 啟動成功後，後端服務會運行在 `http://127.0.0.1:8000`。
   * 您可以開啟 `http://127.0.0.1:8000/docs` 查看 API 互動式文件。

---

### 第二步：設定前端 (React + Vite)

1. **開啟另一個終端機視窗並進入前端目錄**：
   ```bash
   cd frontend
   ```

2. **安裝前端相依套件**：
   ```bash
   npm install
   ```

3. **啟動前端開發伺服器**：
   ```bash
   npm run dev
   ```
   * 啟動成功後，終端機會顯示本地連結，通常為 `http://localhost:5173/`。
   * 在瀏覽器中打開該網址即可開始使用系統。

---

## 3. 開發輔助偵錯工具

後端提供了兩個測試指令碼，方便同仁在修改程式碼時進行快速驗證：

1. **測試 API 金鑰與連線** (`test_models.py`)：
   在後端虛擬環境下執行此檔案，可確認 `GEMINI_API_KEY` 是否有效，並列出可用的 Gemini 模型：
   ```bash
   python test_models.py
   ```
2. **終端機問答與高亮比對偵錯** (`debug_chat.py`)：
   如果不希望每次都透過瀏覽器介面測試，可以直接在後端虛擬環境下運行此腳本。它能模擬前端的長句拆分與匹配邏輯，並直接在命令列中顯示 Gemini 的問答結果、高亮片段以及在 PDF 中的頁碼定位：
   ```bash
   python debug_chat.py
   ```

---

## 4. 注意事項 (Precautions)

**定位漂移與高亮異常**：
   本系統已實現了 PDF 透明文字層的「葉子節點 Span 篩選」及「非同步佈局延遲定位」技術（詳見 [SPEC.md]），若同仁日後修改了前端 React PDF 套件或 CSS 定位，請特別注意是否破壞了雙層渲染層級 (`z-index`)，否則可能導致高亮標記在畫面上完全隱形或滾動位置偏差。
