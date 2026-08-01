import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import DashboardLayout from "@/components/DashboardLayout";
import { useAuth } from "@/contexts/AuthContext";
import { api, BookStub, BookContent } from "@/lib/api";
import { useEffect, useState } from "react";
import { toast } from "sonner";

const LEVEL_GROUPS: Record<string, string[]> = {
  Beginner: ["A1", "A2"],
  Intermediate: ["B1", "B2"],
  Advanced: ["C1", "C2", "NATIVE"],
};

export default function Library() {
  const { user } = useAuth();
  const [stories, setStories] = useState<BookStub[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState("All");
  const [openBook, setOpenBook] = useState<BookContent | null>(null);
  const [openingId, setOpeningId] = useState<string | null>(null);

  useEffect(() => {
    if (!user?.id) return;

    const fetchStories = async () => {
      try {
        const data = await api.getLibraryCatalog(user.id);
        setStories(data);
      } catch (err) {
        toast.error(err instanceof Error ? err.message : "Error loading library");
      } finally {
        setLoading(false);
      }
    };

    fetchStories();
  }, [user?.id]);

  const handleRead = async (bookId: string) => {
    if (!user?.id) return;
    setOpeningId(bookId);
    try {
      const content = await api.getLibraryBook(user.id, bookId);
      setOpenBook(content);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "No se pudo cargar la historia");
    } finally {
      setOpeningId(null);
    }
  };

  const visibleStories =
    filter === "All" ? stories : stories.filter((s) => LEVEL_GROUPS[filter]?.includes(s.level));

  if (openBook) {
    return (
      <DashboardLayout user={{ name: user?.display_name || "User", level: user?.level || "A1" }}>
        <div className="max-w-3xl mx-auto px-4 py-8">
          <Button variant="ghost" className="mb-4" onClick={() => setOpenBook(null)}>
            ← Back to Library
          </Button>
          <Card className="p-8">
            <h1 className="text-3xl font-bold text-foreground mb-2">{openBook.title}</h1>
            <p className="text-sm text-muted-foreground mb-6">
              {openBook.genre_label} · {openBook.level}
            </p>
            <div className="prose text-foreground whitespace-pre-wrap leading-relaxed">{openBook.content}</div>
          </Card>
        </div>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout user={{ name: user?.display_name || "User", level: user?.level || "A1" }}>
      <div className="max-w-6xl mx-auto px-4 py-8">
        <div className="mb-8">
          <h1 className="text-4xl font-bold text-foreground mb-2">Library</h1>
          <p className="text-lg text-muted-foreground">
            AI-generated stories tailored to your level. Each one is unique.
          </p>
        </div>

        <div className="flex gap-2 mb-8 overflow-x-auto pb-2">
          {["All", "Beginner", "Intermediate", "Advanced"].map((f) => (
            <Button
              key={f}
              variant={filter === f ? "default" : "outline"}
              className="whitespace-nowrap"
              onClick={() => setFilter(f)}
            >
              {f}
            </Button>
          ))}
        </div>

        {loading ? (
          <Card className="p-6 text-center">
            <p className="text-muted-foreground">Loading stories...</p>
          </Card>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {visibleStories.length === 0 ? (
              <Card className="p-6 text-center col-span-full">
                <p className="text-muted-foreground">No stories available for this level yet</p>
              </Card>
            ) : (
              visibleStories.map((story) => (
                <Card key={story.id} className="p-6 hover:shadow-lg transition-smooth group">
                  <div className="w-full h-40 bg-gradient-to-br from-primary/20 to-secondary/20 rounded-lg mb-4 flex items-center justify-center group-hover:shadow-md transition-smooth">
                    <span className="text-5xl">📖</span>
                  </div>

                  <h3 className="text-lg font-bold text-foreground mb-1">{story.title}</h3>
                  <p className="text-sm text-muted-foreground mb-4">{story.blurb}</p>

                  <div className="space-y-2 mb-4 text-sm">
                    <div className="flex items-center justify-between">
                      <span className="text-muted-foreground">Level:</span>
                      <span className="px-2 py-1 rounded text-xs font-medium bg-blue-100 text-blue-700">
                        {story.level}
                      </span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-muted-foreground">Genre:</span>
                      <span className="font-medium">{story.genre_label}</span>
                    </div>
                  </div>

                  <Button
                    className="w-full bg-primary hover:bg-primary/90"
                    disabled={openingId === story.id}
                    onClick={() => handleRead(story.id)}
                  >
                    {openingId === story.id ? "Loading..." : "Read Story"}
                  </Button>
                </Card>
              ))
            )}
          </div>
        )}
      </div>
    </DashboardLayout>
  );
}
