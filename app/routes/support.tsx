import { PublicPage } from "../components/public-page";

export const meta = () => [{ title: "Support · PAL Collection Sort Guard" }];

export default function Support() {
  return (
    <PublicPage
      title="Support"
      intro="Get help with collection-content findings, CSV exports, or installation access."
    >
      <h2>Contact</h2>
      <p>Email practicalai_lab_jp@proton.me. Include your myshopify.com domain, approximate audit time, and the exact error shown.</p>
      <h2>Before contacting support</h2>
      <ul>
        <li>Reload the app and run the audit again.</li>
        <li>Confirm the app still has read-products access.</li>
        <li>If a safety-limit banner appears, use the result only for collections reported as scanned.</li>
        <li>Never send passwords, access tokens, payment information, or customer records.</li>
      </ul>
      <h2>Scope of support</h2>
      <p>Support covers app behavior and observed collection-content gaps. The app does not generate or choose replacement content.</p>
    </PublicPage>
  );
}
