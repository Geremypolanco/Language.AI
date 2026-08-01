import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import DashboardLayout from "@/components/DashboardLayout";

/**
 * Library Page - AI-generated stories for reading practice
 */

interface Story {
  id: string;
  title: string;
  author: string;
  level: "Beginner" | "Intermediate" | "Advanced";
  genre: string;
  readTime: number;
  rating: number;
}

const STORIES: Story[] = [
  {
    id: "1",
    title: "The Lost City",
    author: "AI Tutor",
    level: "Beginner",
    genre: "Adventure",
    readTime: 8,
    rating: 4.8,
  },
  {
    id: "2",
    title: "Café Conversations",
    author: "AI Tutor",
    level: "Beginner",
    genre: "Slice of Life",
    readTime: 6,
    rating: 4.6,
  },
  {
    id: "3",
    title: "The Mysterious Letter",
    author: "AI Tutor",
    level: "Intermediate",
    genre: "Mystery",
    readTime: 12,
    rating: 4.9,
  },
  {
    id: "4",
    title: "Journey Through Time",
    author: "AI Tutor",
    level: "Intermediate",
    genre: "Science Fiction",
    readTime: 15,
    rating: 4.7,
  },
  {
    id: "5",
    title: "The Philosopher's Paradox",
    author: "AI Tutor",
    level: "Advanced",
    genre: "Literary Fiction",
    readTime: 20,
    rating: 4.9,
  },
];

export default function Library() {
  return (
    <DashboardLayout user={{ name: "Alex", level: 12 }}>
      <div className="max-w-6xl mx-auto px-4 py-8">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-4xl font-bold text-foreground mb-2">Library</h1>
          <p className="text-lg text-muted-foreground">
            500+ AI-generated stories tailored to your level. Each one is unique.
          </p>
        </div>

        {/* Filters */}
        <div className="flex gap-2 mb-8 overflow-x-auto pb-2">
          {["All", "Beginner", "Intermediate", "Advanced"].map((filter) => (
            <Button
              key={filter}
              variant={filter === "All" ? "default" : "outline"}
              className="whitespace-nowrap"
            >
              {filter}
            </Button>
          ))}
        </div>

        {/* Stories Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {STORIES.map((story) => (
            <Card key={story.id} className="p-6 hover:shadow-lg transition-smooth cursor-pointer group">
              {/* Cover */}
              <div className="w-full h-40 bg-gradient-to-br from-primary/20 to-secondary/20 rounded-lg mb-4 flex items-center justify-center group-hover:shadow-md transition-smooth">
                <span className="text-5xl">📖</span>
              </div>

              {/* Content */}
              <h3 className="text-lg font-bold text-foreground mb-1">{story.title}</h3>
              <p className="text-sm text-muted-foreground mb-4">{story.author}</p>

              {/* Metadata */}
              <div className="space-y-2 mb-4 text-sm">
                <div className="flex items-center justify-between">
                  <span className="text-muted-foreground">Level:</span>
                  <span className={`px-2 py-1 rounded text-xs font-medium ${
                    story.level === "Beginner"
                      ? "bg-green-100 text-green-700"
                      : story.level === "Intermediate"
                      ? "bg-blue-100 text-blue-700"
                      : "bg-purple-100 text-purple-700"
                  }`}>
                    {story.level}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-muted-foreground">Genre:</span>
                  <span className="font-medium">{story.genre}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-muted-foreground">Read time:</span>
                  <span className="font-medium">{story.readTime} min</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-muted-foreground">Rating:</span>
                  <span className="font-medium">⭐ {story.rating}</span>
                </div>
              </div>

              {/* CTA */}
              <Button className="w-full bg-primary hover:bg-primary/90">
                Read Story
              </Button>
            </Card>
          ))}
        </div>

        {/* CTA */}
        <div className="mt-12 p-8 rounded-lg gradient-primary text-white text-center">
          <h3 className="text-2xl font-bold mb-2">Want personalized stories?</h3>
          <p className="mb-4 text-white/90">
            Tell us your interests and we'll generate stories just for you
          </p>
          <Button className="bg-white text-primary hover:bg-white/90">
            Create Custom Story →
          </Button>
        </div>
      </div>
    </DashboardLayout>
  );
}
