import { Form } from "react-router";
import type { AuditResult, CollectionAudit } from "../lib/empty-collection-audit";
import { collectionAdminUrl } from "../lib/empty-collection-audit";
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

function hrefFor(collection: CollectionAudit, shopDomain: string, demo: boolean) {
  return demo ? "#collection-" + collection.legacyResourceId : collectionAdminUrl(shopDomain, collection.legacyResourceId);
}

function CollectionTable({ collections, shopDomain, demo }: {
  collections: CollectionAudit[];
  shopDomain: string;
  demo: boolean;
}) {
  return (
    <s-table variant="auto">
      <s-table-header-row>
        <s-table-header listSlot="primary">Collection</s-table-header>
        <s-table-header>Type</s-table-header>
        <s-table-header>Products</s-table-header>
        <s-table-header>Observed rules</s-table-header>
      </s-table-header-row>
      <s-table-body>
        {collections.slice(0, DISPLAY_LIMIT).map((collection) => (
          <s-table-row key={collection.id}>
            <s-table-cell>
              <a className={styles.productLink} href={hrefFor(collection, shopDomain, demo)} target={demo ? undefined : "_blank"} rel={demo ? undefined : "noreferrer"}>
                {collection.title || "Untitled collection"}
              </a>
            </s-table-cell>
            <s-table-cell>{collection.kind}</s-table-cell>
            <s-table-cell>
              <s-badge tone={collection.empty ? "warning" : "success"}>
                {collection.productsCount}
              </s-badge>
            </s-table-cell>
            <s-table-cell>{collection.ruleSummary}</s-table-cell>
          </s-table-row>
        ))}
      </s-table-body>
    </s-table>
  );
}

export function EmptyCollectionDashboard({
  audit,
  shopDomain,
  shopName,
  scannedAt,
  coverageLimited = false,
  showExport = true,
  demo = false,
}: Props) {
  const nonEmpty = audit.collections.filter((collection) => !collection.empty);
  return (
    <s-page heading="PAL Empty Collection Guard" inlineSize="large">
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
          This public preview uses fictional collection records and the same local audit rules as the installed app.
        </s-banner>
      ) : null}

      <s-banner heading="Read-only collection audit" tone="info">
        The app reports empty collections and observed automated rules. It never deletes collections or changes storefront content.
      </s-banner>

      {coverageLimited ? (
        <s-banner heading="Safety limit reached" tone="warning">
          This run reached the synchronous collection scan limit. Results include only the collections scanned in this run.
        </s-banner>
      ) : null}

      <s-section heading="Empty collection summary">
        <s-stack direction="block" gap="base">
          <s-paragraph>{shopName} · Scanned {audit.summary.collectionsScanned} collections at {scannedAt}.</s-paragraph>
          <div className={styles.metrics}>
            <div className={styles.metricWarning}><span>Empty collections</span><strong>{audit.summary.emptyCollections}</strong></div>
            <div className={styles.metricWarning}><span>Empty automated</span><strong>{audit.summary.emptyAutomated}</strong></div>
            <div className={styles.metric}><span>Empty manual</span><strong>{audit.summary.emptyManual}</strong></div>
            <div className={styles.metricSuccess}><span>Collections with products</span><strong>{nonEmpty.length}</strong></div>
          </div>
        </s-stack>
      </s-section>

      <s-section heading="Empty automated collections">
        {audit.emptyAutomated.length === 0 ? (
          <s-banner heading="No empty automated collections found" tone="success">Every automated collection scanned currently contains at least one product.</s-banner>
        ) : (
          <>
            <s-paragraph>Review the observed rules before changing anything in Shopify Admin.</s-paragraph>
            <CollectionTable collections={audit.emptyAutomated} shopDomain={shopDomain} demo={demo} />
          </>
        )}
      </s-section>

      <s-section heading="Empty manual collections">
        {audit.emptyManual.length === 0 ? (
          <s-paragraph>No empty manual collections were found in this run.</s-paragraph>
        ) : (
          <CollectionTable collections={audit.emptyManual} shopDomain={shopDomain} demo={demo} />
        )}
      </s-section>

      <s-section heading="Collections with products">
        <CollectionTable collections={nonEmpty} shopDomain={shopDomain} demo={demo} />
        {audit.collections.length > DISPLAY_LIMIT ? (
          <p className={styles.tableNote}>Tables show up to {DISPLAY_LIMIT} rows per section. Export the CSV for the complete scanned set.</p>
        ) : null}
      </s-section>
    </s-page>
  );
}
