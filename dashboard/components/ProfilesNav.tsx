"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

/**
 * "Script profiles · Mascots": the two libraries share the Profiles tab. A
 * twelfth top-bar tab would not fit the one-row layout at 1640px, so the tab
 * stays one and this sub-nav switches between its two pages.
 */
export function ProfilesNav() {
  const pathname = usePathname() ?? "";
  const links = [
    { href: "/script-profiles", label: "Script profiles", id: "script-profiles" },
    { href: "/mascots", label: "Mascots", id: "mascots" },
  ];
  return (
    <nav
      data-testid="profiles-subnav"
      aria-label="Profiles"
      style={{ display: "flex", gap: 10, alignItems: "center", marginBottom: 14,
               fontFamily: "var(--mono)", fontSize: 11 }}
    >
      {links.map((l, i) => {
        const active = pathname.startsWith(l.href);
        return (
          <span key={l.id} style={{ display: "flex", gap: 10 }}>
            {i > 0 && <span style={{ color: "var(--faint)" }}>·</span>}
            <Link
              href={l.href}
              data-testid={`profiles-subnav-${l.id}`}
              aria-current={active ? "page" : undefined}
              style={{ textDecoration: "none", color: active ? "var(--amber)" : "var(--dim)",
                       letterSpacing: "0.04em" }}
            >
              {l.label}
            </Link>
          </span>
        );
      })}
    </nav>
  );
}
