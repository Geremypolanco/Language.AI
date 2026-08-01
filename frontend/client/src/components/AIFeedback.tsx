import { useEffect, useState } from "react";
import { Card } from "@/components/ui/card";
import { Spinner } from "@/components/ui/spinner";

interface AIFeedbackProps {
  userAnswer: string;
  correctAnswer: string;
}

export function AIFeedback({ userAnswer, correctAnswer }: AIFeedbackProps) {
  const [feedback, setFeedback] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const getFeedback = async () => {
      try {
        const response = await fetch("/api/ai/feedback", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          credentials: "include",
          body: JSON.stringify({ user_answer: userAnswer, correct_answer: correctAnswer }),
        });
        const data = await response.json();
        setFeedback(data.feedback);
      } catch (err) {
        console.error("Error getting feedback:", err);
        setFeedback("Unable to generate feedback");
      } finally {
        setLoading(false);
      }
    };

    getFeedback();
  }, [userAnswer, correctAnswer]);

  return (
    <Card className="p-4 bg-blue-50 border-blue-200">
      <div className="flex gap-3">
        <span className="text-2xl">🤖</span>
        <div className="flex-1">
          <p className="font-semibold text-foreground mb-2">AI Tutor Feedback</p>
          {loading ? (
            <div className="flex items-center gap-2">
              <Spinner className="h-4 w-4" />
              <p className="text-sm text-muted-foreground">Analyzing your answer...</p>
            </div>
          ) : (
            <p className="text-sm text-foreground">{feedback}</p>
          )}
        </div>
      </div>
    </Card>
  );
}
