import { cx } from "./ui";

/** Official brand marks (from the open svgl.app library, found via the 21st.dev logo search). */
const LOGOS: Record<string, { src: string; name: string }> = {
  meta: { src: "/brands/meta.svg", name: "Meta" },
  google: { src: "/brands/google.svg", name: "Google" },
  google_ads: { src: "/brands/google.svg", name: "Google Ads" },
  ga4: { src: "/brands/google-analytics.svg", name: "Google Analytics" },
  shopify: { src: "/brands/shopify.svg", name: "Shopify" },
  slack: { src: "/brands/slack.svg", name: "Slack" },
};

/** Map anything the API calls a source ("meta_ads", "Google searches", "Shop orders (Shopify)") to a logo key. */
export function brandKey(source: string): string | undefined {
  const s = source.toLowerCase();
  if (s.includes("meta")) return "meta";
  if (s.includes("analytics") || s.includes("ga4")) return "ga4";
  if (s.includes("shop")) return "shopify";
  if (s.includes("slack")) return "slack";
  if (s.includes("google")) return "google";
  return undefined;
}

export function BrandLogo({ brand, className }: { brand: string; className?: string }) {
  const key = LOGOS[brand] ? brand : brandKey(brand);
  const logo = key ? LOGOS[key] : undefined;
  if (!logo) return null;
  return <img src={logo.src} alt="" aria-hidden className={cx("inline-block h-4 w-auto shrink-0", className)} />;
}

/** Logo followed by the brand name, e.g. in table cells and channel headings. */
export function BrandName({ brand, label, className }: { brand: string; label?: string; className?: string }) {
  const key = LOGOS[brand] ? brand : brandKey(brand);
  return (
    <span className={cx("inline-flex items-center gap-2", className)}>
      <BrandLogo brand={brand} />
      {label ?? (key ? LOGOS[key].name : brand)}
    </span>
  );
}
