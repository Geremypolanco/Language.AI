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
                  description="Algoritmos, estructuras de datos, sistemas y fundamentos de programación.",
                  tutor_name="Iván"),
    AcademicField(id="software-engineering", name="Ingeniería de Software", category="Tecnología", icon="pencil",
                  description="Diseño de software, arquitectura, pruebas y desarrollo de aplicaciones.",
                  tutor_name="Sofía"),
    AcademicField(id="data-science", name="Ciencia de Datos", category="Tecnología", icon="sparkle",
                  description="Estadística, análisis de datos, machine learning y visualización.",
                  tutor_name="Max"),
    AcademicField(id="artificial-intelligence", name="Inteligencia Artificial", category="Tecnología", icon="sparkle",
                  description="Aprendizaje automático, redes neuronales, y ética de la IA.",
                  tutor_name="Nova"),
    AcademicField(id="cybersecurity", name="Ciberseguridad", category="Tecnología", icon="lock",
                  description="Seguridad de redes, criptografía y defensa de sistemas.",
                  tutor_name="Iris"),
    # Negocios
    AcademicField(id="business-administration", name="Administración de Empresas", category="Negocios", icon="trophy",
                  description="Gestión, operaciones, liderazgo y estrategia empresarial.",
                  tutor_name="Carlos"),
    AcademicField(id="accounting", name="Contabilidad", category="Negocios", icon="book",
                  description="Contabilidad financiera, costos, auditoría e impuestos.",
                  tutor_name="Elena"),
    AcademicField(id="marketing", name="Marketing", category="Negocios", icon="sparkle",
                  description="Marketing digital, branding, investigación de mercado y ventas.",
                  tutor_name="Luna"),
    AcademicField(id="finance", name="Finanzas", category="Negocios", icon="gem",
                  description="Finanzas corporativas, inversión, mercados y análisis financiero.",
                  tutor_name="Mateo"),
    AcademicField(id="entrepreneurship", name="Emprendimiento", category="Negocios", icon="flame",
                  description="Creación de startups, modelos de negocio y levantamiento de capital.",
                  tutor_name="Valentina"),
    # Salud (teoría — no clínica ni de licenciatura profesional)
    AcademicField(id="nursing-foundations", name="Fundamentos de Enfermería", category="Salud", icon="heart",
                  description="Anatomía, fisiología y fundamentos teóricos del cuidado de la salud.",
                  tutor_name="Clara"),
    AcademicField(id="nutrition", name="Nutrición", category="Salud", icon="heart",
                  description="Ciencia de la nutrición, dietética y salud alimentaria.",
                  tutor_name="Julia"),
    AcademicField(id="public-health", name="Salud Pública", category="Salud", icon="heart",
                  description="Epidemiología, políticas de salud y salud comunitaria.",
                  tutor_name="Marcos"),
    AcademicField(id="psychology", name="Psicología", category="Salud", icon="chat",
                  description="Psicología del desarrollo, cognitiva, clínica y social.",
                  tutor_name="Renata"),
    # Ciencias
    AcademicField(id="biology", name="Biología", category="Ciencias", icon="sparkle",
                  description="Biología celular, genética, ecología y evolución.",
                  tutor_name="Diego"),
    AcademicField(id="chemistry", name="Química", category="Ciencias", icon="sparkle",
                  description="Química general, orgánica, inorgánica y bioquímica.",
                  tutor_name="Ana"),
    AcademicField(id="physics", name="Física", category="Ciencias", icon="sparkle",
                  description="Mecánica, electromagnetismo, termodinámica y física moderna.",
                  tutor_name="Bruno"),
    AcademicField(id="mathematics", name="Matemáticas", category="Ciencias", icon="pencil",
                  description="Cálculo, álgebra lineal, estadística y matemática discreta.",
                  tutor_name="Leo"),
    AcademicField(id="environmental-science", name="Ciencias Ambientales", category="Ciencias", icon="sparkle",
                  description="Ecología, cambio climático, sostenibilidad y gestión ambiental.",
                  tutor_name="Sara"),
    # Ingeniería
    AcademicField(id="civil-engineering", name="Ingeniería Civil", category="Ingeniería", icon="pencil",
                  description="Estructuras, materiales, construcción e infraestructura.",
                  tutor_name="Hugo"),
    AcademicField(id="mechanical-engineering", name="Ingeniería Mecánica", category="Ingeniería", icon="pencil",
                  description="Termodinámica, mecánica, diseño de máquinas y manufactura.",
                  tutor_name="Tomás"),
    AcademicField(id="electrical-engineering", name="Ingeniería Eléctrica", category="Ingeniería", icon="pencil",
                  description="Circuitos, electrónica, señales y sistemas de potencia.",
                  tutor_name="Nico"),
    # Humanidades y Ciencias Sociales
    AcademicField(id="history", name="Historia", category="Humanidades", icon="book",
                  description="Historia mundial, civilizaciones y pensamiento histórico.",
                  tutor_name="Rodrigo"),
    AcademicField(id="philosophy", name="Filosofía", category="Humanidades", icon="book",
                  description="Ética, lógica, metafísica e historia de la filosofía.",
                  tutor_name="Emilio"),
    AcademicField(id="political-science", name="Ciencias Políticas", category="Humanidades", icon="trophy", description="Sistemas políticos, teoría del estado y relaciones internacionales.", tutor_name="Santi"),
    # Expansión Masiva (30+ Nuevas Áreas)
    AcademicField(id="astrophysics", name="Astrofísica", category="Ciencias", icon="sparkle", description="El cosmos, agujeros negros y la física del universo.", tutor_name="Orion"),
    AcademicField(id="bioengineering", name="Bioingeniería", category="Ingeniería", icon="heart", description="Diseño de sistemas biológicos y medicina regenerativa.", tutor_name="Gaea"),
    AcademicField(id="space-law", name="Derecho Espacial", category="Humanidades", icon="lock", description="Leyes fuera de la Tierra y gobernanza galáctica.", tutor_name="Lex"),
    AcademicField(id="quantum-computing", name="Computación Cuántica", category="Tecnología", icon="sparkle", description="Qubits, entrelazamiento y el futuro del procesamiento.", tutor_name="Nano"),
    AcademicField(id="marine-biology", name="Biología Marina", category="Ciencias", icon="heart", description="Ecosistemas oceánicos y vida en las profundidades.", tutor_name="Marina"),
    AcademicField(id="robotics", name="Robótica", category="Ingeniería", icon="pencil", description="Diseño de autómatas, sensores y control de robots.", tutor_name="Bot"),
    AcademicField(id="neuroscience", name="Neurociencia", category="Salud", icon="sparkle", description="El cerebro humano, sinapsis y comportamiento cognitivo.", tutor_name="Cortex"),
    AcademicField(id="renewable-energy", name="Energías Renovables", category="Ciencias", icon="flame", description="Solar, eólica y el futuro de la energía limpia.", tutor_name="Sol"),
    AcademicField(id="game-design", name="Diseño de Videojuegos", category="Tecnología", icon="trophy", description="Mecánicas, narrativa y arte en el desarrollo de juegos.", tutor_name="Pixel"),
    AcademicField(id="digital-art", name="Arte Digital", category="Artes", icon="sparkle", description="Ilustración, modelado 3D y diseño conceptual.", tutor_name="Muse"),
    AcademicField(id="culinary-arts", name="Artes Culinarias", category="Artes", icon="heart", description="Gastronomía, química de alimentos y alta cocina.", tutor_name="Chef"),
    AcademicField(id="archaeology", name="Arqueología", category="Humanidades", icon="book", description="Historia antigua, excavaciones y civilizaciones perdidas.", tutor_name="Indy"),
    AcademicField(id="linguistics", name="Lingüística", category="Humanidades", icon="chat", description="Estructura del lenguaje, fonética y evolución de idiomas.", tutor_name="Glossa"),
    AcademicField(id="architecture", name="Arquitectura", category="Ingeniería", icon="pencil", description="Diseño de espacios, urbanismo y estructuras sostenibles.", tutor_name="Archi"),
    AcademicField(id="fashion-design", name="Diseño de Modas", category="Artes", icon="sparkle", description="Textiles, tendencias y creación de indumentaria.", tutor_name="Vogue"),
    AcademicField(id="music-theory", name="Teoría Musical", category="Artes", icon="sparkle", description="Composición, armonía y análisis de obras musicales.", tutor_name="Aria"),
    AcademicField(id="theology", name="Teología", category="Humanidades", icon="book", description="Estudio de religiones, textos sagrados y fe.", tutor_name="Theo"),
    AcademicField(id="agronomy", name="Agronomía", category="Ciencias", icon="heart", description="Agricultura moderna, suelos y producción de alimentos.", tutor_name="Gaia"),
    AcademicField(id="genetics", name="Genética", category="Ciencias", icon="sparkle", description="ADN, herencia y biotecnología molecular.", tutor_name="Helix"),
    AcademicField(id="urban-planning", name="Urbanismo", category="Ingeniería", icon="pencil", description="Desarrollo de ciudades inteligentes y transporte.", tutor_name="Metro"),
    AcademicField(id="film-studies", name="Estudios de Cine", category="Artes", icon="sparkle", description="Historia del cine, dirección y análisis fílmico.", tutor_name="Director"),
    AcademicField(id="cryptography", name="Criptografía", category="Tecnología", icon="lock", description="Seguridad de la información y algoritmos de cifrado.", tutor_name="Cipher"),
    AcademicField(id="artificial-life", name="Vida Artificial", category="Tecnología", icon="sparkle", description="Simulación de sistemas vivos y evolución digital.", tutor_name="Synth"),
    AcademicField(id="nanotechnology", name="Nanotecnología", category="Ciencias", icon="sparkle", description="Manipulación de la materia a escala atómica.", tutor_name="Atom"),
    AcademicField(id="climatology", name="Climatología", category="Ciencias", icon="flame", description="Estudio del clima, predicción y cambio climático.", tutor_name="Sky"),
    AcademicField(id="ethnobotany", name="Etnobotánica", category="Ciencias", icon="heart", description="Relación entre humanos y plantas medicinales.", tutor_name="Leaf"),
    AcademicField(id="forensic-science", name="Ciencia Forense", category="Salud", icon="lock", description="Investigación criminal y análisis de evidencias.", tutor_name="Sherlock"),
    AcademicField(id="economics", name="Economía", category="Humanidades", icon="gem",
                  description="Microeconomía, macroeconomía y economía del desarrollo.",
                  tutor_name="Andrés"),
    AcademicField(id="sociology", name="Sociología", category="Humanidades", icon="chat",
                  description="Estructuras sociales, cultura, desigualdad e instituciones.",
                  tutor_name="Paula"),
    AcademicField(id="international-relations", name="Relaciones Internacionales", category="Humanidades", icon="wave",
                  description="Diplomacia, política exterior y organismos internacionales.",
                  tutor_name="Gabriel"),
    # Artes y Comunicación
    AcademicField(id="graphic-design", name="Diseño Gráfico", category="Artes", icon="image",
                  description="Teoría del color, tipografía, composición y diseño digital.",
                  tutor_name="Mía"),
    AcademicField(id="journalism", name="Comunicación y Periodismo", category="Artes", icon="chat",
                  description="Redacción periodística, medios digitales y ética de la comunicación.",
                  tutor_name="Lucas"),
    AcademicField(id="music", name="Música", category="Artes", icon="volume",
                  description="Teoría musical, armonía, composición e historia de la música.",
                  tutor_name="Isabela"),
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
        f"Order the courses from foundational to advanced, so difficulty builds gradually across the "
        f"{course_count} courses rather than jumping straight to advanced material. "
        f"Write each one-sentence description in plain, clear language a curious 7-year-old could follow, "
        f"even though the course title itself keeps the real, correct academic name. "
        f"Respond with ONLY a JSON array, no other text, each item shaped like: "
        f'{{"title": "course title in {native_lang}", "description": "one sentence, in {native_lang}, on what it covers"}}'
    )


