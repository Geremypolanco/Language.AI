import { Card } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import DashboardLayout from "@/components/DashboardLayout";

/**
 * Progress Page - Detailed progress tracking and analytics\n */

export default function Progress() {
  const weekData = [
    { day: "Mon", minutes: 25 },
    { day: "Tue", minutes: 30 },
    { day: "Wed", minutes: 20 },
    { day: "Thu", minutes: 35 },
    { day: "Fri", minutes: 40 },
    { day: "Sat", minutes: 45 },
    { day: "Sun", minutes: 30 },
  ];

  const maxMinutes = Math.max(...weekData.map((d) => d.minutes));

  return (
    <DashboardLayout user={{ name: "Alex", level: 12 }}>
      <div className="max-w-6xl mx-auto px-4 py-8">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-4xl font-bold text-foreground mb-2">Your Progress</h1>
          <p className="text-lg text-muted-foreground">
            Track your learning journey and celebrate milestones
          </p>
        </div>

        {/* Key Metrics */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
          {[
            { label: "Current Level", value: "12", icon: "🎯" },
            { label: "Total XP", value: "4,850", icon: "⭐" },
            { label: "Days Learned", value: "47", icon: "📅" },
            { label: "Streak", value: "7 days", icon: "🔥" },
          ].map((metric, i) => (
            <Card key={i} className="p-4 text-center">
              <p className="text-2xl mb-2">{metric.icon}</p>
              <p className="text-2xl font-bold text-primary mb-1">{metric.value}</p>
              <p className="text-xs text-muted-foreground">{metric.label}</p>
            </Card>
          ))}
        </div>

        {/* Tabs */}
        <Tabs defaultValue="weekly" className="space-y-6">
          <TabsList className="grid w-full grid-cols-3">
            <TabsTrigger value="weekly">Weekly</TabsTrigger>
            <TabsTrigger value="skills">Skills</TabsTrigger>
            <TabsTrigger value="achievements">Achievements</TabsTrigger>
          </TabsList>

          {/* Weekly Activity */}
          <TabsContent value="weekly">
            <Card className="p-8">
              <h3 className="text-xl font-bold text-foreground mb-6">This Week's Activity</h3>
              <div className="flex items-end justify-around h-64 gap-2">
                {weekData.map((day, i) => (
                  <div key={i} className="flex flex-col items-center gap-2">
                    <div
                      className="w-12 rounded-lg bg-gradient-to-t from-primary to-secondary transition-smooth hover:shadow-lg"
                      style={{
                        height: `${(day.minutes / maxMinutes) * 200}px`,
                      }}
                      title={`${day.minutes} minutes`}
                    />
                    <span className="text-sm font-medium text-muted-foreground">{day.day}</span>
                  </div>
                ))}
              </div>
              <div className="mt-6 p-4 bg-muted/50 rounded-lg">
                <p className="text-sm text-muted-foreground">
                  <strong>Total this week:</strong> 225 minutes • <strong>Average:</strong> 32 min/day
                </p>
              </div>
            </Card>
          </TabsContent>

          {/* Skills Progress */}
          <TabsContent value="skills">
            <div className="space-y-4">
              {[
                { skill: "Listening", progress: 78 },
                { skill: "Speaking", progress: 65 },
                { skill: "Reading", progress: 82 },
                { skill: "Writing", progress: 58 },
                { skill: "Grammar", progress: 71 },
                { skill: "Vocabulary", progress: 89 },
              ].map((item, i) => (
                <Card key={i} className="p-4">
                  <div className="flex items-center justify-between mb-2">
                    <span className="font-medium text-foreground">{item.skill}</span>
                    <span className="text-sm font-bold text-primary">{item.progress}%</span>
                  </div>
                  <div className="w-full h-2 bg-muted rounded-full overflow-hidden">
                    <div
                      className="h-full bg-gradient-to-r from-primary to-secondary transition-all duration-500"
                      style={{ width: `${item.progress}%` }}
                    />
                  </div>
                </Card>
              ))}
            </div>
          </TabsContent>

          {/* Achievements */}
          <TabsContent value="achievements">
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {[
                { icon: "🏆", title: "First Steps", desc: "Complete your first lesson" },
                { icon: "🔥", title: "On Fire", desc: "7-day streak" },
                { icon: "⭐", title: "Star Learner", desc: "Earn 1,000 XP" },
                { icon: "🎯", title: "Level 10", desc: "Reach level 10" },
                { icon: "📚", title: "Bookworm", desc: "Read 5 stories" },
                { icon: "🗣️", title: "Chatterbox", desc: "Complete 50 speaking exercises" },
              ].map((achievement, i) => (
                <Card key={i} className="p-6 text-center hover:shadow-md transition-smooth">
                  <p className="text-4xl mb-3">{achievement.icon}</p>
                  <h4 className="font-bold text-foreground mb-1">{achievement.title}</h4>
                  <p className="text-sm text-muted-foreground">{achievement.desc}</p>
                </Card>
              ))}
            </div>
          </TabsContent>
        </Tabs>

        {/* Insights */}
        <Card className="mt-8 p-8 bg-gradient-to-r from-secondary/5 to-primary/5 border-secondary/20">
          <h3 className="text-xl font-bold text-foreground mb-4">📊 Your Insights</h3>
          <div className="space-y-2 text-muted-foreground">
            <p>✓ You're most productive in the mornings (8-10 AM)</p>
            <p>✓ Speaking is your strongest skill at 65% mastery</p>
            <p>✓ You learn 12% faster than average learners</p>
            <p>✓ Keep your 7-day streak going! You're on track for 30 days</p>
          </div>
        </Card>
      </div>
    </DashboardLayout>
  );
}
