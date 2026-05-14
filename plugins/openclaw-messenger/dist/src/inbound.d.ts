export type NormalizedMessengerInbound = {
    text: string;
    mediaUrls: string[];
    mediaTypes: string[];
    sticker?: string;
    stickerMediaIncluded?: boolean;
    untrustedStructuredContext?: Array<{
        label: string;
        source?: string;
        type?: string;
        payload: unknown;
    }>;
    messageSid?: string;
};
export declare function messengerAttachmentMediaType(type?: string): string;
export declare function normalizeMessengerInbound(event: any): NormalizedMessengerInbound | null;
