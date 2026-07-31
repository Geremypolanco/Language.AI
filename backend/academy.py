"""University-prep academy: a self-paced, accelerated study layer covering
common academic fields, on top of the same "generate on demand and cache"
architecture the language curriculum and book library already use.

Two things are intentionally NOT here: (1) a live web-search integration —
the HF chat model itself was trained on a huge amount of public information
about standard curricula, and is instructed (see build_curriculum_prompt /
build_course_prompt) to draw only on well-established, real course sequences
and topics for the field, the same "ground the generation, don't invent
implausible facts" approach already used for book/song recommendations;
(2) any claim of accreditation — this app is explicitly NOT a university and
issues no real degree, credit, or certificate. Every enrollment and every
screen that shows academic content must carry that disclaimer; a learner who
wants the actual credential still has to enroll at an accredited institution.
"""

from __future__ import annotations

from .models import AcademicField

_FIELDS: list[AcademicField] = [
    # Tecnología
    AcademicField(id="computer-science", name="Ciencia de la Computación", category="Tecnología", icon="pencil",
                  description="Algoritmos, estructuras de datos, sistemas y fundamentos de programación."),
    AcademicField(id="software-engineering", name="Ingeniería de Software", category="Tecnología", icon="pencil",
                  description="Diseño de software, arquitectura, pruebas y desarrollo de aplicaciones."),
    AcademicField(id="data-science", name="Ciencia de Datos", category="Tecnología", icon="sparkle",
                  description="Estadística, análisis de datos, machine learning y visualización."),
    AcademicField(id="artificial-intelligence", name="Inteligencia Artificial", category="Tecnología", icon="sparkle",
                  description="Aprendizaje automático, redes neuronales, y ética de la IA."),
    AcademicField(id="cybersecurity", name="Ciberseguridad", category="Tecnología", icon="lock",
                  description="Seguridad de redes, criptografía y defensa de sistemas."),
    # Negocios
    AcademicField(id="business-administration", name="Administración de Empresas", category="Negocios", icon="trophy",
                  description="Gestión, operaciones, liderazgo y estrategia empresarial."),
    AcademicField(id="accounting", name="Contabilidad", category="Negocios", icon="book",
                  description="Contabilidad financiera, costos, auditoría e impuestos."),
    AcademicField(id="marketing", name="Marketing", category="Negocios", icon="sparkle",
                  description="Marketing digital, branding, investigación de mercado y ventas."),
    AcademicField(id="finance", name="Finanzas", category="Negocios", icon="gem",
                  description="Finanzas corporativas, inversión, mercados y análisis financiero."),
    AcademicField(id="entrepreneurship", name="Emprendimiento", category="Negocios", icon="flame",
                  description="Creación de startups, modelos de negocio y levantamiento de capital."),
    # Salud (teoría — no clínica ni de licenciatura profesional)
    AcademicField(id="nursing-foundations", name="Fundamentos de Enfermería", category="Salud", icon="heart",
                  description="Anatomía, fisiología y fundamentos teóricos del cuidado de la salud."),
    AcademicField(id="nutrition", name="Nutrición", category="Salud", icon="heart",
                  description="Ciencia de la nutrición, dietética y salud alimentaria."),
    AcademicField(id="public-health", name="Salud Pública", category="Salud", icon="heart",
                  description="Epidemiología, políticas de salud y salud comunitaria."),
    AcademicField(id="psychology", name="Psicología", category="Salud", icon="chat",
                  description="Psicología del desarrollo, cognitiva, clínica y social."),
    # Ciencias
    AcademicField(id="biology", name="Biología", category="Ciencias", icon="sparkle",
                  description="Biología celular, genética, ecología y evolución."),
    AcademicField(id="chemistry", name="Química", category="Ciencias", icon="sparkle",
                  description="Química general, orgánica, inorgánica y bioquímica."),
    AcademicField(id="physics", name="Física", category="Ciencias", icon="sparkle",
                  description="Mecánica, electromagnetismo, termodinámica y física moderna."),
    AcademicField(id="mathematics", name="Matemáticas", category="Ciencias", icon="pencil",
                  description="Cálculo, álgebra lineal, estadística y matemática discreta."),
    AcademicField(id="environmental-science", name="Ciencias Ambientales", category="Ciencias", icon="sparkle",
                  description="Ecología, cambio climático, sostenibilidad y gestión ambiental."),
    # Ingeniería
    AcademicField(id="civil-engineering", name="Ingeniería Civil", category="Ingeniería", icon="pencil",
                  description="Estructuras, materiales, construcción e infraestructura."),
    AcademicField(id="mechanical-engineering", name="Ingeniería Mecánica", category="Ingeniería", icon="pencil",
                  description="Termodinámica, mecánica, diseño de máquinas y manufactura."),
    AcademicField(id="electrical-engineering", name="Ingeniería Eléctrica", category="Ingeniería", icon="pencil",
                  description="Circuitos, electrónica, señales y sistemas de potencia."),
    # Humanidades y Ciencias Sociales
    AcademicField(id="history", name="Historia", category="Humanidades", icon="book",
                  description="Historia mundial, civilizaciones y pensamiento histórico."),
    AcademicField(id="philosophy", name="Filosofía", category="Humanidades", icon="book",
                  description="Ética, lógica, metafísica e historia de la filosofía."),
    AcademicField(id="political-science", name="Ciencias Políticas", category="Humanidades", icon="trophy",
                  description="Teoría política, gobierno, políticas públicas y relaciones de poder."),
    AcademicField(id="economics", name="Economía", category="Humanidades", icon="gem",
                  description="Microeconomía, macroeconomía y economía del desarrollo."),
    AcademicField(id="sociology", name="Sociología", category="Humanidades", icon="chat",
                  description="Estructuras sociales, cultura, desigualdad e instituciones."),
    AcademicField(id="international-relations", name="Relaciones Internacionales", category="Humanidades", icon="wave",
                  description="Diplomacia, política exterior y organismos internacionales."),
    # Artes y Comunicación
    AcademicField(id="graphic-design", name="Diseño Gráfico", category="Artes", icon="image",
                  description="Teoría del color, tipografía, composición y diseño digital."),
    AcademicField(id="journalism", name="Comunicación y Periodismo", category="Artes", icon="chat",
                  description="Redacción periodística, medios digitales y ética de la comunicación."),
    AcademicField(id="music", name="Música", category="Artes", icon="volume",
                  description="Teoría musical, armonía, composición e historia de la música."),
]

