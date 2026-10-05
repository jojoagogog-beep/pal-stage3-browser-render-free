import { Form } from "react-router";
import type { AuditResult, AuditedCollection } from "../lib/collection-image-ratio-audit";
import { collectionAdminUrl } from "../lib/collection-image-ratio-audit";
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

function CollectionTable({
  collections,
  shopDomain,
  demo,
}: {
  collections: AuditedCollection[];
  shopDomain: string;
  demo: boolean;
}) {
  return (
    <s-table variant="auto">
      <s-table-header-row>
        <s-table-header listSlot="primary">Collection</s-table-header>
        <s-table-header>Image size</s-table-header>
        <s-table-header>Ratio group</s-table-header>
        <s-table-header>Review</s-table-header>
      </s-table-header-row>
      <s-table-body>
        {collections.slice(0, DISPLAY_LIMIT).map((collection) => (
          <s-table-row key={collection.id}>
            <s-table-cell>
              <a
                className={styles.productLink}
                href={hrefFor(collection, shopDomain, demo)}
                target={demo ? undefined : "_blank"}
                rel={demo ? undefined : "noreferrer"}
              >
                {collection.title || "Untitled collection"}
              </a>
            </s-table-cell>
            <s-table-cell>
              {collection.image
                ? collection.image.width + " × " + collection.image.height
                : "No image"}
            </s-table-cell>
            <s-table-cell>{collection.ratioLabel}</s-table-cell>
            <s-table-cell>{collection.isOutlier ? "Ratio differs" : "—"}</s-table-cell>
          </s-table-row>
        ))}
      </s-table-body>
    </s-table>
  );
}

export function CollectionImageRatioDashboard({
  audit,
  shopDomain,
  shopName,
  scannedAt,
  coverageLimited = false,
  showExport = true,
  demo = false,
}: Props) {
  return (
    <s-page heading="PAL Collection Ratio Guard" inlineSize="large">
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
            Export diagnostic CSV
          </s-button>
        </Form>
      ) : null}

      {demo ? (
        <s-banner heading="Sample image-ratio audit" tone="info">
          This public preview uses fictional collection image dimensions and the same ratio-bucketing logic as the installed app.
        </s-banner>
      ) : null}

      <s-banner heading="Read-only collection image audit" tone="info">
        The app reads collection image dimensions and groups common aspect ratios. It never uploads, crops, or edits images.
      </s-banner>

      {coverageLimited ? (
        <s-banner heading="Safety limit reached" tone="warning">
          This run reached the synchronous collection scan limit.
        </s-banner>
      ) : null}

      <s-section heading="Image ratio summary">
        <s-stack direction="block" gap="base">
          <s-paragraph>
            {shopName} · Scanned {audit.summary.collectionsScanned} collections at {scannedAt}.
          </s-paragraph>
          <div className={styles.metrics}>
            <div className={styles.metric}>
              <span>Collections with images</span>
              <strong>{audit.summary.collectionsWithImages}</strong>
            </div>
            <div className={styles.metric}>
              <span>Dominant ratio</span>
              <strong>{audit.dominantRatioLabel ?? "—"}</strong>
            </div>
            <div className={styles.metricWarning}>
              <span>Ratio outliers</span>
              <strong>{audit.summary.outliers}</strong>
            </div>
            <div className={styles.metric}>
              <span>Ratio groups</span>
              <strong>{audit.summary.ratioGroups}</strong>
            </div>
          </div>
        </s-stack>
      </s-section>

      <s-section heading="Collections with different image ratios">
        {audit.outliers.length === 0 ? (
          <s-banner heading="No ratio outliers found" tone="success">
            All scanned collection images use the same practical aspect-ratio group.
          </s-banner>
        ) : (
          <CollectionTable
            collections={audit.outliers}
            shopDomain={shopDomain}
            demo={demo}
          />
        )}
      </s-section>

      <s-section heading="Collections missing images">
        {audit.missingImages.length === 0 ? (
          <s-banner heading="No missing collection images" tone="success">
            Every scanned collection has an image.
          </s-banner>
        ) : (
          <CollectionTable
            collections={audit.missingImages}
            shopDomain={shopDomain}
            demo={demo}
          />
        )}
      </s-section>

      <s-section heading="All collection image ratios">
        <CollectionTable
          collections={audit.withImages}
          shopDomain={shopDomain}
          demo={demo}
        />
      </s-section>
    </s-page>
  );
}