def build_course_prompt(field: AcademicField, level_label: str, course_title: str, course_description: str, native_lang: str) -> str:
    return (
        f"Write ELITE self-study course material in {native_lang} for the course \"{course_title}\" "
        f"({course_description}), part of an accelerated, self-paced {field.name} curriculum at a "
        f"{level_label} depth. Structure it as 4 to 6 modules. Each module should teach real, accurate, "
        f"standard content for this topic — the kind of material an actual textbook or course would "
        f"cover, using the correct professional/technical terms this field actually uses — with clear "
        f"explanations and at least one concrete example per module. "
        f"If a concept is complex, include a Mermaid.js diagram in the content using the format [DIAGRAM: graph TD...]. "
        f"Explain each term the first time it appears clearly enough that a curious 7-year-old could follow the explanation, "
        f"even though the terminology itself stays accurate and professional — simplify the explanation, never the vocabulary. "
        f"Respond with ONLY a JSON array, no other text, each item shaped like: "
        f'{{"title": "module title", "content": "the module\'s full teaching content, several paragraphs with diagrams if helpful"}}'
    )

def build_mission_prompt(target_lang: str, level_label: str, scenario_type: str) -> str:
    return (
        f"Create an immersive, high-stakes language mission in {target_lang} for a {level_label} learner. "
        f"Scenario: {scenario_type}. "
        f"The mission should have a clear goal (e.g., 'Convince the border officer to let you in'). "
        f"Provide a brief setup, the persona of the AI (the officer, the doctor, etc.), and the success criteria. "
        f"Respond with ONLY a JSON object: "
        f'{{"title": "mission title", "setup": "...", "goal": "...", "ai_persona": "...", "success_criteria": "..."}}'
    )


