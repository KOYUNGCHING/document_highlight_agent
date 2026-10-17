import os
import json
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel
import requests

class ChatResponse(BaseModel):
    answer: str
    highlights: list[str]

class LLMService:
    def __init__(self):
        self.provider = os.getenv("LLM_PROVIDER", "gemini").lower()
        self.gemini_api_key = os.getenv("GEMINI_API_KEY")
        self.gemma_api_url = os.getenv("GEMMA_API_URL")
        self.gemma_api_key = os.getenv("GEMMA_API_KEY")
        
        if self.provider == "gemini":
            # Using Gemini 2.5 flash or 1.5 flash depending on availability
            self.llm = ChatGoogleGenerativeAI(
                model="gemini-2.5-flash", 
                google_api_key=self.gemini_api_key,
                temperature=0.2,
                model_kwargs={"response_mime_type": "application/json"} # Force clean JSON mode
            )

    def generate_response(self, question: str, context: str) -> dict:
        """Generates an answer based on the provided context."""
        
        system_prompt = """你是一個專業的 PDF 文件問答助理。
請根據以下提供的「參考內容」來回答使用者的「問題」。
如果「參考內容」中找不到相關資訊，請直接回答：「文件無相關內容」，不要自行捏造答案。

此外，為了能在前端 PDF 畫面上將參考來源反白高光 (Highlight) 並定位，請你務必在回答時，同時回傳你參考的「原文精確文字片段」陣列 (highlights)。

請務必嚴格遵守以下 "highlights" 的規則：
1. ⚠️【對應解答區域之一致性與精確定位（單一核心錨點原則）】：
   - 在選取 highlights 片段之前，請先判定該問題的核心解答究竟是「條款條文」還是「表格項目」。
   - **表格項目優先原則**：當使用者詢問關於「特定手術項目/處置項目」的給付資格、是否給付、金額、倍數或計算公式時，你回傳的 highlights **有且僅能包含該手術/處置項目在表格中所在的行原文**（例如 `「22 氬氣雷射治療 3,000」`），**絕對禁止**同時高亮說明給付公式或保險金給付限制的通用條款（例如：「第十條 手術醫療保險金之給付」或「本公司依『投保單位』乘以『每單位手術給付金額表』...」）。
   - 請根據不同類型選擇最合適的第一個高亮元素作為定位的「主力錨點」：
     * 【條文類問答（如除外責任）】：請務必在 highlights 陣列的第一個元素，放入該條款的**標題或條號原文**（例如 `「第十三條 除外責任」`），以讓前端精準滾動到該條款開頭。
     * 【表格項目類問答（如雷射手術給付）】：請**絕對不要**放入通用的表格大標題，並且**絕對不要**包含任何通用保險金計算公式、定義或給付限制條款；你必須直接且唯一將該**特定項目所在的整行完整原文（包含編號、名稱與金額）**作為第一個元素（例如 `「22 氬氣雷射治療 3,000」`），以精準定位到該項目所在的具體頁面。
   - 你回傳的所有 highlights 片段，**必須全部來自於該「核心解答來源段落」或表格項目的範圍內**。
   - ❌【絕對禁止跨條款、跨段落抽取無關但相似的句子，或將「公式條款」與「表格項目」混合】：例如，使用者問除外責任，解答若是第十三條，就絕對不要從第十條或第十一條的尾端抽取類似的通用句子。若是詢問某個項目的給付金額或倍數，請只高亮表格中對應項目的那一行，絕對不要同時高亮第四條或第十條的任何公式說明條款。
2. 陣列中的每個元素必須是「參考內容」中**連續且完全一致**的字串。字元、標點符號、空格必須與原文完全一模一樣，不要有任何改寫、總結或錯別字。
3. ⚠️【禁止回傳過短或常見的單詞與數字】：絕對禁止單獨回傳像是 ["5,000"]、["10"]、["元"]、["本公司"] 等極短或在文件中反覆出現數十次的普通詞彙。這樣會導致前端在整份文件數十處重複標記而失去定位意義！
4. ⚠️【必須包含足夠上下文以維持唯一性】：如果給付金額是 5,000 元，請將項目名稱與金額一併作為連續字串回傳，例如回傳 ["雷射後囊切開術：5,000元"] 或 ["雷射後囊切開術 5,000"]，絕對不要單獨回傳 ["5,000"]。
5. ⚠️【長度限制】：每個高亮片段長度必須在 6 個字以上，50 個字以下，確保其在文件中是唯一的或具備高度特異性。
6. 每次回傳的 highlights 陣列，應該包含 1 到 4 個最關鍵的原文參考連續片段。

你必須以指定的 JSON 格式回傳，不得輸出任何 JSON 以外的解釋性文字。
JSON 格式必須包含兩個鍵：
1. "answer": 你的中文文字回答。
2. "highlights": 符合上述規則的原文精確連續文字片段陣列 (List of strings)。如果無參考，則回傳空陣列 []。

範例回傳:
{
  "answer": "根據條款，皮肌移位手術的給付金額為 30,000 元。",
  "highlights": ["皮肌移位手術的給付金額為 30,000 元"]
}
"""
        
        human_prompt = f"參考內容:\n{context}\n\n使用者的問題:\n{question}"

        if self.provider == "gemini":
            return self._call_gemini(system_prompt, human_prompt)
        elif self.provider == "gemma":
            return self._call_gemma(system_prompt, human_prompt)
        else:
            raise ValueError(f"Unknown LLM provider: {self.provider}")

    def _call_gemini(self, system_prompt: str, human_prompt: str) -> dict:
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=human_prompt)
        ]
        response = self.llm.invoke(messages)
        # Parse JSON from response
        try:
            # Sometime Gemini returns markdown code blocks, let's clean it up
            content = response.content.replace('```json', '').replace('```', '').strip()
            return json.loads(content)
        except json.JSONDecodeError:
            print(f"Failed to parse JSON from Gemini: {response.content}")
            return {"answer": "解析模型回答失敗。原始回答：" + response.content, "highlights": []}

    def _call_gemma(self, system_prompt: str, human_prompt: str) -> dict:
        """Call internal Gemma4 via standard OpenAI REST API format."""
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.gemma_api_key}"
        }
        payload = {
            "model": "gemma", # Adjust model name if needed
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": human_prompt}
            ],
            "temperature": 0.2,
            "response_format": {"type": "json_object"}
        }
        
        response = requests.post(self.gemma_api_url, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()
        
        try:
            content = data['choices'][0]['message']['content']
            return json.loads(content)
        except Exception as e:
            print(f"Failed to parse JSON from Gemma: {e}")
            return {"answer": "解析模型回答失敗。", "highlights": []}
