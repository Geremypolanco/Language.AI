import { ReactNode, useState } from "react";
import { Link, useLocation } from "wouter";
import { Button } from "@/components/ui/button";
import { Menu, X } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { useLocale } from "@/contexts/LocaleContext";
import LanguageToggle from "@/components/LanguageToggle";

interface NavItem {
  key: string;
  icon: string;
  path: string;
  badge?: number;
}

const NAV_ITEMS: NavItem[] = [
  { key: "nav.path", icon: "🛤️", path: "/path" },
  { key: "nav.practice", icon: "⚡", path: "/practice" },
  { key: "nav.library", icon: "📚", path: "/library" },
  { key: "nav.university", icon: "🎓", path: "/university" },
  { key: "nav.talk", icon: "🎤", path: "/talk" },
  { key: "nav.progress", icon: "📊", path: "/progress" },
  { key: "nav.pro", icon: "⭐", path: "/pro" },
];

interface DashboardLayoutProps {
  children: ReactNode;
  user?: { name: string; level: string };
}

export default function DashboardLayout({ children, user }: DashboardLayoutProps) {
  const [location] = useLocation();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const { logout, user: authUser } = useAuth();
  const { t } = useLocale();
  const isPro = authUser?.plan === "pro";

  return (
    <div className="flex h-dvh bg-background">
      {/* Sidebar */}
      <aside
        className={`fixed md:relative z-40 w-64 h-dvh bg-sidebar border-r border-sidebar-border flex flex-col overflow-y-auto transition-transform duration-300 ${
          sidebarOpen ? "translate-x-0" : "-translate-x-full md:translate-x-0"
        }`}
      >
        {/* Header */}
        <div className="p-6 border-b border-sidebar-border">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg gradient-primary flex items-center justify-center">
              <span className="text-white font-bold">L</span>
            </div>
            <h1 className="text-xl font-bold text-sidebar-foreground">Language.AI</h1>
          </div>
        </div>

        {/* User Info */}
        {user && (
          <div className="p-4 mx-4 mt-4 rounded-lg bg-muted/50 border border-sidebar-border">
            <div className="flex items-center gap-2">
              <p className="text-sm font-medium text-sidebar-foreground">{user.name}</p>
              {isPro && (
                <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-primary text-primary-foreground">
                  {t("pro.badge")}
                </span>
              )}
            </div>
            <p className="text-xs text-muted-foreground mt-1">{t("common.level", { level: user.level })}</p>
            {!isPro && (
              <Link href="/pro">
                <a onClick={() => setSidebarOpen(false)} className="text-xs font-semibold text-primary hover:underline">
                  ⭐ {t("pro.upgrade")}
                </a>
              </Link>
            )}
          </div>
        )}

        {/* Navigation */}
        <nav className="flex-1 px-4 py-6 space-y-2 overflow-y-auto">
          {NAV_ITEMS.map((item) => {
            const isActive = location === item.path;
            return (
              <Link key={item.path} href={item.path}>
                <a
                  className={`flex items-center gap-3 px-4 py-3 rounded-lg font-medium transition-smooth ${
                    isActive
                      ? "bg-sidebar-primary text-sidebar-primary-foreground"
                      : "text-sidebar-foreground hover:bg-muted/50"
                  }`}
                  onClick={() => setSidebarOpen(false)}
                >
                  <span className="text-lg">{item.icon}</span>
                  <span>{t(item.key)}</span>
                  {item.badge && (
                    <span className="ml-auto bg-primary text-primary-foreground text-xs font-bold px-2 py-1 rounded-full">
                      {item.badge}
                    </span>
                  )}
                </a>
              </Link>
            );
          })}
        </nav>

        {/* Footer */}
        <div className="p-4 border-t border-sidebar-border space-y-2">
          <div className="flex justify-center pb-1">
            <LanguageToggle compact />
          </div>
          <Link href="/settings">
            <a onClick={() => setSidebarOpen(false)}>
              <Button variant="outline" className="w-full justify-start">
                ⚙️ {t("nav.settings")}
              </Button>
            </a>
          </Link>
          <Button
            variant="outline"
            className="w-full justify-start"
            onClick={() => logout()}
          >
            🚪 {t("nav.signOut")}
          </Button>
        </div>
      </aside>

      {/* Main Content */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Mobile Header */}
        <div className="md:hidden flex items-center justify-between px-4 py-4 bg-card border-b border-border">
          <h2 className="font-bold text-foreground">Language.AI</h2>
          <div className="flex items-center gap-2">
            <LanguageToggle compact />
            <Button
              size="sm"
              variant="ghost"
              onClick={() => setSidebarOpen(!sidebarOpen)}
              aria-label={sidebarOpen ? t("nav.menu.close") : t("nav.menu.open")}
            >
              {sidebarOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
            </Button>
          </div>
        </div>

        {/* Content */}
        <main className="flex-1 overflow-y-auto">
          {children}
        </main>
      </div>

      {/* Mobile Overlay */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 bg-black/50 z-30 md:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}
    </div>
  );
}
