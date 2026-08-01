import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import DashboardLayout from "@/components/DashboardLayout";
import { useAuth } from "@/contexts/AuthContext";
import { api } from "@/lib/api";
import { useEffect, useState } from "react";

interface AcademyField {
  id: string;
  title: string;
  icon: string;
  description: string;
  courses: number;
}

export default function University() {
  const { user } = useAuth();
  const [fields, setFields] = useState<AcademyField[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchFields = async () => {
      try {
        const data = await api.getAcademyFields();
        setFields(data);
      } catch (err) {
        console.error("Error loading academy fields:", err);
      } finally {
        setLoading(false);
      }
    };

    fetchFields();
  }, []);

  return (
    <DashboardLayout user={{ name: user?.display_name || "User", level: user?.level || 1 }}>
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

        <Tabs defaultValue="Bachelor" className="mb-8">
          <TabsList className="grid w-full grid-cols-3">
            <TabsTrigger value="Associate">Associate</TabsTrigger>
            <TabsTrigger value="Bachelor">Bachelor</TabsTrigger>
            <TabsTrigger value="Master">Master</TabsTrigger>
          </TabsList>

          {["Associate", "Bachelor", "Master"].map((depth) => (
            <TabsContent key={depth} value={depth} className="space-y-6">
              {loading ? (
                <Card className="p-6 text-center">
                  <p className="text-muted-foreground">Loading career tracks...</p>
                </Card>
              ) : (
                <div className="grid gap-6">
                  {fields.map((field) => (
                    <Card key={field.id} className="p-6 hover:shadow-md transition-smooth">
                      <div className="flex items-start justify-between mb-4">
                        <div className="flex items-start gap-4">
                          <span className="text-4xl">{field.icon}</span>
                          <div>
                            <h3 className="text-2xl font-bold text-foreground">{field.title}</h3>
                            <p className="text-muted-foreground mt-1">{field.description}</p>
                          </div>
                        </div>
                        <Button className="bg-primary hover:bg-primary/90">
                          Enroll
                        </Button>
                      </div>
                      <div className="mt-4 p-4 bg-muted/50 rounded-lg">
                        <p className="text-sm text-muted-foreground">
                          <strong>{field.courses} courses</strong> in this track
                        </p>
                      </div>
                    </Card>
                  ))}
                </div>
              )}
            </TabsContent>
          ))}
        </Tabs>

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
      </div>
    </DashboardLayout>
  );
}
