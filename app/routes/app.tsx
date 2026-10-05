import type { HeadersFunction, LoaderFunctionArgs } from "react-router";
import { Outlet, useLoaderData, useRouteError } from "react-router";
import { useEffect } from "react";
import { boundary } from "@shopify/shopify-app-react-router/server";
import { AppProvider } from "@shopify/shopify-app-react-router/react";
import { useAppBridge } from "@shopify/app-bridge-react";
import { authenticate } from "../shopify.server";

export const loader = async ({ request }: LoaderFunctionArgs) => {
  await authenticate.admin(request);
  return { apiKey: process.env.SHOPIFY_API_KEY || "" };
};

function SessionTokenSignal() {
  const shopify = useAppBridge();

  useEffect(() => {
    let cancelled = false;
    const sendSignal = async () => {
      try {
        const token = await shopify.idToken();
        if (cancelled) return;
        await fetch("/app/session-token-probe", {
          method: "GET",
          headers: {
            Authorization: "Bearer " + token,
            "Cache-Control": "no-store",
          },
          credentials: "omit",
          cache: "no-store",
        });
      } catch {
      }
    };

    void sendSignal();
    const timer = window.setTimeout(() => void sendSignal(), 2500);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [shopify]);

  return null;
}

export default function App() {
  const { apiKey } = useLoaderData<typeof loader>();
  return (
    <AppProvider embedded apiKey={apiKey}>
      <SessionTokenSignal />
      <Outlet />
    </AppProvider>
  );
}

export function ErrorBoundary() {
  return boundary.error(useRouteError());
}

export const headers: HeadersFunction = (headersArgs) => boundary.headers(headersArgs);
