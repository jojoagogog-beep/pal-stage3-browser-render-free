import type { AuditResult, ProductAudit } from "../lib/variant-image-audit";
import { ISSUE_DEFINITIONS } from "../lib/variant-image-audit";
import styles from "./media-capture.module.css";

type CaptureState = "overview" | "mixed" | "duplicates" | "export" | "clear";

type Props = {
  audit: AuditResult;
  state: CaptureState;
};

const copy: Record<CaptureState, { kicker: string; headline: string }> = {
  overview: {
    kicker: "Read-only variant image audit",
    headline: "See variant image gaps in one audit",
  },
  mixed: {
    kicker: "Mixed coverage",
    headline: "Find variants missing an assigned image",
  },
  duplicates: {
    kicker: "Shared assignments",
    headline: "Spot images shared across variants",
  },
  export: {
    kicker: "Review handoff",
    headline: "Take affected products into a clear CSV",
  },
  clear: {
    kicker: "Merchant control",
    headline: "Review the evidence. Keep every decision yours.",
  },
};

function Badge({ children, tone = "warning" }: { children: React.ReactNode; tone?: "warning" | "success" | "info" }) {
  return <span className={`${styles.badge} ${styles[tone]}`}>{children}</span>;
}

function AppHeader({ state }: { state: CaptureState }) {
  return (
    <header className={styles.appHeader}>
      <div>
        <div className={styles.appName}>PAL Variant Image Guard</div>
        <div className={styles.storeLine}>PAL Sample Catalog · Sample catalog preview</div>
      </div>
      <div className={styles.actions}>
        {state === "export" ? <button className={styles.primaryButton}>Export affected products</button> : null}
        <button className={state === "export" ? styles.secondaryButton : styles.primaryButton}>Run audit again</button>
      </div>
    </header>
  );
}

function Metrics({ audit, emphasize }: { audit: AuditResult; emphasize?: "mixed" | "duplicates" }) {
  const values = [
    ["Products to review", audit.summary.productsWithIssues, "review"],
    ["Mixed coverage", audit.summary.mixedCoverageProducts, "mixed"],
    ["Shared assignments", audit.summary.duplicateAssignmentProducts, "duplicates"],
    ["Variants missing images", audit.summary.variantsMissingImages, "missing"],
  ] as const;
  return (
    <div className={styles.metrics}>
      {values.map(([label, value, key]) => (
        <div
          className={`${styles.metric} ${key === "review" || key === emphasize ? styles.metricActive : ""}`}
          key={key}
        >
          <span>{label}</span>
          <strong>{value}</strong>
        </div>
      ))}
    </div>
  );
}

function ProductRow({ product, focus }: { product: ProductAudit; focus?: "mixed" | "duplicates" }) {
  const isMixed = product.issueKeys.includes("missing_dedicated_image");
  const status = focus === "duplicates" ? "Shared assignment" : product.status;
  return (
    <div className={styles.productRow}>
      <div>
        <strong>{product.title}</strong>
        <small>Sample product</small>
      </div>
      <Badge tone={isMixed ? "warning" : "info"}>{status}</Badge>
      <div className={styles.coverage}>
        <strong>{product.variantsWithImages}/{product.variants.length}</strong>
        <span>variants with images</span>
      </div>
      <div className={styles.coverage}>
        <strong>{product.duplicateAssignments.length || "—"}</strong>
        <span>shared images</span>
      </div>
    </div>
  );
}

function OverviewPanel({ audit }: { audit: AuditResult }) {
  return (
    <>
      <div className={styles.notice}><span>i</span><div><strong>Sample catalog preview</strong><p>Uses labeled sample products and the same audit logic as the installed app.</p></div></div>
      <section className={styles.section}>
        <div className={styles.sectionHeading}>
          <div><small>VARIANT IMAGE ASSIGNMENT AUDIT</small><h2>Catalog review queue</h2></div>
          <Badge tone="info">Read only</Badge>
        </div>
        <Metrics audit={audit} />
      </section>
      <section className={`${styles.section} ${styles.compactSection}`}>
        <div className={styles.sectionHeading}><div><small>AFFECTED PRODUCTS</small><h2>Start with the clearest assignment gaps</h2></div><span className={styles.scanned}>4 products · 11 variants scanned</span></div>
        <div className={styles.productList}>{audit.affectedProducts.map((product) => <ProductRow product={product} key={product.id} />)}</div>
      </section>
    </>
  );
}

