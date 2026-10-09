import {
  Links,
  Meta,
  Outlet,
  Scripts,
  ScrollRestoration,
  useLoaderData,
} from "react-router";

export const loader = () => ({
  apiKey: process.env.SHOPIFY_API_KEY || "",
  mediaCapture: process.env.PAL_MEDIA_CAPTURE === "1",
});

export default function App() {
  const { apiKey, mediaCapture } = useLoaderData<typeof loader>();
  return (
    <html lang="en">
      <head>
        <meta charSet="utf-8" />
        <meta name="viewport" content="width=device-width,initial-scale=1" />
        <meta name="shopify-api-key" content={apiKey} />
        <title>PAL Active Product Age Guard</title>
        {mediaCapture ? null : (
          <>
            <script src="https://cdn.shopify.com/shopifycloud/app-bridge.js" />
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
