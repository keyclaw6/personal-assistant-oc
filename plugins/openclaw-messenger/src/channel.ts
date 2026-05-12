import { createChatChannelPlugin, createChannelPluginBase } from "openclaw/plugin-sdk/channel-core";
import { DEFAULT_ACCOUNT_ID, resolveAccountFromEnv, type ResolvedAccount } from "./accounts.js";
import { sendText, sendMedia, sendSenderAction } from "./send.js";

type Cfg = { channels?: Record<string, any> };

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
    config: {
      resolveAccount: (cfg: Cfg, accountId?: string | null) => resolveAccountFromEnv(cfg, accountId ?? undefined),
      listAccountIds: (cfg: Cfg) => resolveAccountFromEnv(cfg).pageAccessToken ? [DEFAULT_ACCOUNT_ID] : [],
      defaultAccountId: () => DEFAULT_ACCOUNT_ID,
      hasConfiguredState: ({ env }: any) => typeof env?.MESSENGER_PAGE_ACCESS_TOKEN === "string" && env.MESSENGER_PAGE_ACCESS_TOKEN.trim().length > 0,
      isConfigured: (account: ResolvedAccount) => Boolean(account.pageAccessToken?.trim()),
      describeAccount: (account: ResolvedAccount) => ({
        accountId: account.accountId,
        enabled: account.enabled,
        configured: Boolean(account.pageAccessToken?.trim()),
        tokenStatus: account.pageAccessToken ? "available" : "missing",
      }),
    } as any,
    setup: {
      resolveAccountId: (cfg: Cfg, accountId?: string | null) =>
        resolveAccountFromEnv(cfg, accountId ?? undefined),
      inspectAccount: (cfg: Cfg, accountId?: string | null) => {
        const a = resolveAccountFromEnv(cfg, accountId ?? undefined);
        return { enabled: a.enabled, configured: !!a.pageAccessToken, tokenStatus: a.pageAccessToken ? "available" : "missing" };
      },
    } as any,
  }) as any,
  security: {
    dm: {
      channelKey: "messenger",
      resolvePolicy: (account: any) => account.config?.dm?.policy ?? account.config?.dmPolicy,
      resolveAllowFrom: (account: any) => account.config?.dm?.allowFrom ?? account.config?.allowFrom,
      defaultPolicy: "pairing",
    },
  },
  pairing: {
    text: {
      idLabel: "Facebook sender ID",
      message: "Send this code to verify your identity:",
      notify: async (params: any) => {
        const a = resolveAccountFromEnv(params.cfg, params.accountId);
        await sendText(`messenger:${params.id}`, params.message, a);
      },
    },
  },
  threading: {
    scopedAccountReplyToMode: {
      resolveAccount: (cfg: any, accountId?: any) => resolveAccountFromEnv(cfg, accountId),
      resolveReplyToMode: () => "off" as const,
    },
  } as any,
  outbound: {
    base: {
      deliveryMode: "direct" as const,
      textChunkLimit: 2000,
      resolveTarget: (params: any) => {
        const t = params.to?.trim()?.replace(/^messenger:/i, "");
        return t ? { ok: true, to: t } : { ok: false, error: "Missing Messenger target" };
      },
    },
    attachedResults: {
      channel: "messenger",
      sendText: async (params: any) => {
        const a = resolveAccountFromEnv(params.cfg, params.accountId);
        const id = await sendText(params.to, params.text, a);
        return { messageId: id };
      },
      sendMedia: async (params: any) => {
        if (!params.mediaUrl) throw new Error("mediaUrl required");
        const a = resolveAccountFromEnv(params.cfg, params.accountId);
        const id = await sendMedia(params.to, params.mediaUrl, a);
        return { messageId: id };
      },
    },
  },
} as any);
