import type {LoaderFunctionArgs, ActionFunctionArgs} from "react-router";
import {getShopify} from "../../multi-shopify.server";
import {getSelectedMetafields, saveSelectedMetafields} from "./filter-config.server";
import {parseMetafieldSelections, scanCatalog} from "./filter-analysis.server";


async function savedSelections(shop: string) {
  return parseMetafieldSelections(await getSelectedMetafields(shop)).selections;
}

export const loader = async ({ request }: LoaderFunctionArgs) => {
  const { admin, session } = await getShopify("pal-filter-integrity-guard").authenticate.admin(request);
  const selections = await savedSelections(session.shop);
  try {
    const scan = await scanCatalog(admin, selections);
    return { ...scan, selections, scanError: "" };
  } catch (error) {
    console.error(`Filter integrity scan failed for ${session.shop}`, error);
    return {
      shopName: session.shop.replace(".myshopify.com", ""),
      products: [],
      truncated: false,
      audit: null,
      selections,
      scanError: error instanceof Error ? error.message : "The catalog scan could not be completed.",
    };
  }
};

export const action = async ({ request }: ActionFunctionArgs) => {
  const { session } = await getShopify("pal-filter-integrity-guard").authenticate.admin(request);
  const form = await request.formData();
  if (String(form.get("intent") || "") !== "saveMetafields") {
    return { ok: false, error: "Unsupported request." };
  }
  const parsed = parseMetafieldSelections(String(form.get("metafields") || ""));
  if (parsed.error) return { ok: false, error: parsed.error };

  const selectedMetafields = parsed.selections.map((selection) => selection.identifier).join(",");
  await saveSelectedMetafields(session.shop, selectedMetafields);
  return {
    ok: true,
    message: parsed.selections.length
      ? `Saved ${parsed.selections.length} metafield${parsed.selections.length === 1 ? "" : "s"} and rescanned the catalog.`
      : "Cleared metafield selections and rescanned the catalog.",
  };
};
