// SSE frames may span network reads; preserve both partial UTF-8 and partial frames.
export async function readEvents(response, onEvent) {
    if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(typeof body.detail === 'string' ? body.detail : '請求失敗，請稍後重試。');
    }
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let receivedResult = false;
    const dispatch = frame => {
        const data = frame.split('\n').filter(line => line.startsWith('data:'))
            .map(line => line.slice(5).trimStart()).join('\n');
        if (!data) return;
        const event = JSON.parse(data);
        if (event.type === 'error') throw new Error(event.message);
        if (event.type === 'result') receivedResult = true;
        onEvent(event);
    };
    try {
        while (true) {
            const { done, value } = await reader.read();
            buffer += decoder.decode(value, { stream: !done });
            let boundary;
            while ((boundary = buffer.search(/\r?\n\r?\n/)) !== -1) {
                const separator = buffer.slice(boundary).match(/^\r?\n\r?\n/)[0];
                dispatch(buffer.slice(0, boundary).replace(/\r\n/g, '\n'));
                buffer = buffer.slice(boundary + separator.length);
            }
            if (done) break;
        }
        if (buffer.trim()) dispatch(buffer);
        if (!receivedResult) throw new Error('連線中斷，未取得完整回答。');
    } finally {
        await reader.cancel().catch(() => {});
        reader.releaseLock();
    }
}
