import { defineChannelPluginEntry } from "openclaw/plugin-sdk/channel-core";
import { dispatchInboundMessageWithDispatcher } from "openclaw/plugin-sdk/reply-runtime";
import { messengerPlugin } from "./src/channel.js";
import { DEFAULT_ACCOUNT_ID, resolveAccountFromEnv } from "./src/accounts.js";
import { validateSignature } from "./src/signature.js";
import { normalizeMessengerInbound } from "./src/inbound.js";
import { downloadMessengerMedia } from "./src/media-download.js";
import { sendMedia, sendText } from "./src/send.js";

function elapsed(start: number): number {
  return Date.now() - start;
}

function outboundMediaUrls(payload: any): string[] {
  const urls: string[] = [];
  if (typeof payload?.mediaUrl === "string" && payload.mediaUrl) urls.push(payload.mediaUrl);
  if (Array.isArray(payload?.mediaUrls)) {
    for (const url of payload.mediaUrls) {
      if (typeof url === "string" && url) urls.push(url);
    }
  }
  return urls;
}

function messengerSendMediaType(mediaType?: string): string {
  const normalized = (mediaType ?? "").toLowerCase();
  if (!normalized) return "image";
  if (normalized.startsWith("image/") || normalized === "image") return "image";
  if (normalized.startsWith("video/") || normalized === "video") return "video";
  if (normalized.startsWith("audio/") || normalized === "audio") return "audio";
  return "file";
}

function mediaMaxBytes(cfg: any): number {
  const mediaMaxMb = Number(cfg.channels?.messenger?.mediaMaxMb ?? 25);
  return (Number.isFinite(mediaMaxMb) && mediaMaxMb > 0 ? mediaMaxMb : 25) * 1024 * 1024;
}

