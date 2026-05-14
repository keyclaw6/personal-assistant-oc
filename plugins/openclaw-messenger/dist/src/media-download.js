import { randomUUID } from "node:crypto";
import { mkdir, writeFile } from "node:fs/promises";
import { homedir } from "node:os";
import { basename, extname, join } from "node:path";
function mediaTypeExtension(mediaType) {
    const normalized = (mediaType ?? "").split(";")[0].trim().toLowerCase();
    switch (normalized) {
        case "image/jpeg":
            return ".jpg";
        case "image/png":
            return ".png";
        case "image/gif":
            return ".gif";
        case "image/webp":
            return ".webp";
        case "video/mp4":
            return ".mp4";
        case "audio/mpeg":
            return ".mp3";
        case "audio/wav":
            return ".wav";
        case "audio/ogg":
            return ".ogg";
        case "application/pdf":
            return ".pdf";
        default:
            return undefined;
    }
}
function urlExtension(url) {
    try {
        const ext = extname(basename(new URL(url).pathname)).toLowerCase();
        return /^\.[a-z0-9]{2,5}$/.test(ext) ? ext : undefined;
    }
    catch {
        return undefined;
    }
}
export function messengerMediaExtension(mediaType, url) {
    return mediaTypeExtension(mediaType) ?? urlExtension(url) ?? ".bin";
}
async function responseBytes(response, maxBytes) {
    const contentLength = Number(response.headers.get("content-length") ?? 0);
    if (contentLength > maxBytes)
        throw new Error(`media exceeds max bytes (${contentLength} > ${maxBytes})`);
    const chunks = [];
    let total = 0;
    const reader = response.body?.getReader();
    if (!reader) {
        const bytes = new Uint8Array(await response.arrayBuffer());
        if (bytes.byteLength > maxBytes)
            throw new Error(`media exceeds max bytes (${bytes.byteLength} > ${maxBytes})`);
        return bytes;
    }
    while (true) {
        const { done, value } = await reader.read();
        if (done)
            break;
        if (!value)
            continue;
        total += value.byteLength;
        if (total > maxBytes)
            throw new Error(`media exceeds max bytes (${total} > ${maxBytes})`);
        chunks.push(value);
    }
    const out = new Uint8Array(total);
    let offset = 0;
    for (const chunk of chunks) {
        out.set(chunk, offset);
        offset += chunk.byteLength;
    }
    return out;
}
export async function downloadMessengerMedia(mediaUrls, mediaTypes = [], opts = {}) {
    const fetchMedia = opts.fetchImpl ?? fetch;
    const maxBytes = opts.maxBytes ?? 25 * 1024 * 1024;
    const dir = join(homedir(), ".openclaw", "media", "messenger", `${Date.now()}-${randomUUID()}`);
    const paths = [];
    const mediaPaths = mediaUrls.map(() => "");
    const resolvedMediaTypes = mediaUrls.map((_, i) => mediaTypes[i] ?? "");
    const errors = [];
    for (let i = 0; i < mediaUrls.length; i++) {
        const url = mediaUrls[i];
        try {
            const response = await fetchMedia(url);
            if (!response.ok)
                throw new Error(`HTTP ${response.status}`);
            const responseMediaType = response.headers.get("content-type")?.split(";")[0]?.trim() || mediaTypes[i];
            const bytes = await responseBytes(response, maxBytes);
            await mkdir(dir, { recursive: true });
            const filePath = join(dir, `media-${i + 1}${messengerMediaExtension(responseMediaType, url)}`);
            await writeFile(filePath, bytes);
            mediaPaths[i] = filePath;
            resolvedMediaTypes[i] = responseMediaType ?? "";
            paths.push(filePath);
        }
        catch (err) {
            errors.push({ url, error: String(err) });
        }
    }
    return { paths, mediaPaths, mediaTypes: resolvedMediaTypes, dir: paths.length > 0 ? dir : undefined, errors };
}
