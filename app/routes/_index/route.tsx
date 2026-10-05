import type { LoaderFunctionArgs } from "react-router";
import { redirect } from "react-router";
import styles from "./styles.module.css";

export const loader = async ({ request }: LoaderFunctionArgs) => {
  const url = new URL(request.url);
  if (url.searchParams.get("shop")) throw redirect("/app?" + url.searchParams.toString());
  return null;
};

export default function Landing() {
  return (
    <main className={styles.page}>
      <section className={styles.hero}>
        <div className={styles.eyebrow}>PAL · COLLECTION RULE AUDIT</div>
        <h1>Review automated collection sorts before merchandising changes.</h1>
        <p className={styles.lead}>
          Collection Rule Guard creates a read-only inventory of manual and automated collection sorts without changing store data.
        </p>
        <div className={styles.badges}>
          <span>Read-only rule audit</span>
          <span>ANY · ALL · duplicate rules</span>
          <span>Diagnostic CSV export</span>
        </div>
        <p className={styles.installNote}>Install and open the app from its Shopify App Store listing or Shopify admin.</p>
      </section>
      <section className={styles.grid}>
        <article><h2>Inspect automated rules</h2><p>See which collections use automated rules and how many.</p></article>
        <article><h2>Review ANY and ALL matching</h2><p>See whether automated collections match all rules or any rule.</p></article>
        <article><h2>Find exact duplicates</h2><p>Open the matching Shopify Admin collection or export a rule inventory. The app never edits collection logic.</p></article>
      </section>
      <nav className={styles.links}>
        <a href="/privacy">Privacy</a>
        <a href="/terms">Terms</a>
        <a href="/support">Support</a>
      </nav>
    </main>
  );
}
