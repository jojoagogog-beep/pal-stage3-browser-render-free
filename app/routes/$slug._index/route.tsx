import { useParams } from "react-router";
import { ruleModules } from "../../rules";

const restoredApps: Record<string, { title: string; lead: string }> = {
  "pal-variant-image-guard": {
    title: "PAL Variant Image Guard",
    lead: "Review variant image coverage and shared image assignments. Export a read-only remediation report.",
  },
  "pal-variant-order-guard": {
    title: "PAL Variant Order Guard",
    lead: "Review variant option ordering and consistency across your product catalog.",
  },
  "pal-feed-readiness-guard": {
    title: "PAL Feed Readiness Guard",
    lead: "Check catalog completeness and identifiers before exporting products to shopping feeds.",
  },
  "pal-import-row-integrity-guard": {
    title: "PAL Import Row Integrity Guard",
    lead: "Find duplicate SKUs, missing identifiers, and inconsistent inventory tracking in product variants.",
  },
};

export default function Landing() {
  const { slug = "" } = useParams();
  const restored = restoredApps[slug];
  const definition = ruleModules[slug as keyof typeof ruleModules] as any;
  if (!restored && !definition) return <main>Unknown app.</main>;
  const title = restored?.title || definition.appMeta.headline;
  const lead = restored?.lead || definition.appMeta.lead;
  return (
    <main style={{ fontFamily: "system-ui", maxWidth: 900, margin: "48px auto", padding: "0 24px" }}>
      <p>Practical AI Lab</p>
      <h1>{title}</h1>
      <p>{lead}</p>
      <h2>Read-only catalog QA</h2>
      <p>{restored ? "The app analyzes your catalog and exports review findings. It does not automatically edit product data." : definition.appMeta.readOnlyNote}</p>
      <p><a href={'/' + slug + '/review-demo'}>Explore the illustrative demo</a></p>
      <nav>
        <a href={'/' + slug + '/privacy'}>Privacy</a>{" · "}
        <a href={'/' + slug + '/terms'}>Terms</a>{" · "}
        <a href={'/' + slug + '/support'}>Support</a>
      </nav>
    </main>
  );
}
