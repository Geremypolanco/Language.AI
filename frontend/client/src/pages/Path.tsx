import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import DashboardLayout from "@/components/DashboardLayout";

/**
 * Path Page - Language Learning Path (Learna-inspired)
 * 
 * Design Philosophy:
 * - Progressive skill tree: beginner → intermediate → advanced
 * - Visual progress indicators (rings, bars)
 * - Conversational prompts from AI tutor
 * - Card-based lessons with clear difficulty levels
 */

interface Lesson {
  id: string;
  title: string;
  description: string;
  level: "beginner" | "intermediate" | "advanced";
  duration: number; // minutes
  completed: boolean;
  xp: number;
}

const LESSONS: Lesson[] = [
  {
    id: "1",
    title: "Greetings & Introductions",
    description: "Learn how to say hello and introduce yourself",
    level: "beginner",
    duration: 8,
    completed: true,
    xp: 100,
  },
  {
    id: "2",
    title: "Numbers & Counting",
    description: "Master numbers from 1 to 1000",
    level: "beginner",
    duration: 10,
    completed: true,
    xp: 120,
  },
  {
    id: "3",
    title: "Everyday Objects",
    description: "Learn names of common items around you",
    level: "beginner",
    duration: 12,
    completed: false,
    xp: 150,
  },
  {
    id: "4",
    title: "Daily Routines",
    description: "Talk about your day and daily activities",
    level: "intermediate",
    duration: 15,
    completed: false,
    xp: 180,
  },
  {
    id: "5",
    title: "Conversational Flow",
    description: "Master natural conversation patterns",
    level: "intermediate",
    duration: 20,
    completed: false,
    xp: 220,
  },
];

const getLevelColor = (level: string) => {
  switch (level) {
    case "beginner":
      return "bg-green-100 text-green-700";
    case "intermediate":
      return "bg-blue-100 text-blue-700";
    case "advanced":
      return "bg-purple-100 text-purple-700";
    default:
      return "bg-gray-100 text-gray-700";
  }
};

export default function Path() {
  const completedCount = LESSONS.filter((l) => l.completed).length;
  const totalXP = LESSONS.filter((l) => l.completed).reduce((sum, l) => sum + l.xp, 0);
  const progressPercent = (completedCount / LESSONS.length) * 100;

  return (
    <DashboardLayout user={{ name: "Alex", level: 12 }}>
      <div className="max-w-6xl mx-auto px-4 py-8">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-4xl font-bold text-foreground mb-2">Your Learning Path</h1>
          <p className="text-lg text-muted-foreground">
            Progress through structured lessons at your own pace
          </p>
        </div>

        {/* Stats Row */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
          {/* Progress Card */}
          <Card className="p-6 shadow-sm">
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-semibold text-foreground">Overall Progress</h3>
              <span className="text-2xl">📈</span>
            </div>
            <div className="space-y-2">
              <Progress value={progressPercent} className="h-2" />
              <p className="text-sm text-muted-foreground">
                {completedCount} of {LESSONS.length} lessons completed
              </p>
            </div>
          </Card>

          {/* XP Card */}
          <Card className="p-6 shadow-sm">
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-semibold text-foreground">Experience Points</h3>
              <span className="text-2xl">⭐</span>
            </div>
            <p className="text-3xl font-bold text-primary mb-1">{totalXP}</p>
            <p className="text-sm text-muted-foreground">Keep learning to earn more</p>
          </Card>

          {/* Streak Card */}
          <Card className="p-6 shadow-sm">
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-semibold text-foreground">Current Streak</h3>
              <span className="text-2xl">🔥</span>
            </div>
            <p className="text-3xl font-bold text-orange-500 mb-1">7 days</p>
            <p className="text-sm text-muted-foreground">Keep it going!</p>
          </Card>
        </div>

        {/* Tutor Message */}
        <Card className="p-6 mb-8 bg-gradient-to-r from-primary/5 to-secondary/5 border-primary/20">
          <div className="flex gap-4">
            <div className="text-3xl">🤖</div>
            <div>
              <p className="font-semibold text-foreground mb-1">Your AI Tutor</p>
              <p className="text-muted-foreground">
                You're doing great! You've completed {completedCount} lessons. Ready to tackle the next one? "Everyday Objects" will teach you practical vocabulary you'll use every day.
              </p>
            </div>
          </div>
        </Card>

        {/* Lessons Grid */}
        <div className="space-y-4">
          <h2 className="text-2xl font-bold text-foreground">Lessons</h2>
          <div className="grid gap-4">
            {LESSONS.map((lesson, index) => (
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
                      <span className={`px-3 py-1 rounded-full text-sm font-medium ${getLevelColor(lesson.level)}`}>
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
            ))}
          </div>
        </div>

        {/* CTA */}
        <div className="mt-12 p-8 rounded-lg gradient-primary text-white text-center">
          <h3 className="text-2xl font-bold mb-2">Ready for a challenge?</h3>
          <p className="mb-4 text-white/90">
            Complete 5 more lessons to unlock the advanced conversation module
          </p>
          <Button className="bg-white text-primary hover:bg-white/90">
            View Advanced Modules →
          </Button>
        </div>
      </div>
    </DashboardLayout>
  );
}
