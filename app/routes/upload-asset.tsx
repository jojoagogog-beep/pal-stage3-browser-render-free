import type { LoaderFunctionArgs } from "react-router";
import { readFile } from "node:fs/promises";
import { join } from "node:path";

const allowed: Record<string, string> = {
  "app-icon.png": join(process.cwd(), "public", "app-icon.png"),
  "missing.png": join(process.cwd(), "review-assets", "listing", "missing.png"),
  "overview.png": join(process.cwd(), "review-assets", "listing", "overview.png"),
  "ready.png": join(process.cwd(), "review-assets", "listing", "ready.png"),
  "uncategorized.png": join(process.cwd(), "review-assets", "listing", "uncategorized.png"),
  "limit.png": join(process.cwd(), "review-assets", "listing", "limit.png"),
};

export async function loader({ request }: LoaderFunctionArgs) {
  const name = new URL(request.url).searchParams.get("name") || "";
  const path = allowed[name];
  if (!path) return new Response("Not found", { status: 404 });
  const body = await readFile(path);
  return new Response(body, {
    headers: {
      "Content-Type": "image/png",
      "Access-Control-Allow-Origin": "*",
      "Cache-Control": "no-store",
    },
  });
}
