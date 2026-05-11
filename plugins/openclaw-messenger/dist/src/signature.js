import crypto from "node:crypto";
export function validateSignature(body, signature, secret) {
    if (!signature.startsWith("sha256="))
        return false;
    const received = signature.slice(7);
    const computed = crypto.createHmac("sha256", secret).update(body).digest("hex");
    const a = Buffer.from(received, "hex");
    const b = Buffer.from(computed, "hex");
    if (a.length !== b.length)
        return false;
    return crypto.timingSafeEqual(a, b);
}
