import { PassThrough } from "stream";
import { renderToPipeableStream } from "react-dom/server";
import { ServerRouter } from "react-router";
import { createReadableStreamFromReadable } from "@react-router/node";
import { type EntryContext } from "react-router";
import { isbot } from "isbot";
import { getShopify, isKnownSlug } from "./multi-shopify.server";

export const streamTimeout = 5000;

export default async function handleRequest(
  request: Request,
  responseStatusCode: number,
  responseHeaders: Headers,
  reactRouterContext: EntryContext
) {
  const pathname = new URL(request.url).pathname;
  const slug = pathname.split("/").filter(Boolean)[0] || "";
  if (isKnownSlug(slug)) {
    // Legal/support/demo pages remain reachable even when per-app OAuth
    // credentials have not yet been provisioned. Protected /app and /auth
    // endpoints still fail closed rather than serving an unauthenticated UI.
    try {
      getShopify(slug).addDocumentResponseHeaders(request, responseHeaders);
    } catch (error) {
      const publicPage = /^\/pal-[a-z0-9-]+(?:\/(?:privacy|terms|support|review-demo))?\/?$/.test(pathname);
      const missingConfig = error instanceof Error &&
        error.message === "Missing runtime app configuration for " + slug;
      if (!publicPage || !missingConfig) throw error;
    }
  }
  const userAgent = request.headers.get("user-agent");
  const callbackName = isbot(userAgent ?? '')
    ? "onAllReady"
    : "onShellReady";

  return new Promise((resolve, reject) => {
    const { pipe, abort } = renderToPipeableStream(
      <ServerRouter
        context={reactRouterContext}
        url={request.url}
      />,
      {
        [callbackName]: () => {
          const body = new PassThrough();
          const stream = createReadableStreamFromReadable(body);

          responseHeaders.set("Content-Type", "text/html");
          resolve(
            new Response(stream, {
              headers: responseHeaders,
              status: responseStatusCode,
            })
          );
          pipe(body);
        },
        onShellError(error) {
          reject(error);
        },
        onError(error) {
          responseStatusCode = 500;
          console.error(error);
        },
      }
    );

    // Automatically timeout the React renderer after 6 seconds, which ensures
    // React has enough time to flush down the rejected boundary contents
    setTimeout(abort, streamTimeout + 1000);
  });
}
