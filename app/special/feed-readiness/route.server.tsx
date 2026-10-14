import { getShopify, getSlug } from "../../multi-shopify.server";
const authenticate={admin:(request:Request)=>getShopify(getSlug(request)).authenticate.admin(request)};
import type {
  ActionFunctionArgs,
  HeadersFunction,
  LoaderFunctionArgs,
} from "react-router";
import { useLoaderData } from "react-router";
import { boundary } from "@shopify/shopify-app-react-router/server";
import { FeedDashboard } from "./components/feed-dashboard";
import {
  auditCatalog,
  buildRemediationCsv,
  type ProductInput,
  type VariantInput,
} from "./lib/feed-audit";


const PRODUCT_PAGE_SIZE = 100;
const VARIANT_PAGE_SIZE = 250;
const MAX_PRODUCTS_PER_RUN = 500;
const MAX_VARIANTS_PER_RUN = 5000;

const PRODUCTS_QUERY = `#graphql
  query FeedReadinessProducts($cursor: String, $first: Int!) {
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
        vendor
        tags
        category {
          fullName
        }
        media(first: 1, query: "media_type:IMAGE") {
          nodes {
            id
          }
        }
      }
    }
  }
`;

const VARIANTS_QUERY = `#graphql
  query FeedReadinessVariants($cursor: String, $first: Int!) {
    productVariants(first: $first, after: $cursor, sortKey: ID) {
      pageInfo {
        hasNextPage
        endCursor
      }
      nodes {
        id
        title
        sku
        barcode
        product {
          id
        }
      }
    }
  }
`;

type AdminContext = Awaited<ReturnType<typeof authenticate.admin>>;
type AdminClient = AdminContext["admin"];

type GraphqlPageInfo = {
  hasNextPage: boolean;
  endCursor: string | null;
};

type ProductsPayload = {
  shop?: { name?: string };
  products?: {
    pageInfo: GraphqlPageInfo;
    nodes: Array<{
      id: string;
      legacyResourceId: string;
      title: string;
      vendor: string;
      tags: string[];
      category: { fullName: string } | null;
      media: { nodes: Array<{ id: string }> };
    }>;
  };
};

type VariantsPayload = {
  productVariants?: {
    pageInfo: GraphqlPageInfo;
    nodes: Array<{
      id: string;
      title: string;
      sku: string | null;
      barcode: string | null;
      product: { id: string };
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
      "Feed readiness GraphQL request failed",
      detail || response.statusText,
    );
    throw new Response(
      "The catalog audit could not be completed. Try again or contact support if the issue continues.",
      {
        status: 502,
      },
    );
  }
  return json.data;
}

async function loadCatalog(admin: AdminClient) {
  const products: ProductInput[] = [];
  const variants: VariantInput[] = [];
  let shopName = "Your store";
  let productCursor: string | null = null;
  let productHasNextPage = true;

  while (productHasNextPage && products.length < MAX_PRODUCTS_PER_RUN) {
    const data: ProductsPayload = await graphqlData<ProductsPayload>(
      await admin.graphql(PRODUCTS_QUERY, {
        variables: {
          cursor: productCursor,
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
        vendor: product.vendor,
        tags: product.tags,
        categoryName: product.category?.fullName ?? null,
        hasImage: product.media.nodes.length > 0,
      });
    }
    productCursor = connection.pageInfo.endCursor;
    productHasNextPage =
      connection.pageInfo.hasNextPage && Boolean(productCursor);
  }

  let variantCursor: string | null = null;
  let variantHasNextPage = true;
  let variantsVisited = 0;
  const auditedProductIds = new Set(products.map((product) => product.id));
  while (variantHasNextPage && variantsVisited < MAX_VARIANTS_PER_RUN) {
    const data: VariantsPayload = await graphqlData<VariantsPayload>(
      await admin.graphql(VARIANTS_QUERY, {
        variables: {
          cursor: variantCursor,
          first: Math.min(
            VARIANT_PAGE_SIZE,
            MAX_VARIANTS_PER_RUN - variantsVisited,
          ),
        },
      }),
    );
    const connection = data.productVariants;
    if (!connection) break;
    for (const variant of connection.nodes) {
      variantsVisited += 1;
      if (!auditedProductIds.has(variant.product.id)) continue;
      variants.push({
        id: variant.id,
        productId: variant.product.id,
        title: variant.title,
        sku: variant.sku,
        barcode: variant.barcode,
      });
    }
    variantCursor = connection.pageInfo.endCursor;
    variantHasNextPage =
      connection.pageInfo.hasNextPage && Boolean(variantCursor);
  }

  return {
    shopName,
    products,
    variants,
    coverageLimited: productHasNextPage || variantHasNextPage,
  };
}

export const loader = async ({ request }: LoaderFunctionArgs) => {
  const { admin } = await authenticate.admin(request);
  const catalog = await loadCatalog(admin);
  return {
    shopName: catalog.shopName,
    audit: auditCatalog(catalog.products, catalog.variants),
    coverageLimited: catalog.coverageLimited,
    scannedAt: `${new Date().toISOString().slice(0, 16).replace("T", " ")} UTC`,
  };
};

export const action = async ({ request }: ActionFunctionArgs) => {
  const { admin } = await authenticate.admin(request);
  const form = await request.formData();
  if (form.get("intent") !== "exportCsv") {
    return new Response("Unknown action", { status: 400 });
  }

  const catalog = await loadCatalog(admin);
  const csv = buildRemediationCsv(
    auditCatalog(catalog.products, catalog.variants),
  );
  const stamp = new Date().toISOString().slice(0, 10);
  return new Response(csv, {
    headers: {
      "Content-Type": "text/csv; charset=utf-8",
      "Content-Disposition": `attachment; filename="feed-readiness-${stamp}.csv"`,
      "Cache-Control": "no-store",
      "X-Content-Type-Options": "nosniff",
    },
  });
};

export default function Index() {
  const data = useLoaderData<typeof loader>();
  return <FeedDashboard {...data} />;
}

export const headers: HeadersFunction = (headersArgs) =>
  boundary.headers(headersArgs);


