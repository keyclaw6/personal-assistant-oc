export declare const GRAPH_API_BASE = "https://graph.facebook.com/v21.0";
export declare const DEFAULT_ACCOUNT_ID = "default";
export declare const TEXT_CHUNK_LIMIT = 2000;
export interface MessengerConfig {
    enabled?: boolean;
    pageAccessToken?: string;
    appSecret?: string;
    verifyToken?: string;
    tokenFile?: string;
    secretFile?: string;
    webhookPath?: string;
    allowFrom?: Array<string | number>;
    dmPolicy?: string;
    dm?: {
        policy?: string;
        allowFrom?: Array<string | number>;
    };
    accounts?: Record<string, MessengerConfig>;
    [key: string]: unknown;
}
export interface ResolvedAccount {
    accountId: string;
    enabled: boolean;
    pageAccessToken: string;
    appSecret: string;
    verifyToken: string;
    config: MessengerConfig;
}
export declare function resolveAccount(cfg: {
    channels?: Record<string, any>;
}, accountId?: string): ResolvedAccount;
export declare function resolveAccountFromEnv(cfg: {
    channels?: Record<string, any>;
}, accountId?: string): ResolvedAccount;
