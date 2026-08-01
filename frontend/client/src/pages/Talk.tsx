import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useState, useEffect, useRef } from "react";
import DashboardLayout from "@/components/DashboardLayout";
import { useAuth } from "@/contexts/AuthContext";
import { api } from "@/lib/api";
import { toast } from "sonner";

interface Message {
  id: string;
  role: "user" | "tutor";
  text: string;
}

// Mirrors backend/routers/conversation.py's websocket message contract.
type ServerEvent =
  | { type: "ready" | "error"; message: string }
  | { type: "transcript"; text: string }
  | { type: "reply_start" }
  | { type: "reply_chunk"; text: string }
  | { type: "reply_done"; text: string }
  | { type: "reply_audio_chunk"; text: string; audio_base64: string; audio_mime: string };

function blobToBase64(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onloadend = () => resolve((reader.result as string).split(",")[1] ?? "");
    reader.onerror = reject;
    reader.readAsDataURL(blob);
  });
}

export default function Talk() {
  const { user } = useAuth();
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isRecording, setIsRecording] = useState(false);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const audioQueueRef = useRef<HTMLAudioElement[]>([]);
  const playingRef = useRef(false);
  const currentTutorMsgId = useRef<string | null>(null);

  useEffect(() => {
    if (!user?.id) return;
    const ws = api.connectConversation(user.id);
    wsRef.current = ws;

    ws.onopen = () => setConnected(true);
    ws.onclose = () => setConnected(false);
    ws.onerror = () => toast.error("Conexión con el tutor interrumpida");

    ws.onmessage = (event) => {
      const msg: ServerEvent = JSON.parse(event.data);
      switch (msg.type) {
        case "ready":
          setMessages([{ id: "greeting", role: "tutor", text: msg.message }]);
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
      }
    };

    return () => ws.close();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.id]);

  const playNextAudio = () => {
    if (playingRef.current) return;
    const next = audioQueueRef.current.shift();
    if (!next) return;
    playingRef.current = true;
    next.onended = () => {
      playingRef.current = false;
      playNextAudio();
    };
    next.play().catch(() => {
      playingRef.current = false;
    });
  };

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mediaRecorder = new MediaRecorder(stream);
      mediaRecorderRef.current = mediaRecorder;
      audioChunksRef.current = [];

      mediaRecorder.ondataavailable = (event) => audioChunksRef.current.push(event.data);
      mediaRecorder.onstop = async () => {
        const audioBlob = new Blob(audioChunksRef.current, { type: "audio/webm" });
        const base64 = await blobToBase64(audioBlob);
        wsRef.current?.send(JSON.stringify({ type: "audio", data: base64, content_type: "audio/webm" }));
        stream.getTracks().forEach((t) => t.stop());
      };

      mediaRecorder.start();
      setIsRecording(true);
    } catch (err) {
      toast.error("No se pudo acceder al micrófono");
    }
  };

  const stopRecording = () => {
    mediaRecorderRef.current?.stop();
    setIsRecording(false);
  };

  const handleSendMessage = () => {
    if (!input.trim() || !wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
    wsRef.current.send(JSON.stringify({ type: "text", data: input }));
    setInput("");
  };

  return (
    <DashboardLayout user={{ name: user?.display_name || "User", level: user?.level || "A1" }}>
      <div className="max-w-4xl mx-auto px-4 py-8 h-full flex flex-col">
        <div className="mb-6">
          <h1 className="text-3xl font-bold text-foreground mb-2">Talk Live</h1>
          <p className="text-muted-foreground">
            Speak or type with your AI tutor {!connected && "(connecting...)"}
          </p>
        </div>

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
            onClick={isRecording ? stopRecording : startRecording}
            disabled={!connected}
          >
            {isRecording ? "🛑 Stop Recording" : "🎤 Record"}
          </Button>

          <div className="flex gap-2">
            <Input
              placeholder="Or type..."
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSendMessage()}
              className="h-12"
              disabled={!connected}
            />
            <Button onClick={handleSendMessage} disabled={!input.trim() || !connected}>
              Send
            </Button>
          </div>
        </div>
      </div>
    </DashboardLayout>
  );
}
