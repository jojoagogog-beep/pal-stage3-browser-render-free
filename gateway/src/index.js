const pages = {
  "/privacy": {
    title: "Privacy Policy",
    body: [
      "PAL SEO Bulk Fixer processes only merchant data needed to operate, secure, and support the app.",
      "The app reads product titles, descriptions, SEO metadata, and product image alt text to identify missing SEO fields.",
      "When a merchant starts a repair, the app updates only missing product SEO fields and image alt text through Shopify APIs.",
      "We do not sell merchant data and do not intentionally collect customer payment information.",
      "Store data is removed when required by Shopify privacy webhooks and applicable retention rules.",
    ],
  },
  "/terms": {
    title: "Terms of Service",
    body: [
      "PAL SEO Bulk Fixer scans Shopify products for missing SEO titles, meta descriptions, and image alt text.",
      "Bulk repair runs only after merchant action and is designed to preserve fields that already contain content.",
      "Search rankings, traffic, and revenue are not guaranteed because results depend on external search engines and competition.",
      "Merchants remain responsible for reviewing and approving storefront content.",
    ],
  },
  "/support": {
    title: "Support",
    body: [
      "Support: practicalai_lab_jp@proton.me",
      "For help, include the product name and any error message shown by the app.",
      "The safe repair action fills missing fields only.",
    ],
  },
};

function htmlPage(title, paragraphs) {
  const body = paragraphs.map((p) => `<p>${p}</p>`).join("");
  return `<!doctype html><html lang="en"><head><meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1"><title>PAL SEO Bulk Fixer — ${title}</title>  <style>body{font-family:system-ui,-apple-system,sans-serif;max-width:760px;margin:48px auto;padding:0 24px;color:#202223;line-height:1.6}h1{font-size:28px}footer{margin-top:36px;color:#6d7175;font-size:13px}</style>
  </head><body><h1>PAL SEO Bulk Fixer — ${title}</h1>${body}
  <footer>Practical AI Lab · Last updated September 29, 2026</footer></body></html>`;
}

function reviewPage() {
  return `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
  <title>PAL SEO Bulk Fixer</title><style>
  *{box-sizing:border-box}body{margin:0;background:#f6f6f7;color:#202223;font-family:Inter,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
  .top{height:62px;background:#111827;color:#fff;display:flex;align-items:center;padding:0 28px;font-weight:700}
  .main{padding:34px 42px;max-width:1100px;margin:auto}.heading{font-size:28px;margin:0 0 20px}
  .grid{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}.card{background:#fff;border:1px solid #e1e3e5;border-radius:12px;padding:22px;margin-bottom:18px}
  .metric{font-size:30px;font-weight:750}.muted{color:#6d7175}.btn{display:inline-block;background:#111827;color:#fff;border-radius:8px;padding:10px 14px;font-weight:700}
  table{width:100%;border-collapse:collapse}th,td{text-align:left;border-bottom:1px solid #e1e3e5;padding:12px 8px}th{font-size:13px;color:#6d7175}
  .ok{color:#16794d;font-weight:700}.bad{color:#b54708;font-weight:700}@media(max-width:720px){.grid{grid-template-columns:1fr}.main{padding:24px 16px}}
  </style></head><body><div class="top">PAL SEO Bulk Fixer · Practical AI Lab</div><main class="main">
  <h1 class="heading">SEO health</h1>
  <div class="grid"><div class="card"><div class="muted">SEO score</div><div class="metric">72/100</div></div>
  <div class="card"><div class="muted">Products with issues</div><div class="metric">14</div></div>
  <div class="card"><div class="muted">Missing alt text</div><div class="metric">27</div></div></div>  <div class="card"><h2>Safe bulk repair</h2><p>Fill only missing SEO titles, meta descriptions, and image alt text. Existing content is preserved.</p><span class="btn">Fix missing SEO fields</span></div>
  <div class="card"><h2>Product audit</h2><table><thead><tr><th>Product</th><th>SEO title</th><th>Meta description</th><th>Missing alt</th></tr></thead>
  <tbody><tr><td>Classic Linen Shirt</td><td class="ok">OK</td><td class="bad">Missing</td><td>2</td></tr>
  <tr><td>Canvas Weekender Bag</td><td class="bad">Missing</td><td class="ok">OK</td><td>1</td></tr>
  <tr><td>Minimal Desk Lamp</td><td class="ok">OK</td><td class="ok">OK</td><td>0</td></tr></tbody></table></div>
  <div class="card"><h2>What PAL fixes</h2><p>SEO titles are built from product and store names, meta descriptions reuse existing product copy, and alt text is product-based. Only blank fields are changed.</p></div>
  </main></body></html>`;
}

export default {
  async fetch(request, env) {
    const incoming = new URL(request.url);
    if (incoming.pathname === "/_gateway/health") return Response.json({ ok: true, gateway: "pal-seo-bulk-fixer" });
    if (incoming.pathname === "/review-app") return new Response(reviewPage(), { status: 200, headers: { "content-type": "text/html; charset=utf-8", "cache-control": "no-store" } });
    if (pages[incoming.pathname]) {
      const page = pages[incoming.pathname];
      return new Response(htmlPage(page.title, page.body), { status: 200, headers: { "content-type": "text/html; charset=utf-8", "cache-control": "public, max-age=300" } });
    }
    if (!env.PAL_SEO_VPC) return new Response("PAL SEO origin is unavailable", { status: 503 });
    const headers = new Headers(request.headers);
    headers.set("x-forwarded-host", incoming.host);
    headers.set("x-forwarded-proto", "https");
    const privateBase = new URL("http://pal-seo.internal");
    const target = new URL(request.url);
    target.protocol = privateBase.protocol;
    target.host = privateBase.host;
    if (headers.get("origin") === incoming.origin) headers.set("origin", privateBase.origin);
    const referer = headers.get("referer");
    if (referer && referer.startsWith(incoming.origin)) headers.set("referer", privateBase.origin + referer.slice(incoming.origin.length));

    const proxied = new Request(target.toString(), {
      method: request.method,
      headers,
      body: ["GET", "HEAD"].includes(request.method) ? undefined : request.body,
      redirect: "manual",
    });
    try {
      const response = await env.PAL_SEO_VPC.fetch(proxied);
      const responseHeaders = new Headers(response.headers);
      const location = responseHeaders.get("location");
      if (location && location.startsWith(privateBase.origin)) {
        responseHeaders.set("location", incoming.origin + location.slice(privateBase.origin.length));
      }
      return new Response(response.body, { status: response.status, statusText: response.statusText, headers: responseHeaders });
    } catch {
      return new Response("PAL SEO service is temporarily unavailable", { status: 503, headers: { "cache-control": "no-store" } });
    }
  },
};
