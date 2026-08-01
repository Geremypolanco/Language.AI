import { ReactNode, useState } from "react";
import { Link, useLocation } from "wouter";
import { Button } from "@/components/ui/button";
import { Menu, X } from "lucide-react";

interface NavItem {
  label: string;
  icon: string;
  path: string;
  badge?: number;
}

const NAV_ITEMS: NavItem[] = [
  { label: "Path", icon: "🛤️", path: "/path" },
  { label: "Practice", icon: "⚡", path: "/practice" },
  { label: "Library", icon: "📚", path: "/library" },
  { label: "University", icon: "🎓", path: "/university" },
  { label: "Talk Live", icon: "🎤", path: "/talk" },
  { label: "Progress", icon: "📊", path: "/progress" },
];

interface DashboardLayoutProps {
  children: ReactNode;
  user?: { name: string; level: number };
}

export default function DashboardLayout({ children, user }: DashboardLayoutProps) {
  const [location] = useLocation();
  const [sidebarOpen, setSidebarOpen] = useState(false);

  return (
    <div className="flex h-screen bg-background">
      {/* Sidebar */}
      <aside
        className={`fixed md:relative z-40 w-64 h-screen bg-sidebar border-r border-sidebar-border flex flex-col transition-transform duration-300 ${
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
            <p className="text-sm font-medium text-sidebar-foreground">{user.name}</p>
            <p className="text-xs text-muted-foreground mt-1">Level {user.level}</p>
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
                  <span>{item.label}</span>
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
          <Button
            variant="outline"
            className="w-full justify-start"
            onClick={() => {
              // TODO: Settings
              console.log("Settings");
            }}
          >
            ⚙️ Settings
          </Button>
          <Button
            variant="outline"
            className="w-full justify-start"
            onClick={() => {
              // TODO: Logout
              console.log("Logout");
            }}
          >
            🚪 Sign out
          </Button>
        </div>
      </aside>

      {/* Main Content */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Mobile Header */}
        <div className="md:hidden flex items-center justify-between px-4 py-4 bg-card border-b border-border">
          <h2 className="font-bold text-foreground">Language.AI</h2>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => setSidebarOpen(!sidebarOpen)}
          >
            {sidebarOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
          </Button>
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
