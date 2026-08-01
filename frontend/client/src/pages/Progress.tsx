import { Card } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import DashboardLayout from "@/components/DashboardLayout";
import { useAuth } from "@/contexts/AuthContext";
import { api, DashboardData } from "@/lib/api";
import { useEffect, useState } from "react";
import { toast } from "sonner";

const HEATMAP_COLORS = ["bg-muted", "bg-green-100", "bg-green-300", "bg-green-500", "bg-green-700"];

export default function Progress() {
  const { user } = useAuth();
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!user?.id) return;

    const fetchProgress = async () => {
      try {
        const dashboard = await api.getProgressDashboard(user.id);
        setData(dashboard);
      } catch (err) {
        toast.error(err instanceof Error ? err.message : "Error loading progress");
      } finally {
        setLoading(false);
      }
    };

    fetchProgress();
  }, [user?.id]);

  if (loading || !data) {
    return (
      <DashboardLayout user={{ name: user?.display_name || "User", level: user?.level || "A1" }}>
        <div className="flex items-center justify-center h-96">
          <p className="text-muted-foreground">Loading progress...</p>
        </div>
      </DashboardLayout>
    );
  }

  const maxLessons = Math.max(1, ...data.activity.map((d) => d.lessons_completed));

  return (
    <DashboardLayout user={{ name: user?.display_name || "User", level: user?.level || "A1" }}>
      <div className="max-w-6xl mx-auto px-4 py-8">
        <div className="mb-8">
          <h1 className="text-4xl font-bold text-foreground mb-2">Your Progress</h1>
          <p className="text-lg text-muted-foreground">
            Track your learning journey and celebrate milestones
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
          {[
            { label: "Current Level", value: data.level, icon: "🎯" },
            { label: "Total XP", value: data.xp, icon: "⭐" },
            { label: "Streak", value: `${data.streak_days} days`, icon: "🔥" },
            { label: "Due Reviews", value: data.due_reviews, icon: "📋" },
          ].map((metric, i) => (
            <Card key={i} className="p-4 text-center">
              <p className="text-2xl mb-2">{metric.icon}</p>
              <p className="text-2xl font-bold text-primary mb-1">{metric.value}</p>
              <p className="text-xs text-muted-foreground">{metric.label}</p>
            </Card>
          ))}
        </div>

        <Tabs defaultValue="weekly" className="space-y-6">
          <TabsList className="grid w-full grid-cols-3">
            <TabsTrigger value="weekly">Activity</TabsTrigger>
            <TabsTrigger value="knowledge">Knowledge Map</TabsTrigger>
            <TabsTrigger value="leaderboard">Leaderboard</TabsTrigger>
          </TabsList>

          <TabsContent value="weekly">
            <Card className="p-8">
              <h3 className="text-xl font-bold text-foreground mb-6">Last 14 Days</h3>
              <div className="flex items-end justify-around h-64 gap-1">
                {data.activity.map((day, i) => (
                  <div key={i} className="flex flex-col items-center gap-2 flex-1">
                    <div
                      className="w-full max-w-8 rounded-lg bg-gradient-to-t from-primary to-secondary transition-smooth hover:shadow-lg"
                      style={{
                        height: `${Math.max(4, (day.lessons_completed / maxLessons) * 200)}px`,
                      }}
                      title={`${day.lessons_completed} lessons on ${day.date}`}
                    />
                    <span className="text-[10px] text-muted-foreground">{day.date.slice(5)}</span>
                  </div>
                ))}
              </div>
              {data.recent_lessons.length > 0 && (
                <div className="mt-8 space-y-2">
                  <h4 className="font-semibold text-foreground">Recent Lessons</h4>
                  {data.recent_lessons.map((lesson, i) => (
                    <div key={i} className="flex items-center justify-between text-sm py-2 border-b border-border">
                      <span className="text-foreground">{lesson.topic}</span>
                      <span className="text-muted-foreground">{Math.round(lesson.score * 100)}%</span>
                    </div>
                  ))}
                </div>
              )}
            </Card>
          </TabsContent>

          <TabsContent value="knowledge">
            <Card className="p-8">
              <h3 className="text-xl font-bold text-foreground mb-2">Mastery by Level</h3>
              <div className="space-y-3 mb-8">
                {data.mastery_by_level.map((lvl) => (
                  <div key={lvl.level}>
                    <div className="flex justify-between text-sm mb-1">
                      <span className="font-medium text-foreground">{lvl.level}</span>
                      <span className="text-muted-foreground">
                        {lvl.mastered} / {lvl.total}
                      </span>
                    </div>
                    <div className="w-full h-2 bg-muted rounded-full overflow-hidden">
                      <div
                        className="h-full bg-gradient-to-r from-primary to-secondary"
                        style={{ width: `${lvl.total ? (lvl.mastered / lvl.total) * 100 : 0}%` }}
                      />
                    </div>
                  </div>
                ))}
              </div>

              <h3 className="text-xl font-bold text-foreground mb-4">Topic Heatmap</h3>
              <div className="grid grid-cols-6 sm:grid-cols-8 gap-2">
                {data.topic_mastery.map((cell, i) => (
                  <div
                    key={i}
                    title={cell.topic_es}
                    className={`aspect-square rounded ${HEATMAP_COLORS[cell.level] || HEATMAP_COLORS[0]}`}
                  />
                ))}
              </div>
            </Card>
          </TabsContent>

          <TabsContent value="leaderboard">
            <Card className="p-6">
              <p className="text-sm text-muted-foreground mb-4">
                Your weekly XP: <strong className="text-foreground">{data.your_weekly_xp}</strong>
                {data.your_rank && <> — Rank #{data.your_rank}</>}
              </p>
              <div className="space-y-2">
                {data.leaderboard.length === 0 ? (
                  <p className="text-muted-foreground text-sm">No leaderboard activity yet this week.</p>
                ) : (
                  data.leaderboard.map((entry) => (
                    <div
                      key={entry.rank}
                      className={`flex items-center justify-between p-3 rounded-lg ${
                        entry.is_you ? "bg-primary/10 border border-primary/30" : "bg-muted/50"
                      }`}
                    >
                      <span className="font-medium text-foreground">
                        #{entry.rank} {entry.display_name}
                      </span>
                      <span className="text-primary font-bold">{entry.weekly_xp} XP</span>
                    </div>
                  ))
                )}
              </div>
            </Card>
          </TabsContent>
        </Tabs>
      </div>
    </DashboardLayout>
  );
}
