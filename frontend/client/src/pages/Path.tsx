import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import DashboardLayout from "@/components/DashboardLayout";
import { useAuth } from "@/contexts/AuthContext";
import { api } from "@/lib/api";
import { useEffect, useState } from "react";

interface Lesson {
  id: string;
  title: string;
  description: string;
  level: "beginner" | "intermediate" | "advanced";
  duration: number;
  completed: boolean;
  xp: number;
}

export default function Path() {
  const { user } = useAuth();
  const [lessons, setLessons] = useState<Lesson[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!user?.id) return;

    const fetchLessons = async () => {
      try {
        const data = await api.getLessonsPath(user.id);
        setLessons(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Error loading lessons");
      } finally {
        setLoading(false);
      }
    };

    fetchLessons();
  }, [user?.id]);

  const completedCount = lessons.filter((l) => l.completed).length;
  const totalXP = lessons.filter((l) => l.completed).reduce((sum, l) => sum + l.xp, 0);
  const progressPercent = lessons.length > 0 ? (completedCount / lessons.length) * 100 : 0;

  if (loading) {
    return (
      <DashboardLayout user={{ name: user?.display_name || "User", level: user?.level || 1 }}>
        <div className="flex items-center justify-center h-96">
          <p className="text-muted-foreground">Loading lessons...</p>
        </div>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout user={{ name: user?.display_name || "User", level: user?.level || 1 }}>
      <div className="max-w-6xl mx-auto px-4 py-8">
        <div className="mb-8">
          <h1 className="text-4xl font-bold text-foreground mb-2">Your Learning Path</h1>
          <p className="text-lg text-muted-foreground">
            Progress through structured lessons at your own pace
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
              <h3 className="font-semibold text-foreground">Overall Progress</h3>
              <span className="text-2xl">📈</span>
            </div>
            <div className="space-y-2">
              <Progress value={progressPercent} className="h-2" />
              <p className="text-sm text-muted-foreground">
                {completedCount} of {lessons.length} lessons completed
              </p>
            </div>
          </Card>

          <Card className="p-6 shadow-sm">
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-semibold text-foreground">Experience Points</h3>
              <span className="text-2xl">⭐</span>
            </div>
            <p className="text-3xl font-bold text-primary mb-1">{totalXP}</p>
            <p className="text-sm text-muted-foreground">Keep learning to earn more</p>
          </Card>

          <Card className="p-6 shadow-sm">
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-semibold text-foreground">Current Streak</h3>
              <span className="text-2xl">🔥</span>
            </div>
            <p className="text-3xl font-bold text-orange-500 mb-1">7 days</p>
            <p className="text-sm text-muted-foreground">Keep it going!</p>
          </Card>
        </div>

        <Card className="p-6 mb-8 bg-gradient-to-r from-primary/5 to-secondary/5 border-primary/20">
          <div className="flex gap-4">
            <div className="text-3xl">🤖</div>
            <div>
              <p className="font-semibold text-foreground mb-1">Your AI Tutor</p>
              <p className="text-muted-foreground">
                You're making great progress! Complete the next lesson to earn more XP and unlock new content.
              </p>
            </div>
          </div>
        </Card>

        <div className="space-y-4">
          <h2 className="text-2xl font-bold text-foreground">Lessons</h2>
          <div className="grid gap-4">
            {lessons.length === 0 ? (
              <Card className="p-6 text-center">
                <p className="text-muted-foreground">No lessons available yet</p>
              </Card>
            ) : (
              lessons.map((lesson, index) => (
                <Card
                  key={lesson.id}
                  className={`p-6 hover:shadow-md transition-smooth cursor-pointer ${
                    lesson.completed ? "bg-green-50 border-green-200" : ""
                  }`}
                >
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex-1">
                      <div className="flex items-center gap-3 mb-2">
                        <span className="text-2xl">{index + 1}</span>
                        <h3 className="text-xl font-semibold text-foreground">{lesson.title}</h3>
                        {lesson.completed && <span className="text-green-600">✓</span>}
                      </div>
                      <p className="text-muted-foreground mb-3">{lesson.description}</p>
                      <div className="flex items-center gap-4">
                        <span className={`px-3 py-1 rounded-full text-sm font-medium ${
                          lesson.level === "beginner" ? "bg-green-100 text-green-700" :
                          lesson.level === "intermediate" ? "bg-blue-100 text-blue-700" :
                          "bg-purple-100 text-purple-700"
                        }`}>
                          {lesson.level.charAt(0).toUpperCase() + lesson.level.slice(1)}
                        </span>
                        <span className="text-sm text-muted-foreground">⏱️ {lesson.duration} min</span>
                        <span className="text-sm text-primary font-semibold">+{lesson.xp} XP</span>
                      </div>
                    </div>
                    <Button
                      className={`h-10 transition-smooth ${
                        lesson.completed
                          ? "bg-green-600 hover:bg-green-700"
                          : "bg-primary hover:bg-primary/90"
                      }`}
                    >
                      {lesson.completed ? "Review" : "Start"}
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
