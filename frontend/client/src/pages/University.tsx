import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import DashboardLayout from "@/components/DashboardLayout";

/**
 * University Page - Academic Career Tracks (Tutor AI-inspired)
 * 
 * Design Philosophy:
 * - Structured, rigorous curriculum paths
 * - Multiple depth levels: Associate, Bachelor, Master
 * - Clear prerequisites and learning outcomes
 * - Professional, academic tone
 */

interface Course {
  id: string;
  title: string;
  description: string;
  modules: number;
  hours: number;
  difficulty: "Foundational" | "Intermediate" | "Advanced";
  progress: number;
}

interface CareerTrack {
  id: string;
  title: string;
  icon: string;
  description: string;
  courses: Course[];
  depth: "Associate" | "Bachelor" | "Master";
}

const CAREER_TRACKS: CareerTrack[] = [
  {
    id: "business",
    title: "Business Communication",
    icon: "💼",
    description: "Master professional communication, negotiations, and corporate culture",
    depth: "Bachelor",
    courses: [
      {
        id: "bc-1",
        title: "Professional Vocabulary",
        description: "Industry-specific terminology and business jargon",
        modules: 8,
        hours: 12,
        difficulty: "Foundational",
        progress: 100,
      },
      {
        id: "bc-2",
        title: "Meeting & Presentation Skills",
        description: "Lead meetings, present ideas, and persuade audiences",
        modules: 10,
        hours: 16,
        difficulty: "Intermediate",
        progress: 60,
      },
      {
        id: "bc-3",
        title: "Negotiation & Conflict Resolution",
        description: "Navigate complex business discussions",
        modules: 8,
        hours: 14,
        difficulty: "Advanced",
        progress: 0,
      },
    ],
  },
  {
    id: "tech",
    title: "Tech & Innovation",
    icon: "💻",
    description: "Learn technology terminology and startup culture communication",
    depth: "Bachelor",
    courses: [
      {
        id: "tech-1",
        title: "Tech Terminology",
        description: "Essential vocabulary for software, hardware, and AI",
        modules: 10,
        hours: 14,
        difficulty: "Foundational",
        progress: 40,
      },
      {
        id: "tech-2",
        title: "Startup Pitch & Fundraising",
        description: "Communicate your vision to investors",
        modules: 8,
        hours: 12,
        difficulty: "Intermediate",
        progress: 0,
      },
    ],
  },
  {
    id: "academic",
    title: "Academic Excellence",
    icon: "🎓",
    description: "Advanced academic writing, research, and scholarly discourse",
    depth: "Master",
    courses: [
      {
        id: "ac-1",
        title: "Academic Writing",
        description: "Essays, papers, and research communication",
        modules: 12,
        hours: 18,
        difficulty: "Intermediate",
        progress: 0,
      },
      {
        id: "ac-2",
        title: "Critical Analysis & Argumentation",
        description: "Build and defend complex arguments",
        modules: 10,
        hours: 16,
        difficulty: "Advanced",
        progress: 0,
      },
    ],
  },
];

const getDifficultyColor = (difficulty: string) => {
  switch (difficulty) {
    case "Foundational":
      return "bg-green-100 text-green-700";
    case "Intermediate":
      return "bg-blue-100 text-blue-700";
    case "Advanced":
      return "bg-purple-100 text-purple-700";
    default:
      return "bg-gray-100 text-gray-700";
  }
};

