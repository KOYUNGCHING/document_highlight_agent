"""Local PDF agent API: persistent threads, validated documents and SSE progress."""
import asyncio
from contextlib import asynccontextmanager
import json
import logging
import os
from pathlib import Path
from uuid import UUID

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from pydantic import BaseModel, Field

from agent.graph import build_graph
from services.document_service import DocumentStore
from services.llm_service import LLMService

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")
logger = logging.getLogger(__name__)


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000, pattern=r"\S")
    document_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    thread_id: UUID


def create_app(data_dir=None, llm=None):
    data = Path(data_dir) if data_dir else ROOT / "data"
    documents = DocumentStore(data / "documents")

    @asynccontextmanager
    async def lifespan(app):
        async with AsyncSqliteSaver.from_conn_string(str(data / "checkpoints.sqlite3")) as saver:
            await saver.setup()
            app.state.graph = build_graph(llm or LLMService(), documents, saver)
            app.state.active_threads = set()
            yield

    app = FastAPI(title="PDF Insight Agent", lifespan=lifespan)
    app.add_middleware(CORSMiddleware,
        allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(","),
        allow_methods=["GET", "POST"], allow_headers=["Content-Type"])

    def load_document(document_id):
        try:
            return documents.load(document_id)
        except (FileNotFoundError, ValueError):
            raise HTTPException(404, "找不到文件，請重新上傳。") from None

    def public_document(document):
        return {"document_id": document["document_id"], "filename": document["filename"],
                "url": f"/api/documents/{document['document_id']}/file",
                "pages": len(document["pages"])}

    @app.post("/api/upload")
    async def upload_pdf(file: UploadFile = File(...)):
        try:
            content = await file.read(25 * 1024 * 1024 + 1)
            if len(content) > 25 * 1024 * 1024:
                raise HTTPException(413, "PDF 上限為 25 MB。")
            document = await asyncio.to_thread(documents.save, content, file.filename or "document.pdf")
            return public_document(document)
        except HTTPException:
            raise
        except Exception as exc:
            logger.warning("PDF extraction failed: %s", type(exc).__name__)
            raise HTTPException(422, "無法讀取 PDF，請確認文件有效、未加密且包含文字。") from None
        finally:
            await file.close()

    @app.get("/api/current-file")
    async def current_file():
        document = await asyncio.to_thread(documents.current)
        return public_document(document) if document else {"document_id": None, "filename": None, "url": None}

    @app.get("/api/documents/{document_id}/file")
    async def document_file(document_id: str):
        document = load_document(document_id)
        return FileResponse(documents._path(document_id, ".pdf"), media_type="application/pdf",
                            filename=document["filename"], content_disposition_type="inline")

    async def acquire(payload):
        load_document(payload.document_id)
        # The same thread cannot run two turns concurrently or change document.
        key = str(payload.thread_id)
        if key in app.state.active_threads:
            raise HTTPException(409, "這個聊天仍在處理上一個問題。")
        app.state.active_threads.add(key)
        try:
            config = {"configurable": {"thread_id": key}, "recursion_limit": 24}
            snapshot = await app.state.graph.aget_state(config)
            previous = snapshot.values.get("document_id")
            if previous and previous != payload.document_id:
                raise HTTPException(409, "文件已變更，請開啟新的聊天。")
            return key, config
        except BaseException:
            app.state.active_threads.discard(key)
            raise

    def graph_input(payload):
        return {"question": payload.question, "document_id": payload.document_id,
                "messages": [HumanMessage(content=payload.question)]}

    @app.post("/api/chat")
    async def chat(payload: ChatRequest):
        key, config = await acquire(payload)
        try:
            state = await app.state.graph.ainvoke(graph_input(payload), config)
            return {**state["result"], "thread_id": key}
        except Exception as exc:
            logger.warning("Agent failed: %s", type(exc).__name__)
            raise HTTPException(502, "模型服務未完成，請稍後重試。") from None
        finally:
            app.state.active_threads.discard(key)

    def event(data):
        return "data: " + json.dumps(data, ensure_ascii=False) + "\n\n"

    @app.post("/api/chat/stream")
    async def chat_stream(payload: ChatRequest, request: Request):
        key, config = await acquire(payload)

        async def generate():
            try:
                async for mode, chunk in app.state.graph.astream(
                    graph_input(payload), config, stream_mode=["custom", "updates"]):
                    if await request.is_disconnected():
                        return
                    if mode == "custom":
                        yield event(chunk)
                    elif "finalize" in chunk:
                        yield event({"type": "result", **chunk["finalize"]["result"], "thread_id": key})
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("Agent stream failed: %s", type(exc).__name__)
                yield event({"type": "error", "message": "模型服務未完成，請稍後重試。"})
            finally:
                app.state.active_threads.discard(key)

        return StreamingResponse(generate(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @app.get("/api/threads/{thread_id}")
    async def thread_history(thread_id: UUID, document_id: str):
        load_document(document_id)
        snapshot = await app.state.graph.aget_state({"configurable": {"thread_id": str(thread_id)}})
        state = snapshot.values
        if state.get("document_id") and state["document_id"] != document_id:
            raise HTTPException(409, "此聊天屬於其他文件。")
        return {"messages": [{"sender": "user" if m.type == "human" else "ai", "text": m.content}
                             for m in state.get("messages", []) if m.type in {"human", "ai"}],
                "has_summary": bool(state.get("conversation_summary")),
                "result": state.get("result") or None}

    return app


app = create_app()
