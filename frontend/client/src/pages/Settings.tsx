import { useEffect, useState } from "react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import DashboardLayout from "@/components/DashboardLayout";
import { useAuth } from "@/contexts/AuthContext";
import { LANGUAGES } from "@/lib/languages";
import { toast } from "sonner";

export default function Settings() {
  const { user, updateUser } = useAuth();
  const [displayName, setDisplayName] = useState("");
  const [nativeLang, setNativeLang] = useState("en");
  const [targetLang, setTargetLang] = useState("es");
  const [dailyGoal, setDailyGoal] = useState(15);
  const [interests, setInterests] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!user) return;
    setDisplayName(user.display_name);
    setNativeLang(user.native_lang);
    setTargetLang(user.target_lang);
    setDailyGoal(user.daily_goal_minutes);
    setInterests(user.interests.join(", "));
  }, [user]);

  const sameLanguage = nativeLang === targetLang;

  const handleSave = async () => {
    if (!displayName.trim()) {
      toast.error("El nombre no puede estar vacío");
      return;
    }
    if (sameLanguage) {
      toast.error("El idioma natal y el idioma a aprender deben ser diferentes");
      return;
    }
    setSaving(true);
    try {
      await updateUser({
        display_name: displayName.trim(),
        native_lang: nativeLang,
        target_lang: targetLang,
        daily_goal_minutes: dailyGoal,
        interests: interests
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean),
      });
      toast.success("Preferencias guardadas");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "No se pudieron guardar los cambios");
    } finally {
      setSaving(false);
    }
  };

  return (
    <DashboardLayout user={{ name: user?.display_name || "User", level: user?.level || "A1" }}>
      <div className="max-w-xl mx-auto px-4 py-8">
        <h1 className="text-3xl font-bold text-foreground mb-2">Configuración</h1>
        <p className="text-muted-foreground mb-8">Actualiza tu perfil y tus idiomas de aprendizaje.</p>

        <Card className="p-6 space-y-5">
          <div>
            <label className="block text-sm font-medium text-foreground mb-1">Nombre</label>
            <Input value={displayName} onChange={(e) => setDisplayName(e.target.value)} />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-foreground mb-1">Idioma natal</label>
              <select
                value={nativeLang}
                onChange={(e) => setNativeLang(e.target.value)}
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
              <label className="block text-sm font-medium text-foreground mb-1">Idioma a aprender</label>
              <select
                value={targetLang}
                onChange={(e) => setTargetLang(e.target.value)}
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
          {sameLanguage && (
            <p className="text-sm text-destructive -mt-3">El idioma natal y el idioma a aprender deben ser diferentes.</p>
          )}

          <div>
            <label className="block text-sm font-medium text-foreground mb-1">Meta diaria (minutos)</label>
            <select
              value={dailyGoal}
              onChange={(e) => setDailyGoal(parseInt(e.target.value))}
              className="w-full px-3 py-2 border border-border rounded-md bg-background text-foreground"
            >
              {[5, 10, 15, 20, 30, 60].map((m) => (
                <option key={m} value={m}>
                  {m} minutos
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-foreground mb-1">Intereses (separados por comas)</label>
            <Input
              placeholder="viajes, cocina, música"
              value={interests}
              onChange={(e) => setInterests(e.target.value)}
            />
          </div>

          <Button className="w-full" onClick={handleSave} disabled={saving}>
            {saving ? "Guardando..." : "Guardar cambios"}
          </Button>
        </Card>
      </div>
    </DashboardLayout>
  );
}
