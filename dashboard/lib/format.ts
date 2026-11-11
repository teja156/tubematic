/** Binary units, so the figure matches `du -h` on the host. */
export function formatBytes(n: number): string {
  const units = ["B", "KB", "MB", "GB", "TB"];
  let i = 0;
  while (n >= 1024 && i < units.length - 1) { n /= 1024; i++; }
  return i === 0 ? `${n} B` : `${n.toFixed(1)} ${units[i]}`;
}

/** Trailing ".0" dropped: 31 reads "31", 23.5 reads "23.5". */
function oneDecimal(n: number): string {
  return String(Number(n.toFixed(1)));
}

/** Seconds watched, or a dash. A figure the platform did not report reads
 *  "—", never 0: "not reported" and "nobody watched" are different claims. */
export function formatWatchSeconds(value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : `${oneDecimal(value)} s`;
}

/** A share in percent, or a dash. Above 100 is real (a looping Short). */
export function formatShare(value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : `${oneDecimal(value)}%`;
}
