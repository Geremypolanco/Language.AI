import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import DashboardLayout from "@/components/DashboardLayout";

/**
 * Practice Page - Skill-based practice
 * 
 * Design: Grid of practice modes, each with difficulty selection
 */

interface PracticeMode {
  id: string;
  title: string;
  icon: string;
  description: string;
  color: string;
}

const PRACTICE_MODES: PracticeMode[] = [
  {
    id: "listening",
    title: "Listening",
    icon: "👂",
    description: "Train your ear with native speakers",
    color: "from-blue-500 to-blue-600",
  },
  {
    id: "speaking",
    title: "Speaking",
    icon: "🗣️",
    description: "Practice pronunciation and fluency",
    color: "from-red-500 to-red-600",
  },
  {
    id: "reading",
    title: "Reading",
    icon: "📖",
    description: "Improve comprehension with texts",
    color: "from-green-500 to-green-600",
  },
  {
    id: "writing",
    title: "Writing",
    icon: "✍️",
    description: "Enhance written expression",
    color: "from-purple-500 to-purple-600",
  },
  {
    id: "grammar",
    title: "Grammar",
    icon: "📝",
    description: "Master grammar rules and structures",
    color: "from-yellow-500 to-yellow-600",
  },
  {
    id: "vocabulary",
    title: "Vocabulary",
    icon: "📚",
    description: "Expand your word bank",
    color: "from-pink-500 to-pink-600",
  },
];

export default function Practice() {
  return (
    <DashboardLayout user={{ name: "Alex", level: 12 }}>
      <div className="max-w-6xl mx-auto px-4 py-8">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-4xl font-bold text-foreground mb-2">Practice</h1>
          <p className="text-lg text-muted-foreground">
            Choose a skill to practice. No fixed order, no limits.
          </p>
        </div>

        {/* Tutor Message */}
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

        {/* Practice Modes Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {PRACTICE_MODES.map((mode) => (
            <Card key={mode.id} className="p-6 hover:shadow-lg transition-smooth cursor-pointer group overflow-hidden">
              {/* Gradient background */}
              <div className={`absolute inset-0 bg-gradient-to-br ${mode.color} opacity-0 group-hover:opacity-5 transition-smooth`} />
              
              <div className="relative z-10">
                <div className="flex items-start justify-between mb-4">
                  <span className="text-4xl">{mode.icon}</span>
                  <span className="text-2xl opacity-0 group-hover:opacity-100 transition-smooth">→</span>
                </div>
                
                <h3 className="text-xl font-bold text-foreground mb-2">{mode.title}</h3>
                <p className="text-muted-foreground text-sm mb-6">{mode.description}</p>
                
                {/* Difficulty buttons */}
                <div className="space-y-2">
                  <p className="text-xs font-semibold text-muted-foreground uppercase">Choose difficulty:</p>
                  <div className="flex gap-2">
                    {["Easy", "Medium", "Hard"].map((difficulty) => (
                      <Button
                        key={difficulty}
                        size="sm"
                        variant="outline"
                        className="flex-1 text-xs"
                        onClick={(e) => {
                          e.stopPropagation();
                          console.log(`Starting ${mode.title} - ${difficulty}`);
                        }}
                      >
                        {difficulty}
                      </Button>
                    ))}
                  </div>
                </div>
              </div>
            </Card>
          ))}
        </div>

        {/* Stats */}
        <div className="mt-12 grid grid-cols-1 md:grid-cols-3 gap-6">
          <Card className="p-6 text-center">
            <p className="text-4xl font-bold text-primary mb-2">247</p>
            <p className="text-muted-foreground">Minutes practiced this week</p>
          </Card>
          <Card className="p-6 text-center">
            <p className="text-4xl font-bold text-secondary mb-2">1,240</p>
            <p className="text-muted-foreground">Total words mastered</p>
          </Card>
          <Card className="p-6 text-center">
            <p className="text-4xl font-bold text-orange-500 mb-2">92%</p>
            <p className="text-muted-foreground">Accuracy on last session</p>
          </Card>
        </div>
      </div>
    </DashboardLayout>
  );
}