const plugin: any = defineChannelPluginEntry({
  id: "messenger",
  name: "Messenger",
  description: "Facebook Messenger channel plugin via Meta Graph API",
  plugin: messengerPlugin,
  registerFull(api: any) {
    const cfg = api.config ?? { channels: {} };
    const account = resolveAccountFromEnv(cfg);
    const webhookPath = (cfg.channels?.messenger?.webhookPath as string) ?? "/messenger/webhook";

    api.registerHttpRoute({
      path: webhookPath,
      auth: "plugin",
      handler: async (req: any, res: any) => {
        if (req.method === "GET") {
          const url = new URL(req.url ?? "/", `http://${req.headers.host ?? "localhost"}`);
          const mode = url.searchParams.get("hub.mode") ?? "";
          const token = url.searchParams.get("hub.verify_token") ?? "";
          const challenge = url.searchParams.get("hub.challenge") ?? "";
          if (mode === "subscribe" && token === account.verifyToken) {
            res.writeHead(200);
            res.end(challenge);
          } else {
            res.writeHead(403);
            res.end("Forbidden");
          }
          return true;
        }

        if (req.method === "POST") {
          const requestStartedAt = Date.now();
          const chunks: Buffer[] = [];
          for await (const chunk of req) chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk));
          const body = Buffer.concat(chunks).toString("utf-8");
          api.logger?.info?.(`messenger timing: body read ${elapsed(requestStartedAt)}ms bytes=${body.length}`);

          const sig = req.headers["x-hub-signature-256"] as string | undefined;
          if (account.appSecret && sig && !validateSignature(body, sig, account.appSecret)) {
            res.writeHead(403);
            res.end("Invalid signature");
            return true;
          }

          let parsed: any;
          try { parsed = JSON.parse(body); } catch { res.writeHead(400); res.end("Bad JSON"); return true; }
          if (parsed.object !== "page") { res.writeHead(400); res.end("Not a page webhook"); return true; }

          api.logger?.info?.(`messenger webhook received: entries=${parsed.entry?.length ?? 0}`);
          api.logger?.info?.(`messenger timing: parsed+validated ${elapsed(requestStartedAt)}ms entries=${parsed.entry?.length ?? 0}`);

          res.writeHead(200);
          res.end("OK");
          api.logger?.info?.(`messenger timing: ack sent ${elapsed(requestStartedAt)}ms`);

          for (const entry of parsed.entry ?? []) {
            for (const event of entry.messaging ?? []) {
              if (event.message?.is_echo) continue;
              const senderId = event.sender?.id;
              if (!senderId) continue;
              const inbound = normalizeMessengerInbound(event);
              if (!inbound) continue;
              const text = inbound.text;

              try {
                const from = `messenger:${senderId}`;
                const dispatchStartedAt = Date.now();
                const mediaDownload = inbound.mediaUrls.length > 0
                  ? await downloadMessengerMedia(inbound.mediaUrls, inbound.mediaTypes, { maxBytes: mediaMaxBytes(cfg) })
                  : { paths: [], mediaPaths: [], mediaTypes: [], dir: undefined, errors: [] };
                if (inbound.mediaUrls.length > 0) {
                  api.logger?.info?.(`messenger media download: success=${mediaDownload.paths.length} failed=${mediaDownload.errors.length}`);
                  for (const failure of mediaDownload.errors) {
                    api.logger?.warn?.(`messenger media download failed url=${failure.url}: ${failure.error}`);
                  }
                }
                api.logger?.info?.(`messenger timing: dispatch start +${elapsed(requestStartedAt)}ms sender=${senderId} media=${inbound.mediaUrls.length} sticker=${Boolean(inbound.sticker)} reaction=${Boolean(inbound.untrustedStructuredContext?.length)}`);
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
                    MessageSid: inbound.messageSid,
                    Timestamp: event.timestamp,
                    OriginatingChannel: "messenger",
                    OriginatingTo: from,
                    NativeChannelId: senderId,
                    CommandAuthorized: true,
                    ...(inbound.mediaUrls.length > 0 ? {
                      MediaUrl: inbound.mediaUrls[0],
                      MediaUrls: inbound.mediaUrls,
                      MediaType: mediaDownload.mediaTypes[0] || inbound.mediaTypes[0],
                      MediaTypes: mediaDownload.mediaTypes.length > 0 ? mediaDownload.mediaTypes : inbound.mediaTypes,
                      ...(mediaDownload.paths.length > 0 ? {
                        MediaPath: mediaDownload.paths[0],
                        MediaPaths: mediaDownload.mediaPaths,
                        MediaDir: mediaDownload.dir,
                      } : {}),
                    } : {}),
                    ...(inbound.sticker ? {
                      Sticker: { fileId: inbound.sticker },
                      StickerMediaIncluded: inbound.stickerMediaIncluded,
                    } : {}),
                    ...(inbound.untrustedStructuredContext ? {
                      UntrustedStructuredContext: inbound.untrustedStructuredContext,
                    } : {}),
                  },
                  dispatcherOptions: {
                    deliver: async (payload: any) => {
                      const replyText = payload?.text?.trim?.() ?? "";
                      if (replyText) {
                        const sendStartedAt = Date.now();
                        api.logger?.info?.(`messenger timing: sendText start +${elapsed(requestStartedAt)}ms dispatch=${elapsed(dispatchStartedAt)}ms chars=${replyText.length}`);
                        await sendText(from, replyText, account);
                        api.logger?.info?.(`messenger timing: sendText end +${elapsed(requestStartedAt)}ms send=${elapsed(sendStartedAt)}ms dispatch=${elapsed(dispatchStartedAt)}ms`);
                      }
                      const mediaUrls = outboundMediaUrls(payload);
                      const mediaTypes = Array.isArray(payload?.mediaTypes) ? payload.mediaTypes : [];
                      for (let i = 0; i < mediaUrls.length; i++) {
                        const mediaType = typeof mediaTypes[i] === "string" ? mediaTypes[i] : payload?.mediaType;
                        const sendStartedAt = Date.now();
                        api.logger?.info?.(`messenger timing: sendMedia start +${elapsed(requestStartedAt)}ms dispatch=${elapsed(dispatchStartedAt)}ms`);
                        await sendMedia(from, mediaUrls[i], account, messengerSendMediaType(mediaType));
                        api.logger?.info?.(`messenger timing: sendMedia end +${elapsed(requestStartedAt)}ms send=${elapsed(sendStartedAt)}ms dispatch=${elapsed(dispatchStartedAt)}ms`);
                      }
                    },
                    onError: (err: unknown) => {
                      api.logger?.error?.(`messenger reply delivery error: ${String(err)}`);
                    },
                  },
                });
                api.logger?.info?.(`messenger timing: dispatch end +${elapsed(requestStartedAt)}ms dispatch=${elapsed(dispatchStartedAt)}ms`);
                api.logger?.info?.(`messenger message dispatched from ${senderId}`);
              } catch (err) {
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
