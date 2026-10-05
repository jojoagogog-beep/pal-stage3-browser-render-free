import { Form } from "react-router";
import type { AuditResult, AuditedCollection } from "../lib/collection-rule-audit";
import { collectionAdminUrl } from "../lib/collection-rule-audit";
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
  return demo ? "#collection-" + collection.legacyResourceId
    : collectionAdminUrl(shopDomain, collection.legacyResourceId);
}

function RuleSummary({ collection }: { collection: AuditedCollection }) {
  if (!collection.ruleSet) return <>Manual collection</>;
  if (collection.ruleSet.rules.length === 0) return <>No rules observed</>;
  return <>{collection.ruleSet.rules.slice(0, 3).map((r) =>
    `${r.column} ${r.relation} ${r.condition}`).join(" · ")}</>;
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
        <s-table-header>Type</s-table-header>
        <s-table-header>Match mode</s-table-header>
        <s-table-header>Rules</s-table-header>
        <s-table-header>Exact duplicates</s-table-header>
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
            <s-table-cell>{collection.mode === "Manual" ? "Manual" : "Automated"}</s-table-cell>
            <s-table-cell>{collection.mode}</s-table-cell>
            <s-table-cell>{collection.ruleCount}</s-table-cell>
            <s-table-cell>{collection.duplicateRuleCount}</s-table-cell>
          </s-table-row>
        ))}
      </s-table-body>
    </s-table>
  );
}

export function CollectionRuleDashboard({
  audit, shopDomain, shopName, scannedAt,
  coverageLimited = false, showExport = true, demo = false,
}: Props) {
  return (
    <s-page heading="PAL Collection Rule Guard" inlineSize="large">
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
        <s-banner heading="Sample rule audit preview" tone="info">
          This public preview uses fictional collection rules and the same audit logic.
        </s-banner>
      ) : null}

      <s-banner heading="Read-only collection rule audit" tone="info">
        The app inventories observed collection rules. It never changes collection logic.
      </s-banner>

      {coverageLimited ? (
        <s-banner heading="Safety limit reached" tone="warning">
          This run reached the synchronous collection scan limit.
        </s-banner>
      ) : null}

      <s-section heading="Rule inventory">
        <s-stack direction="block" gap="base">
          <s-paragraph>{shopName} · Scanned {audit.summary.collectionsScanned} collections at {scannedAt}.</s-paragraph>
          <div className={styles.metrics}>
            <div className={styles.metric}><span>Automated collections</span><strong>{audit.summary.automatedCollections}</strong></div>
            <div className={styles.metric}><span>ANY-match</span><strong>{audit.summary.anyMatchCollections}</strong></div>
            <div className={styles.metric}><span>ALL-match</span><strong>{audit.summary.allMatchCollections}</strong></div>
            <div className={styles.metricWarning}><span>Exact duplicate rules</span><strong>{audit.summary.collectionsWithDuplicates}</strong></div>
          </div>
        </s-stack>
      </s-section>

      <s-section heading="Collections needing review">
        {audit.needsReview.length === 0 ? (
          <s-banner heading="No exact duplicate rules found" tone="success">
            No scanned automated collection contained an exact duplicate rule.
          </s-banner>
        ) : (
          <>
            <s-paragraph>These collections contain repeated rules with the same column, relation, and condition.</s-paragraph>
            <CollectionTable collections={audit.needsReview} shopDomain={shopDomain} demo={demo} />
          </>
        )}
      </s-section>

      <s-section heading="Automated collections">
        <CollectionTable collections={audit.automated} shopDomain={shopDomain} demo={demo} />
        {audit.automated.slice(0, 5).map((collection) => (
          <p key={collection.id} className={styles.tableNote}>
            <strong>{collection.title}:</strong> <RuleSummary collection={collection} />
          </p>
        ))}
      </s-section>

      <s-section heading="Manual collections">
        <CollectionTable collections={audit.manual} shopDomain={shopDomain} demo={demo} />
      </s-section>
    </s-page>
  );
}
