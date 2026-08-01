import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { api, Exercise } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { Volume2 } from "lucide-react";
import { toast } from "sonner";

interface ExercisePlayerProps {
  userId: string;
  unitId: string;
  exercises: Exercise[];
  onExit: () => void;
}

// Types with a fixed set of options to click.
const CHOICE_TYPES = new Set(["multiple_choice", "image_match"]);
// Types answered by typing text, graded by normalized string match.
const TEXT_TYPES = new Set(["fill_blank", "translate_to_target", "translate_to_native", "listen_type"]);
// Graded automatically (choice or exact-text match) — target_text can double
// as the correct_answer for these, so it must never be shown plainly or the
// exercise grades itself. Self-assessed types show target_text on purpose:
// it's the phrase to repeat or a conversation prompt, not an answer to hide.
const GRADED_TYPES = new Set(Array.from(CHOICE_TYPES).concat(Array.from(TEXT_TYPES)));

function normalize(s: string): string {
  return s.trim().toLowerCase().replace(/[.,!?¡¿]/g, "");
}

export default function ExercisePlayer({ userId, unitId, exercises, onExit }: ExercisePlayerProps) {
  const { user } = useAuth();
  const [index, setIndex] = useState(0);
  const [textAnswer, setTextAnswer] = useState("");
  const [revealed, setRevealed] = useState(false);
  const [wasCorrect, setWasCorrect] = useState(false);
  const [feedbackText, setFeedbackText] = useState<string | null>(null);
  const [correctCount, setCorrectCount] = useState(0);
  const [startedAt] = useState(() => Date.now());
  const [submitting, setSubmitting] = useState(false);
  const [summary, setSummary] = useState<{
    xp_gained: number;
    gems_gained: number;
    streak_days: number;
    leveled_up: string | null;
  } | null>(null);

  // image_match / listen_type media — fetched fresh per exercise, since the
  // AI content (and its cache key) is keyed per unit, not per media asset.
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [imageFailed, setImageFailed] = useState(false);
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const [audioFailed, setAudioFailed] = useState(false);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  // speak_repeat recording/transcription — falls back to manual self-assessment
  // if speech-to-text is unavailable (no HF_TOKEN/network), same "degrade, never
  // fake success" pattern as the rest of the app.
  const [isRecording, setIsRecording] = useState(false);
  const [transcribing, setTranscribing] = useState(false);
  const [transcript, setTranscript] = useState<string | null>(null);
  const [sttUnavailable, setSttUnavailable] = useState(false);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);

  // free_conversation_prompt — a real in-character tutor reply instead of a
  // blind self-assessment banner.
  const [conversationAnswer, setConversationAnswer] = useState("");
  const [tutorReplying, setTutorReplying] = useState(false);

  const exercise = exercises[index];
  const isLast = index === exercises.length - 1;

  // Fetch image_match / listen_type media whenever the exercise changes.
  useEffect(() => {
    setImageUrl(null);
    setImageFailed(false);
    setAudioUrl(null);
    setAudioFailed(false);
    setTranscript(null);
    setSttUnavailable(false);

    let cancelled = false;
    if (exercise.type === "image_match") {
      api
        .getExerciseImage(exercise.image_prompt || exercise.target_text)
        .then((url) => !cancelled && setImageUrl(url))
        .catch(() => !cancelled && setImageFailed(true));
    } else if (exercise.type === "listen_type" && user) {
      api
        .getExerciseAudio(exercise.audio_text || exercise.target_text, user.target_lang)
        .then((url) => !cancelled && setAudioUrl(url))
        .catch(() => !cancelled && setAudioFailed(true));
    }
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [index]);

  // Auto-play listening audio as soon as it's ready.
  useEffect(() => {
    if (audioUrl && audioRef.current) {
      audioRef.current.play().catch(() => {
        // Autoplay can be blocked by the browser — the visible "Escuchar" button still works.
      });
    }
  }, [audioUrl]);

  // Revoke blob: URLs on unmount/change to avoid leaking memory.
  useEffect(() => {
    return () => {
      if (imageUrl) URL.revokeObjectURL(imageUrl);
      if (audioUrl) URL.revokeObjectURL(audioUrl);
    };
  }, [imageUrl, audioUrl]);

  const recordAnswer = async (correct: boolean, feedback: string | null = null) => {
    setWasCorrect(correct);
    setFeedbackText(feedback);
    setRevealed(true);
    if (correct) setCorrectCount((c) => c + 1);
    if (exercise.vocab_key) {
      try {
        await api.submitLessonAnswer(userId, {
          vocab_key: exercise.vocab_key,
          correct,
          attempts_before_correct: 0,
        });
      } catch {
        // SRS scheduling is best-effort — a failure here shouldn't block the lesson.
      }
    }
  };

  const handleChoice = (option: string) => {
    if (revealed) return;
    recordAnswer(normalize(option) === normalize(exercise.correct_answer));
  };

  const handleTextSubmit = () => {
    if (revealed || !textAnswer.trim()) return;
    recordAnswer(normalize(textAnswer) === normalize(exercise.correct_answer));
  };

  const handleSelfAssess = (correct: boolean) => {
    if (revealed) return;
    recordAnswer(correct);
  };

  const replayAudio = async () => {
    if (!user) return;
    try {
      const url = await api.getExerciseAudio(exercise.audio_text || exercise.target_text, user.target_lang);
      setAudioUrl((prev) => {
        if (prev) URL.revokeObjectURL(prev);
        return url;
      });
      setAudioFailed(false);
    } catch {
      setAudioFailed(true);
      toast.error("No se pudo reproducir el audio");
    }
  };

  const startSpeakRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mediaRecorder = new MediaRecorder(stream);
      mediaRecorderRef.current = mediaRecorder;
      audioChunksRef.current = [];
      mediaRecorder.ondataavailable = (e) => audioChunksRef.current.push(e.data);
      mediaRecorder.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        const blob = new Blob(audioChunksRef.current, { type: "audio/webm" });
        setTranscribing(true);
        try {
          const text = await api.transcribeAudio(blob);
          if (!text) {
            setSttUnavailable(true);
            return;
          }
          setTranscript(text);
          const said = normalize(text);
          const target = normalize(exercise.target_text);
          const matched = said.includes(target) || target.includes(said);
          recordAnswer(matched, `Escuchamos: "${text}"`);
        } catch {
          setSttUnavailable(true);
        } finally {
          setTranscribing(false);
        }
      };
      mediaRecorder.start();
      setIsRecording(true);
    } catch {
      toast.error("No se pudo acceder al micrófono");
    }
  };

  const stopSpeakRecording = () => {
    mediaRecorderRef.current?.stop();
    setIsRecording(false);
  };

  const submitConversationAnswer = async () => {
    if (!conversationAnswer.trim() || !user) return;
    setTutorReplying(true);
    try {
      const reply = await api.getExerciseTutorReply({
        target_lang: user.target_lang,
        native_lang: user.native_lang,
        level: user.level,
        interests: user.interests,
        prompt: exercise.prompt,
        user_answer: conversationAnswer,
      });
      // Open-ended conversation has no single right answer — completing it
      // (and getting a real reply back) is what counts.
      recordAnswer(true, reply);
    } catch {
      recordAnswer(true, null);
    } finally {
      setTutorReplying(false);
    }
  };

  const handleNext = async () => {
    if (!isLast) {
      setIndex((i) => i + 1);
      setTextAnswer("");
      setConversationAnswer("");
      setRevealed(false);
      setFeedbackText(null);
      return;
    }
    setSubmitting(true);
    try {
      const finalCorrect = correctCount;
      const score = finalCorrect / exercises.length;
      const elapsedSeconds = Math.round((Date.now() - startedAt) / 1000);
      const result = await api.completeLesson(userId, unitId, score, elapsedSeconds);
      setSummary(result as typeof summary);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "No se pudo guardar el resultado de la lección");
      onExit();
    } finally {
      setSubmitting(false);
    }
  };

  if (summary) {
    return (
      <Card className="max-w-lg mx-auto p-8 text-center space-y-4">
        <div className="text-5xl">🎉</div>
        <h2 className="text-2xl font-bold text-foreground">¡Lección completada!</h2>
        <div className="grid grid-cols-3 gap-4 py-4">
          <div>
            <p className="text-2xl font-bold text-primary">+{summary.xp_gained}</p>
            <p className="text-xs text-muted-foreground">XP</p>
          </div>
          <div>
            <p className="text-2xl font-bold text-primary">+{summary.gems_gained}</p>
            <p className="text-xs text-muted-foreground">Gemas</p>
          </div>
          <div>
            <p className="text-2xl font-bold text-orange-500">{summary.streak_days}</p>
            <p className="text-xs text-muted-foreground">Racha (días)</p>
          </div>
        </div>
        {summary.leveled_up && (
          <p className="text-primary font-semibold">¡Subiste a nivel {summary.leveled_up}!</p>
        )}
        <Button className="w-full" onClick={onExit}>
          Continuar
        </Button>
      </Card>
    );
  }

  // target_text often *is* the correct_answer for graded types — showing it
  // plainly there would give the exercise away before the learner attempts it.
  const targetTextIsAnswer = GRADED_TYPES.has(exercise.type) && normalize(exercise.target_text) === normalize(exercise.correct_answer);

  return (
    <Card className="max-w-lg mx-auto p-8 space-y-6">
      <div>
        <div className="flex justify-between text-sm text-muted-foreground mb-2">
          <span>
            Ejercicio {index + 1} de {exercises.length}
          </span>
          <span>{correctCount} correctas</span>
        </div>
        <Progress value={(index / exercises.length) * 100} className="h-2" />
      </div>

      <div>
        <p className="text-lg font-semibold text-foreground mb-1">{exercise.prompt}</p>
        {exercise.target_text && !targetTextIsAnswer && (
          <p className="text-2xl font-bold text-primary mb-2">{exercise.target_text}</p>
        )}
      </div>

      {exercise.type === "image_match" && (
        <div className="flex justify-center">
          {imageUrl ? (
            <img src={imageUrl} alt="" className="max-h-48 rounded-lg object-cover" />
          ) : imageFailed ? (
            <p className="text-sm text-muted-foreground italic">(Imagen no disponible en este momento)</p>
          ) : (
            <div className="h-48 w-48 rounded-lg bg-muted animate-pulse" />
          )}
        </div>
      )}

      {exercise.type === "listen_type" && (
        <div className="flex items-center justify-center">
          {audioUrl && <audio ref={audioRef} src={audioUrl} />}
          <Button type="button" variant="outline" size="lg" onClick={replayAudio} disabled={!user}>
            <Volume2 className="w-5 h-5 mr-2" />
            Escuchar
          </Button>
          {audioFailed && (
            <p className="text-sm text-muted-foreground italic ml-3">(Audio no disponible en este momento)</p>
          )}
        </div>
      )}

      {CHOICE_TYPES.has(exercise.type) && (
        <div className="grid grid-cols-1 gap-2">
          {exercise.options.map((opt) => {
            const isCorrectOpt = normalize(opt) === normalize(exercise.correct_answer);
            return (
              <Button
                key={opt}
                variant="outline"
                disabled={revealed}
                onClick={() => handleChoice(opt)}
                className={
                  revealed && isCorrectOpt
                    ? "border-green-500 bg-green-50 text-green-700"
                    : revealed
                      ? "opacity-50"
                      : ""
                }
              >
                {opt}
              </Button>
            );
          })}
        </div>
      )}

      {TEXT_TYPES.has(exercise.type) && (
        <div className="flex gap-2">
          <Input
            value={textAnswer}
            onChange={(e) => setTextAnswer(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleTextSubmit()}
            disabled={revealed}
            placeholder="Tu respuesta..."
          />
          <Button onClick={handleTextSubmit} disabled={revealed || !textAnswer.trim()}>
            Verificar
          </Button>
        </div>
      )}

      {exercise.type === "speak_repeat" && !revealed && (
        <div className="space-y-3">
          <div className="flex justify-center">
            <Button
              type="button"
              size="lg"
              className={isRecording ? "bg-destructive" : "bg-primary"}
              onClick={isRecording ? stopSpeakRecording : startSpeakRecording}
              disabled={transcribing}
            >
              {isRecording ? "🛑 Detener" : transcribing ? "Escuchando..." : "🎤 Grabar mi pronunciación"}
            </Button>
          </div>
          {sttUnavailable && (
            <div className="space-y-2 text-center">
              <p className="text-sm text-muted-foreground italic">
                (No se pudo transcribir el audio en este momento — evalúate tú mismo)
              </p>
              <div className="flex gap-2 justify-center">
                <Button variant="outline" onClick={() => handleSelfAssess(true)}>
                  ✅ Lo logré
                </Button>
                <Button variant="outline" onClick={() => handleSelfAssess(false)}>
                  🔁 Necesito practicar más
                </Button>
              </div>
            </div>
          )}
        </div>
      )}

      {exercise.type === "free_conversation_prompt" && !revealed && (
        <div className="flex gap-2">
          <Input
            value={conversationAnswer}
            onChange={(e) => setConversationAnswer(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && submitConversationAnswer()}
            disabled={tutorReplying}
            placeholder="Responde en el idioma que estás practicando..."
          />
          <Button onClick={submitConversationAnswer} disabled={tutorReplying || !conversationAnswer.trim()}>
            {tutorReplying ? "..." : "Enviar"}
          </Button>
        </div>
      )}

      {revealed && (
        <div
          className={`p-3 rounded-lg text-sm ${
            wasCorrect ? "bg-green-50 text-green-700 border border-green-200" : "bg-amber-50 text-amber-700 border border-amber-200"
          }`}
        >
          {feedbackText ? (
            <p>{feedbackText}</p>
          ) : wasCorrect ? (
            "¡Correcto!"
          ) : (
            `La respuesta era: ${exercise.correct_answer}`
          )}
        </div>
      )}

      <div className="flex justify-between">
        <Button variant="ghost" onClick={onExit}>
          Salir
        </Button>
        {revealed && (
          <Button onClick={handleNext} disabled={submitting}>
            {submitting ? "Guardando..." : isLast ? "Terminar" : "Siguiente"}
          </Button>
        )}
      </div>
    </Card>
  );
}
