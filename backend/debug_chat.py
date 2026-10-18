"""Exercise the same HTTP workflow as the browser; run the API first."""
import json
from uuid import uuid4
import httpx


def main():
    with httpx.Client(base_url="http://localhost:8000", timeout=600) as client:
        current = client.get("/api/current-file").raise_for_status().json()
        if not current.get("document_id"):
            print("Upload a PDF in the browser first.")
            return
        thread_id = str(uuid4())
        print(f"Document: {current['filename']}\nThread: {thread_id}")
        while True:
            question = input("Question (q to quit): ").strip()
            if question.lower() == "q":
                break
            if not question:
                continue
            with client.stream("POST", "/api/chat/stream", json={"question": question,
                               "thread_id": thread_id, "document_id": current["document_id"]}) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if line.startswith("data: "):
                        item = json.loads(line[6:])
                        print(item.get("label") or item.get("answer") or item.get("message"))


if __name__ == "__main__":
    main()
