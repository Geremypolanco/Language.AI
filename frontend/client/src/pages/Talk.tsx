import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useState, useEffect } from "react";
import DashboardLayout from "@/components/DashboardLayout";
import { useAuth } from "@/contexts/AuthContext";
import { api } from "@/lib/api";

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
  const [ws, setWs] = useState<WebSocket | null>(null);

  useEffect(() => {
    if (!user?.id) return;

    const websocket = api.connectConversation(user.id);
    
    websocket.onopen = () => {
      console.log("WebSocket connected");
    };

    websocket.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.type === "reply_done" && data.text) {
        const tutorMessage: Message = {
          id: Date.now().toString(),
          role: "tutor",
          text: data.text,
          timestamp: new Date(),
        };
        setMessages((prev) => [...prev, tutorMessage]);
      }
    };

    websocket.onerror = (error) => {
      console.error("WebSocket error:", error);
    };

    setWs(websocket);

    return () => {
      websocket.close();
    };
  }, [user?.id]);

  const handleSendMessage = () => {
    if (!input.trim() || !ws) return;

    const userMessage: Message = {
      id: Date.now().toString(),
      role: "user",
      text: input,
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMessage]);
    ws.send(JSON.stringify({ type: "text", data: input }));
    setInput("");
  };

  return (
    <DashboardLayout user={{ name: user?.display_name || "User", level: user?.level || 1 }}>
      <div className="max-w-4xl mx-auto px-4 py-8 h-full flex flex-col">
        <div className="mb-6">
          <h1 className="text-3xl font-bold text-foreground mb-2">Talk Live</h1>
          <p className="text-muted-foreground">
            Have a real conversation with your AI tutor. Speak or type.
          </p>
        </div>

        <div className="flex-1 bg-card rounded-lg border border-border p-6 mb-6 overflow-y-auto space-y-4">
          {messages.map((msg) => (
            <div
              key={msg.id}
              className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
            >
              <div
                className={`max-w-xs lg:max-w-md px-4 py-3 rounded-lg ${
                  msg.role === "user"
                    ? "bg-primary text-primary-foreground"
                    : "bg-muted text-foreground"
                }`}
              >
                <p className="text-sm">{msg.text}</p>
                <p
                  className={`text-xs mt-1 ${
                    msg.role === "user" ? "text-primary-foreground/70" : "text-muted-foreground"
                  }`}
                >
                  {msg.timestamp.toLocaleTimeString()}
                </p>
              </div>
            </div>
          ))}
        </div>

        <div className="space-y-4">
          <div className="flex gap-2">
            <Button
              size="lg"
              className={`flex-1 h-12 ${
                isRecording
                  ? "bg-destructive hover:bg-destructive/90"
                  : "bg-primary hover:bg-primary/90"
              }`}
              onClick={() => setIsRecording(!isRecording)}
            >
              {isRecording ? (
                <>
                  <span className="animate-pulse mr-2">●</span>
                  Stop Recording
                </>
              ) : (
                <>
                  🎤 Hold to Record
                </>
              )}
            </Button>
          </div>

          <div className="flex gap-2">
            <Input
              placeholder="Or type your message..."
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyPress={(e) => e.key === "Enter" && handleSendMessage()}
              className="h-12"
            />
            <Button
              size="lg"
              className="bg-primary hover:bg-primary/90"
              onClick={handleSendMessage}
              disabled={!input.trim()}
            >
              Send
            </Button>
          </div>
        </div>

        <Card className="mt-6 p-4 bg-blue-50 border-blue-200">
          <p className="text-sm text-blue-900">
            <strong>Tip:</strong> The more you talk, the better you get. Don't worry about mistakes — that's how you learn!
          </p>
        </Card>
      </div>
    </DashboardLayout>
  );
}
