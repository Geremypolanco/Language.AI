import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card } from "@/components/ui/card";
import { useState } from "react";
import { useLocation } from "wouter";

/**
 * Login Page - Senior Design Standard
 * 
 * Design Philosophy:
 * - Asymmetric layout: gradient hero on right, form on left
 * - Warm, encouraging tone from AI tutor
 * - Progressive disclosure: email → password → onboarding
 * - Accessibility-first: proper contrast, keyboard navigation
 */
export default function Login() {
  const [, setLocation] = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");
  const [mode, setMode] = useState<"email" | "password">("email");

  const handleEmailSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setIsLoading(true);

    try {
      // TODO: Connect to backend API
      // const response = await fetch("/api/auth/check-email", {
      //   method: "POST",
      //   headers: { "Content-Type": "application/json" },
      //   body: JSON.stringify({ email }),
      // });
      
      // For now, proceed to password
      setMode("password");
    } catch (err) {
      setError("Something went wrong. Please try again.");
    } finally {
      setIsLoading(false);
    }
  };

  const handlePasswordSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setIsLoading(true);

    try {
      // TODO: Connect to backend API
      // const response = await fetch("/api/auth/login", {
      //   method: "POST",
      //   headers: { "Content-Type": "application/json" },
      //   body: JSON.stringify({ email, password }),
      // });
      
      // Redirect to onboarding or dashboard
      setLocation("/onboarding");
    } catch (err) {
      setError("Invalid email or password. Please try again.");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-stretch">
      {/* Left: Form */}
      <div className="w-full md:w-1/2 flex flex-col justify-center px-6 md:px-12 py-12 bg-background">
        <div className="max-w-sm mx-auto w-full">
          {/* Logo */}
          <div className="mb-12 flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg gradient-primary flex items-center justify-center">
              <span className="text-white font-bold text-lg">L</span>
            </div>
            <h1 className="text-2xl font-bold text-foreground">Language.AI</h1>
          </div>

          {/* Heading */}
          <div className="mb-8">
            <h2 className="text-3xl font-bold text-foreground mb-2">
              {mode === "email" ? "Welcome back" : "Enter your password"}
            </h2>
            <p className="text-muted-foreground text-base">
              {mode === "email"
                ? "Continue learning where you left off"
                : "Keep your account secure"}
            </p>
          </div>

          {/* Form */}
          <form
            onSubmit={mode === "email" ? handleEmailSubmit : handlePasswordSubmit}
            className="space-y-4"
          >
            {mode === "email" ? (
              <>
                <div>
                  <label htmlFor="email" className="block text-sm font-medium text-foreground mb-2">
                    Email address
                  </label>
                  <Input
                    id="email"
                    type="email"
                    placeholder="you@example.com"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    required
                    className="h-11"
                    disabled={isLoading}
                  />
                </div>
                <Button
                  type="submit"
                  className="w-full h-11 bg-primary hover:bg-primary/90 text-primary-foreground font-medium transition-smooth"
                  disabled={isLoading}
                >
                  {isLoading ? "Checking..." : "Continue"}
                </Button>
              </>
            ) : (
              <>
                <div>
                  <p className="text-sm text-muted-foreground mb-3">
                    {email}
                  </p>
                  <label htmlFor="password" className="block text-sm font-medium text-foreground mb-2">
                    Password
                  </label>
                  <Input
                    id="password"
                    type="password"
                    placeholder="••••••••"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    required
                    className="h-11"
                    disabled={isLoading}
                  />
                </div>
                <div className="flex gap-2">
                  <Button
                    type="button"
                    variant="outline"
                    className="flex-1 h-11"
                    onClick={() => setMode("email")}
                    disabled={isLoading}
                  >
                    Back
                  </Button>
                  <Button
                    type="submit"
                    className="flex-1 h-11 bg-primary hover:bg-primary/90 text-primary-foreground font-medium transition-smooth"
                    disabled={isLoading}
                  >
                    {isLoading ? "Signing in..." : "Sign in"}
                  </Button>
                </div>
              </>
            )}

            {error && (
              <div className="p-3 bg-destructive/10 border border-destructive/20 rounded-lg">
                <p className="text-sm text-destructive">{error}</p>
              </div>
            )}
          </form>

          {/* Divider */}
          <div className="relative my-6">
            <div className="absolute inset-0 flex items-center">
              <div className="w-full border-t border-border"></div>
            </div>
            <div className="relative flex justify-center text-sm">
              <span className="px-2 bg-background text-muted-foreground">or</span>
            </div>
          </div>

          {/* Social Login */}
          <Button
            type="button"
            variant="outline"
            className="w-full h-11 border-border hover:bg-muted transition-smooth"
            onClick={() => {
              // TODO: Implement Google OAuth
              console.log("Google OAuth");
            }}
          >
            <svg className="w-5 h-5 mr-2" viewBox="0 0 24 24">
              <path
                fill="currentColor"
                d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
              />
              <path
                fill="currentColor"
                d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
              />
              <path
                fill="currentColor"
                d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
              />
              <path
                fill="currentColor"
                d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
              />
            </svg>
            Continue with Google
          </Button>

          {/* Footer */}
          <p className="text-xs text-muted-foreground text-center mt-6">
            Don't have an account?{" "}
            <button
              type="button"
              className="font-medium text-primary hover:underline"
              onClick={() => setLocation("/signup")}
            >
              Sign up
            </button>
          </p>
        </div>
      </div>

      {/* Right: Hero (Desktop only) */}
      <div className="hidden md:flex md:w-1/2 flex-col justify-center items-center px-12 py-12 gradient-primary relative overflow-hidden">
        {/* Animated background elements */}
        <div className="absolute inset-0 opacity-20">
          <div className="absolute top-10 right-10 w-32 h-32 bg-white rounded-full blur-3xl"></div>
          <div className="absolute bottom-20 left-10 w-40 h-40 bg-white rounded-full blur-3xl"></div>
        </div>

        {/* Content */}
        <div className="relative z-10 text-center max-w-md">
          <h2 className="text-4xl font-bold text-white mb-4">
            Speak like a native
          </h2>
          <p className="text-lg text-white/90 mb-8">
            Master any language with AI tutoring that adapts to your pace. Conversational fluency meets academic rigor.
          </p>

          {/* Feature list */}
          <div className="space-y-4 text-left">
            {[
              { icon: "🎯", text: "Personalized lessons" },
              { icon: "🗣️", text: "Real-time speech feedback" },
              { icon: "📈", text: "Track your progress" },
            ].map((feature, i) => (
              <div key={i} className="flex items-center gap-3 text-white">
                <span className="text-2xl">{feature.icon}</span>
                <span className="font-medium">{feature.text}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
