import http from 'node:http';
import https from 'node:https';

const upstream = new URL('https://pal-shopify-batch50-gateway.onrender.com');
const port = Number(process.env.PORT || 10000);

const server = http.createServer((req, res) => {
  const headers = { ...req.headers, host: upstream.host };
  headers['x-forwarded-host'] = req.headers.host || '';
  headers['x-forwarded-proto'] = 'https';
  const p = https.request({
    protocol: upstream.protocol,
    hostname: upstream.hostname,
    port: 443,
    method: req.method,
    path: req.url,
    headers,
  }, up => {
    const outHeaders = { ...up.headers };
    if (outHeaders.location && outHeaders.location.includes(upstream.host)) {
      outHeaders.location = outHeaders.location.replace(upstream.host, req.headers.host || upstream.host);
    }
    res.writeHead(up.statusCode || 502, outHeaders);
    up.pipe(res);
  });
  p.on('error', err => {
    res.writeHead(502, {'content-type':'text/plain; charset=utf-8'});
    res.end('Proxy error');
  });
  req.pipe(p);
});
server.listen(port, '0.0.0.0', () => console.log('batch50 proxy listening', port));