CATEGORIES: list[str] = sorted({f.category for f in _FIELDS})


def all_fields() -> list[AcademicField]:
    return _FIELDS


def get_field(field_id: str) -> AcademicField | None:
    return next((f for f in _FIELDS if f.id == field_id), None)


def build_curriculum_prompt(field: AcademicField, level_label: str, course_count: int, native_lang: str) -> str:
    return (
        f"Design a {course_count}-course study curriculum for the academic field \"{field.name}\" "
        f"({field.description}), at a depth roughly equivalent to a {level_label} program. "
        f"Base it on real, standard, well-established course sequences universities actually use for "
        f"this field — do not invent implausible or fictional course topics. "
        f"Order the courses from foundational to advanced. "
        f"Respond with ONLY a JSON array, no other text, each item shaped like: "
        f'{{"title": "course title in {native_lang}", "description": "one sentence, in {native_lang}, on what it covers"}}'
    )


def build_course_prompt(field: AcademicField, level_label: str, course_title: str, course_description: str, native_lang: str) -> str:
    return (
        f"Write self-study course material in {native_lang} for the course \"{course_title}\" "
        f"({course_description}), part of an accelerated, self-paced {field.name} curriculum at a "
        f"{level_label} depth. Structure it as 4 to 6 modules. Each module should teach real, accurate, "
        f"standard content for this topic — the kind of material an actual textbook or course would "
        f"cover — with clear explanations and at least one concrete example per module. "
        f"Respond with ONLY a JSON array, no other text, each item shaped like: "
        f'{{"title": "module title", "content": "the module\'s full teaching content, several paragraphs"}}'
    )
