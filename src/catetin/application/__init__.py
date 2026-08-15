"""Application use cases — the only layer allowed to mutate transactions.

Every use case here depends on `domain/` models and `domain/ports/`
protocols only, never on SQLAlchemy, `python-telegram-bot`, or `fpdf2`. The
composition root wires concrete adapters into these constructors.
"""
