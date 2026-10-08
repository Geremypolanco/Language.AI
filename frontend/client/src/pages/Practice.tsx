import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import DashboardLayout from "@/components/DashboardLayout";
import ExercisePlayer from "@/components/ExercisePlayer";
import { useAuth } from "@/contexts/AuthContext";
import { useLocale } from "@/contexts/LocaleContext";
import { api, CEFRLevel, Exercise } from "@/lib/api";
import { useState } from "react";
import { toast } from "sonner";

const CEFR_ORDER: CEFRLevel[] = ["A1", "A2", "B1", "B2", "C1", "C2", "NATIVE"];

function shiftLevel(level: CEFRLevel, delta: number): CEFRLevel {
  const idx = CEFR_ORDER.indexOf(level);
  const clamped = Math.max(0, Math.min(CEFR_ORDER.length - 1, idx + delta));
  return CEFR_ORDER[clamped];
}

// Maps each UI-facing skill to the closest real ExerciseType the backend supports.
const PRACTICE_MODES = [
  { id: "listening", titleKey: "practice.mode.listening", descKey: "practice.mode.listening.desc", icon: "👂", exerciseType: "listen_type" },
  { id: "speaking", titleKey: "practice.mode.speaking", descKey: "practice.mode.speaking.desc", icon: "🗣️", exerciseType: "speak_repeat" },
  { id: "reading", titleKey: "practice.mode.reading", descKey: "practice.mode.reading.desc", icon: "📖", exerciseType: "translate_to_native" },
  { id: "writing", titleKey: "practice.mode.writing", descKey: "practice.mode.writing.desc", icon: "✍️", exerciseType: "fill_blank" },
  { id: "grammar", titleKey: "practice.mode.grammar", descKey: "practice.mode.grammar.desc", icon: "📝", exerciseType: "multiple_choice" },
  { id: "vocabulary", titleKey: "practice.mode.vocabulary", descKey: "practice.mode.vocabulary.desc", icon: "📚", exerciseType: "translate_to_target" },
];

const DIFFICULTIES: { key: string; delta: number }[] = [
  { key: "practice.difficulty.easy", delta: -1 },
  { key: "practice.difficulty.medium", delta: 0 },
  { key: "practice.difficulty.hard", delta: 1 },
];

export default function Practice() {
  const { user } = useAuth();
  const { t } = useLocale();
  const [loadingMode, setLoadingMode] = useState<string | null>(null);
  const [active, setActive] = useState<{ unitId: string; exercises: Exercise[] } | null>(null);

  const startPractice = async (exerciseType: string, delta: number) => {
    if (!user?.id) return;
    const key = `${exerciseType}-${delta}`;
    setLoadingMode(key);
    try {
      const level = shiftLevel(user.level, delta);
      const { unit_id, exercises } = await api.practiceLessonSkill(user.id, exerciseType, level);
      setActive({ unitId: unit_id, exercises });
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t("practice.loadError"));
    } finally {
      setLoadingMode(null);
    }
  };

  const userBadge = { name: user?.display_name || t("common.fallbackUser"), level: user?.level || "A1" };

  if (active) {
    return (
      <DashboardLayout user={userBadge}>
        <div className="px-4 py-8">
          <ExercisePlayer
            userId={user!.id}
            unitId={active.unitId}
            exercises={active.exercises}
            onExit={() => setActive(null)}
          />
        </div>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout user={userBadge}>
      <div className="max-w-6xl mx-auto px-4 py-8">
        <div className="mb-8">
          <h1 className="text-4xl font-bold text-foreground mb-2">{t("practice.title")}</h1>
          <p className="text-lg text-muted-foreground">
            {t("practice.subtitle")}
          </p>
        </div>

        <Card className="p-6 mb-8 bg-gradient-to-r from-primary/5 to-secondary/5 border-primary/20">
          <div className="flex gap-4">
            <div className="text-3xl">🤖</div>
            <div>
              <p className="font-semibold text-foreground mb-1">{t("practice.tutorTitle")}</p>
              <p className="text-muted-foreground">
                {t("practice.tutorBody")}
              </p>
            </div>
          </div>
        </Card>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {PRACTICE_MODES.map((mode) => (
            <Card key={mode.id} className="p-6 hover:shadow-lg transition-smooth overflow-hidden">
              <div className="relative z-10">
                <div className="flex items-start justify-between mb-4">
                  <span className="text-4xl">{mode.icon}</span>
                </div>

                <h3 className="text-xl font-bold text-foreground mb-2">{t(mode.titleKey)}</h3>
                <p className="text-muted-foreground text-sm mb-6">{t(mode.descKey)}</p>

                <div className="space-y-2">
                  <p className="text-xs font-semibold text-muted-foreground uppercase">{t("practice.chooseDifficulty")}</p>
                  <div className="flex gap-2">
                    {DIFFICULTIES.map((d) => {
                      const key = `${mode.exerciseType}-${d.delta}`;
                      return (
                        <Button
                          key={d.key}
                          size="sm"
                          variant="outline"
                          className="flex-1 text-xs"
                          disabled={loadingMode === key}
                          onClick={() => startPractice(mode.exerciseType, d.delta)}
                        >
                          {loadingMode === key ? "..." : t(d.key)}
                        </Button>
                      );
                    })}
                  </div>
                </div>
              </div>
            </Card>
          ))}
        </div>
      </div>
    </DashboardLayout>
  );
}
