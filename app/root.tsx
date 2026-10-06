import {
  Links,
  Meta,
  Outlet,
  Scripts,
  ScrollRestoration,
  useLoaderData,
  type LoaderFunctionArgs,
} from "react-router";
import { appEnvNames } from "./rules/app-env-names";

export const loader = ({ request }: LoaderFunctionArgs) => {
  const slug = new URL(request.url).pathname.split("/").filter(Boolean)[0] || "";
  const names = appEnvNames[slug as keyof typeof appEnvNames];
  const apiKey = names
    ? process.env[names.key] || ""
    : process.env.SHOPIFY_API_KEY || "";
  const title = slug
    ? "PAL " + slug.replace(/^pal-/, "").split("-").map((part) => part.charAt(0).toUpperCase() + part.slice(1)).join(" ")
    : "Practical AI Lab";
  return {
    apiKey,
    title,
    mediaCapture: process.env.PAL_MEDIA_CAPTURE === "1",
  };
};

export default function App() {
  const { apiKey, title, mediaCapture } = useLoaderData<typeof loader>();
  return (
    <html lang="en">
      <head>
        <meta charSet="utf-8" />
        <meta name="viewport" content="width=device-width,initial-scale=1" />
        <meta name="shopify-api-key" content={apiKey} />
        <script src="https://cdn.shopify.com/shopifycloud/app-bridge.js" />
        <title>{title}</title>
        {mediaCapture ? null : (
          <>

            <link rel="preconnect" href="https://cdn.shopify.com/" />
            <link
              rel="stylesheet"
              href="https://cdn.shopify.com/static/fonts/inter/v4/styles.css"
            />
          </>
        )}
        <Meta />
        <Links />
      </head>
      <body>
        <Outlet />
        <ScrollRestoration />
        <Scripts />
      </body>
    </html>
  );
}
