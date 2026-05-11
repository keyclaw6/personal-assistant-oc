import http from "node:http";

const listenHost = process.env.MESSENGER_PROXY_HOST || "127.0.0.1";
const listenPort = Number(process.env.MESSENGER_PROXY_PORT || "18890");
const gatewayHost = process.env.OPENCLAW_GATEWAY_HOST || "127.0.0.1";
const gatewayPort = Number(process.env.OPENCLAW_GATEWAY_PORT || "18789");
const allowedPath = process.env.MESSENGER_WEBHOOK_PATH || "/messenger/webhook";

function buildForwardHeaders(req) {
  const headers = { ...req.headers };
  headers.host = `${gatewayHost}:${gatewayPort}`;
  headers["x-forwarded-for"] = req.socket.remoteAddress || "127.0.0.1";
  headers["x-forwarded-host"] = req.headers.host || `${listenHost}:${listenPort}`;
  headers["x-forwarded-proto"] = "https";
  return headers;
}

export function createProxyServer() {
  return http.createServer((req, res) => {
    const url = new URL(req.url || "/", `http://${req.headers.host || `${listenHost}:${listenPort}`}`);
    if (url.pathname !== allowedPath) {
      res.writeHead(404, { "content-type": "text/plain; charset=utf-8" });
      res.end("Not found");
      return;
    }

    if (req.method !== "GET" && req.method !== "POST") {
      res.writeHead(405, { "content-type": "text/plain; charset=utf-8" });
      res.end("Method not allowed");
      return;
    }

    const forward = http.request(
      {
        host: gatewayHost,
        port: gatewayPort,
        method: req.method,
        path: `${url.pathname}${url.search}`,
        headers: buildForwardHeaders(req),
      },
      (upstream) => {
        res.writeHead(upstream.statusCode || 502, upstream.headers);
        upstream.pipe(res);
      },
    );

    forward.on("error", (err) => {
      res.writeHead(502, { "content-type": "text/plain; charset=utf-8" });
      res.end(`Upstream error: ${String(err.message || err)}`);
    });

    req.pipe(forward);
  });
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const server = createProxyServer();
  server.listen(listenPort, listenHost, () => {
    console.log(`Messenger webhook proxy listening on http://${listenHost}:${listenPort}${allowedPath}`);
    console.log(`Forwarding to http://${gatewayHost}:${gatewayPort}${allowedPath}`);
  });
}
