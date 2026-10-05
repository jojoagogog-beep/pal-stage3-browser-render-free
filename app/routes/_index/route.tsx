import styles from "./styles.module.css";
export default function Landing(){
 return <main className={styles.page}>
  <section className={styles.hero}>
   <div className={styles.eyebrow}>PAL · COLLECTION IMAGE AUDIT</div>
   <h1>Review collection-image aspect ratios before merchandising changes.</h1>
   <p className={styles.lead}>PAL Collection Ratio Guard groups observed collection-image dimensions into practical ratio buckets and highlights ratio outliers without changing images.</p>
   <div className={styles.badges}><span>Read-only audit</span><span>Image dimensions</span><span>CSV worklist</span></div>
   <p className={styles.installNote}>Install and open the app from its Shopify App Store listing or Shopify admin.</p>
  </section>
  <section className={styles.grid}>
   <article><h2>See the dominant ratio</h2><p>Identify the most common observed aspect-ratio group across collection images.</p></article>
   <article><h2>Find ratio outliers</h2><p>Review collections whose image ratio differs from the dominant observed ratio.</p></article>
   <article><h2>Keep image changes merchant-controlled</h2><p>Open affected collections and export a diagnostic worklist without uploading or cropping images.</p></article>
  </section>
  <nav className={styles.links}><a href="/privacy">Privacy</a><a href="/terms">Terms</a><a href="/support">Support</a></nav>
 </main>
}
