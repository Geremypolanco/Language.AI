# Language.AI - Funcionalidades Faltantes

> **Nota (auditoría de dependencias, 2026-08):** este documento describe un
> estado muy temprano del prototipo. Ya no es exacto: la app actual sí tiene
> OAuth de Google real (`backend/routers/auth.py`), persistencia real
> (`backend/db.py`, SQLite local o Supabase Postgres), endpoints reales (no
> mock), grabación/transcripción de audio funcional (`backend/routers/
> conversation.py`) y generación de contenido con IA vía Groq/Pollinations/
> Hugging Face (`backend/hf_client.py`), con 302 tests pasando en CI. Se deja
> el documento como referencia histórica de planificación, no como estado
> actual.

## 🔴 CRÍTICAS (Bloquean uso)

### 1. **Autenticación Real No Funciona**
- ❌ Google OAuth sin implementar en backend
- ❌ `/auth/google/login` no existe
- ❌ `/auth/google/callback` no existe
- ❌ Cookie "pending" no se crea
- ❌ Onboarding no guarda datos en BD

**Impacto:** Usuario no puede loguear → app no funciona

---

### 2. **Base de Datos No Conectada**
- ❌ Usuarios no se guardan
- ❌ Lecciones no se persisten
- ❌ Progreso no se registra
- ❌ Historias no se almacenan

**Impacto:** Todos los datos se pierden al recargar

---

### 3. **Endpoints Backend No Implementados**
- ❌ `GET /api/lessons/{user_id}/path` - Devuelve mock data
- ❌ `GET /api/academy/fields` - Devuelve mock data
- ❌ `GET /api/progress/{user_id}` - Devuelve mock data
- ❌ `GET /api/library/{user_id}/catalog` - Devuelve mock data
- ❌ `WS /ws/conversation/{user_id}` - No existe

**Impacto:** Frontend muestra datos fake, no reales

---

### 4. **Modelos AI No Integrados**
- ❌ Ollama no está corriendo
- ❌ `/api/ai/feedback` no funciona
- ❌ `/api/ai/explain` no funciona
- ❌ `/api/ai/transcribe` no funciona
- ❌ `/api/ai/speak` no funciona

**Impacto:** Componentes AIFeedback, AITutor, PronunciationAnalyzer son shells vacíos

---

## 🟡 IMPORTANTES (Degradan experiencia)

### 5. **Componentes UI Incompletos**
- ❌ DashboardLayout sin sidebar funcional
- ❌ Navegación entre páginas no funciona bien
- ❌ Botones "Start", "Enroll", "Read Story" no hacen nada
- ❌ Filtros en Library no funcionan
- ❌ Tabs en University no cambian contenido

**Impacto:** UX confusa, usuario no sabe qué hacer

---

### 6. **Funcionalidad de Grabación de Audio**
- ❌ Botón "🎤 Hold to Record" no graba
- ❌ No hay acceso a micrófono del navegador
- ❌ No hay visualización de waveform
- ❌ No hay envío de audio a Whisper

**Impacto:** Talk page no funciona

---

### 7. **Generación de Contenido**
- ❌ Historias no se generan (Library vacía)
- ❌ Lecciones no se generan dinámicamente
- ❌ Imágenes de lecciones no se generan
- ❌ Ejercicios no se adaptan al nivel

**Impacto:** Content es estático, no personalizado

---

### 8. **Evaluación y Feedback**
- ❌ Respuestas no se evalúan
- ❌ Puntuaciones no se calculan
- ❌ XP no se otorga
- ❌ Progreso no avanza

**Impacto:** Sistema de gamificación no funciona

---

### 9. **Recomendaciones Personalizadas**
- ❌ No hay búsqueda semántica
- ❌ No hay recomendaciones basadas en intereses
- ❌ No hay sugerencias de próxima lección
- ❌ No hay análisis predictivo

**Impacto:** Experiencia no es personalizada

