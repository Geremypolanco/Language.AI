import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useState, useEffect, useRef } from "react";
import DashboardLayout from "@/components/DashboardLayout";
import { useAuth } from "@/contexts/AuthContext";
import { api, PersonaInfo } from "@/lib/api";
import { haptics } from "@/lib/haptics";
import { toast } from "sonner";

interface Message {
  id: string;
  role: "user" | "tutor";
  text: string;
}

// Mirrors backend/routers/conversation.py's websocket message contract.
type ServerEvent =
  | { type: "ready"; message: string; persona: PersonaInfo }
  | { type: "error"; message: string }
  | { type: "transcript"; text: string }
  | { type: "reply_start" }
  | { type: "reply_chunk"; text: string }
  | { type: "reply_done"; text: string }
  | { type: "reply_audio_chunk"; text: string; audio_base64: string; audio_mime: string }
  // Sent once the server has nothing more to say for this turn (whether
  // TTS succeeded, failed, or there was no reply at all) — the one
  // reliable "safe to start listening again" signal, since reply_audio_chunk
  // messages arrive incrementally and an empty queue doesn't by itself mean
  // no more are coming.
  | { type: "turn_complete" };

// Voice-activity detection tuning for hands-free mode: continuously
// analyzes the mic's volume (RMS of the time-domain waveform) to detect
// when the learner starts and stops talking, instead of requiring a manual
// "stop recording" tap — the difference between a walkie-talkie and an
// actual spoken conversation like Alexa/Siri. Thresholds are a starting
// point tuned by ear, not measured against real hardware in this
// environment — a genuinely quiet/noisy mic may need different values.
const VAD_SILENCE_RMS = 0.02;
const VAD_SILENCE_MS_TO_STOP = 1200;
const VAD_MAX_UTTERANCE_MS = 20000; // safety cap so a stuck-open mic can't record forever

function blobToBase64(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onloadend = () => resolve((reader.result as string).split(",")[1] ?? "");
    reader.onerror = reject;
    reader.readAsDataURL(blob);
  });
}

function TeacherAvatar({ persona, className }: { persona: PersonaInfo; className?: string }) {
  const [broken, setBroken] = useState(false);
  if (broken) {
    return (
      <div className={`flex items-center justify-center bg-primary/10 text-primary font-bold rounded-full ${className}`}>
        {persona.name.charAt(0)}
      </div>
    );
  }
  return (
    <img
      src={persona.portrait_url}
      alt={persona.name}
      className={`object-cover rounded-full bg-muted ${className}`}
      onError={() => setBroken(true)}
    />
  );
}

