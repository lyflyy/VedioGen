"use client";

import { Clapperboard, LayoutGrid, Settings2, Sparkles, UserRoundCog } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

const navigation = [
  { href: "/projects", label: "项目", icon: LayoutGrid },
  { href: "/account-brief", label: "账号资料", icon: UserRoundCog },
];

export function CreatorShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  return (
    <div className="app-shell">
      <aside className="global-sidebar" aria-label="创作导航">
        <Link href="/projects" className="brand" aria-label="VedioGen 项目">
          <span className="brand-mark"><Clapperboard size={20} /></span>
          <span>VedioGen</span>
        </Link>
        <nav className="global-nav">
          {navigation.map((item) => {
            const active = pathname === item.href || (item.href === "/projects" && pathname.startsWith("/projects/"));
            const Icon = item.icon;
            return (
              <Link key={item.href} href={item.href} className="nav-link" aria-current={active ? "page" : undefined}>
                <Icon size={18} aria-hidden="true" />
                <span>{item.label}</span>
              </Link>
            );
          })}
        </nav>
        <div className="sidebar-context">
          <div className="context-icon"><Sparkles size={16} /></div>
          <div><strong>摩托车内容包</strong><span>版本 1.0</span></div>
        </div>
        <Link href="/admin/model-providers" className="nav-link admin-entry">
          <Settings2 size={18} aria-hidden="true" />
          <span>管理后台</span>
        </Link>
      </aside>
      <main className="app-main">{children}</main>
    </div>
  );
}
