import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import DashboardLayout from "@/components/DashboardLayout";
import { useAuth } from "@/contexts/AuthContext";
import { api } from "@/lib/api";
import { useEffect, useState } from "react";

interface Story {
  id: string;
  title: string;
  author: string;
  level: "Beginner" | "Intermediate" | "Advanced";
  genre: string;
  readTime: number;
  rating: number;
}

export default function Library() {
  const { user } = useAuth();
  const [stories, setStories] = useState<Story[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!user?.id) return;

    const fetchStories = async () => {
      try {
        const data = await api.getLibraryCatalog(user.id);
        setStories(data);
      } catch (err) {
        console.error("Error loading library:", err);
      } finally {
        setLoading(false);
      }
    };

    fetchStories();
  }, [user?.id]);

  return (
    <DashboardLayout user={{ name: user?.display_name || "User", level: user?.level || 1 }}>
      <div className="max-w-6xl mx-auto px-4 py-8">
        <div className="mb-8">
          <h1 className="text-4xl font-bold text-foreground mb-2">Library</h1>
          <p className="text-lg text-muted-foreground">
            500+ AI-generated stories tailored to your level. Each one is unique.
          </p>
        </div>

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

        {loading ? (
          <Card className="p-6 text-center">
            <p className="text-muted-foreground">Loading stories...</p>
          </Card>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {stories.length === 0 ? (
              <Card className="p-6 text-center col-span-full">
                <p className="text-muted-foreground">No stories available yet</p>
              </Card>
            ) : (
              stories.map((story) => (
                <Card key={story.id} className="p-6 hover:shadow-lg transition-smooth cursor-pointer group">
                  <div className="w-full h-40 bg-gradient-to-br from-primary/20 to-secondary/20 rounded-lg mb-4 flex items-center justify-center group-hover:shadow-md transition-smooth">
                    <span className="text-5xl">📖</span>
                  </div>

                  <h3 className="text-lg font-bold text-foreground mb-1">{story.title}</h3>
                  <p className="text-sm text-muted-foreground mb-4">{story.author}</p>

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

                  <Button className="w-full bg-primary hover:bg-primary/90">
                    Read Story
                  </Button>
                </Card>
              ))
            )}
          </div>
        )}

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
