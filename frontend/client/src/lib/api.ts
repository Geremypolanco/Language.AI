/**
 * API Client - Conecta con el backend Language.AI
 * Todos los endpoints requieren credentials: "include" para enviar cookies de sesión
 */

export interface ApiError {
  detail?: string;
  message?: string;
}

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
  level?: number;
}

export interface User {
  id: string;
  display_name: string;
  native_lang: string;
  target_lang: string;
  level: number;
  interests: string[];
  daily_goal_minutes: number;
}

export interface Lesson {
  id: string;
  title: string;
  description: string;
  level: "beginner" | "intermediate" | "advanced";
  duration: number;
  completed: boolean;
  xp: number;
}

export interface ProgressData {
  level: number;
  total_xp: number;
  days_learned: number;
  streak: number;
  weekly_activity: { day: string; minutes: number }[];
  skills: { skill: string; progress: number }[];
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
      throw new Error(error.detail || error.message || `HTTP ${response.status}`);
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
    level: number;
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

  async getLesson(userId: string, unitId: string) {
    return this.request(`/api/lessons/${userId}/unit/${unitId}`);
  }

  async submitLessonAnswer(userId: string, data: any) {
    return this.request(`/api/lessons/${userId}/answer`, {
      method: "POST",
      body: JSON.stringify(data),
    });
  }

  async completeLesson(userId: string, lessonId: string) {
    return this.request(`/api/lessons/${userId}/complete`, {
      method: "POST",
      body: JSON.stringify({ lesson_id: lessonId }),
    });
  }

  async practiceLessonSkill(userId: string, data: any) {
    return this.request(`/api/lessons/${userId}/practice`, {
      method: "POST",
      body: JSON.stringify(data),
    });
  }

  // ===== ACADEMY (University) =====
  async getAcademyFields() {
    return this.request("/api/academy/fields");
  }

  async enrollAcademyCareer(userId: string, fieldId: string, level: string) {
    return this.request(`/api/academy/${userId}/enroll`, {
      method: "POST",
      body: JSON.stringify({ field_id: fieldId, level }),
    });
  }

  async getAcademyProgress(userId: string) {
    return this.request(`/api/academy/${userId}/progress`);
  }

  async getAcademyCurriculum(userId: string) {
    return this.request(`/api/academy/${userId}/curriculum`);
  }

  async getAcademyCourse(userId: string, courseId: string) {
    return this.request(`/api/academy/${userId}/courses/${courseId}`);
  }

  // ===== PROGRESS =====
  async getProgressSnapshot(userId: string): Promise<ProgressData> {
    return this.request<ProgressData>(`/api/progress/${userId}`);
  }

  async getProgressDashboard(userId: string) {
    return this.request(`/api/progress/${userId}/dashboard`);
  }

  // ===== TALK (WebSocket) =====
  connectConversation(userId: string): WebSocket {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    return new WebSocket(`${protocol}//${window.location.host}/ws/conversation/${userId}`);
  }

  // ===== LIBRARY =====
  async getLibraryGenres() {
    return this.request("/api/library/genres");
  }

  async getLibraryCatalog(userId: string) {
    return this.request(`/api/library/${userId}/catalog`);
  }

  async getLibraryBook(userId: string, bookId: string) {
    return this.request(`/api/library/${userId}/books/${bookId}`);
  }
}

export const api = new ApiClient();
