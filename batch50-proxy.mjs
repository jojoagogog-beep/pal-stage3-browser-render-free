import http from "node:http";
import https from "node:https";

const upstream = new URL("https://pal-shopify-batch50-gateway.onrender.com");
const port = Number(process.env.PORT || 10000);

const server = http.createServer((req, res) => {
  const forwardedHost = req.headers.host || "";
  const headers = {
    ...req.headers,
    host: upstream.host,
    "x-forwarded-host": forwardedHost,
    "x-forwarded-proto": "https",
  };

  const proxyReq = https.request({
    protocol: upstream.protocol,
    hostname: upstream.hostname,
    port: 443,
    method: req.method,
    path: req.url,
    headers,
  }, (proxyRes) => {
    const out = { ...proxyRes.headers };
    if (typeof out.location === "string") {
      out.location = out.location.replace(
        "https://pal-shopify-batch50-gateway.onrender.com",
        "https://pal-description-raw-url-guard.onrender.com",
      );
    }
    res.writeHead(proxyRes.statusCode || 502, out);
    proxyRes.pipe(res);
  });

  proxyReq.on("error", () => {
    res.writeHead(502, { "content-type": "text/plain; charset=utf-8" });
    res.end("Gateway unavailable");
  });

  req.pipe(proxyReq);
});

server.listen(port, "0.0.0.0", () => {
  console.log("batch50 proxy listening", port);
});
