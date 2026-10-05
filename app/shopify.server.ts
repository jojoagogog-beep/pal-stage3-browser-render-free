import "@shopify/shopify-app-react-router/adapters/node";
import {
  ApiVersion,
  AppDistribution,
  shopifyApp,
} from "@shopify/shopify-app-react-router/server";
import { PrismaSessionStorage } from "@shopify/shopify-app-session-storage-prisma";
import prisma from "./db.server";

const mediaCapture = process.env.PAL_MEDIA_CAPTURE === "1";

const shopify = shopifyApp({
  apiKey:
    process.env.SHOPIFY_API_KEY ||
    (mediaCapture ? "pal-media-capture" : undefined),
  apiSecretKey:
    process.env.SHOPIFY_API_SECRET ||
    (mediaCapture ? "pal-media-capture" : ""),
  apiVersion: ApiVersion.July26,
  scopes: process.env.SCOPES?.split(",") || ["read_products"],
  appUrl:
    process.env.SHOPIFY_APP_URL ||
    (mediaCapture ? "http://127.0.0.1:3016" : ""),
  authPathPrefix: "/auth",
  sessionStorage: new PrismaSessionStorage(prisma),
  distribution: AppDistribution.AppStore,
  future: {
    expiringOfflineAccessTokens: true,
  },
  ...(process.env.SHOP_CUSTOM_DOMAIN
    ? { customShopDomains: [process.env.SHOP_CUSTOM_DOMAIN] }
    : {}),
});

export default shopify;
export const apiVersion = ApiVersion.July26;
export const addDocumentResponseHeaders = shopify.addDocumentResponseHeaders;
export const authenticate = shopify.authenticate;
export const unauthenticated = shopify.unauthenticated;
export const login = shopify.login;
export const registerWebhooks = shopify.registerWebhooks;
export const sessionStorage = shopify.sessionStorage;
