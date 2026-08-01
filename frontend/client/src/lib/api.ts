/**
 * API Client - Conecta con el backend Language.AI
 * Todos los endpoints requieren credentials: "include" para enviar cookies de sesión
 */

// FastAPI's 422 validation errors put a list of {loc, msg, type} under
// `detail` instead of a string; a plain HTTPException(detail="...") is a
// string. Both shapes have to render as readable text, not "[object Object]".
export interface ApiValidationError {
  loc: (string | number)[];
  msg: string;
  type: string;
}

export interface ApiError {
  detail?: string | ApiValidationError[];
  message?: string;
}

export type CEFRLevel = "A1" | "A2" | "B1" | "B2" | "C1" | "C2" | "NATIVE";

export interface SessionData {
  authenticated: boolean;
  pending?: boolean;
  user_id?: string;
  email?: string;
  name?: string;
  picture?: string;
  display_name?: string;
  native_lang?: string;
  target_lang?: string;
  level?: CEFRLevel;
}

export interface User {
  id: string;
  display_name: string;
  native_lang: string;
  target_lang: string;
  level: CEFRLevel;
  interests: string[];
  daily_goal_minutes: number;
  xp: number;
  streak_days: number;
  gems: number;
  tutor_persona_id: string;
}

// Public view of a backend.personas.TeacherPersona (see backend/personas.py)
export interface PersonaInfo {
  id: string;
  name: string;
  title: string;
  philosophy: string;
  correction_focus: string;
  portrait_url: string;
}

// UnitNode — what /api/lessons/{id}/path actually returns (see backend/routers/lessons.py)
export interface Lesson {
  id: string;
  topic: string;
  level: CEFRLevel;
  order: number;
  state: "available" | "mastered";
  best_score: number;
}

export interface ProgressData {
  user_id: string;
  xp: number;
  streak_days: number;
  gems: number;
  streak_freezes: number;
  level: CEFRLevel;
  due_reviews: number;
  units_mastered: number;
  daily_goal_minutes: number;
  today_minutes: number;
}

export interface LevelMastery {
  level: CEFRLevel;
  mastered: number;
  total: number;
}

export interface ActivityDay {
  date: string;
  lessons_completed: number;
}

export interface RecentLesson {
  unit_id: string;
  topic: string;
  score: number;
  completed_at: string;
}

export interface LeaderboardEntry {
  rank: number;
  display_name: string;
  weekly_xp: number;
  is_you: boolean;
}

export interface TopicMastery {
  topic: string;
  topic_es: string;
  level: number;
}

export interface DashboardData {
  user_id: string;
  xp: number;
  streak_days: number;
  gems: number;
  streak_freezes: number;
  level: CEFRLevel;
  next_level: CEFRLevel | null;
  due_reviews: number;
  units_mastered_current_level: number;
  units_total_current_level: number;
  units_required_for_next_level: number;
  daily_goal_minutes: number;
  today_minutes: number;
  mastery_by_level: LevelMastery[];
  activity: ActivityDay[];
  recent_lessons: RecentLesson[];
  leaderboard: LeaderboardEntry[];
  your_weekly_xp: number;
  your_rank: number | null;
  topic_mastery: TopicMastery[];
}

// Exercise — what /api/lessons/{id}/unit/{unitId} and .../practice return
export interface Exercise {
  id: string;
  type:
    | "image_match"
    | "listen_type"
    | "translate_to_target"
    | "translate_to_native"
    | "multiple_choice"
    | "speak_repeat"
    | "fill_blank"
    | "free_conversation_prompt";
  prompt: string;
  target_text: string;
  native_text: string;
  options: string[];
  correct_answer: string;
  image_prompt: string;
  audio_text: string;
  vocab_key: string;
}

export interface AcademicField {
  id: string;
  name: string;
  category: string;
  icon: string;
  description: string;
  tutor_name: string;
}

export interface AcademyEnrollment {
  field_id: string;
  field_name: string;
  tutor_name: string;
  icon: string;
  category: string;
  level: "ASSOCIATE" | "BACHELOR" | "MASTER";
  level_label: string;
  enrolled_at: string;
}

export interface AcademyProgress {
  enrollment: AcademyEnrollment | null;
  completed_course_ids: string[];
  total_courses: number;
}

export interface CourseStub {
  id: string;
  order: number;
  title: string;
  description: string;
}

export interface Curriculum {
  field_id: string;
  field_name: string;
  level: "ASSOCIATE" | "BACHELOR" | "MASTER";
  level_label: string;
  courses: CourseStub[];
}

export interface CourseModule {
  title: string;
  content: string;
}

