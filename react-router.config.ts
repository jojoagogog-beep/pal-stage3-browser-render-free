import type { Config } from "@react-router/dev/config";

// The production service is behind Render's TLS-terminating proxy.
// React Router may see its internal request host during its CSRF origin check.
// Permit only the two known HTTPS application hostnames; do not disable CSRF.
export default {
  ssr: true,
  allowedActionOrigins: [
    "pal-stage3-browser-free-shard1.onrender.com",
    "pal-shopify-batch50-gateway.onrender.com",
  ],
} satisfies Config;
