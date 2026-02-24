// frontend/lib/format.ts

/** Format large numbers as "12.3K" or "1.2M" */
export function formatCount(n: number): string {
  return new Intl.NumberFormat("en-US", {
    notation: "compact",
    maximumFractionDigits: 1,
  }).format(n);
}

/** Format exact numbers with commas: 12,345 */
export function formatExact(n: number): string {
  return new Intl.NumberFormat("en-US").format(n);
}

/** Format UTC ms timestamp as locale date string */
export function formatDate(tsMs: number): string {
  return new Intl.DateTimeFormat("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
    timeZone: "UTC",
  }).format(new Date(tsMs));
}
