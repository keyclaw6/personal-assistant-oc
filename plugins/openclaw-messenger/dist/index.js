import { defineChannelPluginEntry } from "openclaw/plugin-sdk/channel-core";
import { messengerPlugin } from "./src/channel.js";
import { resolveAccountFromEnv } from "./src/accounts.js";
import { validateSignature } from "./src/signature.js";
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
                    const chunks = [];
                    for await (const chunk of req)
                        chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk));
                    const body = Buffer.concat(chunks).toString("utf-8");
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
                    res.writeHead(200);
                    res.end("OK");
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
                                await api.runtime?.channel?.dispatch?.({
                                    channel: "messenger",
                                    from: `messenger:${senderId}`,
                                    body: text,
                                    timestamp: event.timestamp,
                                    messageId: event.message?.mid,
                                });
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
