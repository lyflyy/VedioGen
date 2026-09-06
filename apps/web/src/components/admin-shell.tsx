"use client";

import { Activity, ArrowLeft, FlaskConical, KeyRound, Network, ServerCog, Waypoints } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

const items = [
  { href: "/admin/model-providers", label: "模型平台", icon: ServerCog },
  { href: "/admin/credentials", label: "API Key", icon: KeyRound },
  { href: "/admin/deployments", label: "模型部署", icon: Waypoints },
  { href: "/admin/routing", label: "能力路由", icon: Network },
  { href: "/admin/playground", label: "测试台", icon: FlaskConical },
  { href: "/admin/invocations", label: "调用记录", icon: Activity },
];

export function AdminShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  return (
    <div className="app-shell admin-shell">
      <aside className="global-sidebar" aria-label="管理导航">
        <div className="brand admin-brand"><span className="brand-mark"><ServerCog size={20} /></span><span>管理后台</span></div>
        <nav className="global-nav">
          {items.map((item) => {
            const Icon = item.icon;
            return (
              <Link key={item.href} href={item.href} className="nav-link" aria-current={pathname === item.href ? "page" : undefined}>
                <Icon size={18} aria-hidden="true" /><span>{item.label}</span>
              </Link>
            );
          })}
        </nav>
        <Link href="/projects" className="nav-link admin-entry"><ArrowLeft size={18} /><span>返回创作端</span></Link>
      </aside>
      <main className="app-main">{children}</main>
    </div>
  );
}
