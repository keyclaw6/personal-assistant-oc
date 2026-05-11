import { type ResolvedAccount } from "./accounts.js";
export declare function chunkText(text: string, limit: number): string[];
export declare function graphApiSend(token: string, body: Record<string, unknown>): Promise<{
    message_id?: string;
}>;
export declare function sendText(to: string, text: string, account: ResolvedAccount): Promise<string>;
export declare function sendMedia(to: string, mediaUrl: string, account: ResolvedAccount, type?: string): Promise<string>;
export declare function sendSenderAction(to: string, action: string, account: ResolvedAccount): Promise<void>;
