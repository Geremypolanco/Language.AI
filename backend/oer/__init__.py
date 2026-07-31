"""Open Educational Resources (OER) retrieval pipeline for the Academy.

Grounds Academy course generation in real, citable excerpts instead of
relying purely on the chat model's parametric knowledge: fetch real OER
source documents (sources.py), split them into chunks (chunking.py), embed
the chunks via the HF Inference API (embeddings.py), and store/query them
in a persisted vector store (vectorstore.py). retrieval.py ties those
together into a single "give me grounding context for this course topic"
call that backend/academy.py and hf_client.generate_course_content use.

Populating the store is a deliberately separate, offline step — see
scripts/ingest_oer.py — not something that happens on a user's request.
"""
