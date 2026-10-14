import { getShopify, getSlug } from "../../multi-shopify.server";
const authenticate={admin:(request:Request)=>getShopify(getSlug(request)).authenticate.admin(request)};
import type {
  ActionFunctionArgs,
  HeadersFunction,
  LoaderFunctionArgs,
} from "react-router";
import { useLoaderData } from "react-router";
import { boundary } from "@shopify/shopify-app-react-router/server";
import { VariantImageDashboard } from "./components/variant-image-dashboard";
import {
  auditCatalog,
  buildAffectedProductsCsv,
  type ProductInput,
} from "./lib/variant-image-audit";


const VARIANT_PAGE_SIZE = 50;
const MAX_VARIANTS_PER_RUN = 5_000;

const VARIANTS_QUERY = `#graphql
  query VariantImageAssignments($cursor: String, $first: Int!) {
    shop { name }
    productVariants(first: $first, after: $cursor, sortKey: ID) {
      pageInfo { hasNextPage endCursor }
      nodes {
        id
        legacyResourceId
        title
        product { id legacyResourceId title }
        image { id altText }
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
      product: { id: string; legacyResourceId: string; title: string };
      image: { id: string; altText: string | null } | null;
    }>;
  };
};

async function graphqlData<T>(response: Response): Promise<T> {
  const json = (await response.json()) as {
    data?: T;
    errors?: Array<{ message?: string }>;
  };
  if (!response.ok || json.errors?.length || !json.data) {
    throw new Response(
      "The image assignment audit could not be completed. Try again or contact support.",
      { status: 502 },
    );
  }
  return json.data;
}

async function loadCatalog(admin: AdminContext["admin"]) {
  const products = new Map<string, ProductInput>();
  let shopName = "Your store";
  let cursor: string | null = null;
  let hasNextPage = true;
  let variantsLoaded = 0;

  while (hasNextPage && variantsLoaded < MAX_VARIANTS_PER_RUN) {
    const first = Math.min(
      VARIANT_PAGE_SIZE,
      MAX_VARIANTS_PER_RUN - variantsLoaded,
    );
    const data: QueryPayload = await graphqlData<QueryPayload>(
      await admin.graphql(VARIANTS_QUERY, {
        variables: { cursor, first },
      }),
    );
    shopName = data.shop?.name?.trim() || shopName;
    const connection = data.productVariants;
    if (!connection) break;

    for (const variant of connection.nodes) {
      const product = products.get(variant.product.id) ?? {
        id: variant.product.id,
        legacyResourceId: variant.product.legacyResourceId,
        title: variant.product.title,
        variants: [],
      };
      product.variants.push({
        id: variant.id,
        legacyResourceId: variant.legacyResourceId,
        title: variant.title,
        images: variant.image
          ? [{ id: variant.image.id, alt: variant.image.altText }]
          : [],
      });
      products.set(product.id, product);
      variantsLoaded += 1;
    }

    cursor = connection.pageInfo.endCursor;
    hasNextPage = connection.pageInfo.hasNextPage && Boolean(cursor);
  }

  return {
    shopName,
    products: [...products.values()],
    coverageLimited: hasNextPage,
  };
}

function adminBaseUrl(shopDomain: string) {
  return `https://${shopDomain}/admin`;
}

export const loader = async ({ request }: LoaderFunctionArgs) => {
  const { admin, session } = await authenticate.admin(request);
  const catalog = await loadCatalog(admin);
  return {
    shopName: catalog.shopName,
    audit: auditCatalog(catalog.products),
    coverageLimited: catalog.coverageLimited,
    adminBaseUrl: adminBaseUrl(session.shop),
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
  const csv = buildAffectedProductsCsv(
    auditCatalog(catalog.products),
    adminBaseUrl(session.shop),
  );
  const stamp = new Date().toISOString().slice(0, 10);
  return new Response(csv, {
    headers: {
      "Content-Type": "text/csv; charset=utf-8",
      "Content-Disposition": `attachment; filename="variant-image-guard-${stamp}.csv"`,
      "Cache-Control": "no-store",
      "X-Content-Type-Options": "nosniff",
    },
  });
};

export default function Index() {
  const data = useLoaderData<typeof loader>();
  return <VariantImageDashboard {...data} />;
}

export const headers: HeadersFunction = (args) => boundary.headers(args);


