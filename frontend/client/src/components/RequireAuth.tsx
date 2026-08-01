import { ReactNode, useEffect } from "react";
import { useLocation } from "wouter";
import { useAuth } from "@/contexts/AuthContext";

/**
 * Guards a protected page: while the session check is still in flight, shows
 * a spinner; once resolved, sends an unauthenticated (or logged-out) visitor
 * to the login screen instead of leaving the page's own data-fetching stuck
 * forever. Without this, e.g. Path.tsx's fetchLessons() bails out early on a
 * missing user id but never clears its own `loading` state, so a signed-out
 * visitor hitting a bookmarked/cached URL like /path saw a permanent
 * "Cargando lecciones..." spinner instead of the login page.
 */
export default function RequireAuth({ children }: { children: ReactNode }) {
  const { session, loading } = useAuth();
  const [, setLocation] = useLocation();

  const authenticated = session?.authenticated && !session?.pending;

  useEffect(() => {
    if (!loading && !authenticated) {
      setLocation("/");
    }
  }, [loading, authenticated, setLocation]);

  if (loading || !authenticated) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary mx-auto mb-4"></div>
          <p className="text-muted-foreground">Cargando...</p>
        </div>
      </div>
    );
  }

  return <>{children}</>;
}
