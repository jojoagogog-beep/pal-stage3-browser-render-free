import type { ActionFunctionArgs, HeadersFunction, LoaderFunctionArgs } from "react-router";
import { useLoaderData } from "react-router";
import { boundary } from "@shopify/shopify-app-react-router/server";
import { CollectionSortDashboard } from "../components/collection-sort-dashboard";
import { auditCollections, buildDiagnosticCsv, type CollectionInput } from "../lib/collection-sort-audit";
import { authenticate } from "../shopify.server";

const PAGE_SIZE = 50;
const MAX_COLLECTIONS_PER_RUN = 1000;

const COLLECTIONS_QUERY = [
  "#graphql",
  "query CollectionSortAudit($cursor: String, $first: Int!) {",
  "  shop { name myshopifyDomain }",
  "  collections(first: $first, after: $cursor, sortKey: ID) {",
  "    pageInfo { hasNextPage endCursor }",
  "    nodes { id legacyResourceId title handle sortOrder }",
  "  }",
  "}",
].join("\n");

type Payload = {
  shop?: { name?: string; myshopifyDomain?: string };
  collections?: {
    pageInfo: { hasNextPage: boolean; endCursor: string | null };
    nodes: CollectionInput[];
  };
};

async function loadCollections(admin: Awaited<ReturnType<typeof authenticate.admin>>["admin"]) {
  const collections: CollectionInput[] = [];
  let cursor: string | null = null;
  let hasNextPage = true;
  let shopName = "Your store";
  let shopDomain = "";

  while (hasNextPage && collections.length < MAX_COLLECTIONS_PER_RUN) {
    const first = Math.min(PAGE_SIZE, MAX_COLLECTIONS_PER_RUN - collections.length);
    const response: Response = await admin.graphql(COLLECTIONS_QUERY, {
      variables: { cursor, first },
    });
    const json = await response.json() as {
      data?: Payload;
      errors?: Array<{ message?: string }>;
    };
    if (!response.ok || json.errors?.length || !json.data?.collections) {
      throw new Response("Collection sort data could not be read.", { status: 502 });
    }

    const data = json.data;
    const connection = data.collections!;
    shopName = data.shop?.name?.trim() || shopName;
    shopDomain = data.shop?.myshopifyDomain?.trim() || shopDomain;
    collections.push(...connection.nodes);
    cursor = connection.pageInfo.endCursor;
    hasNextPage = connection.pageInfo.hasNextPage && Boolean(cursor);
    if (connection.nodes.length === 0) break;
  }

  return { collections, shopName, shopDomain, coverageLimited: hasNextPage };
}

export const loader = async ({ request }: LoaderFunctionArgs) => {
  const { admin } = await authenticate.admin(request);
  const data = await loadCollections(admin);
  return {
    shopName: data.shopName,
    shopDomain: data.shopDomain,
    audit: auditCollections(data.collections),
    coverageLimited: data.coverageLimited,
    scannedAt: new Date().toISOString().slice(0, 16).replace("T", " ") + " UTC",
  };
};

export const action = async ({ request }: ActionFunctionArgs) => {
  const { admin } = await authenticate.admin(request);
  const form = await request.formData();
  if (form.get("intent") !== "exportCsv") {
    return new Response("Unknown action", { status: 400 });
  }
  const data = await loadCollections(admin);
  const csv = buildDiagnosticCsv(auditCollections(data.collections), data.shopDomain);
  return new Response(csv, {
    headers: {
      "Content-Type": "text/csv; charset=utf-8",
      "Content-Disposition": "attachment; filename=pal-collection-sort-audit.csv",
      "Cache-Control": "no-store",
      "X-Content-Type-Options": "nosniff",
    },
  });
};

export default function Index() {
  return <CollectionSortDashboard {...useLoaderData<typeof loader>()} />;
}

export const headers: HeadersFunction = (args) => boundary.headers(args);
