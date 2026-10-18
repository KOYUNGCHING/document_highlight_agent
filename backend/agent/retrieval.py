"""Small local lexical retriever; no embedding service is required."""
import re


def terms(text):
    text = text.lower()
    words = set(re.findall(r"[a-z0-9]+", text))
    for part in re.findall(r"[\u3400-\u9fff]+", text):
        words.update(part[i:i + 2] for i in range(len(part) - 1))
    return words


def retrieve(blocks, question, budget=24000):
    if sum(len(b["text"]) for b in blocks) <= budget:
        return blocks
    query = terms(question)
    ranked = sorted(range(len(blocks)),
                    key=lambda i: len(query & terms(blocks[i]["text"])), reverse=True)
    selected, used = set(), 0
    for index in ranked:
        if not query & terms(blocks[index]["text"]):
            continue
        # Neighbors preserve table headings and surrounding qualification clauses.
        for candidate in (index, index - 1, index + 1):
            if candidate < 0 or candidate >= len(blocks) or candidate in selected:
                continue
            size = len(blocks[candidate]["text"])
            if used + size <= budget:
                selected.add(candidate)
                used += size
    return [blocks[i] for i in sorted(selected)]


def batches(blocks, budget=16000):
    group, size = [], 0
    for block in blocks:
        if group and size + len(block["text"]) > budget:
            yield group
            group, size = [], 0
        group.append(block)
        size += len(block["text"])
    if group:
        yield group
