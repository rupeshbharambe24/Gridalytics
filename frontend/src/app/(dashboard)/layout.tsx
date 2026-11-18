"use client";

import { useEffect, useState } from "react";
import { Sidebar } from "@/components/layout/sidebar";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const [collapsed, setCollapsed] = useState(false);

  useEffect(() => {
    try {
      setCollapsed(localStorage.getItem("gridalytics-sidebar") === "collapsed");
    } catch {}
  }, []);

  const handleCollapsed = (v: boolean) => {
    setCollapsed(v);
    try {
      localStorage.setItem("gridalytics-sidebar", v ? "collapsed" : "expanded");
    } catch {}
  };

  return (
    <div className="flex min-h-screen bg-background">
      <Sidebar collapsed={collapsed} setCollapsed={handleCollapsed} />
      <main className={`flex-1 transition-all duration-200 ${collapsed ? "lg:ml-[72px]" : "lg:ml-[240px]"}`}>
        <div className="p-4 lg:p-6 max-w-[1400px] mx-auto pb-20 pt-16 lg:pt-6">
          {children}
        </div>
        <footer className="border-t border-border bg-card/50 py-4 px-6">
          <div className="max-w-[1400px] mx-auto flex items-center justify-between text-xs text-muted-foreground">
            <p>&copy; {new Date().getFullYear()} Rupesh Bharambe. All rights reserved.</p>
            <p className="flex items-center gap-1.5">
              <span className="font-semibold text-foreground">Gridalytics</span>
              <span>&#8212;</span>
              <span>AI-Powered Grid Intelligence</span>
            </p>
          </div>
        </footer>
      </main>
    </div>
  );
}