export interface CourseContent {
  id: string;
  title: string;
  modules: CourseModule[];
}

export interface Assignment {
  id: string;
  type: string;
  title: string;
  instructions: string;
  submitted: boolean;
  response: string;
  feedback: string;
  grade: string;
}

export interface BookStub {
  id: string;
  title: string;
  genre: string;
  genre_label: string;
  level: CEFRLevel;
  blurb: string;
}

export interface BookContent {
  id: string;
  title: string;
  genre_label: string;
  level: CEFRLevel;
  content: string;
}

function extractErrorMessage(error: ApiError): string {
  const { detail } = error;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail.map((e) => `${e.loc?.slice(-1)[0] ?? "field"}: ${e.msg}`).join("; ");
  }
  return error.message || "";
}

class ApiClient {
  private baseUrl = "";

  constructor() {
    // El baseUrl es relativo porque frontend y backend están en el mismo origen
    this.baseUrl = "";
  }

  private async request<T>(
    path: string,
    options: RequestInit = {}
  ): Promise<T> {
    const url = `${this.baseUrl}${path}`;
    const response = await fetch(url, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...options.headers,
      },
      credentials: "include", // Enviar cookies de sesión
    });

    if (!response.ok) {
      const error: ApiError = await response.json().catch(() => ({}));
      throw new Error(extractErrorMessage(error) || `HTTP ${response.status}`);
    }

    if (response.status === 204) return null as T;
    return response.json();
  }

  // ===== AUTH =====
  async getSession(): Promise<SessionData> {
    return this.request<SessionData>("/api/session");
  }

  async loginWithGoogle() {
    window.location.href = "/auth/google/login";
  }

  async devLogin(email: string, name: string) {
    window.location.href = `/auth/dev-login?email=${encodeURIComponent(email)}&name=${encodeURIComponent(name)}`;
  }

  async createProfile(data: {
    display_name: string;
    native_lang: string;
    target_lang: string;
    level: CEFRLevel;
    interests: string[];
    daily_goal_minutes: number;
  }): Promise<User> {
    return this.request<User>("/api/users", {
      method: "POST",
      body: JSON.stringify(data),
    });
  }

  async logout() {
    return this.request("/auth/logout", { method: "POST" });
  }

  // ===== USER =====
  async getMe(): Promise<User> {
    return this.request<User>("/api/users/me");
  }

  async getUser(userId: string): Promise<User> {
    return this.request<User>(`/api/users/${userId}`);
  }

  // ===== LESSONS (Path & Practice) =====
  async getLessonsPath(userId: string): Promise<Lesson[]> {
    return this.request<Lesson[]>(`/api/lessons/${userId}/path`);
  }

  async getLesson(userId: string, unitId: string): Promise<Exercise[]> {
    return this.request<Exercise[]>(`/api/lessons/${userId}/unit/${unitId}`);
  }

  async submitLessonAnswer(
    userId: string,
    data: { vocab_key: string; correct: boolean; attempts_before_correct?: number }
  ): Promise<{ srs: Record<string, unknown> }> {
    return this.request(`/api/lessons/${userId}/answer`, {
      method: "POST",
      body: JSON.stringify(data),
    });
  }

  async completeLesson(userId: string, unitId: string, score: number, elapsedSeconds = 0) {
    return this.request(`/api/lessons/${userId}/complete`, {
      method: "POST",
      body: JSON.stringify({ unit_id: unitId, score, elapsed_seconds: elapsedSeconds }),
    });
  }

  // Returns a same-origin blob: URL — caller must URL.revokeObjectURL() it
  // once no longer displayed/played (image_match/listen_type exercises).
  private async fetchMediaUrl(path: string, body: unknown): Promise<string> {
    const response = await fetch(`${this.baseUrl}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify(body),
    });
    if (!response.ok) {
      const error: ApiError = await response.json().catch(() => ({}));
      throw new Error(extractErrorMessage(error) || `HTTP ${response.status}`);
    }
    const blob = await response.blob();
    return URL.createObjectURL(blob);
  }

  async getExerciseImage(prompt: string): Promise<string> {
    return this.fetchMediaUrl("/api/content/image", { prompt });
  }

  async getExerciseAudio(text: string, targetLang: string): Promise<string> {
    return this.fetchMediaUrl("/api/content/tts", { text, target_lang: targetLang });
  }

  async transcribeAudio(audioBlob: Blob): Promise<string> {
    const response = await fetch(`${this.baseUrl}/api/content/stt`, {
      method: "POST",
      headers: { "Content-Type": audioBlob.type || "audio/webm" },
      credentials: "include",
      body: audioBlob,
    });
    if (!response.ok) {
      const error: ApiError = await response.json().catch(() => ({}));
      throw new Error(extractErrorMessage(error) || `HTTP ${response.status}`);
    }
    const data = await response.json();
    return data.text ?? "";
  }

  async getExerciseTutorReply(payload: {
    target_lang: string;
    native_lang: string;
    level: CEFRLevel;
    interests: string[];
    prompt: string;
    user_answer: string;
  }): Promise<string> {
    const data = await this.request<{ reply: string }>("/api/content/tutor-reply", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    return data.reply;
  }

  async practiceLessonSkill(
    userId: string,
    exerciseType: string,
    level?: CEFRLevel
  ): Promise<{ unit_id: string; exercises: Exercise[] }> {
    return this.request(`/api/lessons/${userId}/practice`, {
      method: "POST",
      body: JSON.stringify({ exercise_type: exerciseType, level }),
    });
  }

  // ===== ACADEMY (University) =====
  async getAcademyFields(): Promise<AcademicField[]> {
    return this.request("/api/academy/fields");
  }

  async enrollAcademyCareer(userId: string, fieldId: string, level: string): Promise<AcademyEnrollment> {
    return this.request(`/api/academy/${userId}/enroll`, {
      method: "POST",
      body: JSON.stringify({ field_id: fieldId, level }),
    });
  }

  async getAcademyProgress(userId: string): Promise<AcademyProgress> {
    return this.request(`/api/academy/${userId}/progress`);
  }

  async getAcademyCurriculum(userId: string): Promise<Curriculum> {
    return this.request(`/api/academy/${userId}/curriculum`);
  }

  async getAcademyCourse(userId: string, courseId: string): Promise<CourseContent> {
    return this.request(`/api/academy/${userId}/courses/${courseId}`);
  }

  async getAcademyScenario(userId: string, courseId: string): Promise<{ scenario: string }> {
    return this.request(`/api/academy/${userId}/courses/${courseId}/scenario`);
  }

  async getAcademyScenarioFeedback(
    userId: string,
    courseId: string,
    scenario: string,
    response: string
  ): Promise<{ feedback: string }> {
    return this.request(`/api/academy/${userId}/courses/${courseId}/scenario/feedback`, {
      method: "POST",
      body: JSON.stringify({ scenario, response }),
    });
  }

  async getAcademyAssignments(userId: string, courseId: string): Promise<Assignment[]> {
    return this.request(`/api/academy/${userId}/courses/${courseId}/assignments`);
  }

  async submitAcademyAssignment(
    userId: string,
    courseId: string,
    assignmentId: string,
    response: string
  ): Promise<{ grade: string; feedback: string }> {
    return this.request(`/api/academy/${userId}/courses/${courseId}/assignments/${assignmentId}/submit`, {
      method: "POST",
      body: JSON.stringify({ response }),
    });
  }

  async completeAcademyCourse(userId: string, courseId: string): Promise<AcademyProgress> {
    return this.request(`/api/academy/${userId}/courses/${courseId}/complete`, { method: "POST" });
  }

  // ===== PROGRESS =====
  async getProgressSnapshot(userId: string): Promise<ProgressData> {
    return this.request<ProgressData>(`/api/progress/${userId}`);
  }

  async getProgressDashboard(userId: string): Promise<DashboardData> {
    return this.request<DashboardData>(`/api/progress/${userId}/dashboard`);
  }

  // ===== TALK (WebSocket) =====
  connectConversation(userId: string, personaId?: string): WebSocket {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const query = personaId ? `?persona=${encodeURIComponent(personaId)}` : "";
    return new WebSocket(`${protocol}//${window.location.host}/ws/conversation/${userId}${query}`);
  }

  // ===== PERSONAS (Talk Live teacher picker — see backend/personas.py) =====
  async getPersonas(): Promise<PersonaInfo[]> {
    return this.request("/api/personas");
  }

  async setTutorPersona(userId: string, personaId: string): Promise<User> {
    return this.request(`/api/users/${userId}`, {
      method: "PATCH",
      body: JSON.stringify({ tutor_persona_id: personaId }),
    });
  }

  // ===== LIBRARY =====
  async getLibraryGenres(): Promise<string[]> {
    return this.request("/api/library/genres");
  }

  async getLibraryCatalog(userId: string): Promise<BookStub[]> {
    return this.request(`/api/library/${userId}/catalog`);
  }

  async getLibraryBook(userId: string, bookId: string): Promise<BookContent> {
    return this.request(`/api/library/${userId}/books/${bookId}`);
  }
}

export const api = new ApiClient();
