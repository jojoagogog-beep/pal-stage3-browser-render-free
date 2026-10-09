import { redirect, type LoaderFunctionArgs } from "react-router";
export const loader = ({request}: LoaderFunctionArgs) => {
  const u = new URL(request.url);
  if (u.searchParams.has("shop")) return redirect("/app" + u.search);
  return null;
};
import styles from "./styles.module.css";
export default function Landing(){return <main className={styles.page}><section className={styles.hero}><div className={styles.eyebrow}>PAL · READ-ONLY PRODUCT AUDIT</div><h1>Find active products not updated in over 365 days.</h1><p className={styles.lead}>PAL Active Product Age Guard gives merchants a focused read-only catalog review with direct product links and CSV export.</p><div className={styles.badges}><span>Read-only audit</span><span>Product evidence</span><span>CSV worklist</span></div></section><section className={styles.grid}><article><h2>Focused review</h2><p>Surface only the product records that match this audit condition.</p></article><article><h2>Direct Admin links</h2><p>Open the matching Shopify Admin product from the diagnostic table.</p></article><article><h2>No catalog edits</h2><p>The app never changes product content or configuration.</p></article></section><nav className={styles.links}><a href="/privacy">Privacy</a><a href="/terms">Terms</a><a href="/support">Support</a></nav></main>;}