import { Form } from "react-router";
import type {
  AuditResult,
  ProductAudit,
} from "../lib/variant-image-audit";
import styles from "./variant-image-dashboard.module.css";

type Props = {
  audit: AuditResult;
  shopName: string;
  scannedAt: string;
  adminBaseUrl?: string;
  coverageLimited?: boolean;
  showExport?: boolean;
  demo?: boolean;
};

function productHref(
  product: ProductAudit,
  demo: boolean,
  adminBaseUrl?: string,
) {
  if (demo) return `/review-demo#${product.legacyResourceId}`;
  return `${adminBaseUrl?.replace(/\/$/, "") ?? ""}/products/${encodeURIComponent(product.legacyResourceId)}`;
}

function statusTone(status: ProductAudit["status"]) {
  if (status === "Covered") return "success";
  if (status === "No variant images") return "info";
  return "warning";
}

export function VariantImageDashboard({
  audit,
  shopName,
  scannedAt,
  adminBaseUrl,
  coverageLimited = false,
  showExport = true,
  demo = false,
}: Props) {
  const visibleProducts = audit.affectedProducts.slice(0, 50);

  return (
    <s-page heading="PAL Variant Image Guard" inlineSize="large">
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
            Export affected products
          </s-button>
        </Form>
      ) : null}

      {demo ? (
        <s-banner heading="Sample catalog preview" tone="info">
          This preview uses clearly labeled sample products and the same audit
          logic as the installed app. It does not connect to a merchant store.
        </s-banner>
      ) : null}

      {coverageLimited ? (
        <s-banner heading="Audit safety limit reached" tone="warning">
          This run reached a catalog or per-variant media safety limit. Results
          and the CSV cover only the records reported as scanned; review them as
          a partial audit.
        </s-banner>
      ) : null}

      <s-section heading="Variant image assignment audit">
        <s-stack direction="block" gap="base">
          <s-paragraph>
            {shopName} · Scanned {audit.summary.productsScanned} products and{" "}
            {audit.summary.variantsScanned} variants at {scannedAt}.
          </s-paragraph>
          <s-paragraph>
            Read-only audit. The app reports image assignments and never changes
            product media, variants, themes, or storefront behavior.
          </s-paragraph>

          <div className={styles.metrics}>
            <div className={styles.metricPrimary}>
              <span>Products to review</span>
              <strong>{audit.summary.productsWithIssues}</strong>
            </div>
            <div className={styles.metric}>
              <span>Mixed coverage</span>
              <strong>{audit.summary.mixedCoverageProducts}</strong>
            </div>
            <div className={styles.metric}>
              <span>Duplicate assignments</span>
              <strong>{audit.summary.duplicateAssignmentProducts}</strong>
            </div>
            <div className={styles.metric}>
              <span>Variants missing images</span>
              <strong>{audit.summary.variantsMissingImages}</strong>
            </div>
          </div>
        </s-stack>
      </s-section>

      <s-section heading="Findings by check">
        {audit.rankedIssues.length === 0 ? (
          <s-banner heading="No mixed or duplicate assignments found" tone="success">
            The checked products did not contain mixed variant-image coverage or
            image assignments shared across multiple variants. Products with no
            dedicated variant images are counted separately and are not flagged
            unless a sibling variant has an image.
          </s-banner>
        ) : (
          <s-table variant="auto">
            <s-table-header-row>
              <s-table-header listSlot="primary">Check</s-table-header>
              <s-table-header listSlot="labeled">Classification</s-table-header>
              <s-table-header format="numeric">Products</s-table-header>
              <s-table-header format="numeric">Variants</s-table-header>
              <s-table-header>Recommended next step</s-table-header>
            </s-table-header-row>
            <s-table-body>
              {audit.rankedIssues.map((issue) => (
                <s-table-row key={issue.key}>
                  <s-table-cell>
                    <s-text type="strong">{issue.label}</s-text>
                  </s-table-cell>
                  <s-table-cell>
                    <s-badge tone="warning">{issue.priority}</s-badge>
                  </s-table-cell>
                  <s-table-cell>{issue.affectedProducts}</s-table-cell>
                  <s-table-cell>{issue.affectedVariants}</s-table-cell>
                  <s-table-cell>{issue.recommendation}</s-table-cell>
                </s-table-row>
              ))}
            </s-table-body>
          </s-table>
        )}
      </s-section>

      <s-section heading="Affected products">
        {visibleProducts.length === 0 ? (
          <s-paragraph>
            No products need review for the two checked assignment patterns.
          </s-paragraph>
        ) : (
          <s-table variant="auto">
            <s-table-header-row>
              <s-table-header listSlot="primary">Product</s-table-header>
              <s-table-header listSlot="labeled">Status</s-table-header>
              <s-table-header>Image coverage</s-table-header>
              <s-table-header format="numeric">Shared images</s-table-header>
              <s-table-header>Finding</s-table-header>
            </s-table-header-row>
            <s-table-body>
              {visibleProducts.map((product) => (
                <s-table-row key={product.id}>
                  <s-table-cell>
                    <a
                      className={styles.productLink}
                      href={productHref(product, demo, adminBaseUrl)}
                      target={demo ? undefined : "_blank"}
                      rel={demo ? undefined : "noreferrer"}
                    >
                      {product.title || "Untitled product"}
                    </a>
                  </s-table-cell>
                  <s-table-cell>
                    <s-badge tone={statusTone(product.status)}>
                      {product.status}
                    </s-badge>
                  </s-table-cell>
                  <s-table-cell>
                    {product.variantsWithImages}/{product.variants.length} variants
                  </s-table-cell>
                  <s-table-cell>
                    {product.duplicateAssignments.length || "—"}
                  </s-table-cell>
                  <s-table-cell>{product.findings.join(" · ")}</s-table-cell>
                </s-table-row>
              ))}
            </s-table-body>
          </s-table>
        )}
        {audit.affectedProducts.length > visibleProducts.length ? (
          <s-paragraph>
            Showing the first {visibleProducts.length} affected products. The
            CSV includes every finding in this audit run.
          </s-paragraph>
        ) : null}
      </s-section>

      <s-section heading="What the audit checks">
        <s-unordered-list>
          <s-list-item>
            Variants with no assigned image when at least one sibling variant
            has its own image.
          </s-list-item>
          <s-list-item>
            The same product image assigned to more than one variant of a
            product.
          </s-list-item>
          <s-list-item>
            Products are grouped by mixed coverage so review can begin with the
            clearest assignment gaps.
          </s-list-item>
          <s-list-item>
            Shared images can be intentional. The app reports evidence and leaves
            every catalog decision to the merchant.
          </s-list-item>
        </s-unordered-list>
        <s-paragraph>
          {audit.summary.productsWithNoVariantImages} checked product(s) had no
          dedicated variant images at all. They are not flagged as mixed coverage.
        </s-paragraph>
      </s-section>

      <div className={styles.footerLinks}>
        <a href="/privacy" target="_blank" rel="noreferrer">Privacy</a>
        <a href="/terms" target="_blank" rel="noreferrer">Terms</a>
        <a href="/support" target="_blank" rel="noreferrer">Support</a>
      </div>
    </s-page>
  );
}
