import { Form } from "react-router";
import type { AuditResult, ProductAudit } from "../lib/import-integrity-audit";
import styles from "./import-integrity-dashboard.module.css";

type Props = {
  audit: AuditResult;
  shopName: string;
  scannedAt: string;
  coverageLimited?: boolean;
  showExport?: boolean;
  demo?: boolean;
  shopDomain?: string;
  mediaMode?: boolean;
  mediaFocus?:
    | "overview"
    | "duplicates"
    | "identifiers"
    | "tracking"
    | "export"
    | "ready"
    | "limit";
};

function productHref(
  product: ProductAudit,
  demo: boolean,
  shopDomain?: string,
) {
  if (demo) return `/review-demo#${product.legacyResourceId}`;
  const normalizedShop = shopDomain?.trim().toLocaleLowerCase();
  if (!normalizedShop?.match(/^[a-z0-9][a-z0-9-]*\.myshopify\.com$/)) {
    return "/app";
  }
  return `https://${normalizedShop}/admin/products/${encodeURIComponent(product.legacyResourceId)}`;
}

function priorityTone(priority: "High" | "Medium" | "Review") {
  if (priority === "High") return "critical";
  if (priority === "Medium") return "warning";
  return "info";
}

export function ImportIntegrityDashboard({
  audit,
  shopName,
  scannedAt,
  coverageLimited = false,
  showExport = true,
  demo = false,
  shopDomain,
  mediaMode = false,
  mediaFocus = "overview",
}: Props) {
  const visibleProducts = audit.products.slice(0, 50);
  const visibleVariants = (
    audit.variants.some((variant) => variant.issueKeys.length)
      ? audit.variants.filter((variant) => variant.issueKeys.length)
      : audit.variants
  ).slice(0, 50);
  const issueLabels = new Map(
    audit.rankedIssues.map((issue) => [issue.key, issue.label]),
  );
  const showSnapshot =
    !mediaMode || ["overview", "export", "ready", "limit"].includes(mediaFocus);
  const showFindings =
    !mediaMode || ["overview", "export", "ready", "limit"].includes(mediaFocus);
  const showProducts = !mediaMode;
  const showEvidence =
    !mediaMode ||
    ["duplicates", "identifiers", "tracking"].includes(mediaFocus);
  const showHandoff = !mediaMode || mediaFocus === "export";
  const showChecks = !mediaMode;

  return (
    <s-page heading="Import Row Integrity Guard" inlineSize="large">
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
          This public demo uses fictional product and variant records. The
          installed app reads the merchant&apos;s live catalog with read-only
          access and does not store audit results.
        </s-banner>
      ) : null}

      {coverageLimited ? (
        <s-banner heading="Catalog safety limit reached" tone="warning">
          This run stopped at 5,000 variants. Results and the CSV cover only the
          rows counted below; no unscanned row is reported as clear.
        </s-banner>
      ) : null}

      {showSnapshot ? (
        <s-section heading="Import integrity snapshot">
          <s-stack direction="block" gap="base">
            <s-paragraph>
              {mediaMode
                ? `${shopName} · Fictional sample catalog · ${scannedAt}.`
                : `${shopName} · Scanned ${audit.summary.productsScanned} products and ${audit.summary.variantsScanned} variant rows at ${scannedAt}.`}
            </s-paragraph>
            <s-paragraph>
              Read-only evidence from the current catalog. The app does not
              upload CSV files, edit products, or decide whether a flagged
              pattern is intentional.
            </s-paragraph>

            {mediaMode ? null : (
              <div className={styles.metrics} aria-label="Audit summary">
                <div className={styles.metric}>
                  <span>Products to review</span>
                  <strong>{audit.summary.productsWithIssues}</strong>
                </div>
                <div className={styles.metric}>
                  <span>Variant rows to review</span>
                  <strong>{audit.summary.variantsWithIssues}</strong>
                </div>
                <div className={styles.metric}>
                  <span>Duplicate SKU groups</span>
                  <strong>{audit.summary.duplicateSkuGroups}</strong>
                </div>
                <div className={styles.metric}>
                  <span>Rows without identifiers</span>
                  <strong>{audit.summary.rowsMissingIdentifiers}</strong>
                </div>
              </div>
            )}
          </s-stack>
        </s-section>
      ) : null}

      {showFindings ? (
        <s-section heading="Prioritized findings">
          {audit.rankedIssues.length === 0 ? (
            <s-banner heading="No checked import patterns found" tone="success">
              This run found no repeated SKUs, missing row identifiers,
              suspicious Default Title rows, or mixed tracking settings in the
              scanned catalog. It is not a validation of the original CSV file.
            </s-banner>
          ) : (
            <s-table variant="auto">
              <s-table-header-row>
                <s-table-header listSlot="primary">Finding</s-table-header>
                <s-table-header listSlot="labeled">Priority</s-table-header>
                {mediaMode ? null : (
                  <>
                    <s-table-header format="numeric">Products</s-table-header>
                    <s-table-header format="numeric">Rows</s-table-header>
                  </>
                )}
                <s-table-header>Recommended next step</s-table-header>
              </s-table-header-row>
              <s-table-body>
                {audit.rankedIssues.map((issue) => (
                  <s-table-row key={issue.key}>
                    <s-table-cell>
                      <s-text type="strong">{issue.label}</s-text>
                    </s-table-cell>
                    <s-table-cell>
                      <s-badge tone={priorityTone(issue.priority)}>
                        {issue.priority}
                      </s-badge>
                    </s-table-cell>
                    {mediaMode ? null : (
                      <>
                        <s-table-cell>{issue.affectedProducts}</s-table-cell>
                        <s-table-cell>{issue.affectedVariants}</s-table-cell>
                      </>
                    )}
                    <s-table-cell>{issue.recommendation}</s-table-cell>
                  </s-table-row>
                ))}
              </s-table-body>
            </s-table>
          )}
        </s-section>
      ) : null}

      {showProducts ? (
        <s-section heading="Products to review">
          {visibleProducts.length === 0 ? (
            <s-paragraph>
              No product variants were returned for this store.
            </s-paragraph>
          ) : (
            <s-table variant="auto">
              <s-table-header-row>
                <s-table-header listSlot="primary">Product</s-table-header>
                <s-table-header listSlot="labeled">Status</s-table-header>
                {mediaMode ? null : (
                  <s-table-header format="numeric">Flagged rows</s-table-header>
                )}
                <s-table-header>Detected patterns</s-table-header>
              </s-table-header-row>
              <s-table-body>
                {visibleProducts.map((product) => (
                  <s-table-row key={product.id}>
                    <s-table-cell>
                      <a
                        className={styles.productLink}
                        href={productHref(product, demo, shopDomain)}
                        target={demo ? undefined : "_blank"}
                        rel={demo ? undefined : "noreferrer"}
                      >
                        {product.title || "Untitled product"}
                      </a>
                      <span className={styles.handle}>/{product.handle}</span>
                    </s-table-cell>
                    <s-table-cell>
                      <s-badge
                        tone={
                          product.status === "No flagged pattern"
                            ? "success"
                            : "warning"
                        }
                      >
                        {product.status}
                      </s-badge>
                    </s-table-cell>
                    {mediaMode ? null : (
                      <s-table-cell>
                        {product.affectedVariantCount}/{product.variants.length}
                      </s-table-cell>
                    )}
                    <s-table-cell>
                      {product.issueKeys.length
                        ? product.issueKeys
                            .map((key) => issueLabels.get(key))
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
              Showing the first {visibleProducts.length} products. The exported
              CSV includes every flagged row in this audit.
            </s-paragraph>
          ) : null}
        </s-section>
      ) : null}

      {showEvidence ? (
        <s-section heading="Variant evidence">
          <s-table variant="auto">
            <s-table-header-row>
              <s-table-header listSlot="primary">
                Product / variant
              </s-table-header>
              <s-table-header>SKU</s-table-header>
              <s-table-header>Barcode</s-table-header>
              <s-table-header>Tracking</s-table-header>
              <s-table-header>Evidence</s-table-header>
            </s-table-header-row>
            <s-table-body>
              {visibleVariants.map((variant) => (
                <s-table-row key={variant.id}>
                  <s-table-cell>
                    <s-text type="strong">{variant.product.title}</s-text>
                    <span className={styles.handle}>{variant.title}</span>
                  </s-table-cell>
                  <s-table-cell>{variant.sku?.trim() || "Blank"}</s-table-cell>
                  <s-table-cell>
                    {variant.barcode?.trim() || "Blank"}
                  </s-table-cell>
                  <s-table-cell>
                    <s-badge
                      tone={variant.inventoryTracked ? "success" : "info"}
                    >
                      {variant.inventoryTracked ? "Tracked" : "Not tracked"}
                    </s-badge>
                  </s-table-cell>
                  <s-table-cell>
                    {variant.findings.length
                      ? variant.findings.join(" ")
                      : "None in checked fields"}
                  </s-table-cell>
                </s-table-row>
              ))}
            </s-table-body>
          </s-table>
          {audit.variants.length > visibleVariants.length ? (
            <s-paragraph>
              Showing the first {visibleVariants.length} rows. The exported CSV
              includes every flagged row in this audit.
            </s-paragraph>
          ) : null}
        </s-section>
      ) : null}

      {showHandoff ? (
        <s-section heading="Remediation handoff">
          <s-stack direction="block" gap="base">
            <s-paragraph>
              Export a spreadsheet-safe checklist with one row per finding. It
              includes the product, variant, current field values, evidence,
              priority, and recommended next step.
            </s-paragraph>
            <div className={styles.fieldList} aria-label="Exported CSV fields">
              <span>Priority</span>
              <span>Finding</span>
              <span>Product and variant</span>
              <span>Current values</span>
              <span>Evidence</span>
              <span>Next step</span>
            </div>
          </s-stack>
        </s-section>
      ) : null}

      {showChecks ? (
        <s-section heading="What this audit checks">
          <s-unordered-list>
            <s-list-item>
              Repeated non-empty SKUs, compared without case or extra
              surrounding whitespace.
            </s-list-item>
            <s-list-item>
              Variant rows with neither a SKU nor barcode, plus rows with a
              barcode but no SKU.
            </s-list-item>
            <s-list-item>
              Default Title rows only when the product is also named Default
              Title or the row has no SKU and no barcode.
            </s-list-item>
            <s-list-item>
              Products whose variants mix tracked and untracked inventory
              settings.
            </s-list-item>
            <s-list-item>
              Findings are review prompts, not proof that the original import
              was malformed.
            </s-list-item>
          </s-unordered-list>
        </s-section>
      ) : null}

      {!mediaMode ? (
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
      ) : null}
    </s-page>
  );
}
