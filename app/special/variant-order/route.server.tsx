import { getShopify, getSlug } from "../../multi-shopify.server";
const authenticate={admin:(request:Request)=>getShopify(getSlug(request)).authenticate.admin(request)};
import type {
  ActionFunctionArgs,
  HeadersFunction,
  LoaderFunctionArgs,
} from "react-router";
import { useLoaderData } from "react-router";
import { boundary } from "@shopify/shopify-app-react-router/server";
import { VariantDashboard } from "./components/variant-dashboard";
import {
  auditCatalog,
  buildRemediationCsv,
  type ProductInput,
} from "./lib/variant-order-audit";


const PRODUCT_PAGE_SIZE = 100;
const MAX_PRODUCTS_PER_RUN = 500;

const PRODUCTS_QUERY = `#graphql
  query VariantOrderProducts($cursor: String, $first: Int!) {
    shop {
      name
    }
    products(first: $first, after: $cursor, sortKey: ID) {
      pageInfo {
        hasNextPage
        endCursor
      }
      nodes {
        id
        legacyResourceId
        title
        options {
          name
          position
          optionValues {
            name
          }
        }
      }
    }
  }
`;

type AdminContext = Awaited<ReturnType<typeof authenticate.admin>>;
type AdminClient = AdminContext["admin"];

type Payload = {
  shop?: { name?: string };
  products?: {
    pageInfo: {
      hasNextPage: boolean;
      endCursor: string | null;
    };
    nodes: Array<{
      id: string;
      legacyResourceId: string;
      title: string;
      options: Array<{
        name: string;
        position: number;
        optionValues: Array<{ name: string }>;
      }>;
    }>;
  };
};

async function graphqlData<T>(response: Response): Promise<T> {
  const json = (await response.json()) as {
    data?: T;
    errors?: Array<{ message?: string }>;
  };
  if (!response.ok || json.errors?.length || !json.data) {
    const detail = json.errors
      ?.map((error) => error.message)
      .filter(Boolean)
      .join("; ");
    console.error(
      "Variant order GraphQL request failed",
      detail || response.statusText,
    );
    throw new Response(
      "The catalog structure audit could not be completed. Try again or contact support if the issue continues.",
      { status: 502 },
    );
  }
  return json.data;
}

async function loadCatalog(admin: AdminClient) {
  const products: ProductInput[] = [];
  let shopName = "Your store";
  let cursor: string | null = null;
  let hasNextPage = true;

  while (hasNextPage && products.length < MAX_PRODUCTS_PER_RUN) {
    const data: Payload = await graphqlData<Payload>(
      await admin.graphql(PRODUCTS_QUERY, {
        variables: {
          cursor,
          first: Math.min(
            PRODUCT_PAGE_SIZE,
            MAX_PRODUCTS_PER_RUN - products.length,
          ),
        },
      }),
    );

    shopName = data.shop?.name?.trim() || shopName;
    const connection = data.products;
    if (!connection) break;

    for (const product of connection.nodes) {
      products.push({
        id: product.id,
        legacyResourceId: product.legacyResourceId,
        title: product.title,
        options: product.options.map((option) => ({
          name: option.name,
          position: option.position,
          values: option.optionValues.map((value) => value.name),
        })),
      });
    }

    cursor = connection.pageInfo.endCursor;
    hasNextPage = connection.pageInfo.hasNextPage && Boolean(cursor);
  }

  return {
    shopName,
    products,
    coverageLimited: hasNextPage,
  };
}

export const loader = async ({ request }: LoaderFunctionArgs) => {
  const { admin } = await authenticate.admin(request);
  const catalog = await loadCatalog(admin);
  return {
    shopName: catalog.shopName,
    audit: auditCatalog(catalog.products),
    coverageLimited: catalog.coverageLimited,
    scannedAt: `${new Date()
      .toISOString()
      .slice(0, 16)
      .replace("T", " ")} UTC`,
  };
};

export const action = async ({ request }: ActionFunctionArgs) => {
  const { admin } = await authenticate.admin(request);
  const form = await request.formData();
  if (form.get("intent") !== "exportCsv") {
    return new Response("Unknown action", { status: 400 });
  }

  const catalog = await loadCatalog(admin);
  const csv = buildRemediationCsv(auditCatalog(catalog.products));
  const stamp = new Date().toISOString().slice(0, 10);

  return new Response(csv, {
    headers: {
      "Content-Type": "text/csv; charset=utf-8",
      "Content-Disposition": `attachment; filename="variant-order-${stamp}.csv"`,
      "Cache-Control": "no-store",
      "X-Content-Type-Options": "nosniff",
    },
  });
};

export default function Index() {
  const data = useLoaderData<typeof loader>();
  return <VariantDashboard {...data} />;
}

export const headers: HeadersFunction = (headersArgs) =>
  boundary.headers(headersArgs);


