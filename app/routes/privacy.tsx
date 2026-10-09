import { PublicPage } from "../components/public-page";
export const meta=()=>[{title:"Privacy Policy · PAL Active Product Age Guard"}];
export default function Privacy(){return <PublicPage title="Privacy Policy" intro="PAL Active Product Age Guard is a read-only catalog freshness audit. This policy explains the limited Shopify data processed to provide that audit.">
<h2>Data we process</h2><p>After installation, the app processes the shop domain and Shopify authentication session information required to keep the app connected and secure. An audit reads product identifiers, product titles, product status, and last-updated timestamps.</p>
<h2>How we use data</h2><p>These catalog signals are used only to calculate the audit shown to the merchant and to create a diagnostic CSV when requested. The app does not require protected customer records and does not write product, vendor, theme, order, or customer data.</p>
<h2>Storage and sharing</h2><p>Catalog audit results are generated on request and are not stored as merchant analytics. Shopify session records are stored for authentication. We do not sell merchant data.</p>
<h2>Retention and deletion</h2><p>Session records are removed through uninstall and shop-redact handling. Mandatory privacy webhooks are supported even though the app does not request protected customer data.</p>
<h2>Contact</h2><p>For privacy questions, email practicalai_lab_jp@proton.me. Include the shop domain, but never send passwords, access tokens, or customer data.</p>
</PublicPage>}
