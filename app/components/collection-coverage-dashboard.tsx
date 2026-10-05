import { Form } from "react-router";
import type { AuditResult, ProductAudit } from "../lib/collection-coverage-audit";
import { productAdminUrl } from "../lib/collection-coverage-audit";
import styles from "./category-attribute-dashboard.module.css";

type Props = {
  audit: AuditResult;
  shopDomain: string;
  shopName: string;
  scannedAt: string;
  coverageLimited?: boolean;
  showExport?: boolean;
  demo?: boolean;
};

const DISPLAY_LIMIT = 100;

function productHref(product: ProductAudit, shopDomain: string, demo: boolean) {
  return demo ? "#product-" + product.legacyResourceId : productAdminUrl(shopDomain, product.legacyResourceId);
}

function ProductTable({
  products,
  shopDomain,
  demo,
}: {
  products: ProductAudit[];
  shopDomain: string;
  demo: boolean;
}) {
  return (
    <s-table variant="auto">
      <s-table-header-row>
        <s-table-header listSlot="primary">Product</s-table-header>
        <s-table-header>Product status</s-table-header>
        <s-table-header>Collections</s-table-header>
        <s-table-header>Coverage</s-table-header>
      </s-table-header-row>
      <s-table-body>
        {products.slice(0, DISPLAY_LIMIT).map((product) => (
          <s-table-row key={product.id}>
            <s-table-cell>
              <a
                className={styles.productLink}
                href={productHref(product, shopDomain, demo)}
                target={demo ? undefined : "_blank"}
                rel={demo ? undefined : "noreferrer"}
              >
                {product.title || "Untitled product"}
              </a>
            </s-table-cell>
            <s-table-cell>{product.status}</s-table-cell>
            <s-table-cell>
              {product.collections.length
                ? product.collections.map((c) => c.title).join(", ") + (product.collectionsLimited ? ", …" : "")
                : "None"}
            </s-table-cell>
            <s-table-cell>
              <s-badge tone={product.statusLabel === "Orphaned" ? "warning" : "success"}>
                {product.statusLabel}
              </s-badge>
            </s-table-cell>
          </s-table-row>
        ))}
      </s-table-body>
    </s-table>
  );
}

export function CollectionCoverageDashboard({
  audit,
  shopDomain,
  shopName,
  scannedAt,
  coverageLimited = false,
  showExport = true,
  demo = false,
}: Props) {
  return (
    <s-page heading="PAL Collection Coverage Guard" inlineSize="large">
      <s-button slot="primary-action" variant="primary" onClick={() => window.location.reload()}>
        Run audit again
      </s-button>

      {showExport ? (
        <Form method="post" reloadDocument slot="secondary-actions">
          <input type="hidden" name="intent" value="exportCsv" />
          <s-button type="submit" variant="secondary">Export diagnostic CSV</s-button>
        </Form>
      ) : null}

      {demo ? (
        <s-banner heading="Sample audit preview" tone="info">
          This public preview uses fictional catalog records and the same local coverage rules as the installed app.
        </s-banner>
      ) : null}

      <s-banner heading="Read-only collection coverage" tone="info">
        The app reports observed collection membership. It never assigns products to collections or changes catalog data.
      </s-banner>

      {coverageLimited ? (
        <s-banner heading="Safety limit reached" tone="warning">
          This run reached the synchronous product scan limit. The dashboard and CSV include only products scanned in this run.
        </s-banner>
      ) : null}

      <s-section heading="Collection coverage summary">
        <s-stack direction="block" gap="base">
          <s-paragraph>
            {shopName} · Scanned {audit.summary.productsScanned} products at {scannedAt}.
          </s-paragraph>
          <div className={styles.metrics}>
            <div className={styles.metricWarning}>
              <span>Active products with no collection</span>
              <strong>{audit.summary.activeOrphanedProducts}</strong>
            </div>
            <div className={styles.metricWarning}>
              <span>All orphaned products</span>
              <strong>{audit.summary.orphanedProducts}</strong>
            </div>
            <div className={styles.metricSuccess}>
              <span>Products in collections</span>
              <strong>{audit.summary.coveredProducts}</strong>
            </div>
            <div className={styles.metric}>
              <span>Products scanned</span>
              <strong>{audit.summary.productsScanned}</strong>
            </div>
          </div>
        </s-stack>
      </s-section>

      <s-section heading="Active products without a collection">
        {audit.activeOrphaned.length === 0 ? (
          <s-banner heading="No active orphaned products found" tone="success">
            Every active product scanned belongs to at least one collection.
          </s-banner>
        ) : (
          <>
            <s-paragraph>
              These active products have no observed collection membership. Review them in Shopify Admin before making any changes.
            </s-paragraph>
            <ProductTable products={audit.activeOrphaned} shopDomain={shopDomain} demo={demo} />
          </>
        )}
      </s-section>

      <s-section heading="Draft or archived products without a collection">
        {audit.nonActiveOrphaned.length === 0 ? (
          <s-paragraph>No draft or archived orphaned products were found in this run.</s-paragraph>
        ) : (
          <ProductTable products={audit.nonActiveOrphaned} shopDomain={shopDomain} demo={demo} />
        )}
      </s-section>

      <s-section heading="Observed collection membership">
        <ProductTable
          products={audit.products.filter((product) => product.statusLabel === "In collection")}
          shopDomain={shopDomain}
          demo={demo}
        />
        {audit.products.length > DISPLAY_LIMIT ? (
          <p className={styles.tableNote}>
            Tables show up to {DISPLAY_LIMIT} rows per section. Export the CSV for the complete scanned set.
          </p>
        ) : null}
      </s-section>
    </s-page>
  );
}
