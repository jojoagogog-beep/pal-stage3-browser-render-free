import { Form } from "react-router";
import type { AuditResult, CollectionAudit } from "../lib/collection-content-audit";
import { collectionAdminUrl } from "../lib/collection-content-audit";
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
        <s-table-header>Missing fields</s-table-header>
        <s-table-header>Description</s-table-header>
        <s-table-header>Image</s-table-header>
        <s-table-header>SEO</s-table-header>
      </s-table-header-row>
      <s-table-body>
        {collections.slice(0, DISPLAY_LIMIT).map((collection) => (
          <s-table-row key={collection.id}>
            <s-table-cell>
              <a className={styles.productLink} href={hrefFor(collection, shopDomain, demo)} target={demo ? undefined : "_blank"} rel={demo ? undefined : "noreferrer"}>
                {collection.title || "Untitled collection"}
              </a>
            </s-table-cell>
            <s-table-cell>{collection.gaps.join(", ") || "None"}</s-table-cell>
            <s-table-cell>{collection.description.trim() ? "Present" : "Missing"}</s-table-cell>
            <s-table-cell>{collection.image?.url ? "Present" : "Missing"}</s-table-cell>
            <s-table-cell>{collection.seo?.title?.trim() && collection.seo?.description?.trim() ? "Complete" : "Incomplete"}</s-table-cell>
          </s-table-row>
        ))}
      </s-table-body>
    </s-table>
  );
}

export function CollectionContentDashboard({
  audit, shopDomain, shopName, scannedAt,
  coverageLimited = false, showExport = true, demo = false,
}: Props) {
  return (
    <s-page heading="PAL Collection Content Guard" inlineSize="large">
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

      <s-banner heading="Read-only collection content audit" tone="info">
        The app reports observed collection content gaps. It never writes descriptions, images, SEO fields, or collection data.
      </s-banner>

      {coverageLimited ? (
        <s-banner heading="Safety limit reached" tone="warning">
          This run reached the synchronous collection scan limit. Results include only the collections scanned in this run.
        </s-banner>
      ) : null}

      <s-section heading="Collection content readiness">
        <s-stack direction="block" gap="base">
          <s-paragraph>{shopName} · Scanned {audit.summary.collectionsScanned} collections at {scannedAt}.</s-paragraph>
          <div className={styles.metrics}>
            <div className={styles.metricWarning}><span>Collections with gaps</span><strong>{audit.summary.collectionsWithGaps}</strong></div>
            <div className={styles.metricWarning}><span>Missing descriptions</span><strong>{audit.summary.missingDescriptions}</strong></div>
            <div className={styles.metric}><span>Missing images</span><strong>{audit.summary.missingImages}</strong></div>
            <div className={styles.metricSuccess}><span>Content-ready collections</span><strong>{audit.ready.length}</strong></div>
          </div>
        </s-stack>
      </s-section>

      <s-section heading="Collections with content gaps">
        {audit.withGaps.length === 0 ? (
          <s-banner heading="No content gaps found" tone="success">
            Every scanned collection has a description, image, SEO title, and SEO description.
          </s-banner>
        ) : (
          <>
            <s-paragraph>Review the observed gaps in Shopify Admin. The app does not generate or write replacement content.</s-paragraph>
            <CollectionTable collections={audit.withGaps} shopDomain={shopDomain} demo={demo} />
          </>
        )}
      </s-section>

      <s-section heading="Content-ready collections">
        {audit.ready.length === 0 ? (
          <s-paragraph>No fully content-ready collections were found in this run.</s-paragraph>
        ) : (
          <CollectionTable collections={audit.ready} shopDomain={shopDomain} demo={demo} />
        )}
        {audit.collections.length > DISPLAY_LIMIT ? (
          <p className={styles.tableNote}>Tables show up to {DISPLAY_LIMIT} rows per section. Export the CSV for the complete scanned set.</p>
        ) : null}
      </s-section>
    </s-page>
  );
}
