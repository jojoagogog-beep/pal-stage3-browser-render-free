import { Form } from "react-router";
import type {
  AuditResult,
  AttributeAudit,
  ProductAudit,
} from "../lib/category-attribute-audit";
import { productAdminUrl } from "../lib/category-attribute-audit";
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

type Row = {
  product: ProductAudit;
  attribute: AttributeAudit;
};

const DISPLAY_LIMIT = 100;

function observedValue(value: string | null) {
  if (!value || value.trim() === "" || value.trim() === "[]") {
    return "Not set";
  }
  const trimmed = value.trim();
  if (trimmed.length <= 100) return trimmed;
  return trimmed.slice(0, 97) + "...";
}

function productHref(
  product: ProductAudit,
  shopDomain: string,
  demo: boolean,
) {
  return demo
    ? "#product-" + product.legacyResourceId
    : productAdminUrl(
        shopDomain,
        product.legacyResourceId,
      );
}

function EvidenceTable({
  rows,
  shopDomain,
  demo,
}: {
  rows: Row[];
  shopDomain: string;
  demo: boolean;
}) {
  return (
    <s-table variant="auto">
      <s-table-header-row>
        <s-table-header listSlot="primary">
          Product
        </s-table-header>
        <s-table-header>Category</s-table-header>
        <s-table-header>Category field</s-table-header>
        <s-table-header>Observed value</s-table-header>
        <s-table-header>Status</s-table-header>
      </s-table-header-row>
      <s-table-body>
        {rows.slice(0, DISPLAY_LIMIT).map(
          ({ product, attribute }) => (
            <s-table-row
              key={product.id + "-" + attribute.id}
            >
              <s-table-cell>
                <a
                  className={styles.productLink}
                  href={productHref(
                    product,
                    shopDomain,
                    demo,
                  )}
                  target={demo ? undefined : "_blank"}
                  rel={demo ? undefined : "noreferrer"}
                >
                  {product.title || "Untitled product"}
                </a>
              </s-table-cell>
              <s-table-cell>
                {product.category?.fullName || "—"}
              </s-table-cell>
              <s-table-cell>
                {attribute.name}
              </s-table-cell>
              <s-table-cell>
                {observedValue(attribute.value)}
              </s-table-cell>
              <s-table-cell>
                <s-badge
                  tone={
                    attribute.status === "Missing"
                      ? "warning"
                      : "success"
                  }
                >
                  {attribute.status}
                </s-badge>
              </s-table-cell>
            </s-table-row>
          ),
        )}
      </s-table-body>
    </s-table>
  );
}

function NoCategoryTable({
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
        <s-table-header listSlot="primary">
          Product
        </s-table-header>
        <s-table-header>Status</s-table-header>
      </s-table-header-row>
      <s-table-body>
        {products.slice(0, DISPLAY_LIMIT).map(
          (product) => (
            <s-table-row key={product.id}>
              <s-table-cell>
                <a
                  className={styles.productLink}
                  href={productHref(
                    product,
                    shopDomain,
                    demo,
                  )}
                  target={demo ? undefined : "_blank"}
                  rel={demo ? undefined : "noreferrer"}
                >
                  {product.title || "Untitled product"}
                </a>
              </s-table-cell>
              <s-table-cell>
                <s-badge tone="warning">
                  No category
                </s-badge>
              </s-table-cell>
            </s-table-row>
          ),
        )}
      </s-table-body>
    </s-table>
  );
}

