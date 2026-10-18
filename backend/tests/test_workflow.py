"""Offline regression tests: real graph, SQLite and API; deterministic fake model."""
import asyncio
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

import fitz
from fastapi.testclient import TestClient
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from agent.graph import build_graph, citation_failures
from agent.retrieval import batches, retrieve
from agent.state import Draft, MemorySummary, Plan, Review
from main import create_app
from services.document_service import DocumentStore
from services.llm_service import LLMService


def pdf_bytes(text="Laser treatment: 3000. Exclusion: experimental procedures."):
    with fitz.open() as doc:
        page = doc.new_page()
        page.insert_text((50, 70), text)
        return doc.tobytes()


class FakeModel:
    def __init__(self, invalid=False, reject=False, summary_fail=False):
        self.calls = []
        self.invalid, self.reject, self.summary_fail = invalid, reject, summary_fail

    async def structured(self, system, data, schema):
        self.calls.append((schema.__name__, data))
        if schema is Plan:
            question = data["question"]
            task = "clarify" if question == "which?" else "document_summary" if "summary" in question or "摘要" in question else "qa"
            return Plan(task=task, resolved_question=question, clarification="Which treatment?")
        if schema is MemorySummary:
            if self.summary_fail:
                raise ValueError("unavailable")
            return MemorySummary(summary="The user asked about laser treatment; verify against the PDF.")
        if schema is Review:
            return Review(supported=not self.reject, feedback=["Unsupported amount"] if self.reject else [])
        if schema is Draft:
            blocks = data.get("evidence", [])
            source = "missing-source" if self.invalid else blocks[0]["block_id"] if blocks else data["partial_summaries"][0]["citation_ids"][0]
            return Draft(answer=f"Laser treatment: 3000 [{source}]", citation_ids=[source], primary_citation_id=source)
        raise AssertionError(schema)


