import assert from "node:assert/strict";
import http from "node:http";
import { once } from "node:events";
import { test } from "node:test";

function request(port, path, options = {}) {
  return new Promise((resolve, reject) => {
    const req = http.request(
      {
        host: "127.0.0.1",
        port,
        path,
        method: options.method || "GET",
        headers: options.headers || {},
      },
      (res) => {
        const chunks = [];
        res.on("data", (chunk) => chunks.push(chunk));
        res.on("end", () => resolve({ status: res.statusCode, body: Buffer.concat(chunks).toString("utf-8") }));
      },
    );
    req.on("error", reject);
    if (options.body) req.write(options.body);
    req.end();
  });
}

test("proxy only exposes the messenger webhook path and forwards GET requests", async () => {
  process.env.OPENCLAW_GATEWAY_PORT = "18901";
  process.env.MESSENGER_PROXY_PORT = "18902";
  process.env.MESSENGER_WEBHOOK_PATH = "/messenger/webhook";

  const { createProxyServer } = await import("../scripts/messenger-webhook-proxy.mjs");

  const upstream = http.createServer((req, res) => {
    res.writeHead(200, { "content-type": "text/plain" });
    res.end(req.url === "/messenger/webhook?hub.challenge=test" ? "test" : "unexpected");
  });
  upstream.listen(18901, "127.0.0.1");
  await once(upstream, "listening");

  const proxy = createProxyServer();
  proxy.listen(18902, "127.0.0.1");
  await once(proxy, "listening");

  try {
    const ok = await request(18902, "/messenger/webhook?hub.challenge=test");
    assert.equal(ok.status, 200);
    assert.equal(ok.body, "test");

    const blocked = await request(18902, "/");
    assert.equal(blocked.status, 404);
  } finally {
    proxy.close();
    upstream.close();
    delete process.env.OPENCLAW_GATEWAY_PORT;
    delete process.env.MESSENGER_PROXY_PORT;
    delete process.env.MESSENGER_WEBHOOK_PATH;
  }
});

test("proxy rejects unsupported methods", async () => {
  process.env.OPENCLAW_GATEWAY_PORT = "18903";
  process.env.MESSENGER_PROXY_PORT = "18904";
  process.env.MESSENGER_WEBHOOK_PATH = "/messenger/webhook";

  const { createProxyServer } = await import("../scripts/messenger-webhook-proxy.mjs");
  const proxy = createProxyServer();
  proxy.listen(18904, "127.0.0.1");
  await once(proxy, "listening");

  try {
    const res = await request(18904, "/messenger/webhook", { method: "PUT" });
    assert.equal(res.status, 405);
  } finally {
    proxy.close();
    delete process.env.OPENCLAW_GATEWAY_PORT;
    delete process.env.MESSENGER_PROXY_PORT;
    delete process.env.MESSENGER_WEBHOOK_PATH;
  }
});
