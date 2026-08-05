"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import styles from "./layout.module.css";
import { UploadIcon } from "./ingest/icons";
import { SearchIcon } from "./explorer/icons";
import { BoxIcon } from "./cluster/icons";

const navItems = [
  { href: "/ingest", label: "Ingest", Icon: UploadIcon },
  { href: "/explorer", label: "Explorer", Icon: SearchIcon },
  { href: "/cluster", label: "Cluster", Icon: BoxIcon },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <nav className={styles.sidebar}>
      <div className={styles.brand}>
        <span className={styles.brandIcon}>👻</span>
        <span className={styles.brandText}>GhostKube</span>
      </div>
      <ul className={styles.navList}>
        {navItems.map((item) => {
          // Note Detail (/notes/[chunkId]) has no nav item of its own - it's
          // reached via Explorer, so it keeps Explorer highlighted as active.
          const active =
            pathname === item.href ||
            (item.href === "/explorer" && pathname?.startsWith("/notes"));

          return (
            <li key={item.href}>
              <Link
                href={item.href}
                className={`${styles.navLink} ${
                  active ? styles.navLinkActive : ""
                }`}
              >
                <item.Icon className={styles.navIcon} />
                <span className={styles.navLabel}>{item.label}</span>
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
