import { defineChannelPluginEntry } from "openclaw/plugin-sdk/channel-core";
import { dispatchInboundMessageWithDispatcher } from "openclaw/plugin-sdk/reply-runtime";
import { messengerPlugin } from "./src/channel.js";
import { DEFAULT_ACCOUNT_ID, resolveAccountFromEnv } from "./src/accounts.js";
import { validateSignature } from "./src/signature.js";
import { sendText } from "./src/send.js";
function elapsed(start) {
    return Date.now() - start;
}
const plugin = defineChannelPluginEntry({
    id: "messenger",
    name: "Messenger",
    description: "Facebook Messenger channel plugin via Meta Graph API",
    plugin: messengerPlugin,
    registerFull(api) {
        const cfg = api.config ?? { channels: {} };
        const account = resolveAccountFromEnv(cfg);
        const webhookPath = cfg.channels?.messenger?.webhookPath ?? "/messenger/webhook";
        api.registerHttpRoute({
            path: webhookPath,
            auth: "plugin",
            handler: async (req, res) => {
                if (req.method === "GET") {
                    const url = new URL(req.url ?? "/", `http://${req.headers.host ?? "localhost"}`);
                    const mode = url.searchParams.get("hub.mode") ?? "";
                    const token = url.searchParams.get("hub.verify_token") ?? "";
                    const challenge = url.searchParams.get("hub.challenge") ?? "";
                    if (mode === "subscribe" && token === account.verifyToken) {
                        res.writeHead(200);
                        res.end(challenge);
                    }
                    else {
                        res.writeHead(403);
                        res.end("Forbidden");
                    }
                    return true;
                }
                if (req.method === "POST") {
                    const requestStartedAt = Date.now();
                    const chunks = [];
                    for await (const chunk of req)
                        chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk));
                    const body = Buffer.concat(chunks).toString("utf-8");
                    api.logger?.info?.(`messenger timing: body read ${elapsed(requestStartedAt)}ms bytes=${body.length}`);
                    const sig = req.headers["x-hub-signature-256"];
                    if (account.appSecret && sig && !validateSignature(body, sig, account.appSecret)) {
                        res.writeHead(403);
                        res.end("Invalid signature");
                        return true;
                    }
                    let parsed;
                    try {
                        parsed = JSON.parse(body);
                    }
                    catch {
                        res.writeHead(400);
                        res.end("Bad JSON");
                        return true;
                    }
                    if (parsed.object !== "page") {
                        res.writeHead(400);
                        res.end("Not a page webhook");
                        return true;
                    }
                    api.logger?.info?.(`messenger webhook received: entries=${parsed.entry?.length ?? 0}`);
                    api.logger?.info?.(`messenger timing: parsed+validated ${elapsed(requestStartedAt)}ms entries=${parsed.entry?.length ?? 0}`);
                    res.writeHead(200);
                    res.end("OK");
                    api.logger?.info?.(`messenger timing: ack sent ${elapsed(requestStartedAt)}ms`);
                    for (const entry of parsed.entry ?? []) {
                        for (const event of entry.messaging ?? []) {
                            if (event.message?.is_echo)
                                continue;
                            if (!event.message && !event.postback)
                                continue;
                            const senderId = event.sender?.id;
                            if (!senderId)
                                continue;
                            const text = event.message?.text ?? event.postback?.title ?? "";
                            if (!text)
                                continue;
                            try {
                                const from = `messenger:${senderId}`;
                                const dispatchStartedAt = Date.now();
                                api.logger?.info?.(`messenger timing: dispatch start +${elapsed(requestStartedAt)}ms sender=${senderId}`);
                                await dispatchInboundMessageWithDispatcher({
                                    cfg,
                                    ctx: {
                                        Body: text,
                                        BodyForAgent: text,
                                        RawBody: text,
                                        CommandBody: text.trim(),
                                        BodyForCommands: text.trim(),
                                        From: from,
                                        To: from,
                                        SessionKey: `messenger:dm:${senderId}`,
                                        AccountId: DEFAULT_ACCOUNT_ID,
                                        ChatType: "direct",
                                        ConversationLabel: `Messenger ${senderId}`,
                                        SenderId: senderId,
                                        Provider: "messenger",
                                        Surface: "messenger",
                                        MessageSid: event.message?.mid,
                                        Timestamp: event.timestamp,
                                        OriginatingChannel: "messenger",
                                        OriginatingTo: from,
                                        NativeChannelId: senderId,
                                        CommandAuthorized: true,
                                    },
                                    dispatcherOptions: {
                                        deliver: async (payload) => {
                                            const replyText = payload?.text?.trim?.() ?? "";
                                            if (!replyText)
                                                return;
                                            const sendStartedAt = Date.now();
                                            api.logger?.info?.(`messenger timing: sendText start +${elapsed(requestStartedAt)}ms dispatch=${elapsed(dispatchStartedAt)}ms chars=${replyText.length}`);
                                            await sendText(from, replyText, account);
                                            api.logger?.info?.(`messenger timing: sendText end +${elapsed(requestStartedAt)}ms send=${elapsed(sendStartedAt)}ms dispatch=${elapsed(dispatchStartedAt)}ms`);
                                        },
                                        onError: (err) => {
                                            api.logger?.error?.(`messenger reply delivery error: ${String(err)}`);
                                        },
                                    },
                                });
                                api.logger?.info?.(`messenger timing: dispatch end +${elapsed(requestStartedAt)}ms dispatch=${elapsed(dispatchStartedAt)}ms`);
                                api.logger?.info?.(`messenger message dispatched from ${senderId}`);
                            }
                            catch (err) {
                                api.logger?.error?.(`messenger dispatch error: ${String(err)}`);
                            }
                        }
                    }
                    return true;
                }
                return false;
            },
        });
    },
});
export default plugin;
