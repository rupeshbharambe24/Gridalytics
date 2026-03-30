"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import {
  LayoutDashboard, TrendingUp, BarChart3, FlaskConical,
  LineChart, Target, Info, Zap, ChevronLeft, ChevronRight,
  Settings, Sun, Moon, Menu, X,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useState, useEffect } from "react";
import { getMe } from "@/lib/api";

const allNavItems = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/forecast", label: "Forecast", icon: TrendingUp },
  { href: "/models", label: "Models", icon: BarChart3 },
  { href: "/what-if", label: "What-If", icon: FlaskConical },
  { href: "/analytics", label: "Analytics", icon: LineChart },
  { href: "/accuracy", label: "Accuracy", icon: Target },
  { href: "/info", label: "How It Works", icon: Info },
  { href: "/admin", label: "Admin", icon: Settings },
];

export function Sidebar() {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [isAdmin, setIsAdmin] = useState(false);
  const [isDark, setIsDark] = useState(true);

  useEffect(() => {
    getMe()
      .then((user) => setIsAdmin(user.role === "admin"))
      .catch(() => setIsAdmin(false));
  }, []);

  // Close mobile menu on route change
  useEffect(() => {
    setMobileOpen(false);
  }, [pathname]);

  const toggleTheme = () => {
    const html = document.documentElement;
    if (isDark) {
      html.classList.remove("dark");
    } else {
      html.classList.add("dark");
    }
    setIsDark(!isDark);
  };

  const navItems = isAdmin
    ? allNavItems
    : allNavItems.filter((item) => item.href !== "/admin");

  const sidebarContent = (
    <>
      {/* Logo */}
      <div className="flex items-center gap-3 px-4 h-16 border-b border-sidebar-border">
        <div className="flex items-center justify-center w-9 h-9 rounded-lg bg-blue-600">
          <Zap className="w-5 h-5 text-white" />
        </div>
        {!collapsed && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
            <h1 className="text-lg font-bold text-sidebar-foreground tracking-tight">Gridalytics</h1>
            <p className="text-[10px] text-muted-foreground -mt-0.5">Grid Intelligence</p>
          </motion.div>
        )}
        {/* Mobile close */}
        <button
          onClick={() => setMobileOpen(false)}
          className="ml-auto lg:hidden p-1 rounded text-muted-foreground hover:text-foreground"
        >
          <X className="w-5 h-5" />
        </button>
      </div>

      {/* Nav */}
      <nav className="flex-1 py-4 px-3 space-y-1 overflow-y-auto">
        {navItems.map((item) => {
          const isActive = pathname === item.href;
          return (
            <Link key={item.href} href={item.href}>
              <motion.div
                whileHover={{ x: 2 }}
                whileTap={{ scale: 0.98 }}
                className={cn(
                  "flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors relative",
                  isActive
                    ? "text-blue-400 bg-blue-500/10"
                    : "text-muted-foreground hover:text-sidebar-foreground hover:bg-sidebar-accent"
                )}
              >
                {isActive && (
                  <motion.div
                    layoutId="activeNav"
                    className="absolute left-0 top-1/2 -translate-y-1/2 w-[3px] h-5 bg-blue-500 rounded-r-full"
                  />
                )}
                <item.icon className="w-5 h-5 shrink-0" />
                {!collapsed && <span>{item.label}</span>}
              </motion.div>
            </Link>
          );
        })}
      </nav>

      {/* Bottom: theme toggle + collapse */}
      <div className="p-3 border-t border-sidebar-border space-y-1">
        <button
          onClick={toggleTheme}
          className="w-full flex items-center gap-3 px-3 py-2 rounded-lg text-muted-foreground hover:text-sidebar-foreground hover:bg-sidebar-accent transition-colors"
        >
          {isDark ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
          {!collapsed && <span className="text-sm">{isDark ? "Light Mode" : "Dark Mode"}</span>}
        </button>
        <button
          onClick={() => setCollapsed(!collapsed)}
          className="w-full flex items-center justify-center py-2 rounded-lg text-muted-foreground hover:text-sidebar-foreground hover:bg-sidebar-accent transition-colors hidden lg:flex"
        >
          {collapsed ? <ChevronRight className="w-4 h-4" /> : <ChevronLeft className="w-4 h-4" />}
        </button>
      </div>
    </>
  );

  return (
    <>
      {/* Mobile hamburger */}
      <button
        onClick={() => setMobileOpen(true)}
        className="fixed top-4 left-4 z-50 p-2 rounded-lg bg-card border border-border lg:hidden"
      >
        <Menu className="w-5 h-5" />
      </button>

      {/* Mobile overlay */}
      <AnimatePresence>
        {mobileOpen && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={() => setMobileOpen(false)}
            className="fixed inset-0 bg-black/50 z-40 lg:hidden"
          />
        )}
      </AnimatePresence>

      {/* Mobile sidebar */}
      <AnimatePresence>
        {mobileOpen && (
          <motion.aside
            initial={{ x: -280 }}
            animate={{ x: 0 }}
            exit={{ x: -280 }}
            transition={{ duration: 0.2 }}
            className="fixed left-0 top-0 z-50 h-screen w-[240px] bg-sidebar border-r border-sidebar-border flex flex-col lg:hidden"
          >
            {sidebarContent}
          </motion.aside>
        )}
      </AnimatePresence>

      {/* Desktop sidebar */}
      <motion.aside
        animate={{ width: collapsed ? 72 : 240 }}
        transition={{ duration: 0.2, ease: "easeInOut" }}
        className="fixed left-0 top-0 z-40 h-screen bg-sidebar border-r border-sidebar-border flex-col hidden lg:flex"
      >
        {sidebarContent}
      </motion.aside>
    </>
  );
}