export function CategoryAttributeDashboard({
  audit,
  shopDomain,
  shopName,
  scannedAt,
  coverageLimited = false,
  showExport = true,
  demo = false,
}: Props) {
  const rows: Row[] = audit.products.flatMap(
    (product) =>
      product.attributes.map((attribute) => ({
        product,
        attribute,
      })),
  );
  const missingRows = rows.filter(
    ({ attribute }) => attribute.status === "Missing",
  );
  const populatedRows = rows.filter(
    ({ attribute }) =>
      attribute.status === "Populated",
  );
  const noCategory = audit.products.filter(
    (product) => product.status === "No category",
  );

  return (
    <s-page
      heading="PAL Category Attribute Guard"
      inlineSize="large"
    >
      <s-button
        slot="primary-action"
        variant="primary"
        onClick={() => window.location.reload()}
      >
        Run audit again
      </s-button>
      {showExport ? (
        <Form
          method="post"
          reloadDocument
          slot="secondary-actions"
        >
          <input
            type="hidden"
            name="intent"
            value="exportCsv"
          />
          <s-button
            type="submit"
            variant="secondary"
          >
            Export diagnostic CSV
          </s-button>
        </Form>
      ) : null}

      {demo ? (
        <s-banner
          heading="Sample audit preview"
          tone="info"
        >
          This public preview uses labeled sample
          catalog records and the same local coverage
          rules as the installed app.
        </s-banner>
      ) : null}

      <s-banner
        heading="Read-only taxonomy coverage"
        tone="info"
      >
        The app reports category assignment and
        category-constrained product metafield
        coverage. It never guesses or writes
        categories or attribute values.
      </s-banner>
      {coverageLimited ? (
        <s-banner
          heading="Safety limit reached"
          tone="warning"
        >
          This run reached a synchronous scan limit.
          The dashboard and CSV include only the
          products and definitions scanned in this run.
        </s-banner>
      ) : null}

      <s-section heading="Category-field coverage">
        <s-stack direction="block" gap="base">
          <s-paragraph>
            {shopName} · Scanned{" "}
            {audit.summary.productsScanned} products
            and {audit.summary.attributesChecked}{" "}
            applicable category fields at {scannedAt}.
          </s-paragraph>
          <s-paragraph>
            Coverage is based on Shopify product
            categories and product metafield
            definitions constrained to those
            categories.
          </s-paragraph>
          <div className={styles.metrics}>
            <div className={styles.metricWarning}>
              <span>Missing category fields</span>
              <strong>
                {audit.summary.missingAttributes}
              </strong>
            </div>
            <div className={styles.metricWarning}>
              <span>Products with gaps</span>
              <strong>
                {audit.summary.productsWithGaps}
              </strong>
            </div>
            <div className={styles.metric}>
              <span>Products without category</span>
              <strong>
                {audit.summary.productsWithoutCategory}
              </strong>
            </div>
            <div className={styles.metricSuccess}>
              <span>Populated fields</span>
              <strong>
                {audit.summary.populatedAttributes}
              </strong>
            </div>
          </div>
        </s-stack>
      </s-section>

      <s-section
        heading="Missing category-specific fields"
      >
        {missingRows.length === 0 ? (
          <s-banner
            heading="No missing fields found"
            tone="success"
          >
            No missing values were found among the
            applicable category-constrained fields
            scanned in this run.
          </s-banner>
        ) : (
          <>
            <s-paragraph>
              Review these observed gaps in Shopify
              Admin. The app does not recommend what
              any value should be.
            </s-paragraph>
            <EvidenceTable
              rows={missingRows}
              shopDomain={shopDomain}
              demo={demo}
            />
            {missingRows.length > DISPLAY_LIMIT ? (
              <p className={styles.tableNote}>
                Showing the first {DISPLAY_LIMIT}{" "}
                missing fields. Export the CSV for the
                complete scanned set.
              </p>
            ) : null}
          </>
        )}
      </s-section>

      <s-section
        heading="Products without a taxonomy category"
      >
        {noCategory.length === 0 ? (
          <s-banner
            heading="Every scanned product has a category"
            tone="success"
          >
            All scanned products have a Shopify
            taxonomy category assigned.
          </s-banner>
        ) : (
          <>
            <s-paragraph>
              A category is required before
              category-specific coverage can be
              evaluated.
            </s-paragraph>
            <NoCategoryTable
              products={noCategory}
              shopDomain={shopDomain}
              demo={demo}
            />
            {noCategory.length > DISPLAY_LIMIT ? (
              <p className={styles.tableNote}>
                Showing the first {DISPLAY_LIMIT}{" "}
                uncategorized products. Export the CSV
                for the complete scanned set.
              </p>
            ) : null}
          </>
        )}
      </s-section>

      <s-section
        heading="Observed category-specific values"
      >
        {populatedRows.length === 0 ? (
          <s-banner
            heading="No populated fields found"
            tone="warning"
          >
            None of the applicable scanned fields has
            an observed value.
          </s-banner>
        ) : (
          <>
            <s-paragraph>
              These values are shown as observed. The
              app does not judge whether a value is
              correct for the product.
            </s-paragraph>
            <EvidenceTable
              rows={populatedRows}
              shopDomain={shopDomain}
              demo={demo}
            />
            {populatedRows.length > DISPLAY_LIMIT ? (
              <p className={styles.tableNote}>
                Showing the first {DISPLAY_LIMIT}{" "}
                populated fields. Export the CSV for
                the complete scanned set.
              </p>
            ) : null}
          </>
        )}
      </s-section>

      <s-section heading="What the audit does">
        <s-unordered-list>
          <s-list-item>
            Reads products, assigned Shopify taxonomy
            categories, product metafields, and
            category constraints on product metafield
            definitions.
          </s-list-item>
          <s-list-item>
            Separates no-category products from
            categorized products with missing
            category-specific values.
          </s-list-item>
          <s-list-item>
            Exports the observed coverage status with
            direct Shopify Admin product links.
          </s-list-item>
          <s-list-item>
            Does not assign categories, invent values,
            or change products, inventory, orders,
            customers, or themes.
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
