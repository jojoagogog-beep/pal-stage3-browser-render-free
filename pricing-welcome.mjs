// Route only known apps back to their existing authenticated app loader.
// plan_handle and other query parameters never establish entitlement here.
export function pricingWelcomeLocation(pathname, search, appPrefixes) {
  const prefix = appPrefixes.find(prefix =>
    pathname === prefix + "welcome" || pathname === prefix + "app/welcome"
  );
  return prefix ? prefix + "app" + search : null;
}
