import { useEffect, useState } from "react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import DashboardLayout from "@/components/DashboardLayout";
import { useAuth } from "@/contexts/AuthContext";
import { useLocale } from "@/contexts/LocaleContext";
import { LANGUAGES } from "@/lib/languages";
import { toast } from "sonner";

const DAILY_GOAL_OPTIONS = [5, 10, 15, 20, 30, 60];

export default function Settings() {
  const { user, updateUser } = useAuth();
  const { t } = useLocale();
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
      toast.error(t("settings.emptyName"));
      return;
    }
    if (sameLanguage) {
      toast.error(t("settings.sameLanguage"));
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
      toast.success(t("settings.saved"));
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t("settings.saveError"));
    } finally {
      setSaving(false);
    }
  };

  const selectClass =
    "w-full px-3 py-2 border border-border rounded-md bg-background text-foreground";

  return (
    <DashboardLayout user={{ name: user?.display_name || t("common.fallbackUser"), level: user?.level || "A1" }}>
      <div className="max-w-xl mx-auto px-4 py-8">
        <h1 className="text-3xl font-bold text-foreground mb-2">{t("settings.title")}</h1>
        <p className="text-muted-foreground mb-8">{t("settings.subtitle")}</p>

        <Card className="p-6 space-y-5">
          <div>
            <label className="block text-sm font-medium text-foreground mb-1">{t("settings.name")}</label>
            <Input value={displayName} onChange={(e) => setDisplayName(e.target.value)} />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-foreground mb-1">{t("settings.nativeLang")}</label>
              <select
                value={nativeLang}
                onChange={(e) => setNativeLang(e.target.value)}
                className={selectClass}
              >
                {LANGUAGES.map(([code, name]) => (
                  <option key={code} value={code}>
                    {name}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-foreground mb-1">{t("settings.targetLang")}</label>
              <select
                value={targetLang}
                onChange={(e) => setTargetLang(e.target.value)}
                className={selectClass}
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
            <p className="text-sm text-destructive -mt-3">{t("settings.sameLanguage")}</p>
          )}

          <div>
            <label className="block text-sm font-medium text-foreground mb-1">{t("settings.dailyGoal")}</label>
            <select
              value={dailyGoal}
              onChange={(e) => setDailyGoal(parseInt(e.target.value))}
              className={selectClass}
            >
              {DAILY_GOAL_OPTIONS.map((m) => (
                <option key={m} value={m}>
                  {t("settings.minutesUnit", { m })}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-foreground mb-1">{t("settings.interests")}</label>
            <Input
              placeholder={t("settings.interestsPh")}
              value={interests}
              onChange={(e) => setInterests(e.target.value)}
            />
          </div>

          <Button className="w-full" onClick={handleSave} disabled={saving}>
            {saving ? t("settings.saving") : t("settings.save")}
          </Button>
        </Card>
      </div>
    </DashboardLayout>
  );
}
