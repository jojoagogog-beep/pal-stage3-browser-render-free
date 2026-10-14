import { PublicPage } from "./components/public-page";

export const meta = () => [
  { title: "Privacy Policy · PAL Feed Readiness Guard" },
];

export default function Privacy() {
  return (
    <PublicPage
      title="Privacy Policy"
      intro="PAL Feed Readiness Guard is a read-only catalog audit app. This policy explains the limited data the app processes to provide that audit."
    >
      <h2>Data we process</h2>
      <p>
        After a merchant installs the app, we process the shop domain and
        Shopify authentication session information required to keep the app
        connected and secure. An audit reads product titles, vendors, tags,
        Shopify product categories, primary-image presence, and variant titles,
        SKUs, and barcodes.
      </p>

      <h2>How we use data</h2>
      <p>
        Catalog fields are used only to calculate the audit shown to the
        merchant and to create a remediation CSV when the merchant requests one.
        The first release does not edit product data, connect to advertising
        accounts, or require customer records.
      </p>

      <h2>Storage and sharing</h2>
      <p>
        Catalog audit results are generated on request and are not stored in the
        app database. Shopify session records are stored for authentication. We
        do not sell merchant data. Data is processed by Shopify and the
        app&apos;s infrastructure providers only as needed to deliver and secure
        the service.
      </p>

      <h2>Retention and deletion</h2>
      <p>
        Session records are removed when Shopify sends an app-uninstalled or
        shop-redact webhook. Shopify&apos;s mandatory customer data-request and
        customer-redact webhooks are acknowledged; the app does not request or
        store protected customer data.
      </p>

      <h2>Contact</h2>
      <p>
        For privacy questions or deletion requests, email
        practicalai_lab_jp@proton.me. Include the shop domain, but never send
        passwords, access tokens, or customer data.
      </p>
    </PublicPage>
  );
}
