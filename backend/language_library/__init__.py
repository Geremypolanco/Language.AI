"""Pre-generated language-lesson library — the same "build once, serve
forever, no AI at study time" architecture as backend/academy_library/,
applied to backend/curriculum.py's unit-based exercise content.

Core principle this module exists to enforce: content belongs to the
course, not the user. build.py always generates with interests=[] and
recent_mistakes=[] (see generators.py's docstring) so every student who
studies a given (target_lang, native_lang, unit) gets byte-identical
content — the previous on-demand path personalized on interests, which
meant a "shared" cache entry was actually fragmented per interest set.

Genuinely dynamic and NOT moved into this pre-generated model (matches
the request's own "qué sí es dinámico" list): free-form practice mode
(routers/lessons.py's get_practice_exercises, which deliberately weaves in
a learner's own recent_mistakes and lets them pick modality live), the
live conversation tutor, pronunciation/writing correction, and
recommendations — all of those are personalization layers on top of this
shared content, not this content itself.

Deliberately NOT generated here: a verified IPA phonetic transcription per
flashcard (see generators.build_flashcards's docstring for why fabricating
one would be actively misleading), image galleries beyond the single
per-word image already generated/cached elsewhere, and a separate
dialogues content type (free_conversation_prompt exercises already cover
that role). See build.py and generators.py for the rest of the scoping
reasoning.
"""
