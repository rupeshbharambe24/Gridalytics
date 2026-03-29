"use client";

import { Sidebar } from "@/components/layout/sidebar";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen bg-background">
      <Sidebar />
      <main className="flex-1 ml-[240px] transition-all duration-200">
        <div className="p-6 max-w-[1400px] mx-auto pb-20">
          {children}
        </div>
        <footer className="ml-0 border-t border-border bg-card/50 py-4 px-6">
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
