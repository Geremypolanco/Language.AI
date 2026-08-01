import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { api, Assignment, CourseContent, CourseStub } from "@/lib/api";
import { toast } from "sonner";

interface CourseViewerProps {
  userId: string;
  course: CourseStub;
  alreadyCompleted: boolean;
  onExit: () => void;
  onCompleted: () => void;
}

function AssignmentCard({
  userId,
  courseId,
  assignment,
  onSubmitted,
}: {
  userId: string;
  courseId: string;
  assignment: Assignment;
  onSubmitted: (updated: Assignment) => void;
}) {
  const [response, setResponse] = useState(assignment.response);
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async () => {
    if (!response.trim()) return;
    setSubmitting(true);
    try {
      const result = await api.submitAcademyAssignment(userId, courseId, assignment.id, response);
      onSubmitted({ ...assignment, submitted: true, response, feedback: result.feedback, grade: result.grade });
      toast.success("Tarea enviada y calificada");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "No se pudo enviar la tarea");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Card className="p-5 space-y-3">
      <div className="flex items-center justify-between">
        <h4 className="font-bold text-foreground">{assignment.title}</h4>
        <Badge variant="secondary">{assignment.type}</Badge>
      </div>
      <p className="text-sm text-muted-foreground">{assignment.instructions}</p>
      {assignment.submitted ? (
        <div className="space-y-2">
          <div className="rounded-lg bg-muted/50 p-3 text-sm whitespace-pre-wrap">{assignment.response}</div>
          <div className="rounded-lg border border-primary/30 bg-primary/5 p-3 text-sm space-y-1">
            <p className="font-semibold text-primary">Calificación: {assignment.grade}</p>
            <p className="text-foreground whitespace-pre-wrap">{assignment.feedback}</p>
          </div>
        </div>
      ) : (
        <div className="space-y-2">
          <Textarea
            value={response}
            onChange={(e) => setResponse(e.target.value)}
            placeholder="Escribe tu respuesta..."
            rows={4}
          />
          <Button size="sm" onClick={handleSubmit} disabled={submitting || !response.trim()}>
            {submitting ? "Enviando..." : "Enviar tarea"}
          </Button>
        </div>
      )}
    </Card>
  );
}

export default function CourseViewer({ userId, course, alreadyCompleted, onExit, onCompleted }: CourseViewerProps) {
  const [content, setContent] = useState<CourseContent | null>(null);
  const [loadingContent, setLoadingContent] = useState(true);

  const [scenario, setScenario] = useState<string | null>(null);
  const [loadingScenario, setLoadingScenario] = useState(false);
  const [scenarioResponse, setScenarioResponse] = useState("");
  const [scenarioFeedback, setScenarioFeedback] = useState<string | null>(null);
  const [submittingScenario, setSubmittingScenario] = useState(false);

  const [assignments, setAssignments] = useState<Assignment[] | null>(null);
  const [loadingAssignments, setLoadingAssignments] = useState(false);

  const [completing, setCompleting] = useState(false);

  useEffect(() => {
    setLoadingContent(true);
    api
      .getAcademyCourse(userId, course.id)
      .then(setContent)
      .catch((err) => toast.error(err instanceof Error ? err.message : "No se pudo cargar el curso"))
      .finally(() => setLoadingContent(false));

    setLoadingAssignments(true);
    api
      .getAcademyAssignments(userId, course.id)
      .then(setAssignments)
      .catch(() => setAssignments([]))
      .finally(() => setLoadingAssignments(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [course.id]);

  const loadScenario = async () => {
    setLoadingScenario(true);
    try {
      const data = await api.getAcademyScenario(userId, course.id);
      setScenario(data.scenario);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "No se pudo generar el caso práctico");
    } finally {
      setLoadingScenario(false);
    }
  };

  const submitScenario = async () => {
    if (!scenario || !scenarioResponse.trim()) return;
    setSubmittingScenario(true);
    try {
      const data = await api.getAcademyScenarioFeedback(userId, course.id, scenario, scenarioResponse);
      setScenarioFeedback(data.feedback);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "No se pudo evaluar tu respuesta");
    } finally {
      setSubmittingScenario(false);
    }
  };

  const handleComplete = async () => {
    setCompleting(true);
    try {
      await api.completeAcademyCourse(userId, course.id);
      toast.success("¡Curso completado!");
      onCompleted();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "No se pudo marcar el curso como completado");
    } finally {
      setCompleting(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <Button variant="ghost" onClick={onExit}>
          ← Volver al plan de estudios
        </Button>
        {alreadyCompleted ? (
          <Badge>Completado ✓</Badge>
        ) : (
          <Button onClick={handleComplete} disabled={completing}>
            {completing ? "Guardando..." : "Marcar curso como completado"}
          </Button>
        )}
      </div>

      <div>
        <h2 className="text-2xl font-bold text-foreground">{course.title}</h2>
        <p className="text-muted-foreground mt-1">{course.description}</p>
      </div>

      {loadingContent ? (
        <Card className="p-6 text-center">
          <p className="text-muted-foreground">Cargando contenido del curso...</p>
        </Card>
      ) : !content || content.modules.length === 0 ? (
        <Card className="p-6 text-center">
          <p className="text-muted-foreground">No se pudo generar el contenido de este curso en este momento.</p>
        </Card>
      ) : (
        <div className="space-y-4">
          {content.modules.map((m, i) => (
            <Card key={i} className="p-5">
              <h3 className="font-bold text-foreground mb-2">{m.title}</h3>
              <div className="text-sm text-foreground whitespace-pre-wrap leading-relaxed">{m.content}</div>
            </Card>
          ))}
        </div>
      )}

      <div>
        <h3 className="text-lg font-bold text-foreground mb-3">Caso práctico</h3>
        {!scenario ? (
          <Button variant="outline" onClick={loadScenario} disabled={loadingScenario}>
            {loadingScenario ? "Generando caso..." : "Generar un caso práctico"}
          </Button>
        ) : (
          <Card className="p-5 space-y-3">
            <p className="text-sm text-foreground whitespace-pre-wrap">{scenario}</p>
            {scenarioFeedback ? (
              <div className="rounded-lg border border-primary/30 bg-primary/5 p-3 text-sm whitespace-pre-wrap">
                {scenarioFeedback}
              </div>
            ) : (
              <div className="space-y-2">
                <Textarea
                  value={scenarioResponse}
                  onChange={(e) => setScenarioResponse(e.target.value)}
                  placeholder="¿Cómo resolverías este caso?"
                  rows={4}
                />
                <Button size="sm" onClick={submitScenario} disabled={submittingScenario || !scenarioResponse.trim()}>
                  {submittingScenario ? "Evaluando..." : "Enviar respuesta"}
                </Button>
              </div>
            )}
          </Card>
        )}
      </div>

      <div>
        <h3 className="text-lg font-bold text-foreground mb-3">Tareas</h3>
        {loadingAssignments ? (
          <p className="text-sm text-muted-foreground">Cargando tareas...</p>
        ) : !assignments || assignments.length === 0 ? (
          <p className="text-sm text-muted-foreground">No hay tareas disponibles para este curso en este momento.</p>
        ) : (
          <div className="space-y-4">
            {assignments.map((a) => (
              <AssignmentCard
                key={a.id}
                userId={userId}
                courseId={course.id}
                assignment={a}
                onSubmitted={(updated) =>
                  setAssignments((prev) => prev!.map((x) => (x.id === updated.id ? updated : x)))
                }
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
