import { PublicPage } from "./components/public-page";

export const meta = () => [{ title: "Support · PAL Variant Order Guard" }];

export default function Support() {
  return (
    <PublicPage
      title="Support"
      intro="Get help with option-order audits, naming-drift findings, numeric-value reviews, CSV exports, or installation access."
    >
      <h2>Contact</h2>
      <p>
        Email practicalai_lab_jp@proton.me. Include your myshopify.com domain,
        the approximate time of the audit, and the exact error message shown.
      </p>

      <h2>Before contacting support</h2>
      <ul>
        <li>Reload the app and run the audit again.</li>
        <li>Confirm the app still has read-products access in Shopify admin.</li>
        <li>
          For CSV questions, include the issue label and product title, but do
          not attach customer data.
        </li>
        <li>
          Never send passwords, Shopify access tokens, payment information, or
          customer records.
        </li>
      </ul>

      <h2>What the app does not do</h2>
      <p>
        The app does not edit option order, rename options, reorder values, or
        modify theme code. Product links open the relevant Shopify admin record
        so the merchant can review differences directly.
      </p>
    </PublicPage>
  );
}
