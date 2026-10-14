import type { LoaderFunctionArgs } from "react-router";
import db from "../db.server";

// Public readiness probe. Only health status is disclosed, never DB data,
// addresses, credentials, session tokens or query/exception details.
// Cache on the application instance to protect Render Free from frequent probes.
let lastChecked = 0;
let lastHealthy = false;
export async function loader({ request }: LoaderFunctionArgs) {
  if (request.method !== "GET") return new Response(null, { status: 405 });
  if (Date.now() - lastChecked >= 60_000 || !lastChecked) {
    try {
      const provider = (db as unknown as { _engineConfig?: { activeProvider?: string } })
        ._engineConfig?.activeProvider;
      // Fail closed if a local SQLite-generated Prisma client was mistakenly
      // reused for a production PostgreSQL service.
      if (provider !== "postgresql" || !process.env.DATABASE_URL) {
        lastHealthy = false;
      } else {
        await db.$queryRaw`SELECT 1`;
        lastHealthy = true;
      }
    } catch {
      lastHealthy = false;
    } finally {
      lastChecked = Date.now();
    }
  }
  return new Response(
    JSON.stringify({ database: lastHealthy ? "available" : "unavailable" }),
    {
      status: lastHealthy ? 200 : 503,
      headers: {
        "Content-Type": "application/json; charset=utf-8",
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
      },
    },
  );
}
