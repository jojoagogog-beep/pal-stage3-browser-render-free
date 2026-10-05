import { Form } from "react-router";
import type { AuditResult, ProductAudit } from "../lib/variant-sale-audit";
import styles from "./variant-dashboard.module.css";

type Props = {
  audit: AuditResult;
  shopName: string;
  scannedAt: string;
  coverageLimited?: boolean;
  showExport?: boolean;
  demo?: boolean;
};

function productHref(product: ProductAudit, demo: boolean) {
  return demo
    ? `/review-demo#${product.legacyResourceId}`
    : `shopify://admin/products/${product.legacyResourceId}`;
}

export function VariantDashboard({
  audit,
  shopName,
  scannedAt,
  coverageLimited = false,
  showExport = true,
  demo = false,
}: Props) {
  const visibleProducts = audit.products.slice(0, 50);

  return (
    <s-page heading="Variant Sale Guard" inlineSize="large">
      <s-button slot="primary-action" variant="primary" onClick={() => window.location.reload()}>
        Run audit again
      </s-button>

      {showExport ? (
        <Form method="post" reloadDocument slot="secondary-actions">
          <input type="hidden" name="intent" value="exportCsv" />
          <s-button type="submit" variant="secondary">
            Export remediation CSV
          </s-button>
        </Form>
      ) : null}

      {demo ? (
        <s-banner heading="Reviewer demo" tone="info">
          This public demo uses fictional pricing records. The installed app reads
          product variant prices and compare-at prices only.
        </s-banner>
      ) : null}

      {coverageLimited ? (
        <s-banner heading="Large catalog safety limit reached" tone="warning">
          This run stopped at its safety limit. Results and CSV cover only the
          products shown as scanned.
        </s-banner>
      ) : null}

      <s-section heading="Variant sale consistency audit">
        <s-stack direction="block" gap="base">
          <s-paragraph>
            {shopName} · Scanned {audit.summary.productsScanned} products and{" "}
            {audit.summary.variantsScanned} variants at {scannedAt}.
          </s-paragraph>
          <s-paragraph>
            Read-only audit. Variant Sale Guard reports pricing evidence and never
            changes prices, compare-at prices, products, themes, or discounts.
          </s-paragraph>

          <div className={styles.metrics}>
            <div className={styles.metric}>
              <span>Products to review</span>
              <strong>{audit.summary.productsWithIssues}</strong>
            </div>
            <div className={styles.metric}>
              <span>Mixed sale state</span>
              <strong>{audit.summary.partialSaleMix}</strong>
            </div>
            <div className={styles.metric}>
              <span>Consistent products</span>
              <strong>{audit.summary.consistentProducts}</strong>
            </div>
          </div>
        </s-stack>
      </s-section>

      <s-section heading="Prioritized findings">
        {audit.rankedIssues.length === 0 ? (
          <s-banner heading="No pricing consistency issues found" tone="success">
            This run found no invalid compare-at prices, mixed sale states,
            extreme discount spread, or zero-price findings.
          </s-banner>
        ) : (
          <s-table variant="auto">
            <s-table-header-row>
              <s-table-header listSlot="primary">Finding</s-table-header>
              <s-table-header listSlot="labeled">Priority</s-table-header>
              <s-table-header format="numeric">Products</s-table-header>
              <s-table-header>Recommended next step</s-table-header>
            </s-table-header-row>
            <s-table-body>
              {audit.rankedIssues.map((issue) => (
                <s-table-row key={issue.key}>
                  <s-table-cell><s-text type="strong">{issue.label}</s-text></s-table-cell>
                  <s-table-cell>
                    <s-badge tone={issue.priority === "High" ? "critical" : issue.priority === "Medium" ? "warning" : "info"}>
                      {issue.priority}
                    </s-badge>
                  </s-table-cell>
                  <s-table-cell>{issue.affectedProducts}</s-table-cell>
                  <s-table-cell>{issue.recommendation}</s-table-cell>
                </s-table-row>
              ))}
            </s-table-body>
          </s-table>
        )}
      </s-section>

      <s-section heading="Products to review">
        {visibleProducts.length === 0 ? (
          <s-paragraph>No products were returned for this store.</s-paragraph>
        ) : (
          <s-table variant="auto">
            <s-table-header-row>
              <s-table-header listSlot="primary">Product</s-table-header>
              <s-table-header listSlot="labeled">Status</s-table-header>
              <s-table-header>Sale variants</s-table-header>
              <s-table-header>Discount range</s-table-header>
              <s-table-header>Finding</s-table-header>
            </s-table-header-row>
            <s-table-body>
              {visibleProducts.map((product) => (
                <s-table-row key={product.id}>
                  <s-table-cell>
                    <a className={styles.productLink} href={productHref(product, demo)} target={demo ? undefined : "_top"}>
                      {product.title || "Untitled product"}
                    </a>
                  </s-table-cell>
                  <s-table-cell>
                    <s-badge tone={product.status === "Consistent" ? "success" : "warning"}>
                      {product.status}
                    </s-badge>
                  </s-table-cell>
                  <s-table-cell>{product.saleVariantCount}/{product.variantCount}</s-table-cell>
                  <s-table-cell>{product.discountRange}</s-table-cell>
                  <s-table-cell>{product.findings.length ? product.findings.join(" · ") : "None in checked pricing"}</s-table-cell>
                </s-table-row>
              ))}
            </s-table-body>
          </s-table>
        )}
        {audit.products.length > visibleProducts.length ? (
          <s-paragraph>
            Showing the first {visibleProducts.length} products. The CSV includes all audited findings.
          </s-paragraph>
        ) : null}
      </s-section>

      <s-section heading="What the audit checks">
        <s-unordered-list>
          <s-list-item>Compare-at prices that are equal to or below the selling price.</s-list-item>
          <s-list-item>Products where only some variants have a valid sale price.</s-list-item>
          <s-list-item>Large differences in discount percentage across variants of the same product.</s-list-item>
          <s-list-item>Zero-price variants that may need merchant review.</s-list-item>
          <s-list-item>The app reports evidence only. Merchants decide whether each difference is intentional.</s-list-item>
        </s-unordered-list>
      </s-section>

      <div className={styles.footerLinks}>
        <a href="/privacy" target="_blank" rel="noreferrer">Privacy</a>
        <a href="/terms" target="_blank" rel="noreferrer">Terms</a>
        <a href="/support" target="_blank" rel="noreferrer">Support</a>
      </div>
    </s-page>
  );
}
