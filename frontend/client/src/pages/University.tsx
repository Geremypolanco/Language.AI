import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import DashboardLayout from "@/components/DashboardLayout";
import CourseViewer from "@/components/CourseViewer";
import { useAuth } from "@/contexts/AuthContext";
import { api, AcademicField, AcademyProgress, Curriculum, CourseStub } from "@/lib/api";
import { LANGUAGES } from "@/lib/languages";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import {
  BookOpen,
  MessageCircle,
  Flame,
  Gem,
  Heart,
  Image as ImageIcon,
  Lock,
  Pencil,
  Sparkles,
  Trophy,
  Volume2,
  Waves,
  GraduationCap,
  CheckCircle2,
  Circle,
  type LucideIcon,
} from "lucide-react";

// backend/academy.py's AcademicField.icon is a semantic name, not an emoji —
// map it to the matching lucide icon (falls back to a generic cap icon for
// any name not in this list, rather than printing the raw word).
const FIELD_ICONS: Record<string, LucideIcon> = {
  book: BookOpen,
  chat: MessageCircle,
  flame: Flame,
  gem: Gem,
  heart: Heart,
  image: ImageIcon,
  lock: Lock,
  pencil: Pencil,
  sparkle: Sparkles,
  trophy: Trophy,
  volume: Volume2,
  wave: Waves,
};

function FieldIcon({ name, className }: { name: string; className?: string }) {
  const Icon = FIELD_ICONS[name] || GraduationCap;
  return <Icon className={className} />;
}

function languageName(code: string): string {
  return LANGUAGES.find(([c]) => c === code)?.[1] || code;
}

// Course counts per depth — mirrors AcademicLevel.course_count in backend/models.py
// (not returned by GET /api/academy/fields, which lists fields only).
const LEVEL_TABS: { value: "ASSOCIATE" | "BACHELOR" | "MASTER"; label: string; courseCount: number }[] = [
  { value: "ASSOCIATE", label: "Técnico", courseCount: 12 },
  { value: "BACHELOR", label: "Profesional", courseCount: 24 },
  { value: "MASTER", label: "Avanzado", courseCount: 10 },
];

type View = "fields" | "curriculum" | "course";

