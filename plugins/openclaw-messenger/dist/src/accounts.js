export const GRAPH_API_BASE = "https://graph.facebook.com/v21.0";
export const DEFAULT_ACCOUNT_ID = "default";
export const TEXT_CHUNK_LIMIT = 2000;
export function resolveAccount(cfg, accountId) {
    const mc = cfg.channels?.messenger;
    const acct = accountId && accountId !== DEFAULT_ACCOUNT_ID ? mc?.accounts?.[accountId] : undefined;
    const merged = { ...mc, ...acct };
    const token = acct?.pageAccessToken ?? mc?.pageAccessToken ?? "";
    const secret = acct?.appSecret ?? mc?.appSecret ?? "";
    const verify = acct?.verifyToken ?? mc?.verifyToken ?? "";
    return {
        accountId: accountId ?? DEFAULT_ACCOUNT_ID,
        enabled: merged.enabled !== false && !!token,
        pageAccessToken: token,
        appSecret: secret,
        verifyToken: verify,
        config: merged,
    };
}
export function resolveAccountFromEnv(cfg, accountId) {
    const base = resolveAccount(cfg, accountId);
    if (base.pageAccessToken)
        return base;
    return {
        ...base,
        pageAccessToken: process.env.MESSENGER_PAGE_ACCESS_TOKEN ?? base.pageAccessToken,
        appSecret: process.env.MESSENGER_APP_SECRET ?? base.appSecret,
        verifyToken: process.env.MESSENGER_VERIFY_TOKEN ?? base.verifyToken,
        enabled: base.enabled || !!(process.env.MESSENGER_PAGE_ACCESS_TOKEN),
    };
}
