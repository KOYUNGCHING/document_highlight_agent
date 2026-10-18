import assert from 'node:assert/strict';
import test from 'node:test';
import { readEvents } from './stream.js';

function responseFrom(text, chunkSize = 1) {
    const bytes = new TextEncoder().encode(text);
    return new Response(new ReadableStream({ start(controller) {
        for (let i = 0; i < bytes.length; i += chunkSize) controller.enqueue(bytes.slice(i, i + chunkSize));
        controller.close();
    } }));
}

test('preserves fragmented UTF-8 and SSE frames', async () => {
    const events = [];
    await readEvents(responseFrom('data: {"type":"status","label":"檢索完成"}\n\ndata: {"type":"result","answer":"三千元"}\n\n'), e => events.push(e));
    assert.equal(events[0].label, '檢索完成');
    assert.equal(events[1].answer, '三千元');
});

test('rejects a stream ending without a result', async () => {
    await assert.rejects(readEvents(responseFrom('data: {"type":"status"}\n\n'), () => {}), /未取得完整回答/);
});

test('surfaces server error events', async () => {
    await assert.rejects(readEvents(responseFrom('data: {"type":"error","message":"模型未完成"}\n\n'), () => {}), /模型未完成/);
});

test('supports CRLF boundaries split across reads', async () => {
    const events = [];
    await readEvents(responseFrom('data: {"type":"status"}\r\n\r\ndata: {"type":"result"}\r\n\r\n'), e => events.push(e));
    assert.equal(events.length, 2);
});
