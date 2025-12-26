"""
SM-2 Spaced Repetition Algorithm

Quality ratings:
0 - Complete blackout, didn't recognize the word
1 - Incorrect, but upon seeing answer, remembered
2 - Incorrect, but answer seemed easy to recall
3 - Correct with serious difficulty
4 - Correct after hesitation
5 - Perfect response
"""

from datetime import datetime, timedelta
from models import CardDB


def calculate_sm2(card: CardDB, quality: int) -> CardDB:
    """
    Apply SM-2 algorithm to update card's spaced repetition fields.
    
    Args:
        card: The flashcard to update
        quality: Response quality (0-5)
    
    Returns:
        Updated card with new scheduling
    """
    # Clamp quality to valid range
    quality = max(0, min(5, quality))
    
    # Update ease factor
    # EF' = EF + (0.1 - (5 - q) * (0.08 + (5 - q) * 0.02))
    card.ease_factor = max(
        1.3,  # Minimum EF
        card.ease_factor + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
    )
    
    if quality < 3:
        # Failed - reset repetitions, review again soon
        card.repetitions = 0
        card.interval = 1  # Review tomorrow
    else:
        # Success - increase interval
        if card.repetitions == 0:
            card.interval = 1
        elif card.repetitions == 1:
            card.interval = 6
        else:
            card.interval = round(card.interval * card.ease_factor)
        
        card.repetitions += 1
    
    # Set next review date
    card.next_review = datetime.utcnow() + timedelta(days=card.interval)
    
    return card


def get_due_cards(session, limit: int = 20) -> list[CardDB]:
    """Get cards that are due for review."""
    now = datetime.utcnow()
    return (
        session.query(CardDB)
        .filter(CardDB.next_review <= now)
        .order_by(CardDB.next_review)
        .limit(limit)
        .all()
    )


def get_new_cards(session, limit: int = 10) -> list[CardDB]:
    """Get cards that have never been reviewed."""
    return (
        session.query(CardDB)
        .filter(CardDB.repetitions == 0)
        .order_by(CardDB.created_at)
        .limit(limit)
        .all()
    )