export default function University() {
  return (
    <DashboardLayout user={{ name: "Alex", level: 12 }}>
      <div className="max-w-6xl mx-auto px-4 py-8">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-4xl font-bold text-foreground mb-2">University</h1>
          <p className="text-lg text-muted-foreground">
            Structured, rigorous career tracks designed for professional mastery
          </p>
        </div>

        {/* Disclaimer */}
        <Card className="p-4 mb-8 border-yellow-200 bg-yellow-50">
          <p className="text-sm text-yellow-900">
            <strong>Note:</strong> These are self-paced learning tracks designed to build professional proficiency. They are not accredited programs and do not grant official credentials or degrees.
          </p>
        </Card>

        {/* Tabs for Depth Levels */}
        <Tabs defaultValue="Bachelor" className="mb-8">
          <TabsList className="grid w-full grid-cols-3">
            <TabsTrigger value="Associate">Associate</TabsTrigger>
            <TabsTrigger value="Bachelor">Bachelor</TabsTrigger>
            <TabsTrigger value="Master">Master</TabsTrigger>
          </TabsList>

          {["Associate", "Bachelor", "Master"].map((depth) => (
            <TabsContent key={depth} value={depth} className="space-y-6">
              <div className="grid gap-6">
                {CAREER_TRACKS.filter((track) => track.depth === depth).map((track) => (
                  <Card key={track.id} className="p-6 hover:shadow-md transition-smooth">
                    <div className="flex items-start justify-between mb-4">
                      <div className="flex items-start gap-4">
                        <span className="text-4xl">{track.icon}</span>
                        <div>
                          <h3 className="text-2xl font-bold text-foreground">{track.title}</h3>
                          <p className="text-muted-foreground mt-1">{track.description}</p>
                        </div>
                      </div>
                      <Button className="bg-primary hover:bg-primary/90">
                        Enroll
                      </Button>
                    </div>

                    {/* Courses */}
                    <div className="mt-6 space-y-3 border-t border-border pt-6">
                      <h4 className="font-semibold text-foreground">Courses in this track:</h4>
                      {track.courses.map((course) => (
                        <div
                          key={course.id}
                          className="p-4 rounded-lg bg-muted/50 hover:bg-muted transition-smooth cursor-pointer"
                        >
                          <div className="flex items-start justify-between mb-2">
                            <div className="flex-1">
                              <h5 className="font-semibold text-foreground">{course.title}</h5>
                              <p className="text-sm text-muted-foreground mt-1">{course.description}</p>
                            </div>
                            <span className={`px-3 py-1 rounded-full text-xs font-medium whitespace-nowrap ml-4 ${getDifficultyColor(course.difficulty)}`}>
                              {course.difficulty}
                            </span>
                          </div>
                          <div className="flex items-center gap-4 text-xs text-muted-foreground mt-3">
                            <span>📚 {course.modules} modules</span>
                            <span>⏱️ {course.hours} hours</span>
                            {course.progress > 0 && (
                              <span className="text-primary font-medium">{course.progress}% complete</span>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  </Card>
                ))}
              </div>
            </TabsContent>
          ))}
        </Tabs>

        {/* Learning Outcomes */}
        <Card className="p-8 bg-gradient-to-r from-secondary/5 to-primary/5 border-secondary/20">
          <h3 className="text-2xl font-bold text-foreground mb-4">What You'll Achieve</h3>
          <div className="grid md:grid-cols-2 gap-6">
            {[
              "Speak with confidence in professional settings",
              "Master industry-specific vocabulary and concepts",
              "Present ideas persuasively to diverse audiences",
              "Navigate complex negotiations and discussions",
              "Write clearly and academically",
              "Understand cultural nuances in business",
            ].map((outcome, i) => (
              <div key={i} className="flex items-start gap-3">
                <span className="text-xl">✓</span>
                <p className="text-foreground">{outcome}</p>
              </div>
            ))}
          </div>
        </Card>

        {/* FAQ */}
        <div className="mt-12">
          <h3 className="text-2xl font-bold text-foreground mb-6">Frequently Asked Questions</h3>
          <div className="space-y-4">
            {[
              {
                q: "How long does each track take?",
                a: "Depends on your pace. Most students complete a Bachelor track in 3-6 months with 1-2 hours daily. You can go faster or slower.",
              },
              {
                q: "Can I switch tracks?",
                a: "Yes! You can enroll in multiple tracks simultaneously or switch anytime. Progress is saved for each track.",
              },
              {
                q: "Do I get a certificate?",
                a: "These are learning tracks, not accredited programs. You'll get a completion badge in your profile, but not an official degree.",
              },
              {
                q: "What if I get stuck?",
                a: "Your AI tutor is available 24/7 to answer questions, provide examples, and adjust the difficulty.",
              },
            ].map((faq, i) => (
              <Card key={i} className="p-4">
                <h4 className="font-semibold text-foreground mb-2">{faq.q}</h4>
                <p className="text-muted-foreground">{faq.a}</p>
              </Card>
            ))}
          </div>
        </div>
      </div>
    </DashboardLayout>
  );
}
