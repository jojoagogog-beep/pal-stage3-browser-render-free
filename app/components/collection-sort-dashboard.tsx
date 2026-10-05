import { Form } from "react-router";
import type { AuditResult, AuditedCollection } from "../lib/collection-sort-audit";
import { collectionAdminUrl } from "../lib/collection-sort-audit";
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

function hrefFor(collection: AuditedCollection, shopDomain: string, demo: boolean) {
  return demo
    ? "#collection-" + collection.legacyResourceId
    : collectionAdminUrl(shopDomain, collection.legacyResourceId);
}

function CollectionTable({ collections, shopDomain, demo }: {
  collections: AuditedCollection[];
  shopDomain: string;
  demo: boolean;
}) {
  return (
    <s-table variant="auto">
      <s-table-header-row>
        <s-table-header listSlot="primary">Collection</s-table-header>
        <s-table-header>Sort order</s-table-header>
        <s-table-header>Manual sort</s-table-header>
      </s-table-header-row>
      <s-table-body>
        {collections.slice(0, DISPLAY_LIMIT).map((collection) => (
          <s-table-row key={collection.id}>
            <s-table-cell>
              <a className={styles.productLink}
                 href={hrefFor(collection, shopDomain, demo)}
                 target={demo ? undefined : "_blank"}
                 rel={demo ? undefined : "noreferrer"}>
                {collection.title || "Untitled collection"}
              </a>
            </s-table-cell>
            <s-table-cell>{collection.sortOrder}</s-table-cell>
            <s-table-cell>{collection.manualSort ? "Yes" : "No"}</s-table-cell>
          </s-table-row>
        ))}
      </s-table-body>
    </s-table>
  );
}

export function CollectionSortDashboard({
  audit, shopDomain, shopName, scannedAt,
  coverageLimited = false, showExport = true, demo = false,
}: Props) {
  return (
    <s-page heading="PAL Collection Sort Guard" inlineSize="large">
      <s-button slot="primary-action" variant="primary"
        onClick={() => window.location.reload()}>
        Run audit again
      </s-button>

      {showExport ? (
        <Form method="post" reloadDocument slot="secondary-actions">
          <input type="hidden" name="intent" value="exportCsv" />
          <s-button type="submit" variant="secondary">
            Export diagnostic CSV
          </s-button>
        </Form>
      ) : null}

      {demo ? (
        <s-banner heading="Sample sort audit preview" tone="info">
          This public preview uses fictional collections and the same audit logic.
        </s-banner>
      ) : null}

      <s-banner heading="Read-only collection sort audit" tone="info">
        The app reports current collection sort modes. It never changes collection order.
      </s-banner>

      {coverageLimited ? (
        <s-banner heading="Safety limit reached" tone="warning">
          This run reached the synchronous collection scan limit.
        </s-banner>
      ) : null}

      <s-section heading="Sort-order inventory">
        <s-stack direction="block" gap="base">
          <s-paragraph>{shopName} · Scanned {audit.summary.collectionsScanned} collections at {scannedAt}.</s-paragraph>
          <div className={styles.metrics}>
            <div className={styles.metricWarning}><span>Manual sort</span><strong>{audit.summary.manualSortCollections}</strong></div>
            <div className={styles.metric}><span>Automatic sort</span><strong>{audit.summary.automaticSortCollections}</strong></div>
            <div className={styles.metricSuccess}><span>Sort modes used</span><strong>{audit.summary.sortModesUsed}</strong></div>
          </div>
        </s-stack>
      </s-section>

      <s-section heading="Collections using manual sort">
        {audit.manual.length === 0 ? (
          <s-banner heading="No manual-sort collections found" tone="success">
            Every scanned collection uses a non-manual sort mode.
          </s-banner>
        ) : (
          <CollectionTable collections={audit.manual} shopDomain={shopDomain} demo={demo} />
        )}
      </s-section>

      <s-section heading="Collections using automatic sort">
        {audit.automatic.length === 0 ? (
          <s-paragraph>No automatically sorted collections were found in this run.</s-paragraph>
        ) : (
          <CollectionTable collections={audit.automatic} shopDomain={shopDomain} demo={demo} />
        )}
      </s-section>

      <s-section heading="Sort-mode breakdown">
        <s-stack direction="block" gap="base">
          {Object.entries(audit.counts).map(([mode, count]) => (
            <s-paragraph key={mode}>{mode}: {count}</s-paragraph>
          ))}
        </s-stack>
      </s-section>
    </s-page>
  );
}
