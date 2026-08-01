# Lingua AI — The Professional Language Learning Experience

Lingua is a high-performance, mobile-first language learning application that leverages advanced AI to provide a truly immersive experience. This repository has been transformed from a generic prototype into a **professional-grade product** with authentic human interaction and context-aware intelligence.

## 🌟 Key Innovations

### 🎭 Authentic Human Presence
- **Real Tutor Avatars**: Friendly, professional human faces instead of generic mascots.
- **Dynamic Response Animations**: Tutors react visually to your speech, creating a genuine "live call" feel.
- **Low-Latency Voice Engine**: Seamless WebSocket-based conversation with high-quality streaming audio.

### 📱 Mobile-First Design (UX/UI)
- **Thumb-Optimized Navigation**: A bottom navigation bar designed for effortless one-handed use.
- **Integrated "Talk" Hub**: A central, accessible hub for instant voice practice.
- **Premium Visual Language**: Emerald & Teal professional color palette with full Dark Mode support.

### 📺 Contextual Multimedia Learning
- **YouTube Smart Integration**: Automatically embeds relevant educational videos based on your current lesson topic.
- **Google Images Visual Aids**: Dynamic image galleries that reinforce vocabulary through real-world visual context.
- **AI-Powered Library**: 500+ books with custom-generated covers that match the story's genre and theme.

### 🎓 Lingua Academy
- **Specialized Career Tracks**: Study Software Engineering, Business, or Health in your target language.
- **Domain-Specific Tutors**: Each field features a specialized AI mentor with a unique visual identity.

## 🛠️ Technical Architecture

- **Backend**: FastAPI (Python 3.11) + WebSocket streaming.
- **Frontend**: High-performance Vanilla JS (ES6+) with zero-dependency architecture.
- **Visuals**: Dynamic discovery via YouTube/Google APIs with AI fallback.
- **Voice**: Hybrid architecture using self-hosted Piper TTS and Hugging Face MMS.

## 📁 Repository Structure

```text
.
├── backend/            # FastAPI Backend (Routers, AI, Search Logic)
├── frontend/           # Mobile-first Web App (HTML, CSS, JS)
├── public/             # Branding, Professional Avatars, and Hero Assets
├── tests/              # Full API and Logic Test Suite
└── requirements.txt    # Python Dependencies
```

## 🏁 Getting Started

1. **Clone**: `gh repo clone Geremypolanco/Language.AI`
2. **Install**: `pip install -r requirements.txt`
3. **Configure**: Set `GOOGLE_CSE_API_KEY` for enhanced image search (optional).
4. **Launch**: `python -m backend.main`

---
*Lingua — Speak like a native, learn with a professional.*