export default function Talk() {
  const { user } = useAuth();
  const [personas, setPersonas] = useState<PersonaInfo[]>([]);
  const [selectedPersonaId, setSelectedPersonaId] = useState<string | null>(null);
  const [activePersona, setActivePersona] = useState<PersonaInfo | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isRecording, setIsRecording] = useState(false);
  const [connected, setConnected] = useState(false);
  const [connectionLost, setConnectionLost] = useState(false);
  const [reconnectKey, setReconnectKey] = useState(0);
  // Hands-free mode: listens continuously, auto-detects when the learner
  // stops talking (voice activity detection, no manual "stop" tap needed),
  // and automatically starts listening again once the tutor's spoken reply
  // finishes — the actual thing being asked for ("una conversación fluida
  // ... como Alexa, Siri"), not a push-to-talk walkie-talkie. Defaults on;
  // a learner who prefers manual control (noisy room, wants to type
  // instead) can turn it off.
  const [handsFree, setHandsFree] = useState(true);
  const wsRef = useRef<WebSocket | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const audioQueueRef = useRef<HTMLAudioElement[]>([]);
  const playingRef = useRef(false);
  const currentTutorMsgId = useRef<string | null>(null);
  // Voice-activity detection plumbing — see VAD_* constants above.
  const audioContextRef = useRef<AudioContext | null>(null);
  const vadFrameRef = useRef<number | null>(null);
  // True once the server's turn_complete has arrived AND any queued reply
  // audio has finished playing — the actual "safe to listen again" signal,
  // since those two events can arrive/finish in either order.
  const turnCompleteRef = useRef(false);
  // Mirrors isRecording in a ref — maybeResumeListening is called from
  // callbacks (ws.onmessage, audio.onended) set up once per WebSocket
  // connection, so it would otherwise close over a stale isRecording value
  // from whatever render was active when those callbacks were created.
  const isRecordingRef = useRef(false);
  const handsFreeRef = useRef(handsFree);
  useEffect(() => {
    handsFreeRef.current = handsFree;
  }, [handsFree]);

  // Load the roster of selectable teachers once, and default to the
  // learner's previously-saved persona (if any) so returning users don't
  // have to re-pick every session.
  useEffect(() => {
    api
      .getPersonas()
      .then(setPersonas)
      .catch((err) => toast.error(err instanceof Error ? err.message : "No se pudieron cargar los maestros"));
  }, []);

  useEffect(() => {
    if (user?.tutor_persona_id) setSelectedPersonaId(user.tutor_persona_id);
  }, [user?.tutor_persona_id]);

  useEffect(() => {
    if (!user?.id || !selectedPersonaId) return;
    const ws = api.connectConversation(user.id, selectedPersonaId);
    wsRef.current = ws;

    ws.onopen = () => {
      setConnected(true);
      setConnectionLost(false);
    };
    ws.onclose = () => {
      setConnected(false);
      setConnectionLost(true);
    };
    ws.onerror = () => toast.error("Conexión con el tutor interrumpida");

    ws.onmessage = (event) => {
      const msg: ServerEvent = JSON.parse(event.data);
      switch (msg.type) {
        case "ready":
          setActivePersona(msg.persona);
          setMessages([{ id: "greeting", role: "tutor", text: msg.message }]);
          // The greeting is text-only (no spoken audio turn), so there's no
          // turn_complete to wait for here — just start listening directly.
          if (handsFreeRef.current) startListening();
          break;
        case "error":
          toast.error(msg.message);
          break;
        case "transcript":
          setMessages((prev) => [...prev, { id: `u-${Date.now()}`, role: "user", text: msg.text }]);
          break;
        case "reply_start": {
          const id = `t-${Date.now()}`;
          currentTutorMsgId.current = id;
          setMessages((prev) => [...prev, { id, role: "tutor", text: "" }]);
          haptics.thinking();
          break;
        }
        case "reply_chunk":
          setMessages((prev) =>
            prev.map((m) => (m.id === currentTutorMsgId.current ? { ...m, text: m.text + msg.text } : m))
          );
          break;
        case "reply_done": {
          // setMessages' updater runs asynchronously (React defers it past
          // this synchronous block), so nulling the ref on the next line
          // would already have happened by the time the updater reads it —
          // capture the id now, while it's still valid.
          const finishedId = currentTutorMsgId.current;
          setMessages((prev) => prev.map((m) => (m.id === finishedId ? { ...m, text: msg.text } : m)));
          currentTutorMsgId.current = null;
          break;
        }
        case "reply_audio_chunk": {
          const audio = new Audio(`data:${msg.audio_mime};base64,${msg.audio_base64}`);
          audioQueueRef.current.push(audio);
          playNextAudio();
          break;
        }
        case "turn_complete":
          turnCompleteRef.current = true;
          maybeResumeListening();
          break;
      }
    };

    return () => ws.close();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.id, selectedPersonaId, reconnectKey]);

  const playNextAudio = () => {
    if (playingRef.current) return;
    const next = audioQueueRef.current.shift();
    if (!next) {
      // Nothing left queued right now — if the server already told us the
      // turn is fully done, this is the point where "done talking" actually
      // becomes true (reply_audio_chunk messages can still arrive after an
      // empty queue moment, but never after turn_complete).
      maybeResumeListening();
      return;
    }
    playingRef.current = true;
    next.onended = () => {
      playingRef.current = false;
      playNextAudio();
    };
    next.play().catch(() => {
      playingRef.current = false;
    });
  };

  const stopVad = () => {
    if (vadFrameRef.current !== null) {
      cancelAnimationFrame(vadFrameRef.current);
      vadFrameRef.current = null;
    }
    audioContextRef.current?.close().catch(() => {});
    audioContextRef.current = null;
  };

  // The actual "safe to listen again" check — hands-free mode must wait for
  // BOTH signals (server done sending, AND any queued audio has finished
  // playing) since they can arrive/finish in either order.
  const maybeResumeListening = () => {
    if (
      handsFreeRef.current &&
      turnCompleteRef.current &&
      audioQueueRef.current.length === 0 &&
      !playingRef.current &&
      !isRecordingRef.current &&
      wsRef.current?.readyState === WebSocket.OPEN
    ) {
      turnCompleteRef.current = false;
      startListening();
    }
  };

  const startListening = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mediaRecorder = new MediaRecorder(stream);
      mediaRecorderRef.current = mediaRecorder;
      audioChunksRef.current = [];

      mediaRecorder.ondataavailable = (event) => audioChunksRef.current.push(event.data);
      mediaRecorder.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        stopVad();
        const audioBlob = new Blob(audioChunksRef.current, { type: "audio/webm" });
        const base64 = await blobToBase64(audioBlob);
        if (wsRef.current?.readyState === WebSocket.OPEN) {
          wsRef.current.send(JSON.stringify({ type: "audio", data: base64, content_type: "audio/webm" }));
        } else {
          toast.error("Se perdió la conexión — tu grabación no se envió. Reconecta e intenta de nuevo.");
        }
      };

      mediaRecorder.start();
      isRecordingRef.current = true;
      setIsRecording(true);

      // Voice activity detection: watches the mic's live volume so the
      // recording stops on its own once the learner stops talking, instead
      // of requiring a manual tap — see the VAD_* constants above.
      if (handsFreeRef.current) {
        const audioContext = new AudioContext();
        audioContextRef.current = audioContext;
        const source = audioContext.createMediaStreamSource(stream);
        const analyser = audioContext.createAnalyser();
        analyser.fftSize = 2048;
        source.connect(analyser);
        const data = new Uint8Array(analyser.fftSize);

        let speechDetected = false;
        let silenceStartedAt: number | null = null;
        const listenStartedAt = Date.now();

        const tick = () => {
          if (mediaRecorderRef.current?.state !== "recording") return;

          if (Date.now() - listenStartedAt > VAD_MAX_UTTERANCE_MS) {
            stopListening();
            return;
          }

          analyser.getByteTimeDomainData(data);
          let sumSquares = 0;
          for (let i = 0; i < data.length; i++) {
            const normalized = (data[i] - 128) / 128;
            sumSquares += normalized * normalized;
          }
          const rms = Math.sqrt(sumSquares / data.length);

          if (rms > VAD_SILENCE_RMS) {
            speechDetected = true;
            silenceStartedAt = null;
          } else if (speechDetected) {
            if (silenceStartedAt === null) {
              silenceStartedAt = Date.now();
            } else if (Date.now() - silenceStartedAt > VAD_SILENCE_MS_TO_STOP) {
              stopListening();
              return;
            }
          }
          vadFrameRef.current = requestAnimationFrame(tick);
        };
        vadFrameRef.current = requestAnimationFrame(tick);
      }
    } catch {
      toast.error("No se pudo acceder al micrófono");
    }
  };

  const stopListening = () => {
    mediaRecorderRef.current?.stop();
    isRecordingRef.current = false;
    setIsRecording(false);
  };

  // Clean up the mic/VAD if the learner navigates away mid-recording.
  useEffect(() => {
    return () => {
      stopVad();
      if (mediaRecorderRef.current?.state === "recording") mediaRecorderRef.current.stop();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleSendMessage = () => {
    if (!input.trim() || !wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
    wsRef.current.send(JSON.stringify({ type: "text", data: input }));
    setInput("");
  };

  const choosePersona = async (personaId: string) => {
    setSelectedPersonaId(personaId);
    if (user?.id) {
      try {
        await api.setTutorPersona(user.id, personaId);
      } catch {
        // Saving the default is a nicety — a failed save shouldn't block
        // starting the conversation with the persona the learner just picked.
      }
    }
  };

  if (!selectedPersonaId) {
    return (
      <DashboardLayout user={{ name: user?.display_name || "User", level: user?.level || "A1" }}>
        <div className="max-w-4xl mx-auto px-4 py-8">
          <div className="mb-8">
            <h1 className="text-3xl font-bold text-foreground mb-2">Elige tu maestro</h1>
            <p className="text-muted-foreground">Cada uno tiene un estilo de enseñanza y una voz diferentes.</p>
          </div>
          {personas.length === 0 ? (
            <p className="text-muted-foreground">Cargando maestros...</p>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {personas.map((p) => (
                <Card
                  key={p.id}
                  className="p-5 flex gap-4 items-start hover:shadow-lg transition-smooth cursor-pointer"
                  onClick={() => choosePersona(p.id)}
                >
                  <TeacherAvatar persona={p} className="w-16 h-16 flex-shrink-0 text-xl" />
                  <div>
                    <h3 className="font-bold text-foreground">{p.name}</h3>
                    <p className="text-xs text-primary font-medium mb-1">{p.title}</p>
                    <p className="text-sm text-muted-foreground">{p.philosophy}</p>
                  </div>
                </Card>
              ))}
            </div>
          )}
        </div>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout user={{ name: user?.display_name || "User", level: user?.level || "A1" }}>
      <div className="max-w-4xl mx-auto px-4 py-8 h-full flex flex-col">
        <div className="mb-6 flex items-center justify-between">
          <div className="flex items-center gap-3">
            {activePersona && <TeacherAvatar persona={activePersona} className="w-12 h-12" />}
            <div>
              <h1 className="text-2xl font-bold text-foreground">{activePersona?.name || "Talk Live"}</h1>
              <p className="text-sm text-muted-foreground">
                {activePersona?.title || (!connected && "conectando...")}
              </p>
            </div>
          </div>
          <Button variant="outline" size="sm" onClick={() => setSelectedPersonaId(null)}>
            Cambiar de maestro
          </Button>
        </div>

        {connectionLost && (
          <div className="mb-4 flex items-center justify-between rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-700">
            <span>Se perdió la conexión con el tutor.</span>
            <Button size="sm" variant="outline" onClick={() => setReconnectKey((k) => k + 1)}>
              Reconectar
            </Button>
          </div>
        )}

        <div className="flex-1 bg-card rounded-lg border border-border p-6 mb-6 overflow-y-auto space-y-4 min-h-[300px]">
          {messages.map((msg) => (
            <div key={msg.id} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
              <div
                className={`max-w-xs px-4 py-3 rounded-lg ${
                  msg.role === "user" ? "bg-primary text-primary-foreground" : "bg-muted text-foreground"
                }`}
              >
                <p className="text-sm">{msg.text}</p>
              </div>
            </div>
          ))}
        </div>

        <div className="space-y-4">
          <Button
            size="lg"
            className={`w-full h-12 ${isRecording ? "bg-destructive" : "bg-primary"}`}
            onClick={isRecording ? stopListening : startListening}
            disabled={!connected}
          >
            {isRecording
              ? handsFree
                ? "🎙️ Escuchando... (toca para enviar)"
                : "🛑 Detener grabación"
              : "🎤 Hablar"}
          </Button>

          <button
            type="button"
            className="w-full text-center text-xs text-muted-foreground hover:text-foreground transition-smooth"
            onClick={() => setHandsFree((v) => !v)}
          >
            {handsFree
              ? "🔊 Modo manos libres activado — el tutor te escuchará de nuevo automáticamente. Desactivar"
              : "Modo manos libres desactivado — activar para conversar sin tocar botones"}
          </button>

          <div className="flex gap-2">
            <Input
              placeholder="O escribe..."
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSendMessage()}
              className="h-12"
              disabled={!connected}
            />
            <Button onClick={handleSendMessage} disabled={!input.trim() || !connected}>
              Enviar
            </Button>
          </div>
        </div>
      </div>
    </DashboardLayout>
  );
}
