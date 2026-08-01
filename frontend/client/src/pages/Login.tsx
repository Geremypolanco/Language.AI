import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card } from "@/components/ui/card";
import { useState } from "react";
import { useLocation } from "wouter";
import { useAuth } from "@/contexts/AuthContext";

/**
 * Login Page - Google OAuth + Onboarding
 * 
 * Flow:
 * 1. Usuario hace click en "Continuar con Google"
 * 2. Redirige a /auth/google/login
 * 3. Google redirige a /auth/google/callback
 * 4. Backend deja cookie "pending"
 * 5. SPA llama /api/session → {pending: true, email, name, picture}
 * 6. Muestra formulario de onboarding
 * 7. POST /api/users con perfil
 * 8. Redirige a /path
 */

const LANGUAGES = [
  ["en", "English"],
  ["es", "Español"],
  ["fr", "Français"],
  ["de", "Deutsch"],
  ["it", "Italiano"],
  ["pt", "Português"],
  ["ja", "日本語"],
  ["ko", "한국어"],
  ["zh", "中文"],
  ["ru", "Русский"],
];

export default function Login() {
  const [, setLocation] = useLocation();
  const { session, loading, login, devLogin, createProfile } = useAuth();
  const [isOnboarding, setIsOnboarding] = useState(false);
  const [formData, setFormData] = useState({
    display_name: session?.name || "",
    native_lang: "en",
    target_lang: "es",
    level: "A1",
    interests: "",
    daily_goal_minutes: 15,
  });
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [devEmail, setDevEmail] = useState("");
  const [devName, setDevName] = useState("");

  // Si ya está autenticado y no pending, redirige a /path
  if (!loading && session?.authenticated && !session?.pending) {
    setLocation("/path");
    return null;
  }

  // Si está pending, muestra onboarding
  if (!loading && session?.pending && !isOnboarding) {
    setIsOnboarding(true);
    setFormData((prev) => ({
      ...prev,
      display_name: session.name || "",
    }));
  }

  const handleSubmitOnboarding = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);
    setError("");

    try {
      await createProfile({
        display_name: formData.display_name,
        native_lang: formData.native_lang,
        target_lang: formData.target_lang,
        level: formData.level,
        interests: formData.interests
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean),
        daily_goal_minutes: formData.daily_goal_minutes,
      });
      setLocation("/path");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error creating profile");
    } finally {
      setIsSubmitting(false);
    }
  };

  if (isOnboarding) {
    return (
      <div className="min-h-screen flex items-center justify-center px-4 py-12 bg-background">
        <Card className="w-full max-w-md p-8">
          <div className="mb-8">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 rounded-lg gradient-primary flex items-center justify-center">
                <span className="text-white font-bold">L</span>
              </div>
              <h1 className="text-2xl font-bold">Language.AI</h1>
            </div>
            <h2 className="text-2xl font-bold text-foreground mb-2">Complete Your Profile</h2>
            <p className="text-muted-foreground">
              Welcome, {session?.name}! Let's set up your learning preferences.
            </p>
          </div>

          <form onSubmit={handleSubmitOnboarding} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-foreground mb-1">
                Display Name
              </label>
              <Input
                value={formData.display_name}
                onChange={(e) =>
                  setFormData({ ...formData, display_name: e.target.value })
                }
                required
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-foreground mb-1">
                  Native Language
                </label>
                <select
                  value={formData.native_lang}
                  onChange={(e) =>
                    setFormData({ ...formData, native_lang: e.target.value })
                  }
                  className="w-full px-3 py-2 border border-border rounded-md bg-background text-foreground"
                >
                  {LANGUAGES.map(([code, name]) => (
                    <option key={code} value={code}>
                      {name}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium text-foreground mb-1">
                  Target Language
                </label>
                <select
                  value={formData.target_lang}
                  onChange={(e) =>
                    setFormData({ ...formData, target_lang: e.target.value })
                  }
                  className="w-full px-3 py-2 border border-border rounded-md bg-background text-foreground"
                >
                  {LANGUAGES.map(([code, name]) => (
                    <option key={code} value={code}>
                      {name}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-foreground mb-1">
                Starting Level
              </label>
              <select
                value={formData.level}
                onChange={(e) =>
                  setFormData({ ...formData, level: e.target.value })
                }
                className="w-full px-3 py-2 border border-border rounded-md bg-background text-foreground"
              >
                <option value="A1">Beginner (A1)</option>
                <option value="A2">Elementary (A2)</option>
                <option value="B1">Intermediate (B1)</option>
                <option value="B2">Upper-Intermediate (B2)</option>
                <option value="C1">Advanced (C1)</option>
                <option value="C2">Fluent (C2)</option>
              </select>
            </div>

            <div>
              <label className="block text-sm font-medium text-foreground mb-1">
                Interests (comma-separated)
              </label>
              <Input
                placeholder="e.g., travel, cooking, movies"
                value={formData.interests}
                onChange={(e) =>
                  setFormData({ ...formData, interests: e.target.value })
                }
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-foreground mb-1">
                Daily Goal (minutes)
              </label>
              <select
                value={formData.daily_goal_minutes}
                onChange={(e) =>
                  setFormData({
                    ...formData,
                    daily_goal_minutes: parseInt(e.target.value),
                  })
                }
                className="w-full px-3 py-2 border border-border rounded-md bg-background text-foreground"
              >
                <option value={5}>5 minutes</option>
                <option value={10}>10 minutes</option>
                <option value={15}>15 minutes</option>
                <option value={20}>20 minutes</option>
                <option value={30}>30 minutes</option>
                <option value={60}>60 minutes</option>
              </select>
            </div>

            {error && (
              <div className="p-3 bg-destructive/10 border border-destructive/20 rounded-lg">
                <p className="text-sm text-destructive">{error}</p>
              </div>
            )}

            <Button
              type="submit"
              className="w-full bg-primary hover:bg-primary/90"
              disabled={isSubmitting}
            >
              {isSubmitting ? "Setting up..." : "Start Learning"}
            </Button>
          </form>
        </Card>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary mx-auto mb-4"></div>
          <p className="text-muted-foreground">Loading...</p>
        </div>
      </div>
    );
  }

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
            <h2 className="text-3xl font-bold text-foreground mb-2">Welcome</h2>
            <p className="text-muted-foreground text-base">
              Master any language with AI tutoring
            </p>
          </div>

          {/* Social Login */}
          <Button
            type="button"
            className="w-full h-11 bg-primary hover:bg-primary/90 text-primary-foreground font-medium transition-smooth mb-4"
            onClick={login}
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

          {/* Divider */}
          <div className="relative my-6">
            <div className="absolute inset-0 flex items-center">
              <div className="w-full border-t border-border"></div>
            </div>
            <div className="relative flex justify-center text-sm">
              <span className="px-2 bg-background text-muted-foreground">or</span>
            </div>
          </div>

          {/* Dev Login */}
          <div className="space-y-2">
            <p className="text-xs text-muted-foreground text-center">
              Development: Quick login without Google
            </p>
            <div className="flex gap-2">
              <Input
                placeholder="Email"
                type="email"
                value={devEmail}
                onChange={(e) => setDevEmail(e.target.value)}
                className="h-10"
              />
              <Input
                placeholder="Name"
                value={devName}
                onChange={(e) => setDevName(e.target.value)}
                className="h-10"
              />
            </div>
            <Button
              type="button"
              variant="outline"
              className="w-full h-10"
              onClick={() => devLogin(devEmail, devName)}
              disabled={!devEmail || !devName}
            >
              Dev Login
            </Button>
          </div>
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
          <h2 className="text-4xl font-bold text-white mb-4">Speak like a native</h2>
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
