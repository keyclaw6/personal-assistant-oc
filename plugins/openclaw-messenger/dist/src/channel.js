import { createChatChannelPlugin, createChannelPluginBase } from "openclaw/plugin-sdk/channel-core";
import { resolveAccountFromEnv } from "./accounts.js";
import { sendText, sendMedia } from "./send.js";
export const messengerPlugin = createChatChannelPlugin({
    base: createChannelPluginBase({
        id: "messenger",
        meta: {
            label: "Messenger",
            selectionLabel: "Facebook Messenger (Graph API)",
            detailLabel: "Facebook Messenger",
            docsPath: "/channels/messenger",
            docsLabel: "messenger",
            blurb: "Facebook Messenger bot via Meta Graph API.",
        },
        setup: {
            resolveAccountId: (cfg, accountId) => resolveAccountFromEnv(cfg, accountId ?? undefined),
            inspectAccount: (cfg, accountId) => {
                const a = resolveAccountFromEnv(cfg, accountId ?? undefined);
                return { enabled: a.enabled, configured: !!a.pageAccessToken, tokenStatus: a.pageAccessToken ? "available" : "missing" };
            },
        },
    }),
    security: {
        dm: {
            channelKey: "messenger",
            resolvePolicy: (account) => account.config?.dm?.policy ?? account.config?.dmPolicy,
            resolveAllowFrom: (account) => account.config?.dm?.allowFrom ?? account.config?.allowFrom,
            defaultPolicy: "pairing",
        },
    },
    pairing: {
        text: {
            idLabel: "Facebook sender ID",
            message: "Send this code to verify your identity:",
            notify: async (params) => {
                const a = resolveAccountFromEnv(params.cfg, params.accountId);
                await sendText(`messenger:${params.id}`, params.message, a);
            },
        },
    },
    threading: {
        scopedAccountReplyToMode: {
            resolveAccount: (cfg, accountId) => resolveAccountFromEnv(cfg, accountId),
            resolveReplyToMode: () => "off",
        },
    },
    outbound: {
        base: {
            deliveryMode: "direct",
            textChunkLimit: 2000,
            resolveTarget: (params) => {
                const t = params.to?.trim()?.replace(/^messenger:/i, "");
                return t ? { ok: true, to: t } : { ok: false, error: "Missing Messenger target" };
            },
        },
        attachedResults: {
            channel: "messenger",
            sendText: async (params) => {
                const a = resolveAccountFromEnv(params.cfg, params.accountId);
                const id = await sendText(params.to, params.text, a);
                return { messageId: id };
            },
            sendMedia: async (params) => {
                if (!params.mediaUrl)
                    throw new Error("mediaUrl required");
                const a = resolveAccountFromEnv(params.cfg, params.accountId);
                const id = await sendMedia(params.to, params.mediaUrl, a);
                return { messageId: id };
            },
        },
    },
});
