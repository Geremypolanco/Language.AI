import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useState, useEffect, useRef } from "react";
import DashboardLayout from "@/components/DashboardLayout";
import { useAuth } from "@/contexts/AuthContext";

interface Message {
  id: string;
  role: "user" | "tutor";
  text: string;
  timestamp: Date;
}

export default function Talk() {
  const { user } = useAuth();
  const [messages, setMessages] = useState<Message[]>([
    {
      id: "1",
      role: "tutor",
      text: "Hello! I'm your AI tutor. Ready for a conversation? You can speak or type.",
      timestamp: new Date(),
    },
  ]);
  const [input, setInput] = useState("");
  const [isRecording, setIsRecording] = useState(false);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mediaRecorder = new MediaRecorder(stream);
      mediaRecorderRef.current = mediaRecorder;
      audioChunksRef.current = [];

      mediaRecorder.ondataavailable = (event) => {
        audioChunksRef.current.push(event.data);
      };

      mediaRecorder.onstop = async () => {
        const audioBlob = new Blob(audioChunksRef.current, { type: "audio/wav" });
        await transcribeAudio(audioBlob);
      };

      mediaRecorder.start();
      setIsRecording(true);
    } catch (err) {
      console.error("Microphone access denied:", err);
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current) {
      mediaRecorderRef.current.stop();
      setIsRecording(false);
    }
  };

  const transcribeAudio = async (audioBlob: Blob) => {
    try {
      const formData = new FormData();
      formData.append("file", audioBlob);
      const response = await fetch("/api/ai/transcribe", {
        method: "POST",
        credentials: "include",
        body: formData,
      });
      const data = await response.json();
      if (data.text) {
        setInput(data.text);
      }
    } catch (err) {
      console.error("Transcription error:", err);
    }
  };

  const handleSendMessage = async () => {
    if (!input.trim()) return;

    const userMessage: Message = {
      id: Date.now().toString(),
      role: "user",
      text: input,
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setInput("");

    try {
      const response = await fetch("/api/ai/explain", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ concept: input }),
      });
      const data = await response.json();
      const tutorMessage: Message = {
        id: (Date.now() + 1).toString(),
        role: "tutor",
        text: data.explanation || "I understood that. Tell me more!",
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, tutorMessage]);
    } catch (err) {
      console.error("Error:", err);
    }
  };

  return (
    <DashboardLayout user={{ name: user?.display_name || "User", level: user?.level || 1 }}>
      <div className="max-w-4xl mx-auto px-4 py-8 h-full flex flex-col">
        <div className="mb-6">
          <h1 className="text-3xl font-bold text-foreground mb-2">Talk Live</h1>
          <p className="text-muted-foreground">Speak or type with your AI tutor</p>
        </div>

        <div className="flex-1 bg-card rounded-lg border border-border p-6 mb-6 overflow-y-auto space-y-4">
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
          >
            {isRecording ? "🛑 Stop Recording" : "🎤 Record"}
          </Button>

          <div className="flex gap-2">
            <Input
              placeholder="Or type..."
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyPress={(e) => e.key === "Enter" && handleSendMessage()}
              className="h-12"
            />
            <Button onClick={handleSendMessage} disabled={!input.trim()}>
              Send
            </Button>
          </div>
        </div>
      </div>
    </DashboardLayout>
  );
}
