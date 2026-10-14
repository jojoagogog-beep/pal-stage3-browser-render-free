import { getShopify, getSlug } from "../../multi-shopify.server";
const authenticate={admin:(request:Request)=>getShopify(getSlug(request)).authenticate.admin(request)};
import type {
  ActionFunctionArgs,
  HeadersFunction,
  LoaderFunctionArgs,
} from "react-router";
import { useLoaderData } from "react-router";
import { boundary } from "@shopify/shopify-app-react-router/server";
import { ImportIntegrityDashboard } from "./components/import-integrity-dashboard";
import {
  auditCatalog,
  buildRemediationCsv,
  type VariantInput,
} from "./lib/import-integrity-audit";


const VARIANT_PAGE_SIZE = 250;
const MAX_VARIANTS_PER_RUN = 5_000;

const VARIANTS_QUERY = `#graphql
  query ImportIntegrityVariants($cursor: String, $first: Int!) {
    shop {
      name
    }
    productVariants(first: $first, after: $cursor, sortKey: ID) {
      pageInfo {
        hasNextPage
        endCursor
      }
      nodes {
        id
        legacyResourceId
        title
        sku
        barcode
        inventoryItem {
          tracked
        }
        product {
          id
          legacyResourceId
          title
          handle
        }
      }
    }
  }
`;

type AdminContext = Awaited<ReturnType<typeof authenticate.admin>>;

type QueryPayload = {
  shop?: { name?: string };
  productVariants?: {
    pageInfo: { hasNextPage: boolean; endCursor: string | null };
    nodes: Array<{
      id: string;
      legacyResourceId: string;
      title: string;
      sku: string | null;
      barcode: string | null;
      inventoryItem: { tracked: boolean };
      product: {
        id: string;
        legacyResourceId: string;
        title: string;
        handle: string;
      };
    }>;
  };
};

const MAX_THROTTLE_RETRIES = 3;

async function graphqlData<T>(
  request: () => Promise<Response>,
  attempt = 0,
): Promise<T> {
  const response = await request();
  const json = (await response.json()) as {
    data?: T;
    errors?: Array<{
      message?: string;
      extensions?: { code?: string };
    }>;
  };

  const throttled = json.errors?.some(
    (error) => error.extensions?.code === "THROTTLED",
  );
  if (throttled && attempt < MAX_THROTTLE_RETRIES) {
    await new Promise((resolve) => setTimeout(resolve, 500 * 2 ** attempt));
    return graphqlData(request, attempt + 1);
  }

  if (!response.ok || json.errors?.length || !json.data) {
    console.error("Import integrity query failed", {
      status: response.status,
      errors: json.errors?.map((error) => error.message).filter(Boolean),
    });
    throw new Response(
      "The import integrity audit could not be completed. Try again or contact support.",
      { status: 502 },
    );
  }
  return json.data;
}

async function loadCatalog(admin: AdminContext["admin"]) {
  const variants: VariantInput[] = [];
  let shopName = "Your store";
  let cursor: string | null = null;
  let hasNextPage = true;

  while (hasNextPage && variants.length < MAX_VARIANTS_PER_RUN) {
    const first = Math.min(
      VARIANT_PAGE_SIZE,
      MAX_VARIANTS_PER_RUN - variants.length,
    );
    const data: QueryPayload = await graphqlData<QueryPayload>(() =>
      admin.graphql(VARIANTS_QUERY, {
        variables: { cursor, first },
      }),
    );
    shopName = data.shop?.name?.trim() || shopName;
    const connection = data.productVariants;
    if (!connection) break;

    for (const variant of connection.nodes) {
      variants.push({
        id: variant.id,
        legacyResourceId: variant.legacyResourceId,
        title: variant.title,
        sku: variant.sku,
        barcode: variant.barcode,
        inventoryTracked: variant.inventoryItem.tracked,
        product: variant.product,
      });
    }

    cursor = connection.pageInfo.endCursor;
    hasNextPage = connection.pageInfo.hasNextPage && Boolean(cursor);
  }

  return {
    shopName,
    variants,
    coverageLimited: hasNextPage,
  };
}

export const loader = async ({ request }: LoaderFunctionArgs) => {
  const { admin, session } = await authenticate.admin(request);
  const catalog = await loadCatalog(admin);
  return {
    shopDomain: session.shop,
    shopName: catalog.shopName,
    audit: auditCatalog(catalog.variants),
    coverageLimited: catalog.coverageLimited,
    scannedAt: `${new Date().toISOString().slice(0, 16).replace("T", " ")} UTC`,
  };
};

export const action = async ({ request }: ActionFunctionArgs) => {
  const { admin, session } = await authenticate.admin(request);
  const form = await request.formData();
  if (form.get("intent") !== "exportCsv") {
    return new Response("Unknown action", { status: 400 });
  }

  const catalog = await loadCatalog(admin);
  const csv = buildRemediationCsv(auditCatalog(catalog.variants), session.shop);
  const stamp = new Date().toISOString().slice(0, 10);
  return new Response(csv, {
    headers: {
      "Content-Type": "text/csv; charset=utf-8",
      "Content-Disposition": `attachment; filename="import-row-integrity-${stamp}.csv"`,
      "Cache-Control": "private, no-store, max-age=0",
      "X-Content-Type-Options": "nosniff",
    },
  });
};

export default function Index() {
  const data = useLoaderData<typeof loader>();
  return <ImportIntegrityDashboard {...data} />;
}

export const headers: HeadersFunction = (args) => boundary.headers(args);


