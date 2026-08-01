import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import NotFound from "@/pages/NotFound";
import Login from "@/pages/Login";
import Path from "@/pages/Path";
import University from "@/pages/University";
import Practice from "@/pages/Practice";
import Talk from "@/pages/Talk";
import Progress from "@/pages/Progress";
import Library from "@/pages/Library";
import Settings from "@/pages/Settings";
import RequireAuth from "@/components/RequireAuth";
import { Route, Switch } from "wouter";
import ErrorBoundary from "./components/ErrorBoundary";
import { ThemeProvider } from "./contexts/ThemeContext";
import { AuthProvider } from "./contexts/AuthContext";

function Router() {
  return (
    <Switch>
      <Route path={"/"} component={Login} />
      <Route path={"/login"} component={Login} />
      <Route path={"/path"}>
        <RequireAuth>
          <Path />
        </RequireAuth>
      </Route>
      <Route path={"/practice"}>
        <RequireAuth>
          <Practice />
        </RequireAuth>
      </Route>
      <Route path={"/library"}>
        <RequireAuth>
          <Library />
        </RequireAuth>
      </Route>
      <Route path={"/university"}>
        <RequireAuth>
          <University />
        </RequireAuth>
      </Route>
      <Route path={"/talk"}>
        <RequireAuth>
          <Talk />
        </RequireAuth>
      </Route>
      <Route path={"/progress"}>
        <RequireAuth>
          <Progress />
        </RequireAuth>
      </Route>
      <Route path={"/settings"}>
        <RequireAuth>
          <Settings />
        </RequireAuth>
      </Route>
      <Route path={"/404"} component={NotFound} />
      {/* Final fallback route */}
      <Route component={NotFound} />
    </Switch>
  );
}

function App() {
  return (
    <ErrorBoundary>
      <ThemeProvider defaultTheme="light">
        <AuthProvider>
          <TooltipProvider>
            <Toaster />
            <Router />
          </TooltipProvider>
        </AuthProvider>
      </ThemeProvider>
    </ErrorBoundary>
  );
}

export default App;
