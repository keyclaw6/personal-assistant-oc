export type MessengerMediaDownloadResult = {
    /** Successful local paths only. */
    paths: string[];
    /** One entry per input URL; failed downloads are empty strings so MediaUrls stay index-aligned. */
    mediaPaths: string[];
    /** One entry per input URL using the downloaded response content-type when available. */
    mediaTypes: string[];
    dir?: string;
    errors: Array<{
        url: string;
        error: string;
    }>;
};
type DownloadOptions = {
    maxBytes?: number;
    fetchImpl?: typeof fetch;
};
export declare function messengerMediaExtension(mediaType: string | undefined, url: string): string;
export declare function downloadMessengerMedia(mediaUrls: string[], mediaTypes?: string[], opts?: DownloadOptions): Promise<MessengerMediaDownloadResult>;
export {};
