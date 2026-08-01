import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import DashboardLayout from "@/components/DashboardLayout";
import { useAuth } from "@/contexts/AuthContext";
import { api, AcademicField, AcademyProgress } from "@/lib/api";
import { useEffect, useState } from "react";
import { toast } from "sonner";

// Course counts per depth — mirrors AcademicLevel.course_count in backend/models.py
// (not returned by GET /api/academy/fields, which lists fields only).
const LEVEL_TABS: { value: "ASSOCIATE" | "BACHELOR" | "MASTER"; label: string; courseCount: number }[] = [
  { value: "ASSOCIATE", label: "Associate", courseCount: 12 },
  { value: "BACHELOR", label: "Bachelor", courseCount: 24 },
  { value: "MASTER", label: "Master", courseCount: 10 },
];

export default function University() {
  const { user } = useAuth();
  const [fields, setFields] = useState<AcademicField[]>([]);
  const [progress, setProgress] = useState<AcademyProgress | null>(null);
  const [loading, setLoading] = useState(true);
  const [enrollingFieldId, setEnrollingFieldId] = useState<string | null>(null);

  const refreshProgress = async () => {
    if (!user?.id) return;
    try {
      const data = await api.getAcademyProgress(user.id);
      setProgress(data);
    } catch (err) {
      console.error("Error loading academy progress:", err);
    }
  };

  useEffect(() => {
    const load = async () => {
      try {
        const data = await api.getAcademyFields();
        setFields(data);
      } catch (err) {
        toast.error(err instanceof Error ? err.message : "Error loading academy fields");
      } finally {
        setLoading(false);
      }
    };
    load();
    refreshProgress();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.id]);

  const handleEnroll = async (fieldId: string, level: "ASSOCIATE" | "BACHELOR" | "MASTER") => {
    if (!user?.id) return;
    setEnrollingFieldId(fieldId);
    try {
      const enrollment = await api.enrollAcademyCareer(user.id, fieldId, level);
      toast.success(`Inscrito en ${enrollment.field_name} (${enrollment.level_label})`);
      await refreshProgress();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "No se pudo completar la inscripción");
    } finally {
      setEnrollingFieldId(null);
    }
  };

  const enrolledFieldId = progress?.enrollment?.field_id;

  return (
    <DashboardLayout user={{ name: user?.display_name || "User", level: user?.level || "A1" }}>
      <div className="max-w-6xl mx-auto px-4 py-8">
        <div className="mb-8">
          <h1 className="text-4xl font-bold text-foreground mb-2">University</h1>
          <p className="text-lg text-muted-foreground">
            Structured, rigorous career tracks designed for professional mastery
          </p>
        </div>

        <Card className="p-4 mb-8 border-yellow-200 bg-yellow-50">
          <p className="text-sm text-yellow-900">
            <strong>Note:</strong> These are self-paced learning tracks designed to build professional proficiency. They are not accredited programs and do not grant official credentials or degrees.
          </p>
        </Card>

        {progress?.enrollment && (
          <Card className="p-4 mb-8 border-primary/30 bg-primary/5">
            <p className="text-sm text-foreground">
              Currently enrolled: <strong>{progress.enrollment.field_name}</strong> ({progress.enrollment.level_label}) —{" "}
              {progress.completed_course_ids.length} of {progress.total_courses} courses completed
            </p>
          </Card>
        )}

        <Tabs defaultValue="BACHELOR" className="mb-8">
          <TabsList className="grid w-full grid-cols-3">
            {LEVEL_TABS.map((t) => (
              <TabsTrigger key={t.value} value={t.value}>
                {t.label}
              </TabsTrigger>
            ))}
          </TabsList>

          {LEVEL_TABS.map((tab) => (
            <TabsContent key={tab.value} value={tab.value} className="space-y-6">
              {loading ? (
                <Card className="p-6 text-center">
                  <p className="text-muted-foreground">Loading career tracks...</p>
                </Card>
              ) : (
                <div className="grid gap-6">
                  {fields.map((field) => {
                    const isEnrolled = enrolledFieldId === field.id;
                    return (
                      <Card key={field.id} className="p-6 hover:shadow-md transition-smooth">
                        <div className="flex items-start justify-between mb-4">
                          <div className="flex items-start gap-4">
                            <span className="text-4xl">{field.icon}</span>
                            <div>
                              <h3 className="text-2xl font-bold text-foreground">{field.name}</h3>
                              <p className="text-muted-foreground mt-1">{field.description}</p>
                            </div>
                          </div>
                          <Button
                            className="bg-primary hover:bg-primary/90"
                            disabled={enrollingFieldId === field.id}
                            onClick={() => handleEnroll(field.id, tab.value)}
                          >
                            {isEnrolled ? "Enrolled ✓" : enrollingFieldId === field.id ? "Enrolling..." : "Enroll"}
                          </Button>
                        </div>
                        <div className="mt-4 p-4 bg-muted/50 rounded-lg">
                          <p className="text-sm text-muted-foreground">
                            <strong>{tab.courseCount} courses</strong> in this track · Tutor: {field.tutor_name}
                          </p>
                        </div>
                      </Card>
                    );
                  })}
                </div>
              )}
            </TabsContent>
          ))}
        </Tabs>
      </div>
    </DashboardLayout>
  );
}
