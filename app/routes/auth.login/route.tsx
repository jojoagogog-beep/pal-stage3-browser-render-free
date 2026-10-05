import { AppProvider } from "@shopify/shopify-app-react-router/react";
import type { LoaderFunctionArgs } from "react-router";
import { login } from "../../shopify.server";

export const loader = async ({ request }: LoaderFunctionArgs) => {
  await login(request);
  return null;
};

export default function Auth() {
  return (
    <AppProvider embedded={false}>
      <s-page heading="Open PAL Category Attribute Guard from Shopify">
        <s-section heading="Shopify authentication required">
          <s-paragraph>
            For security, installation and sign-in start from the Shopify App
            Store or Shopify admin. Return to Shopify and open PAL Category
            Attribute Guard from Apps.
          </s-paragraph>
        </s-section>
      </s-page>
    </AppProvider>
  );
}