function FindingPanel({ audit, state }: { audit: AuditResult; state: "mixed" | "duplicates" }) {
  const product = audit.affectedProducts[0];
  const issue = state === "mixed" ? ISSUE_DEFINITIONS.missing_dedicated_image : ISSUE_DEFINITIONS.duplicate_image_assignment;
  const variants = state === "mixed" ? product.missingVariants : product.variants.filter((variant) => product.duplicateAssignments.some((item) => item.variantIds.includes(variant.id)));
  return (
    <>
      <section className={styles.section}>
        <div className={styles.sectionHeading}>
          <div><small>SAMPLE AUDIT RESULT</small><h2>{product.title}</h2></div>
          <Badge>{issue.priority}</Badge>
        </div>
        <Metrics audit={audit} emphasize={state} />
      </section>
      <section className={`${styles.section} ${styles.findingSection}`}>
        <div className={styles.findingHeader}>
          <div className={styles.findingIcon}>!</div>
          <div><small>FINDING</small><h2>{issue.label}</h2><p>{product.findings[state === "mixed" ? 0 : product.findings.length - 1]}</p></div>
        </div>
        <div className={styles.variantGrid}>
          {variants.map((variant) => (
            <div className={styles.variantCard} key={variant.id}>
              <div><strong>{variant.title}</strong><span>Sample variant</span></div>
              <Badge tone={variant.images.length ? "info" : "warning"}>{variant.images.length ? "Image shared" : "No image assigned"}</Badge>
            </div>
          ))}
        </div>
        <div className={styles.recommendation}><strong>Recommended review</strong><span>{issue.recommendation}</span></div>
      </section>
    </>
  );
}

function ExportPanel({ audit }: { audit: AuditResult }) {
  const mixed = audit.affectedProducts.find((product) => product.issueKeys.includes("missing_dedicated_image"));
  const duplicate = audit.affectedProducts.find((product) => product.issueKeys.includes("duplicate_image_assignment"));
  return (
    <section className={`${styles.section} ${styles.exportSection}`}>
      <div className={styles.sectionHeading}>
        <div><small>CSV PREVIEW · SAMPLE DATA</small><h2>Affected-products worklist</h2></div>
        <Badge tone="success">Ready to export</Badge>
      </div>
      <div className={styles.csvTable}>
        <div className={`${styles.csvRow} ${styles.csvHeader}`}><span>Finding</span><span>Product</span><span>Variant</span><span>Recommended next step</span></div>
        {mixed?.missingVariants.slice(0, 2).map((variant) => (
          <div className={styles.csvRow} key={variant.id}><span>Mixed coverage</span><span>{mixed.title}</span><span>{variant.title}</span><span>Review whether dedicated media is needed</span></div>
        ))}
        {duplicate?.duplicateAssignments.slice(0, 1).map((assignment) => (
          <div className={styles.csvRow} key={assignment.imageId}><span>Shared assignment</span><span>{duplicate.title}</span><span>{assignment.variantTitles.join(" + ")}</span><span>Confirm whether image reuse is intentional</span></div>
        ))}
      </div>
      <div className={styles.exportFoot}>
        <div><strong>What travels with the worklist</strong><p>Product, variant, finding, evidence, and a cautious recommended review step.</p></div>
        <div className={styles.filePill}><span>CSV</span> variant-image-guard-sample.csv</div>
      </div>
    </section>
  );
}

function ClearPanel({ audit }: { audit: AuditResult }) {
  return (
    <>
      <section className={styles.section}>
        <div className={styles.sectionHeading}><div><small>SAMPLE AUDIT RESULT</small><h2>No mixed or shared assignments found</h2></div><Badge tone="success">Review complete</Badge></div>
        <Metrics audit={audit} />
      </section>
      <section className={`${styles.section} ${styles.controlSection}`}>
        <div className={styles.controlHero}><div className={styles.shield}>✓</div><div><small>READ-ONLY BY DESIGN</small><h2>The app reports assignment evidence</h2><p>It never changes product media, variants, themes, or storefront behavior.</p></div></div>
        <div className={styles.boundaries}>
          <div><span>1</span><p><strong>Run the audit</strong>Check current variant image assignments.</p></div>
          <div><span>2</span><p><strong>Review the evidence</strong>Open the focused product worklist.</p></div>
          <div><span>3</span><p><strong>Choose what changes</strong>Every catalog decision stays with the merchant.</p></div>
        </div>
        <p className={styles.clearNote}>Sample note: products with no dedicated variant images are counted separately and are not flagged as mixed coverage.</p>
      </section>
    </>
  );
}

export function MediaCapture({ audit, state }: Props) {
  return (
    <main className={styles.canvas} data-capture-state={state}>
      <div className={styles.backdropOrb} />
      <section className={styles.story}>
        <div className={styles.brandMark}><span>PAL</span><b>Variant Image Guard</b></div>
        <div className={styles.copyBlock}><p>{copy[state].kicker}</p><h1>{copy[state].headline}</h1></div>
        <div className={styles.proofLine}><span>✓</span> Local sample data · Actual audit logic</div>
      </section>
      <section className={styles.appFrame}>
        <AppHeader state={state} />
        <div className={styles.appBody}>
          {state === "overview" ? <OverviewPanel audit={audit} /> : null}
          {state === "mixed" || state === "duplicates" ? <FindingPanel audit={audit} state={state} /> : null}
          {state === "export" ? <ExportPanel audit={audit} /> : null}
          {state === "clear" ? <ClearPanel audit={audit} /> : null}
        </div>
      </section>
    </main>
  );
}
