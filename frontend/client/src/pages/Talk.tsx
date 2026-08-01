import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useState } from "react";
import DashboardLayout from "@/components/DashboardLayout";

/**
 * Talk Page - Live conversation with AI tutor
 */

interface Message {
  id: string;
  role: "user" | "tutor";
  text: string;
  timestamp: Date;
}

export default function Talk() {
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

  const handleSendMessage = () => {
    if (!input.trim()) return;

    const userMessage: Message = {
      id: Date.now().toString(),
      role: "user",
      text: input,
      timestamp: new Date(),
    };

    setMessages([...messages, userMessage]);
    setInput("");

    // Simulate tutor response
    setTimeout(() => {
      const tutorMessage: Message = {
        id: (Date.now() + 1).toString(),
        role: "tutor",
        text: "That's great! Let me help you with that. Could you tell me more?",
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, tutorMessage]);
    }, 1000);
  };

  return (
    <DashboardLayout user={{ name: "Alex", level: 12 }}>
      <div className="max-w-4xl mx-auto px-4 py-8 h-full flex flex-col">
        {/* Header */}
        <div className="mb-6">
          <h1 className="text-3xl font-bold text-foreground mb-2">Talk Live</h1>
          <p className="text-muted-foreground">
            Have a real conversation with your AI tutor. Speak or type.
          </p>
        </div>

        {/* Chat Container */}
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

        {/* Input Area */}
        <div className="space-y-4">
          {/* Voice Recording */}
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

          {/* Text Input */}
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

        {/* Tips */}
        <Card className="mt-6 p-4 bg-blue-50 border-blue-200">
          <p className="text-sm text-blue-900">
            <strong>Tip:</strong> The more you talk, the better you get. Don't worry about mistakes — that's how you learn!
          </p>
        </Card>
      </div>
    </DashboardLayout>
  );
}
