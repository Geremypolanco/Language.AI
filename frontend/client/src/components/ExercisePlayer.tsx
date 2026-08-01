import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { api, Exercise } from "@/lib/api";
import { toast } from "sonner";

interface ExercisePlayerProps {
  userId: string;
  unitId: string;
  exercises: Exercise[];
  onExit: () => void;
}

// Types with a fixed set of options to click.
const CHOICE_TYPES = new Set(["multiple_choice", "image_match"]);
// Types answered by typing text, graded by normalized string match.
const TEXT_TYPES = new Set(["fill_blank", "translate_to_target", "translate_to_native", "listen_type"]);
// Types with no reliable text/click grading here (need real audio/STT) — self-assessed instead.
const SELF_ASSESSED_TYPES = new Set(["speak_repeat", "free_conversation_prompt"]);

function normalize(s: string): string {
  return s.trim().toLowerCase().replace(/[.,!?¡¿]/g, "");
}

export default function ExercisePlayer({ userId, unitId, exercises, onExit }: ExercisePlayerProps) {
  const [index, setIndex] = useState(0);
  const [textAnswer, setTextAnswer] = useState("");
  const [revealed, setRevealed] = useState(false);
  const [wasCorrect, setWasCorrect] = useState(false);
  const [correctCount, setCorrectCount] = useState(0);
  const [startedAt] = useState(() => Date.now());
  const [submitting, setSubmitting] = useState(false);
  const [summary, setSummary] = useState<{
    xp_gained: number;
    gems_gained: number;
    streak_days: number;
    leveled_up: string | null;
  } | null>(null);

  const exercise = exercises[index];
  const isLast = index === exercises.length - 1;

  const recordAnswer = async (correct: boolean) => {
    setWasCorrect(correct);
    setRevealed(true);
    if (correct) setCorrectCount((c) => c + 1);
    if (exercise.vocab_key) {
      try {
        await api.submitLessonAnswer(userId, {
          vocab_key: exercise.vocab_key,
          correct,
          attempts_before_correct: 0,
        });
      } catch {
        // SRS scheduling is best-effort — a failure here shouldn't block the lesson.
      }
    }
  };

  const handleChoice = (option: string) => {
    if (revealed) return;
    recordAnswer(normalize(option) === normalize(exercise.correct_answer));
  };

  const handleTextSubmit = () => {
    if (revealed || !textAnswer.trim()) return;
    recordAnswer(normalize(textAnswer) === normalize(exercise.correct_answer));
  };

  const handleSelfAssess = (correct: boolean) => {
    if (revealed) return;
    recordAnswer(correct);
  };

  const handleNext = async () => {
    if (!isLast) {
      setIndex((i) => i + 1);
      setTextAnswer("");
      setRevealed(false);
      return;
    }
    setSubmitting(true);
    try {
      const finalCorrect = correctCount;
      const score = finalCorrect / exercises.length;
      const elapsedSeconds = Math.round((Date.now() - startedAt) / 1000);
      const result = await api.completeLesson(userId, unitId, score, elapsedSeconds);
      setSummary(result as typeof summary);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "No se pudo guardar el resultado de la lección");
      onExit();
    } finally {
      setSubmitting(false);
    }
  };

  if (summary) {
    return (
      <Card className="max-w-lg mx-auto p-8 text-center space-y-4">
        <div className="text-5xl">🎉</div>
        <h2 className="text-2xl font-bold text-foreground">¡Lección completada!</h2>
        <div className="grid grid-cols-3 gap-4 py-4">
          <div>
            <p className="text-2xl font-bold text-primary">+{summary.xp_gained}</p>
            <p className="text-xs text-muted-foreground">XP</p>
          </div>
          <div>
            <p className="text-2xl font-bold text-primary">+{summary.gems_gained}</p>
            <p className="text-xs text-muted-foreground">Gemas</p>
          </div>
          <div>
            <p className="text-2xl font-bold text-orange-500">{summary.streak_days}</p>
            <p className="text-xs text-muted-foreground">Racha (días)</p>
          </div>
        </div>
        {summary.leveled_up && (
          <p className="text-primary font-semibold">¡Subiste a nivel {summary.leveled_up}!</p>
        )}
        <Button className="w-full" onClick={onExit}>
          Continuar
        </Button>
      </Card>
    );
  }

  return (
    <Card className="max-w-lg mx-auto p-8 space-y-6">
      <div>
        <div className="flex justify-between text-sm text-muted-foreground mb-2">
          <span>
            Ejercicio {index + 1} de {exercises.length}
          </span>
          <span>{correctCount} correctas</span>
        </div>
        <Progress value={(index / exercises.length) * 100} className="h-2" />
      </div>

      <div>
        <p className="text-lg font-semibold text-foreground mb-1">{exercise.prompt}</p>
        {exercise.target_text && (
          <p className="text-2xl font-bold text-primary mb-2">{exercise.target_text}</p>
        )}
      </div>

      {CHOICE_TYPES.has(exercise.type) && (
        <div className="grid grid-cols-1 gap-2">
          {exercise.options.map((opt) => {
            const isCorrectOpt = normalize(opt) === normalize(exercise.correct_answer);
            return (
              <Button
                key={opt}
                variant="outline"
                disabled={revealed}
                onClick={() => handleChoice(opt)}
                className={
                  revealed && isCorrectOpt
                    ? "border-green-500 bg-green-50 text-green-700"
                    : revealed
                      ? "opacity-50"
                      : ""
                }
              >
                {opt}
              </Button>
            );
          })}
        </div>
      )}

      {TEXT_TYPES.has(exercise.type) && (
        <div className="flex gap-2">
          <Input
            value={textAnswer}
            onChange={(e) => setTextAnswer(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleTextSubmit()}
            disabled={revealed}
            placeholder="Tu respuesta..."
          />
          <Button onClick={handleTextSubmit} disabled={revealed || !textAnswer.trim()}>
            Verificar
          </Button>
        </div>
      )}

      {SELF_ASSESSED_TYPES.has(exercise.type) && !revealed && (
        <div className="flex gap-2">
          <Button variant="outline" className="flex-1" onClick={() => handleSelfAssess(true)}>
            ✅ Lo logré
          </Button>
          <Button variant="outline" className="flex-1" onClick={() => handleSelfAssess(false)}>
            🔁 Necesito practicar más
          </Button>
        </div>
      )}

      {revealed && (
        <div
          className={`p-3 rounded-lg text-sm ${
            wasCorrect ? "bg-green-50 text-green-700 border border-green-200" : "bg-amber-50 text-amber-700 border border-amber-200"
          }`}
        >
          {wasCorrect ? "¡Correcto!" : `La respuesta era: ${exercise.correct_answer}`}
        </div>
      )}

      <div className="flex justify-between">
        <Button variant="ghost" onClick={onExit}>
          Salir
        </Button>
        {revealed && (
          <Button onClick={handleNext} disabled={submitting}>
            {submitting ? "Guardando..." : isLast ? "Terminar" : "Siguiente"}
          </Button>
        )}
      </div>
    </Card>
  );
}