class DocumentTests(unittest.TestCase):
    def test_content_identity_same_filename_and_geometry(self):
        with tempfile.TemporaryDirectory() as root:
            store = DocumentStore(Path(root))
            first = store.save(pdf_bytes(), "../../same.pdf")
            second = store.save(pdf_bytes("Different amount: 9000"), "same.pdf")
            self.assertNotEqual(first["document_id"], second["document_id"])
            self.assertEqual(first["filename"], "same.pdf")
            block = store.blocks(first["document_id"])[0]
            self.assertIn("3000", block["text"])
            self.assertTrue(all(0 <= n <= 1 for n in block["rect"]))
            self.assertEqual(store.current()["document_id"], second["document_id"])
            with self.assertRaises(ValueError):
                store.load("../../secret")

    def test_blank_pdf_rejected_without_changing_current(self):
        with tempfile.TemporaryDirectory() as root:
            store = DocumentStore(Path(root))
            with fitz.open() as doc:
                doc.new_page()
                data = doc.tobytes()
            with self.assertRaises(ValueError):
                store.save(data, "blank.pdf")
            self.assertIsNone(store.current())

    def test_retrieval_and_batch_coverage(self):
        blocks = [{"block_id": str(i), "text": text} for i, text in enumerate(
            ["heading", "laser treatment 3000", "exclusion", "other" * 50])]
        found = retrieve(blocks, "laser", budget=80)
        self.assertEqual([b["block_id"] for b in found], ["0", "1", "2"])
        flattened = [b for group in batches(blocks, budget=50) for b in group]
        self.assertEqual(flattened, blocks)


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.model = FakeModel()
        self.app = create_app(self.temp.name, self.model)
        self.client = TestClient(self.app)
        self.client.__enter__()
        uploaded = self.client.post("/api/upload", files={"file": ("policy.pdf", pdf_bytes(), "application/pdf")})
        self.assertEqual(uploaded.status_code, 200, uploaded.text)
        self.doc = uploaded.json()["document_id"]
        self.thread = str(uuid4())

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.temp.cleanup()

    def payload(self, question="laser amount?", thread=None):
        return {"question": question, "document_id": self.doc, "thread_id": thread or self.thread}

    def test_answer_followup_and_thread_isolation(self):
        result = self.client.post("/api/chat", json=self.payload()).json()
        self.assertEqual(result["status"], "answered")
        self.assertEqual(result["target_page"], 1)
        self.assertEqual(result["citations"][0]["document_id"], self.doc)
        self.client.post("/api/chat", json=self.payload("and exclusions?"))
        plans = [data for schema, data in self.model.calls if schema == "Plan"]
        self.assertEqual(len(plans[-1]["conversation"]["messages"]), 3)
        history = self.client.get(f"/api/threads/{self.thread}", params={"document_id": self.doc}).json()
        self.assertEqual(len(history["messages"]), 4)
        self.client.post("/api/chat", json=self.payload(thread=str(uuid4())))
        plans = [data for schema, data in self.model.calls if schema == "Plan"]
        self.assertEqual(len(plans[-1]["conversation"]["messages"]), 1)

    def test_summary_stream_has_status_and_final_result(self):
        response = self.client.post("/api/chat/stream", json=self.payload("summary whole document"))
        self.assertEqual(response.status_code, 200)
        events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
        self.assertTrue(any(e.get("stage") == "document_summarizing" for e in events))
        self.assertEqual(events[-1]["type"], "result")
        self.assertEqual(events[-1]["status"], "answered")

    def test_invalid_citations_only_one_revision_and_no_unverified_highlight(self):
        self.model.invalid = True
        result = self.client.post("/api/chat", json=self.payload()).json()
        self.assertEqual(result["status"], "unverified")
        self.assertEqual(result["citations"], [])
        drafts = [c for c in self.model.calls if c[0] == "Draft"]
        self.assertEqual(len(drafts), 2)

    def test_semantic_review_failure_blocks_answer(self):
        self.model.reject = True
        result = self.client.post("/api/chat", json=self.payload()).json()
        self.assertEqual(result["status"], "unverified")
        self.assertNotIn("3000", result["answer"])

    def test_clarification_does_not_call_answer_model(self):
        result = self.client.post("/api/chat", json=self.payload("which?")).json()
        self.assertEqual(result["status"], "clarify")
        self.assertFalse(any(c[0] == "Draft" for c in self.model.calls))

    def test_thread_cannot_change_document(self):
        self.client.post("/api/chat", json=self.payload())
        other = self.client.post("/api/upload", files={"file": ("other.pdf", pdf_bytes("Other text"))}).json()
        payload = {**self.payload(), "document_id": other["document_id"]}
        self.assertEqual(self.client.post("/api/chat", json=payload).status_code, 409)

    def test_bad_requests(self):
        self.assertEqual(self.client.post("/api/chat", json=self.payload("   ")).status_code, 422)
        self.assertEqual(self.client.post("/api/upload", files={"file": ("bad.pdf", b"not pdf")}).status_code, 422)
        self.assertEqual(self.client.get("/api/documents/not-an-id/file").status_code, 404)
        file_response = self.client.get(f"/api/documents/{self.doc}/file")
        self.assertTrue(file_response.content.startswith(b"%PDF-"))


