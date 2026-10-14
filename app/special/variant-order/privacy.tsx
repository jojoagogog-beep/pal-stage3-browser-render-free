import { PublicPage } from "./components/public-page";

export const meta = () => [
  { title: "Privacy Policy · PAL Variant Order Guard" },
];

export default function Privacy() {
  return (
    <PublicPage
      title="Privacy Policy"
      intro="PAL Variant Order Guard is a read-only catalog structure audit app. This policy explains the limited Shopify data processed to provide that audit."
    >
      <h2>Data we process</h2>
      <p>
        After installation, the app processes the shop domain and Shopify
        authentication session information required to keep the app connected
        and secure. An audit reads product titles, product option names, option
        positions, and option values.
      </p>

      <h2>How we use data</h2>
      <p>
        Product option structure is used only to calculate the audit shown to
        the merchant and to create a remediation CSV when requested. The first
        release does not edit products, variants, themes, or option values and
        does not require customer records.
      </p>

      <h2>Storage and sharing</h2>
      <p>
        Catalog audit results are generated on request and are not stored in the
        app database. Shopify session records are stored for authentication. We
        do not sell merchant data.
      </p>

      <h2>Retention and deletion</h2>
      <p>
        Session records are removed when Shopify sends an app-uninstalled or
        shop-redact webhook. Mandatory customer privacy webhooks are
        acknowledged even though the app does not request protected customer
        data.
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
