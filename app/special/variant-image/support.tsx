import { PublicPage } from "./components/public-page";

export const meta = () => [{ title: "Support · PAL Variant Image Guard" }];

export default function Support() {
  return (
    <PublicPage
      title="Support"
      intro="Get help with image-coverage audits, shared-assignment findings, CSV exports, or installation access."
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
          For CSV questions, include the finding label and product title, but do
          not attach customer or credential data.
        </li>
        <li>
          Never send passwords, Shopify access tokens, payment information, or
          customer records.
        </li>
      </ul>

      <h2>What the app does not do</h2>
      <p>
        The app does not assign, remove, reorder, or upload product media and
        does not modify theme code. Product links open the relevant Shopify
        admin record so the merchant can review assignments directly.
      </p>
    </PublicPage>
  );
}
