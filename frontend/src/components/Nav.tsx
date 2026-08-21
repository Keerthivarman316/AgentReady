"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  { href: "/buyer", label: "Buyer" },
  { href: "/merchant", label: "Merchant" },
  { href: "/audit", label: "Audit trail" },
];

export default function Nav() {
  const pathname = usePathname();

  return (
    <nav className="border-b border-gray-200 bg-white">
      <div className="mx-auto flex max-w-5xl items-center gap-6 px-6 py-4">
        <Link href="/" className="font-semibold text-gray-900">
          AgentReady
        </Link>
        <div className="flex gap-4">
          {LINKS.map((link) => {
            const active = pathname?.startsWith(link.href);
            return (
              <Link
                key={link.href}
                href={link.href}
                className={active ? "text-sm font-medium text-indigo-600" : "text-sm text-gray-500 hover:text-gray-900"}
              >
                {link.label}
              </Link>
            );
          })}
        </div>
      </div>
    </nav>
  );
}
