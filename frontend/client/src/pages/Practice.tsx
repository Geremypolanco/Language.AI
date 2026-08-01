import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import DashboardLayout from "@/components/DashboardLayout";
import ExercisePlayer from "@/components/ExercisePlayer";
import { useAuth } from "@/contexts/AuthContext";
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
  { id: "listening", title: "Listening", icon: "👂", description: "Train your ear with native speakers", exerciseType: "listen_type" },
  { id: "speaking", title: "Speaking", icon: "🗣️", description: "Practice pronunciation and fluency", exerciseType: "speak_repeat" },
  { id: "reading", title: "Reading", icon: "📖", description: "Improve comprehension with texts", exerciseType: "translate_to_native" },
  { id: "writing", title: "Writing", icon: "✍️", description: "Enhance written expression", exerciseType: "fill_blank" },
  { id: "grammar", title: "Grammar", icon: "📝", description: "Master grammar rules and structures", exerciseType: "multiple_choice" },
  { id: "vocabulary", title: "Vocabulary", icon: "📚", description: "Expand your word bank", exerciseType: "translate_to_target" },
];

const DIFFICULTIES: { label: string; delta: number }[] = [
  { label: "Easy", delta: -1 },
  { label: "Medium", delta: 0 },
  { label: "Hard", delta: 1 },
];

export default function Practice() {
  const { user } = useAuth();
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
      toast.error(err instanceof Error ? err.message : "No se pudo cargar la práctica");
    } finally {
      setLoadingMode(null);
    }
  };

  if (active) {
    return (
      <DashboardLayout user={{ name: user?.display_name || "User", level: user?.level || "A1" }}>
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
    <DashboardLayout user={{ name: user?.display_name || "User", level: user?.level || "A1" }}>
      <div className="max-w-6xl mx-auto px-4 py-8">
        <div className="mb-8">
          <h1 className="text-4xl font-bold text-foreground mb-2">Practice</h1>
          <p className="text-lg text-muted-foreground">
            Choose a skill to practice. No fixed order, no limits.
          </p>
        </div>

        <Card className="p-6 mb-8 bg-gradient-to-r from-primary/5 to-secondary/5 border-primary/20">
          <div className="flex gap-4">
            <div className="text-3xl">🤖</div>
            <div>
              <p className="font-semibold text-foreground mb-1">Your AI Tutor</p>
              <p className="text-muted-foreground">
                Want to focus on a specific skill? Pick any mode below and practice as much as you want. The difficulty adjusts to your level.
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

                <h3 className="text-xl font-bold text-foreground mb-2">{mode.title}</h3>
                <p className="text-muted-foreground text-sm mb-6">{mode.description}</p>

                <div className="space-y-2">
                  <p className="text-xs font-semibold text-muted-foreground uppercase">Choose difficulty:</p>
                  <div className="flex gap-2">
                    {DIFFICULTIES.map((d) => {
                      const key = `${mode.exerciseType}-${d.delta}`;
                      return (
                        <Button
                          key={d.label}
                          size="sm"
                          variant="outline"
                          className="flex-1 text-xs"
                          disabled={loadingMode === key}
                          onClick={() => startPractice(mode.exerciseType, d.delta)}
                        >
                          {loadingMode === key ? "..." : d.label}
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
