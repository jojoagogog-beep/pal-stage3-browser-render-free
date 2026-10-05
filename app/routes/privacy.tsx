import { PublicPage } from "../components/public-page";

export const meta = () => [{ title: "Privacy Policy · PAL Collection Ratio Guard" }];

export default function Privacy() {
  return (
    <PublicPage
      title="Privacy Policy"
      intro="PAL Collection Ratio Guard is a read-only audit of collection image dimensions and aspect-ratio consistency."
    >
      <h2>Data we process</h2>
      <p>The app processes the shop domain and authentication session needed to operate securely. An audit reads collection identifiers, titles, and collection image dimensions.</p>
      <h2>How we use data</h2>
      <p>Collection data is used only to generate the requested audit and diagnostic CSV. The app does not request protected customer data and does not upload, crop, replace, or edit collection images or collection data.</p>
      <h2>Storage and sharing</h2>
      <p>Audit results are generated on request and are not stored as merchant analytics. Authentication session records are stored only to operate the installed app. We do not sell merchant data.</p>
      <h2>Retention and deletion</h2>
      <p>Authentication sessions are removed when Shopify notifies the app of uninstall or shop redaction. Mandatory privacy webhooks are supported.</p>
      <h2>Contact</h2>
      <p>For privacy questions, email practicalai_lab_jp@proton.me. Never send passwords, access tokens, payment information, or customer records.</p>
    </PublicPage>
  );
}
