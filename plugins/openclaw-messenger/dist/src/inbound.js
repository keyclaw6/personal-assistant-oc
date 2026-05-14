export function messengerAttachmentMediaType(type) {
    switch ((type ?? "").toLowerCase()) {
        case "image":
            return "image/jpeg";
        case "video":
            return "video/mp4";
        case "audio":
            return "audio/mpeg";
        default:
            return "application/octet-stream";
    }
}
function attachmentLabel(attachment) {
    const type = attachment.type || "file";
    const title = attachment.payload?.title ? ` \"${attachment.payload.title}\"` : "";
    const sticker = attachment.payload?.sticker_id ? ` (sticker ${attachment.payload.sticker_id})` : "";
    return `${type}${title}${sticker}`;
}
function buildAttachmentSummary(attachments) {
    if (attachments.length === 0)
        return "";
    return `Messenger attachments: ${attachments.map(attachmentLabel).join(", ")}.`;
}
function findStickerId(message, attachments) {
    const stickerId = message?.sticker_id ?? attachments.find((attachment) => attachment.payload?.sticker_id)?.payload?.sticker_id;
    return stickerId == null ? undefined : String(stickerId);
}
export function normalizeMessengerInbound(event) {
    if (event.reaction) {
        const reaction = event.reaction;
        const action = reaction.action || "react";
        const value = reaction.reaction || reaction.emoji || "reaction";
        const mid = reaction.mid || "unknown";
        return {
            text: `Messenger reaction: ${action} ${value} on message ${mid}.`,
            mediaUrls: [],
            mediaTypes: [],
            messageSid: reaction.mid,
            untrustedStructuredContext: [
                {
                    label: "Messenger reaction",
                    source: "messenger",
                    type: "reaction",
                    payload: {
                        action: reaction.action,
                        reaction: reaction.reaction,
                        emoji: reaction.emoji,
                        mid: reaction.mid,
                    },
                },
            ],
        };
    }
    if (!event.message && !event.postback)
        return null;
    const message = event.message;
    const attachments = Array.isArray(message?.attachments) ? message.attachments : [];
    const mediaAttachments = attachments.filter((attachment) => typeof attachment.payload?.url === "string" && attachment.payload.url.length > 0);
    const originalText = message?.text ?? event.postback?.title ?? "";
    const attachmentSummary = buildAttachmentSummary(attachments);
    const text = [originalText, attachmentSummary].filter(Boolean).join("\n");
    if (!text)
        return null;
    const sticker = findStickerId(message, attachments);
    const stickerMediaIncluded = Boolean(sticker && mediaAttachments.some((attachment) => (attachment.type ?? "").toLowerCase() === "image"));
    return {
        text,
        mediaUrls: mediaAttachments.map((attachment) => attachment.payload.url),
        mediaTypes: mediaAttachments.map((attachment) => messengerAttachmentMediaType(attachment.type)),
        sticker,
        stickerMediaIncluded,
        messageSid: message?.mid,
    };
}
