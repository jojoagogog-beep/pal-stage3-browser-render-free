import {Form, useActionData, useLoaderData, useNavigation, useRevalidator} from "react-router";
import type {loader, action} from "./route.server";
import styles from "../../styles/filter-dashboard.module.css";
const DISPLAY_SCAN_LIMIT = 500;

function productAdminHref(productId: string) {
  return `shopify://admin/products/${productId.split("/").pop()}`;
}

function downloadIssuesCsv(issues: Array<{
  kind: string;
  source: string;
  field: string;
  productId: string;
  productTitle: string;
  observedValue: string;
  suggestedValue: string;
  collections: string[];
}>) {
  const cell = (value: string) => /[",\r\n]/.test(value) ? `"${value.replaceAll('"', '""')}"` : value;
  const rows = [
    ["Issue", "Source", "Field", "Product", "Observed value", "Suggested value", "Collections", "Shopify Admin link"],
    ...issues.map((issue) => [
      issue.kind,
      issue.source,
      issue.field,
      issue.productTitle,
      issue.observedValue,
      issue.suggestedValue,
      issue.collections.join(" | "),
      productAdminHref(issue.productId),
    ]),
  ];
  const csv = `\uFEFF${rows.map((row) => row.map((value) => cell(String(value))).join(",")).join("\r\n")}\r\n`;
  const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = `pal-filter-remediation-${new Date().toISOString().slice(0, 10)}.csv`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

export default function Index() {
  const { shopName, truncated, audit, selections, scanError } = useLoaderData<typeof loader>();
  const result = useActionData<typeof action>();
  const navigation = useNavigation();
  const revalidator = useRevalidator();
  const saving = navigation.state === "submitting";
  const rescanning = revalidator.state === "loading";
  const issues = audit?.issues || [];

  return (
    <s-page heading="PAL Filter Integrity Guard">
      <div className={styles.shell}>
        <div className={styles.introRow}>
          <div>
            <p className={styles.eyebrow}>READ-ONLY FILTER HEALTH</p>
            <h2 className={styles.title}>Find filter gaps before shoppers do</h2>
            <p className={styles.lead}>
              Scan product options, tags, and chosen metafields for missing or fragmented values. PAL suggests a
              normalization target but never changes catalog data.
            </p>
          </div>
          <div className={styles.actions}>
            <button className={styles.secondaryButton} type="button" onClick={() => revalidator.revalidate()} disabled={rescanning}>
              {rescanning ? "Scanning…" : "Run scan again"}
            </button>
            <button className={styles.primaryButton} type="button" onClick={() => downloadIssuesCsv(issues)} disabled={!issues.length}>
              Export remediation CSV
            </button>
          </div>
        </div>

        {scanError ? (
          <div className={styles.errorNotice} role="alert"><strong>Scan unavailable.</strong> {scanError} No catalog data was changed.</div>
        ) : null}
        {result ? (
          <div className={result.ok ? styles.successNotice : styles.errorNotice} role="status">
            {result.ok ? result.message : result.error}
          </div>
        ) : null}

        <section className={styles.summaryCard} aria-labelledby="summary-heading">
          <div>
            <p className={styles.cardLabel}>CURRENT SCAN</p>
            <h3 id="summary-heading">{shopName}</h3>
            <p className={styles.muted}>
              {truncated
                ? `Showing the first ${DISPLAY_SCAN_LIMIT} products. Export contains the same bounded scan.`
                : "Results reflect the catalog values returned by Shopify at scan time."}
            </p>
          </div>
          <div className={styles.metrics}>
            <Metric label="Products scanned" value={audit?.summary.scannedProducts ?? "—"} />
            <Metric label="Affected products" value={audit?.summary.affectedProducts ?? "—"} tone="warning" />
            <Metric label="Missing values" value={audit?.summary.missingValues ?? "—"} />
            <Metric label="Inconsistent values" value={audit?.summary.inconsistentValues ?? "—"} />
          </div>
        </section>

        <div className={styles.twoColumn}>
          <section className={styles.card} aria-labelledby="groups-heading">
            <div className={styles.cardHeader}>
              <div><p className={styles.cardLabel}>NORMALIZATION GROUPS</p><h3 id="groups-heading">Equivalent values to review</h3></div>
              <span className={styles.countBadge}>{audit?.summary.duplicateGroups ?? 0}</span>
            </div>
            {audit?.duplicateGroups.length ? (
              <div className={styles.groupList}>
                {audit.duplicateGroups.slice(0, 6).map((group) => (
                  <div className={styles.groupItem} key={`${group.source}-${group.field}-${group.suggestedValue}`}>
                    <div className={styles.groupTopline}><strong>{group.field}</strong><span>{group.source}</span></div>
                    <p>{group.variants.join(" · ")}</p>
                    <small>Suggested group label: <strong>{group.suggestedValue}</strong> · {group.affectedProducts} affected product{group.affectedProducts === 1 ? "" : "s"}</small>
                  </div>
                ))}
              </div>
            ) : <EmptyState text="No formatting-equivalent values were found in this scan." />}
          </section>

          <section className={styles.card} aria-labelledby="settings-heading">
            <p className={styles.cardLabel}>SCAN SETTINGS</p>
            <h3 id="settings-heading">Filter-enabled metafields</h3>
            <p className={styles.muted}>Add up to 10 product metafields as <code>namespace.key</code>, separated by commas or new lines. Product options and tags are always included.</p>
            <Form method="post" className={styles.settingsForm}>
              <input type="hidden" name="intent" value="saveMetafields" />
              <label htmlFor="metafields">Product metafields</label>
              <textarea id="metafields" name="metafields" rows={4} maxLength={1000} defaultValue={selections.map((selection) => selection.identifier).join("\n")} placeholder={"custom.color\ncustom.material"} />
              <button className={styles.primaryButton} type="submit" disabled={saving}>{saving ? "Saving and scanning…" : "Save and rescan"}</button>
            </Form>
            <p className={styles.helperText}>
              Common option fields in this scan: {audit?.optionFields.length ? audit.optionFields.join(", ") : "none"}. An option is treated as common when it appears on at least two products and 20% of the scanned catalog.
            </p>
          </section>
        </div>

        <section className={styles.card} aria-labelledby="issues-heading">
          <div className={styles.cardHeader}>
            <div><p className={styles.cardLabel}>REMEDIATION LIST</p><h3 id="issues-heading">Affected products and suggested next steps</h3></div>
            <span className={styles.countBadge}>{issues.length}</span>
          </div>
          <p className={styles.muted}>Missing options are suggestions for review, not proof of an error. PAL never writes the suggested values.</p>
          {issues.length ? (
            <div className={styles.tableWrap}>
              <table className={styles.table}>
                <thead><tr><th>Issue</th><th>Product</th><th>Field</th><th>Observed</th><th>Suggested</th><th>Collection</th></tr></thead>
                <tbody>
                  {issues.slice(0, 100).map((issue, index) => (
                    <tr key={`${issue.productId}-${issue.field}-${issue.observedValue}-${index}`}>
                      <td><span className={issue.kind === "Missing" ? styles.missingPill : styles.inconsistentPill}>{issue.kind}</span></td>
                      <td><a href={productAdminHref(issue.productId)} target="_top">{issue.productTitle}</a><small>{issue.source}</small></td>
                      <td>{issue.field}</td><td>{issue.observedValue || "—"}</td><td>{issue.suggestedValue}</td>
                      <td>{issue.collections.join(", ") || "Not in a collection"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {issues.length > 100 ? <p className={styles.tableNote}>Showing 100 of {issues.length} issues. Export the CSV for the complete remediation list.</p> : null}
            </div>
          ) : <EmptyState text={audit ? "No missing or inconsistent filter values were found." : "Run the scan again to load catalog results."} />}
        </section>

        <footer className={styles.footer}>
          <span>Read-only analysis · No theme changes · No customer data</span>
          <nav aria-label="Policies and support">
            <a href="/pal-filter-integrity-guard/privacy" target="_blank" rel="noreferrer">Privacy</a><a href="/pal-filter-integrity-guard/terms" target="_blank" rel="noreferrer">Terms</a><a href="/pal-filter-integrity-guard/support" target="_blank" rel="noreferrer">Support</a>
          </nav>
        </footer>
      </div>
    </s-page>
  );
}

function Metric({ label, value, tone }: { label: string; value: string | number; tone?: "warning" }) {
  return <div className={styles.metric}><span>{label}</span><strong className={tone === "warning" ? styles.warningText : undefined}>{value}</strong></div>;
}

function EmptyState({ text }: { text: string }) {
  return <div className={styles.emptyState}>{text}</div>;
}
