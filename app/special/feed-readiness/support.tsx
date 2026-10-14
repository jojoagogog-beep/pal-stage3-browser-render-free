import { PublicPage } from "./components/public-page";

export const meta = () => [{ title: "Support · PAL Feed Readiness Guard" }];

export default function Support() {
  return (
    <PublicPage
      title="Support"
      intro="Get help with catalog audits, identifier classification, CSV exports, or installation access."
    >
      <h2>Contact</h2>
      <p>
        Email practicalai_lab_jp@proton.me from an address associated with your
        business. Include your myshopify.com domain, the approximate time of the
        audit, and the exact error message shown.
      </p>

      <h2>Before contacting support</h2>
      <ul>
        <li>Reload the embedded app and run the audit again.</li>
        <li>
          Confirm the app still has read-products access in Shopify admin.
        </li>
        <li>
          For CSV questions, include the issue label and product title, but do
          not attach customer data.
        </li>
        <li>
          Never send a password, Shopify access token, payment information, or
          customer records.
        </li>
      </ul>

      <h2>What the app does not do</h2>
      <p>
        The app does not edit products, create identifiers, connect to Google or
        Meta accounts, or decide whether a channel will approve a product.
        Product links in the audit open the relevant Shopify admin record so the
        merchant can review and make changes directly.
      </p>
    </PublicPage>
  );
}