def build_practice_scenario_prompt(
    field: AcademicField, level_label: str, course_title: str, course_description: str, native_lang: str
) -> str:
    return (
        f"Write a short, realistic hands-on practice scenario in {native_lang} for a student studying "
        f"\"{course_title}\" ({course_description}) in {field.name}, at a {level_label} depth. "
        f"Describe a concrete situation the student must respond to — e.g. a case to analyze, a problem "
        f"to solve, a decision to make — appropriate for this field (a clinical-style case for health "
        f"fields, a design/debugging problem for engineering or computer science, a business case for "
        f"business fields, a text/argument to analyze for humanities, etc). End with a direct question "
        f"asking what the student would do. 2 to 4 short paragraphs. Write it in plain, clear language "
        f"a curious 7-year-old could follow, keeping any necessary technical terms but explaining them "
        f"the first time they appear. Output ONLY the scenario text."
    )


def build_assignments_prompt(
    field: AcademicField, level_label: str, course_title: str, course_description: str, native_lang: str
) -> str:
    return (
        f"Design 3 pieces of real, gradeable schoolwork in {native_lang} for the course \"{course_title}\" "
        f"({course_description}), part of a {field.name} curriculum at a {level_label} depth — the same "
        f"kind of assigned work a normal school or university course would give: exactly one short "
        f"homework task (\"tarea\"), one written report (\"informe\"), and one small project (\"proyecto\"), "
        f"each appropriately scoped for self-study (a report or project a self-paced learner can realistically "
        f"finish in one sitting, not a semester-long undertaking). "
        f"Write instructions clear enough for a curious 7-year-old to follow, using the correct "
        f"professional/technical vocabulary this field actually uses — simplify the explanation, never the "
        f"terminology. Each item's instructions must say exactly what to submit (e.g. word count, what "
        f"questions to answer, what the project should include). "
        f"Respond with ONLY a JSON array of exactly 3 items, no other text, each shaped like: "
        f'{{"type": "tarea|informe|proyecto", "title": "short title", "instructions": "what the student must do and submit"}}'
    )
