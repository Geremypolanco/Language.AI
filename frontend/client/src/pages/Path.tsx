import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import DashboardLayout from "@/components/DashboardLayout";
import ExercisePlayer from "@/components/ExercisePlayer";
import { useAuth } from "@/contexts/AuthContext";
import { api, Exercise, Lesson } from "@/lib/api";
import { useEffect, useState } from "react";
import { toast } from "sonner";

export default function Path() {
  const { user } = useAuth();
  const [lessons, setLessons] = useState<Lesson[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [activeUnit, setActiveUnit] = useState<{ unitId: string; exercises: Exercise[] } | null>(null);
  const [startingUnitId, setStartingUnitId] = useState<string | null>(null);
  const [dueReviews, setDueReviews] = useState(0);
  const [startingReview, setStartingReview] = useState(false);

  const fetchLessons = async () => {
    if (!user?.id) return;
    try {
      const data = await api.getLessonsPath(user.id);
      setLessons(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudieron cargar las lecciones");
    } finally {
      setLoading(false);
    }
  };

  const fetchDueReviews = async () => {
    if (!user?.id) return;
    try {
      const progress = await api.getProgressSnapshot(user.id);
      setDueReviews(progress.due_reviews);
    } catch {
      // Non-critical — the Repaso card just won't show a count.
    }
  };

  useEffect(() => {
    fetchLessons();
    fetchDueReviews();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.id]);

  const handleStart = async (unitId: string) => {
    if (!user?.id) return;
    setStartingUnitId(unitId);
    try {
      const exercises = await api.getLesson(user.id, unitId);
      setActiveUnit({ unitId, exercises });
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "No se pudieron cargar los ejercicios");
    } finally {
      setStartingUnitId(null);
    }
  };

  const handleStartReview = async () => {
    if (!user?.id) return;
    setStartingReview(true);
    try {
      const { unit_id, exercises } = await api.getReviewSession(user.id);
      if (exercises.length === 0) {
        toast("No tienes repasos pendientes ahora mismo. ¡Vuelve más tarde!");
        return;
      }
      setActiveUnit({ unitId: unit_id, exercises });
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "No se pudo cargar el repaso");
    } finally {
      setStartingReview(false);
    }
  };

  const masteredCount = lessons.filter((l) => l.state === "mastered").length;
  const progressPercent = lessons.length > 0 ? (masteredCount / lessons.length) * 100 : 0;

  if (loading) {
    return (
      <DashboardLayout user={{ name: user?.display_name || "User", level: user?.level || "A1" }}>
        <div className="flex items-center justify-center h-96">
          <p className="text-muted-foreground">Cargando lecciones...</p>
        </div>
      </DashboardLayout>
    );
  }

  if (activeUnit) {
    return (
      <DashboardLayout user={{ name: user?.display_name || "User", level: user?.level || "A1" }}>
        <div className="px-4 py-8">
          <ExercisePlayer
            userId={user!.id}
            unitId={activeUnit.unitId}
            exercises={activeUnit.exercises}
            onExit={() => {
              setActiveUnit(null);
              fetchLessons();
              fetchDueReviews();
            }}
          />
        </div>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout user={{ name: user?.display_name || "User", level: user?.level || "A1" }}>
      <div className="max-w-6xl mx-auto px-4 py-8">
        <div className="mb-8">
          <h1 className="text-4xl font-bold text-foreground mb-2">Tu ruta de aprendizaje</h1>
          <p className="text-lg text-muted-foreground">
            Avanza por lecciones estructuradas a tu propio ritmo
          </p>
        </div>

        {error && (
          <Card className="p-4 mb-8 bg-destructive/10 border-destructive/20">
            <p className="text-sm text-destructive">{error}</p>
          </Card>
        )}

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
          <Card className="p-6 shadow-sm">
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-semibold text-foreground">Progreso general</h3>
              <span className="text-2xl">📈</span>
            </div>
            <div className="space-y-2">
              <Progress value={progressPercent} className="h-2" />
              <p className="text-sm text-muted-foreground">
                {masteredCount} de {lessons.length} unidades dominadas
              </p>
            </div>
          </Card>

          <Card className="p-6 shadow-sm">
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-semibold text-foreground">Puntos de experiencia</h3>
              <span className="text-2xl">⭐</span>
            </div>
            <p className="text-3xl font-bold text-primary mb-1">{user?.xp ?? 0}</p>
            <p className="text-sm text-muted-foreground">Sigue aprendiendo para ganar más</p>
          </Card>

          <Card className="p-6 shadow-sm">
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-semibold text-foreground">Racha actual</h3>
              <span className="text-2xl">🔥</span>
            </div>
            <p className="text-3xl font-bold text-orange-500 mb-1">{user?.streak_days ?? 0} días</p>
            <p className="text-sm text-muted-foreground">¡Sigue así!</p>
          </Card>
        </div>

        <Card className={`p-6 mb-8 shadow-sm ${dueReviews > 0 ? "bg-amber-50 border-amber-200" : ""}`}>
          <div className="flex items-center justify-between gap-4">
            <div>
              <div className="flex items-center gap-2 mb-1">
                <span className="text-2xl">🔁</span>
                <h3 className="text-lg font-semibold text-foreground">Repaso</h3>
              </div>
              <p className="text-sm text-muted-foreground">
                {dueReviews > 0
                  ? `${dueReviews} palabra${dueReviews === 1 ? "" : "s"} lista${dueReviews === 1 ? "" : "s"} para repasar ahora`
                  : "Palabras que ya aprendiste, para no olvidarlas — te avisamos cuando toque repasar"}
              </p>
            </div>
            <Button
              variant={dueReviews > 0 ? "default" : "outline"}
              disabled={startingReview}
              onClick={handleStartReview}
            >
              {startingReview ? "Cargando..." : "Repasar ahora"}
            </Button>
          </div>
        </Card>

        <div className="space-y-4">
          <h2 className="text-2xl font-bold text-foreground">Lecciones</h2>
          <div className="grid gap-4">
            {lessons.length === 0 ? (
              <Card className="p-6 text-center">
                <p className="text-muted-foreground">Aún no hay lecciones disponibles</p>
              </Card>
            ) : (
              lessons.map((lesson, index) => (
                <Card
                  key={lesson.id}
                  className={`p-6 hover:shadow-md transition-smooth ${
                    lesson.state === "mastered" ? "bg-green-50 border-green-200" : ""
                  }`}
                >
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex-1">
                      <div className="flex items-center gap-3 mb-2">
                        <span className="text-2xl">{index + 1}</span>
                        <h3 className="text-xl font-semibold text-foreground">{lesson.topic_es}</h3>
                        {lesson.state === "mastered" && <span className="text-green-600">✓</span>}
                      </div>
                      <div className="flex items-center gap-4">
                        <span className="px-3 py-1 rounded-full text-sm font-medium bg-blue-100 text-blue-700">
                          {lesson.level}
                        </span>
                        {lesson.best_score > 0 && (
                          <span className="text-sm text-muted-foreground">
                            Mejor puntaje: {Math.round(lesson.best_score * 100)}%
                          </span>
                        )}
                      </div>
                    </div>
                    <Button
                      className={`h-10 transition-smooth ${
                        lesson.state === "mastered" ? "bg-green-600 hover:bg-green-700" : "bg-primary hover:bg-primary/90"
                      }`}
                      disabled={startingUnitId === lesson.id}
                      onClick={() => handleStart(lesson.id)}
                    >
                      {startingUnitId === lesson.id ? "Cargando..." : lesson.state === "mastered" ? "Repasar" : "Comenzar"}
                    </Button>
                  </div>
                </Card>
              ))
            )}
          </div>
        </div>
      </div>
    </DashboardLayout>
  );
}
