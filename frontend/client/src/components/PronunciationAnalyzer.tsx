import { useState } from "react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

interface PronunciationAnalyzerProps {
  referenceText: string;
}

export function PronunciationAnalyzer({ referenceText }: PronunciationAnalyzerProps) {
  const [recording, setRecording] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  const handleRecord = async () => {
    if (!recording) {
      setRecording(true);
      // Placeholder for actual recording logic
    } else {
      setRecording(false);
      setLoading(true);
      
      try {
        // Simulate pronunciation check
        const response = await fetch("/api/ai/check-pronunciation", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          credentials: "include",
          body: JSON.stringify({ user_text: "test", reference_text: referenceText }),
        });
        const data = await response.json();
        setResult(data);
      } catch (err) {
        console.error("Error:", err);
      } finally {
        setLoading(false);
      }
    }
  };

  return (
    <Card className="p-6">
      <h3 className="text-lg font-bold mb-4">Pronunciation Practice</h3>
      
      <div className="mb-4 p-4 bg-muted rounded-lg">
        <p className="text-sm text-muted-foreground">Say this:</p>
        <p className="text-xl font-semibold">{referenceText}</p>
      </div>

      <Button
        onClick={handleRecord}
        className={`w-full mb-4 ${recording ? "bg-destructive" : "bg-primary"}`}
        disabled={loading}
      >
        {recording ? "🛑 Stop Recording" : "🎤 Start Recording"}
      </Button>

      {result && (
        <div className="space-y-3">
          <div className="p-3 bg-green-50 rounded-lg">
            <p className="text-sm font-semibold text-green-900">Accuracy: {result.accuracy}%</p>
          </div>
          {result.issues && (
            <div className="p-3 bg-yellow-50 rounded-lg">
              <p className="text-sm font-semibold text-yellow-900 mb-1">Issues:</p>
              <ul className="text-sm text-yellow-800">
                {result.issues.map((issue: string, i: number) => (
                  <li key={i}>• {issue}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </Card>
  );
}
