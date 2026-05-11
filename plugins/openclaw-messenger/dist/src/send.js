import { GRAPH_API_BASE, TEXT_CHUNK_LIMIT } from "./accounts.js";
export function chunkText(text, limit) {
    if (text.length <= limit)
        return [text];
    const chunks = [];
    let remaining = text;
    while (remaining.length > 0) {
        if (remaining.length <= limit) {
            chunks.push(remaining);
            break;
        }
        let brk = limit;
        const nl = remaining.lastIndexOf("\n", limit);
        if (nl > limit * 0.5)
            brk = nl + 1;
        chunks.push(remaining.slice(0, brk));
        remaining = remaining.slice(brk);
    }
    return chunks;
}
export async function graphApiSend(token, body) {
    const res = await fetch(`${GRAPH_API_BASE}/me/messages`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify(body),
    });
    if (!res.ok) {
        const t = await res.text().catch(() => "");
        throw new Error(`Messenger API ${res.status}: ${t.slice(0, 500)}`);
    }
    return res.json();
}
export async function sendText(to, text, account) {
    const chatId = to.replace(/^messenger:/i, "");
    const chunks = chunkText(text, TEXT_CHUNK_LIMIT);
    let lastId = "sent";
    for (const chunk of chunks) {
        const r = await graphApiSend(account.pageAccessToken, {
            recipient: { id: chatId },
            messaging_type: "RESPONSE",
            message: { text: chunk },
        });
        lastId = r.message_id ?? lastId;
    }
    return lastId;
}
export async function sendMedia(to, mediaUrl, account, type = "image") {
    const chatId = to.replace(/^messenger:/i, "");
    const r = await graphApiSend(account.pageAccessToken, {
        recipient: { id: chatId },
        messaging_type: "RESPONSE",
        message: { attachment: { type, payload: { url: mediaUrl, is_reusable: true } } },
    });
    return r.message_id ?? "media";
}
export async function sendSenderAction(to, action, account) {
    const chatId = to.replace(/^messenger:/i, "");
    try {
        await fetch(`${GRAPH_API_BASE}/me/messages`, {
            method: "POST",
            headers: { "Content-Type": "application/json", Authorization: `Bearer ${account.pageAccessToken}` },
            body: JSON.stringify({ recipient: { id: chatId }, sender_action: action }),
        });
    }
    catch { /* non-fatal */ }
}
