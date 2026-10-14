import { Form } from "react-router";
import type { AuditResult, ProductAudit } from "../lib/feed-audit";
import styles from "./feed-dashboard.module.css";

type FeedDashboardProps = {
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

function statusTone(status: ProductAudit["status"]) {
  if (status === "Ready") return "success";
  if (status === "Action needed") return "critical";
  return "warning";
}

export function FeedDashboard({
  audit,
  shopName,
  scannedAt,
  coverageLimited = false,
  showExport = true,
  demo = false,
}: FeedDashboardProps) {
  const visibleProducts = audit.products.slice(0, 50);

  return (
    <s-page heading="Feed Readiness Guard" inlineSize="large">
      <s-button
        slot="primary-action"
        variant="primary"
        onClick={() => window.location.reload()}
      >
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
          This public demo uses fictional catalog records. The installed app
          reads the merchant&apos;s own product catalog with read-only access.
        </s-banner>
      ) : null}

      {coverageLimited ? (
        <s-banner heading="Large catalog safety limit reached" tone="warning">
          This run stopped at its safety limit. The results and CSV cover only
          the products and variants shown as scanned. Run another audit after
          addressing these items.
        </s-banner>
      ) : null}

      <s-section heading="Catalog pre-flight">
        <s-stack direction="block" gap="base">
          <s-paragraph>
            {shopName} · Scanned {audit.summary.productsScanned} products and{" "}
            {audit.summary.variantsScanned} variants at {scannedAt}.
          </s-paragraph>
          <s-paragraph>
            Read-only audit. Feed Readiness Guard never changes product data and
            does not guarantee channel approval.
          </s-paragraph>
          <div className={styles.metrics}>
            <div className={styles.metric}>
              <span>Products needing action</span>
              <strong>{audit.summary.productsWithActions}</strong>
            </div>
            <div className={styles.metric}>
              <span>Identifier reviews</span>
              <strong>{audit.summary.productsForIdentifierReview}</strong>
            </div>
            <div className={styles.metric}>
              <span>No flagged gaps</span>
              <strong>{audit.summary.productsReady}</strong>
            </div>
          </div>
        </s-stack>
      </s-section>

      <s-section heading="Prioritized issues">
        {audit.rankedIssues.length === 0 ? (
          <s-banner heading="No feed-readiness gaps found" tone="success">
            This audit did not flag missing values in the checked fields.
            Channel requirements can still vary by product and market.
          </s-banner>
        ) : (
          <s-table variant="auto">
            <s-table-header-row>
              <s-table-header listSlot="primary">Issue</s-table-header>
              <s-table-header listSlot="labeled">Priority</s-table-header>
              <s-table-header>Channel relevance</s-table-header>
              <s-table-header format="numeric">Products</s-table-header>
              <s-table-header format="numeric">Variants</s-table-header>
            </s-table-header-row>
            <s-table-body>
              {audit.rankedIssues.map((issue) => (
                <s-table-row key={issue.key}>
                  <s-table-cell>
                    <s-text type="strong">{issue.label}</s-text>
                  </s-table-cell>
                  <s-table-cell>
                    <s-badge
                      tone={
                        issue.priority === "High"
                          ? "critical"
                          : issue.priority === "Medium"
                            ? "warning"
                            : "info"
                      }
                    >
                      {issue.priority}
                    </s-badge>
                  </s-table-cell>
                  <s-table-cell>{issue.channel}</s-table-cell>
                  <s-table-cell>{issue.affectedProducts}</s-table-cell>
                  <s-table-cell>{issue.affectedVariants || "—"}</s-table-cell>
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
              <s-table-header>Classification</s-table-header>
              <s-table-header>Flagged fields</s-table-header>
            </s-table-header-row>
            <s-table-body>
              {visibleProducts.map((product) => (
                <s-table-row key={product.id}>
                  <s-table-cell>
                    <a
                      className={styles.productLink}
                      href={productHref(product, demo)}
                      target={demo ? undefined : "_top"}
                    >
                      {product.title || "Untitled product"}
                    </a>
                  </s-table-cell>
                  <s-table-cell>
                    <s-badge tone={statusTone(product.status)}>
                      {product.status}
                    </s-badge>
                  </s-table-cell>
                  <s-table-cell>{product.kindLabel}</s-table-cell>
                  <s-table-cell>
                    {product.issueKeys.length
                      ? product.issueKeys
                          .map(
                            (key) =>
                              audit.rankedIssues.find(
                                (issue) => issue.key === key,
                              )?.label,
                          )
                          .filter(Boolean)
                          .join(" · ")
                      : "None in checked fields"}
                  </s-table-cell>
                </s-table-row>
              ))}
            </s-table-body>
          </s-table>
        )}
        {audit.products.length > visibleProducts.length ? (
          <s-paragraph>
            Showing the first {visibleProducts.length} products in the
            dashboard. The CSV includes all audited findings.
          </s-paragraph>
        ) : null}
      </s-section>

      <s-section heading="How identifier review works">
        <s-unordered-list>
          <s-list-item>
            Products with a vendor and no custom-product cues are grouped as
            standard branded products.
          </s-list-item>
          <s-list-item>
            Products tagged or named as custom, personalized, handmade,
            made-to-order, or print-on-demand are separated for review.
          </s-list-item>
          <s-list-item>
            Missing vendor products remain unclassified. The app never invents
            or writes GTINs, SKUs, brands, or categories.
          </s-list-item>
        </s-unordered-list>
      </s-section>

      <div className={styles.footerLinks}>
        <a href="/privacy" target="_blank" rel="noreferrer">
          Privacy
        </a>
        <a href="/terms" target="_blank" rel="noreferrer">
          Terms
        </a>
        <a href="/support" target="_blank" rel="noreferrer">
          Support
        </a>
      </div>
    </s-page>
  );
}
