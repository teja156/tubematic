// Display names for publishing platforms. The API stores them lower-case, and
// CSS capitalisation gets two of them wrong ("Youtube", "Tiktok").
export const PLATFORM_LABEL: Record<string, string> = {
  youtube: "YouTube",
  instagram: "Instagram",
  tiktok: "TikTok",
  facebook: "Facebook",
};

export function platformLabel(platform: string): string {
  return PLATFORM_LABEL[platform] ?? platform;
}

export type AccountName = { username: string; platform: string };

/** "demo_channel (Instagram)". The id stands in for a name the lookup could not
 *  supply — publishing off, postforme unreachable, or an account disconnected
 *  since it posted — so the Analytics filter and graph still work, just less
 *  readably. */
export function accountLabel(id: string, platform: string, names: Record<string, AccountName>) {
  const known = names[id];
  return `${known?.username || id} (${platformLabel(known?.platform || platform)})`;
}