export default function University() {
  const { user } = useAuth();
  const [fields, setFields] = useState<AcademicField[]>([]);
  const [progress, setProgress] = useState<AcademyProgress | null>(null);
  const [loading, setLoading] = useState(true);
  const [enrollingFieldId, setEnrollingFieldId] = useState<string | null>(null);

  const [view, setView] = useState<View>("fields");
  const [curriculum, setCurriculum] = useState<Curriculum | null>(null);
  const [loadingCurriculum, setLoadingCurriculum] = useState(false);
  const [activeCourse, setActiveCourse] = useState<CourseStub | null>(null);

  // Language to study the career's content in — independent of the
  // learner's own native_lang, so e.g. a Spanish speaker can study a
  // career in English for extra immersion. Defaults to native_lang.
  const [contentLang, setContentLang] = useState("");
  useEffect(() => {
    if (user?.native_lang) setContentLang(user.native_lang);
  }, [user?.native_lang]);

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
        toast.error(err instanceof Error ? err.message : "No se pudieron cargar las áreas de estudio");
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
      const enrollment = await api.enrollAcademyCareer(user.id, fieldId, level, contentLang || undefined);
      toast.success(`Inscrito en ${enrollment.field_name} (${enrollment.level_label})`);
      await refreshProgress();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "No se pudo completar la inscripción");
    } finally {
      setEnrollingFieldId(null);
    }
  };

  const openCurriculum = async () => {
    if (!user?.id) return;
    setView("curriculum");
    setLoadingCurriculum(true);
    try {
      const data = await api.getAcademyCurriculum(user.id);
      setCurriculum(data);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "No se pudo cargar el plan de estudios");
      setView("fields");
    } finally {
      setLoadingCurriculum(false);
    }
  };

  const enrolledFieldId = progress?.enrollment?.field_id;
  const completedIds = new Set(progress?.completed_course_ids ?? []);

  if (view === "course" && activeCourse && user?.id) {
    return (
      <DashboardLayout user={{ name: user?.display_name || "User", level: user?.level || "A1" }}>
        <div className="max-w-4xl mx-auto px-4 py-8">
          <CourseViewer
            userId={user.id}
            course={activeCourse}
            alreadyCompleted={completedIds.has(activeCourse.id)}
            onExit={() => setView("curriculum")}
            onCompleted={async () => {
              await refreshProgress();
              setView("curriculum");
            }}
          />
        </div>
      </DashboardLayout>
    );
  }

  if (view === "curriculum") {
    return (
      <DashboardLayout user={{ name: user?.display_name || "User", level: user?.level || "A1" }}>
        <div className="max-w-4xl mx-auto px-4 py-8 space-y-6">
          <div className="flex items-center justify-between">
            <Button variant="ghost" onClick={() => setView("fields")}>
              ← Volver a las carreras
            </Button>
          </div>
          {curriculum && (
            <div>
              <h1 className="text-3xl font-bold text-foreground mb-1">{curriculum.field_name}</h1>
              <p className="text-muted-foreground">
                {curriculum.level_label} · {completedIds.size} de {curriculum.courses.length} cursos completados
                {progress?.enrollment && <> · Contenido en {languageName(progress.enrollment.content_lang)}</>}
              </p>
            </div>
          )}
          {loadingCurriculum ? (
            <Card className="p-6 text-center">
              <p className="text-muted-foreground">Cargando plan de estudios...</p>
            </Card>
          ) : (
            <div className="space-y-3">
              {curriculum?.courses.map((course) => {
                const done = completedIds.has(course.id);
                return (
                  <Card
                    key={course.id}
                    className="p-4 flex items-center gap-4 hover:shadow-md transition-smooth cursor-pointer"
                    onClick={() => {
                      setActiveCourse(course);
                      setView("course");
                    }}
                  >
                    {done ? (
                      <CheckCircle2 className="w-6 h-6 text-primary flex-shrink-0" />
                    ) : (
                      <Circle className="w-6 h-6 text-muted-foreground flex-shrink-0" />
                    )}
                    <div className="flex-1">
                      <h3 className="font-bold text-foreground">
                        {course.order + 1}. {course.title}
                      </h3>
                      <p className="text-sm text-muted-foreground">{course.description}</p>
                    </div>
                  </Card>
                );
              })}
            </div>
          )}
        </div>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout user={{ name: user?.display_name || "User", level: user?.level || "A1" }}>
      <div className="max-w-6xl mx-auto px-4 py-8">
        <div className="mb-8">
          <h1 className="text-4xl font-bold text-foreground mb-2">Universidad</h1>
          <p className="text-lg text-muted-foreground">
            Carreras autodirigidas y rigurosas diseñadas para el dominio profesional
          </p>
        </div>

        <Card className="p-4 mb-8 border-yellow-200 bg-yellow-50">
          <p className="text-sm text-yellow-900">
            <strong>Nota:</strong> Estas son rutas de aprendizaje a tu propio ritmo diseñadas para desarrollar
            competencia profesional. No son programas acreditados y no otorgan títulos ni credenciales oficiales.
          </p>
        </Card>

        {progress?.enrollment && (
          <Card className="p-4 mb-8 border-primary/30 bg-primary/5 flex items-center justify-between flex-wrap gap-3">
            <p className="text-sm text-foreground">
              Inscrito actualmente en: <strong>{progress.enrollment.field_name}</strong> ({progress.enrollment.level_label}) —{" "}
              {progress.completed_course_ids.length} de {progress.total_courses} cursos completados · Contenido en{" "}
              <strong>{languageName(progress.enrollment.content_lang)}</strong>
            </p>
            <Button size="sm" onClick={openCurriculum}>
              Ver plan de estudios
            </Button>
          </Card>
        )}

        <Card className="p-4 mb-8 flex items-center gap-3 flex-wrap">
          <label className="text-sm font-medium text-foreground">Idioma del contenido al inscribirme:</label>
          <select
            value={contentLang}
            onChange={(e) => setContentLang(e.target.value)}
            className="px-3 py-1.5 border border-border rounded-md bg-background text-foreground text-sm"
          >
            {LANGUAGES.map(([code, name]) => (
              <option key={code} value={code}>
                {name}
              </option>
            ))}
          </select>
          <span className="text-xs text-muted-foreground">
            Puedes estudiar una carrera en cualquier idioma, no solo en tu idioma natal.
          </span>
        </Card>

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
                  <p className="text-muted-foreground">Cargando carreras...</p>
                </Card>
              ) : (
                <div className="grid gap-6">
                  {fields.map((field) => {
                    const isEnrolled = enrolledFieldId === field.id;
                    return (
                      <Card key={field.id} className="p-6 hover:shadow-md transition-smooth">
                        <div className="flex items-start justify-between mb-4">
                          <div className="flex items-start gap-4">
                            <FieldIcon name={field.icon} className="w-10 h-10 text-primary" />
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
                            {isEnrolled ? "Inscrito ✓" : enrollingFieldId === field.id ? "Inscribiendo..." : "Inscribirme"}
                          </Button>
                        </div>
                        <div className="mt-4 p-4 bg-muted/50 rounded-lg">
                          <p className="text-sm text-muted-foreground">
                            <strong>{tab.courseCount} cursos</strong> en esta ruta · Tutor: {field.tutor_name}
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