---

### 10. **Estadísticas y Analytics**
- ❌ Gráficos de progreso son mock
- ❌ Heatmap de habilidades no es real
- ❌ Streak no se calcula
- ❌ XP total no se suma

**Impacto:** Progress page muestra datos falsos

---

## 🟠 MEJORAS (Nice-to-have)

### 11. **Gamificación Avanzada**
- ❌ Sistema de logros/badges
- ❌ Leaderboards
- ❌ Challenges semanales
- ❌ Rewards/Puntos canjeables

---

### 12. **Social Features**
- ❌ Compartir progreso
- ❌ Estudiar con amigos
- ❌ Comentarios en historias
- ❌ Competencias

---

### 13. **Personalización**
- ❌ Temas (dark/light)
- ❌ Preferencias de idioma
- ❌ Configuración de notificaciones
- ❌ Perfil de usuario editable

---

### 14. **Integración Externa**
- ❌ Exportar progreso a PDF
- ❌ Sincronizar con Google Calendar
- ❌ Integración con Duolingo
- ❌ API pública para terceros

---

### 15. **Mobile Responsiveness**
- ⚠️ Parcialmente responsive
- ❌ Optimización para mobile
- ❌ App nativa (iOS/Android)
- ❌ Offline mode

---

## 📊 RESUMEN POR PRIORIDAD

| Prioridad | Cantidad | Impacto |
|-----------|----------|---------|
| 🔴 Crítica | 4 | App no funciona |
| 🟡 Importante | 6 | Experiencia degradada |
| 🟠 Mejora | 5 | Funcionalidad extra |
| **TOTAL** | **15** | **Aplicación incompleta** |

---

## 🚦 ROADMAP DE IMPLEMENTACIÓN

### Fase 1: Core Functionality (1-2 semanas)
1. ✅ Autenticación real (Google OAuth)
2. ✅ Base de datos (SQLite/PostgreSQL)
3. ✅ Endpoints backend reales
4. ✅ Modelos AI funcionando

### Fase 2: Features (1-2 semanas)
5. ✅ Grabación de audio
6. ✅ Generación de contenido
7. ✅ Evaluación y feedback
8. ✅ Recomendaciones

### Fase 3: Polish (1 semana)
9. ✅ UI/UX completa
10. ✅ Analytics real
11. ✅ Gamificación
12. ✅ Mobile responsive

### Fase 4: Extras (Ongoing)
13. ✅ Social features
14. ✅ Integraciones
15. ✅ Optimizaciones

---

## 🎯 ESTADO ACTUAL

**Frontend:** 70% - UI bonita pero sin funcionalidad
**Backend:** 30% - Estructura lista, endpoints mock
**AI:** 20% - Servicios creados, no conectados
**Base de Datos:** 0% - No existe
**Autenticación:** 0% - No funciona

**Conclusión:** La app es un prototipo visual. Necesita backend real para funcionar.

---

## 💡 RECOMENDACIÓN

Para que Language.AI sea funcional, necesitas:

1. **Backend real** (2-3 días)
   - Implementar autenticación OAuth
   - Crear BD con esquema de usuarios/lecciones
   - Implementar endpoints reales

2. **AI conectado** (2-3 días)
   - Setup Ollama local
   - Conectar Whisper
   - Conectar TTS

3. **Frontend conectado** (1-2 días)
   - Cambiar mock data por API calls
   - Implementar grabación de audio
   - Conectar componentes AI

4. **Testing** (1 día)
   - Flujo completo: login → lección → feedback
   - Pruebas de audio
   - Pruebas de AI

**Tiempo total:** ~1 semana para MVP funcional

---

## 📝 PRÓXIMOS PASOS

¿Quieres que implemente:
1. Autenticación OAuth real?
2. Base de datos con schema?
3. Endpoints backend reales?
4. Integración de Ollama?
5. Grabación de audio en Talk?
6. Todo lo anterior?
