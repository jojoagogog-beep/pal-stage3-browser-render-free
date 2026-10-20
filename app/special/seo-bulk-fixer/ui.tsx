import {Form, useActionData, useLoaderData, useNavigation} from "react-router";
import type {loader, action} from "./route.server";

export default function Index() {
  const { shopName, rows, summary, score } = useLoaderData<typeof loader>();
  const result = useActionData<typeof action>();
  const nav = useNavigation();
  const busy = nav.state === "submitting";  return (
    <s-page heading="PAL SEO Bulk Fixer">
      <s-section heading="SEO health">
        <s-paragraph>{shopName} · SEO completeness score: {score}/100</s-paragraph>
        <s-paragraph>
          Scanned {summary.products} recently updated products (up to 50). {summary.productsWithIssues} products need attention.
        </s-paragraph>
      </s-section>

      <s-section heading="Issues found">
        <s-paragraph>Missing SEO titles: {summary.missingSeoTitles}</s-paragraph>
        <s-paragraph>Missing meta descriptions: {summary.missingSeoDescriptions}</s-paragraph>
        <s-paragraph>Missing image alt text: {summary.missingAltTexts}</s-paragraph>
      </s-section>

      <s-section heading="Safe bulk repair">
        <s-paragraph>
          PAL only fills missing fields. Existing SEO titles, meta descriptions, and image alt text are never overwritten.
        </s-paragraph>
        <Form method="post">
          <input type="hidden" name="intent" value="fixMissing" />
          <button type="submit" disabled={busy || summary.productsWithIssues === 0}>
            {busy ? "Applying safe fixes…" : "Fix missing SEO fields"}
          </button>
        </Form>
        {result ? (
          result.ok ? (
            <s-paragraph>
              Fixed {result.seoFieldsFixed || 0} SEO fields and {result.altTextsFixed || 0} image alt texts across {result.productsUpdated || 0} products.
            </s-paragraph>
          ) : (
            <s-paragraph>
              Completed with review needed: {(result.errors || []).join(" | ") || result.error || "Unknown error"}
            </s-paragraph>
          )
        ) : null}
      </s-section>      <s-section heading="Product audit">
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr>
                <th style={{ textAlign: "left", padding: 8 }}>Product</th>
                <th style={{ textAlign: "left", padding: 8 }}>SEO title</th>
                <th style={{ textAlign: "left", padding: 8 }}>Meta description</th>
                <th style={{ textAlign: "right", padding: 8 }}>Missing alt</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(({ product, audit }) => (
                <tr key={product.id}>
                  <td style={{ padding: 8 }}>{product.title}</td>
                  <td style={{ padding: 8 }}>{audit.missingSeoTitle ? "Missing" : "OK"}</td>
                  <td style={{ padding: 8 }}>{audit.missingSeoDescription ? "Missing" : "OK"}</td>
                  <td style={{ padding: 8, textAlign: "right" }}>{audit.missingAlt}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </s-section>

      <s-section heading="What PAL fixes">
        <s-paragraph>SEO title: generated from the product title and store name when blank.</s-paragraph>
        <s-paragraph>Meta description: derived from the existing product description when blank.</s-paragraph>
        <s-paragraph>Image alt text: descriptive product-based text is added only when alt text is blank.</s-paragraph>
      </s-section>
    </s-page>
  );
}

