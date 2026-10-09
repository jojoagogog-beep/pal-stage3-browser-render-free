const pages = {
  "/privacy": {
    title: "Privacy Policy",
    body: [
      "PAL Active Product Age Guard processes only merchant data needed to operate, secure, and support the app.",
      "The app reads product creation dates and age information to identify products within or outside configured age ranges.",
      "When a merchant configures age restrictions, the app applies settings through Shopify APIs without modifying product data.",
      "We do not sell merchant data and do not intentionally collect customer payment information.",
      "Store data is removed when required by Shopify privacy webhooks and applicable retention rules.",
    ],
  },
  "/terms": {
    title: "Terms of Service",
    body: [
      "PAL Active Product Age Guard monitors Shopify products and applies age-based visibility rules based on merchant configuration.",
      "Rules are applied only after merchant action and merchant remains responsible for any restrictions set.",
      "Product visibility results depend on merchant configuration and Shopify's storefront settings and cannot be guaranteed.",
      "Merchants remain responsible for reviewing and approving all product settings.",
    ],
  },
  "/support": {
    title: "Support",
    body: [
      "Support: practicalai_lab_jp@proton.me",
      "For help, include the product name and any error message shown by the app.",
      "Our team will assist with configuration and troubleshooting.",
    ],
  },
};

function htmlPage(title, paragraphs) {
  const body = paragraphs.map((p) => `<p>${p}</p>`).join("");
  return `<!doctype html><html lang="en"><head><meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1"><title>PAL Active Product Age Guard — ${title}</title>  <style>body{font-family:system-ui,-apple-system,sans-serif;max-width:760px;margin:48px auto;padding:0 24px;color:#202223;line-height:1.6}h1{font-size:28px}footer{margin-top:36px;color:#6d7175;font-size:13px}</style>
  </head><body><h1>PAL Active Product Age Guard — ${title}</h1>${body}
  <footer>Practical AI Lab · Last updated October 8, 2026</footer></body></html>`;
}

function reviewPage() {
  return `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
  <title>PAL Active Product Age Guard</title><style>
  *{box-sizing:border-box}body{margin:0;background:#f6f6f7;color:#202223;font-family:Inter,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
  .top{height:62px;background:#111827;color:#fff;display:flex;align-items:center;padding:0 28px;font-weight:700}
  .main{padding:34px 42px;max-width:1100px;margin:auto}.heading{font-size:28px;margin:0 0 20px}
  .grid{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}.card{background:#fff;border:1px solid #e1e3e5;border-radius:12px;padding:22px;margin-bottom:18px}
  .metric{font-size:30px;font-weight:750}.muted{color:#6d7175}.btn{display:inline-block;background:#111827;color:#fff;border-radius:8px;padding:10px 14px;font-weight:700}
  table{width:100%;border-collapse:collapse}th,td{text-align:left;border-bottom:1px solid #e1e3e5;padding:12px 8px}th{font-size:13px;color:#6d7175}
  .ok{color:#16794d;font-weight:700}.bad{color:#b54708;font-weight:700}@media(max-width:720px){.grid{grid-template-columns:1fr}.main{padding:24px 16px}}
  </style></head><body><div class="top">PAL Active Product Age Guard · Practical AI Lab</div><main class="main">
  <h1 class="heading">Product age tracking</h1>
  <div class="grid"><div class="card"><div class="muted">Total products</div><div class="metric">128</div></div>
  <div class="card"><div class="muted">Age monitored</div><div class="metric">112</div></div>
  <div class="card"><div class="muted">Rules applied</div><div class="metric">8</div></div></div>  <div class="card"><h2>Age-based rules</h2><p>Configure age ranges to automatically manage product visibility and access restrictions based on product creation date.</p><span class="btn">Configure age rules</span></div>
  <div class="card"><h2>Product age summary</h2><table><thead><tr><th>Age range</th><th>Product count</th><th>Rules</th></tr></thead>
  <tbody><tr><td>&lt; 30 days</td><td class="ok">42</td><td>Active</td></tr>
  <tr><td>30-90 days</td><td class="ok">56</td><td>Active</td></tr>
  <tr><td>&gt; 90 days</td><td class="bad">30</td><td>None</td></tr></tbody></table></div>
  <div class="card"><h2>What PAL monitors</h2><p>PAL Active Product Age Guard tracks product creation dates and applies configured age-based rules. Configuration changes apply automatically across your store.</p></div>
  </main></body></html>`;
}

export default {
  async fetch(request, env) {
    const incoming = new URL(request.url);
    if (incoming.pathname === "/_gateway/health") return Response.json({ ok: true, gateway: "pal-active-product-age-guard" });
    if (incoming.pathname === "/review-app") return new Response(reviewPage(), { status: 200, headers: { "content-type": "text/html; charset=utf-8", "cache-control": "no-store" } });
    if (pages[incoming.pathname]) {
      const page = pages[incoming.pathname];
      return new Response(htmlPage(page.title, page.body), { status: 200, headers: { "content-type": "text/html; charset=utf-8", "cache-control": "public, max-age=300" } });
    }
    if (!env.PAL_APP_VPC) return new Response("PAL Active Product Age Guard origin is unavailable", { status: 503 });
    const headers = new Headers(request.headers);
    headers.set("x-forwarded-host", incoming.host);
    headers.set("x-forwarded-proto", "https");
    const privateBase = new URL("http://pal-active-product-age-guard.internal");
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
      const response = await env.PAL_APP_VPC.fetch(proxied);
      const responseHeaders = new Headers(response.headers);
      const location = responseHeaders.get("location");
      if (location && location.startsWith(privateBase.origin)) {
        responseHeaders.set("location", incoming.origin + location.slice(privateBase.origin.length));
      }
      return new Response(response.body, { status: response.status, statusText: response.statusText, headers: responseHeaders });
    } catch {
      return new Response("PAL Active Product Age Guard service is temporarily unavailable", { status: 503, headers: { "cache-control": "no-store" } });
    }
  },
};
