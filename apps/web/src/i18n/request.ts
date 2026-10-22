import { getRequestConfig } from "next-intl/server";

// English only until SG-27 adds locale routing and the other languages.
export default getRequestConfig(async () => {
  const locale = "en";
  return {
    locale,
    messages: (await import(`../messages/${locale}.json`)).default,
  };
});
