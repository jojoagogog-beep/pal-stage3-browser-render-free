import { PublicPage } from "../components/public-page";
export const meta=()=>[{title:"Support · PAL Product Image Alt Guard"}];
export default function Support(){return <PublicPage title="Support" intro="Get help with tag findings, normalization cues, CSV exports, or installation access.">
<h2>Contact</h2><p>Email practicalai_lab_jp@proton.me. Include your myshopify.com domain, the approximate audit time, and the exact error shown.</p>
<h2>Before contacting support</h2><ul><li>Reload the app and run the audit again.</li><li>Confirm the app still has read-products access.</li><li>For CSV questions, include the product title and observed vendor value, but do not attach customer data.</li><li>Never send passwords, Shopify access tokens, payment information, or customer records.</li></ul>
<h2>What the app does not do</h2><p>The app does not merge vendors or edit products. It highlights likely naming drift for merchant review.</p>
</PublicPage>}