class MemoryTests(unittest.IsolatedAsyncioTestCase):
    async def test_persistence_across_restart_and_turn_reset(self):
        with tempfile.TemporaryDirectory() as root:
            store = DocumentStore(Path(root) / "documents")
            doc = store.save(pdf_bytes(), "policy.pdf")
            config = {"configurable": {"thread_id": "persistent"}}
            path = str(Path(root) / "memory.sqlite3")
            async with AsyncSqliteSaver.from_conn_string(path) as saver:
                graph = build_graph(FakeModel(invalid=True), store, saver)
                await graph.ainvoke({"document_id": doc["document_id"], "question": "amount?",
                                     "messages": [HumanMessage(content="amount?")]}, config)
            model = FakeModel()
            async with AsyncSqliteSaver.from_conn_string(path) as saver:
                graph = build_graph(model, store, saver)
                state = await graph.ainvoke({"document_id": doc["document_id"], "question": "followup?",
                                            "messages": [HumanMessage(content="followup?")]}, config)
                self.assertEqual(state["revision_count"], 0)
                self.assertEqual(state["result"]["status"], "answered")
                self.assertEqual(len(state["messages"]), 4)

    async def test_batched_summary_processes_every_source_and_combines(self):
        class Sources:
            def blocks(self, _document_id):
                return [{"document_id": "doc", "block_id": f"p{i + 1}-b0", "page": i + 1,
                         "text": "laser " * 1000, "rect": [0, 0, 1, 1]} for i in range(7)]
        with tempfile.TemporaryDirectory() as root:
            model = FakeModel()
            async with AsyncSqliteSaver.from_conn_string(str(Path(root) / "db")) as saver:
                graph = build_graph(model, Sources(), saver)
                state = await graph.ainvoke({"document_id": "doc", "question": "summary",
                    "messages": [HumanMessage(content="summary")]},
                    {"configurable": {"thread_id": "map"}})
                partial_inputs = [data for schema, data in model.calls
                                  if schema == "Draft" and "evidence" in data]
                ids = [b["block_id"] for data in partial_inputs for b in data["evidence"]]
                self.assertEqual(len(ids), 7)
                self.assertEqual(len(set(ids)), 7)
                self.assertTrue(any("partial_summaries" in data for _, data in model.calls))
                self.assertEqual(state["result"]["status"], "answered")

    async def test_invalid_partial_summary_cannot_become_full_summary(self):
        class Sources:
            def blocks(self, _document_id):
                return [{"document_id": "doc", "block_id": "p1-b0", "page": 1,
                         "text": "laser treatment 3000", "rect": [0, 0, 1, 1]}]
        with tempfile.TemporaryDirectory() as root:
            model = FakeModel(invalid=True)
            async with AsyncSqliteSaver.from_conn_string(str(Path(root) / "db")) as saver:
                graph = build_graph(model, Sources(), saver)
                state = await graph.ainvoke({"document_id": "doc", "question": "summary",
                    "messages": [HumanMessage(content="summary")]},
                    {"configurable": {"thread_id": "bad-map"}})
                self.assertEqual(state["result"]["status"], "insufficient_evidence")
                self.assertEqual(state["result"]["citations"], [])
                self.assertIn("未完成整份", state["result"]["answer"])

    async def test_memory_compression_success_and_failure(self):
        for fails in (False, True):
            with self.subTest(fails=fails), tempfile.TemporaryDirectory() as root:
                store = DocumentStore(Path(root) / "documents")
                doc = store.save(pdf_bytes(), "policy.pdf")
                model = FakeModel(summary_fail=fails)
                with patch.dict(os.environ, {"MEMORY_SUMMARY_TRIGGER_CHARS": "1000", "MEMORY_KEEP_TURNS": "1"}):
                    async with AsyncSqliteSaver.from_conn_string(str(Path(root) / "memory.sqlite3")) as saver:
                        graph = build_graph(model, store, saver)
                        config = {"configurable": {"thread_id": "summary"}}
                        for i in range(4):
                            state = await graph.ainvoke({"document_id": doc["document_id"],
                                "question": f"laser {i}", "messages": [HumanMessage(content="long question " * 100)]}, config)
                        self.assertEqual(bool(state.get("conversation_summary")), not fails)
                        if fails:
                            self.assertEqual(len(state["messages"]), 8)
                        else:
                            self.assertLess(len(state["messages"]), 8)
                            self.assertEqual(state["messages"][-2].type, "human")


class ProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_invalid_json_retries_then_validates(self):
        service = LLMService()
        outputs = iter(['{"answer": 123}', '{"answer":"ok","status":"insufficient_evidence"}'])
        async def invoke(_messages):
            return next(outputs)
        service._invoke = invoke
        result = await service.structured("prompt", {}, Draft)
        self.assertEqual(result.answer, "ok")

    async def test_invalid_json_exhausts_bounded_retry(self):
        service = LLMService()
        count = 0
        async def invoke(_messages):
            nonlocal count
            count += 1
            return 'not json'
        service._invoke = invoke
        with self.assertRaises(ValueError):
            await service.structured("prompt", {}, Draft)
        self.assertEqual(count, 2)


if __name__ == "__main__":
    unittest.main()
