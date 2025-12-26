"""
FastAPI backend for the Duocards flashcard app.
Integrates copilot.py (GPT-4.1) and forvo.py (TTS).
"""

import os
from datetime import datetime
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.orm import Session

from models import (
    CardDB, CardCreate, CardResponse, CardDetailResponse, ReviewRequest, ReviewHistory,
    GenerateRequest, GenerateResponse,
    get_engine, init_db, get_session
)
from spaced_rep import calculate_sm2, get_due_cards, get_new_cards
from copilot import CopilotClient
from forvo import load_word as forvo_load_word
from pydantic import BaseModel
# Database setup
DB_PATH = Path(__file__).parent / "flashcards.db"
engine = get_engine(str(DB_PATH))


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize database
    init_db(engine)
    print(f"✓ Database initialized at {DB_PATH}")
    yield
    # Shutdown: cleanup if needed


app = FastAPI(
    title="Duocards Flashcard API",
    description="Flashcard app with AI generation and spaced repetition",
    version="1.0.0",
    lifespan=lifespan,
)

# Serve frontend static files
FRONTEND_DIR = Path(__file__).parent / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


# Dependency to get DB session
def get_db():
    session = get_session(engine)
    try:
        yield session
    finally:
        session.close()


# Initialize Copilot client (lazy loaded)
_copilot_client = None

def get_copilot():
    global _copilot_client
    if _copilot_client is None:
        _copilot_client = CopilotClient()
    return _copilot_client


# --- Routes ---

@app.get("/")
async def root():
    """Serve the frontend."""
    index_path = FRONTEND_DIR / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return {"message": "Duocards API - Frontend not found. Visit /docs for API."}


@app.get("/api/cards", response_model=list[CardResponse])
async def list_cards(db: Session = Depends(get_db)):
    """List all flashcards."""
    cards = db.query(CardDB).order_by(CardDB.created_at.desc()).all()
    return cards


@app.post("/api/cards", response_model=CardResponse)
async def create_card(card: CardCreate, db: Session = Depends(get_db)):
    """Create a new flashcard."""
    db_card = CardDB(
        word=card.word,
        translation=card.translation,
        grammar=card.grammar,
        example=card.example,
        audio_url=card.audio_url,
    )
    db.add(db_card)
    db.commit()
    db.refresh(db_card)
    return db_card


@app.get("/api/cards/{card_id}", response_model=CardResponse)
async def get_card(card_id: int, db: Session = Depends(get_db)):
    """Get a specific card by ID."""
    card = db.query(CardDB).filter(CardDB.id == card_id).first()
    if not card:
        raise HTTPException(status_code=404, detail="Card not found")
    return card


@app.get("/api/cards/{card_id}/details", response_model=CardDetailResponse)
async def get_card_details(card_id: int, db: Session = Depends(get_db)):
    """Get a specific card with full details and history."""
    card = db.query(CardDB).filter(CardDB.id == card_id).first()
    if not card:
        raise HTTPException(status_code=404, detail="Card not found")
    return card


@app.delete("/api/cards/{card_id}")
async def delete_card(card_id: int, db: Session = Depends(get_db)):
    """Delete a card."""
    card = db.query(CardDB).filter(CardDB.id == card_id).first()
    if not card:
        raise HTTPException(status_code=404, detail="Card not found")
    db.delete(card)
    db.commit()
    return {"message": "Card deleted"}


@app.get("/api/review", response_model=list[CardResponse])
async def get_review_cards(limit: int = 20, db: Session = Depends(get_db)):
    """Get cards due for review (combines due + new cards)."""
    due = get_due_cards(db, limit=limit)
    
    # If not enough due cards, add some new cards
    if len(due) < limit:
        remaining = limit - len(due)
        new = get_new_cards(db, limit=remaining)
        due.extend(new)
    
    return due


@app.post("/api/review/{card_id}", response_model=CardResponse)
async def review_card(card_id: int, review: ReviewRequest, db: Session = Depends(get_db)):
    """Submit a review result for a card."""
    card = db.query(CardDB).filter(CardDB.id == card_id).first()
    if not card:
        raise HTTPException(status_code=404, detail="Card not found")
    
    # Apply SM-2 algorithm
    card = calculate_sm2(card, review.quality)
    
    # Record history
    history = ReviewHistory(
        card_id=card.id,
        quality=review.quality
    )
    db.add(history)
    
    db.commit()
    db.refresh(card)
    
    return card


@app.post("/api/generate", response_model=GenerateResponse)
async def generate_card(request: GenerateRequest):
    """Generate flashcard content using GPT-4.1 via Copilot with dictionary-style content."""
    copilot = get_copilot()
    
    prompt = f"""Du bist ein Sprachlehrer für {request.source_lang}. Erstelle einen detaillierten Wörterbucheintrag für das Wort.

Wort: {request.word}
Übersetzung nach: {request.target_lang}

Erstelle:
1. Übersetzung ins {request.target_lang}
2. Bedeutung/Definition: Kurze Erklärung, was das Wort bedeutet (2-3 Sätze auf Deutsch)
3. Grammatik: Detaillierte Grammatikinfo im Wörterbuchstil:
   - Für Substantive: Genus (m/f/n), alle 6 Fälle (Nominativ, Genitiv, Dativ, Akkusativ, Lokativ, Instrumental) im Singular und Plural
   - Für Verben: Infinitiv, 1./2./3. Person Singular Präsens, Perfekt
   - Für Adjektive: Grundform, Steigerung (Komparativ, Superlativ)
4. Drei verschiedene Beispielsätze auf {request.source_lang}
5. Synonyme: 2-3 ähnliche Wörter auf {request.source_lang} mit deutscher Übersetzung
6. Verwendung: Wann/Wie man dieses Wort typisch verwendet (auf Deutsch)

Antworte NUR mit diesem JSON (keine anderen Texte):
{{
    "translation": "deutsche Übersetzung",
    "meaning": "Bedeutung und Definition auf Deutsch",
    "grammar": "Genus: m|f|n\\nSingular: Nom: X, Gen: X, Dat: X, Akk: X\\nPlural: Nom: X, Gen: X, Dat: X, Akk: X",
    "examples": [
        "Erster Beispielsatz auf {request.source_lang}",
        "Zweiter Beispielsatz auf {request.source_lang}",
        "Dritter Beispielsatz auf {request.source_lang}"
    ],
    "synonyms": [
        {{"word": "synonym1", "translation": "Übersetzung1"}},
        {{"word": "synonym2", "translation": "Übersetzung2"}}
    ],
    "usage": "Erklärung, wann und wie das Wort verwendet wird"
}}"""

    try:
        response = copilot.chat(message=prompt, model="gpt-4.1")
        content = response.get("content", "")
        
        # Parse JSON from response
        import json
        start = content.find("{")
        end = content.rfind("}") + 1
        if start >= 0 and end > start:
            data = json.loads(content[start:end])
            return GenerateResponse(
                word=request.word,
                translation=data.get("translation", ""),
                grammar=data.get("grammar", ""),
                examples=data.get("examples", []),
                synonyms=data.get("synonyms", []),
                usage=data.get("usage", ""),
                meaning=data.get("meaning", ""),
            )
        else:
            raise HTTPException(status_code=500, detail="Could not parse AI response")
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=500, detail=f"JSON parse error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Generation failed: {str(e)}")


# Audio cache directory
AUDIO_CACHE_DIR = Path(__file__).parent / "audio_cache"
AUDIO_CACHE_DIR.mkdir(exist_ok=True)


class GenerateFromGermanRequest(BaseModel):
    """Request to generate card from German word."""
    german_word: str
    source_lang: str = "Deutsch"
    target_lang: str = "Slowenisch"


class TranslateRequest(BaseModel):
    """Request for quick translation of selected text."""
    text: str
    auto_detect: bool = True


class TranslateResponse(BaseModel):
    """Response with translation."""
    text: str
    translation: str
    detected_lang: str  # "sl" or "de"


@app.post("/api/translate", response_model=TranslateResponse)
async def translate_text(request: TranslateRequest):
    """Quick translation for selected text - auto-detects language and translates."""
    copilot = get_copilot()
    
    # Simple language detection prompt
    detect_prompt = f"""Detect if this text is in Slovene (sl) or German (de). Answer with ONLY 'sl' or 'de', nothing else.

Text: {request.text}"""
    
    try:
        detect_response = copilot.chat(message=detect_prompt, model="gpt-4.1")
        detected_lang = detect_response.get("content", "").strip().lower()
        
        # Default to sl if detection fails
        if detected_lang not in ["sl", "de"]:
            detected_lang = "sl"
        
        # Translate to opposite language
        target_lang = "Deutsch" if detected_lang == "sl" else "Slowenisch"
        source_lang = "Slowenisch" if detected_lang == "sl" else "Deutsch"
        
        translate_prompt = f"""Übersetze diesen Text von {source_lang} nach {target_lang}. Antworte NUR mit der Übersetzung, keine Erklärungen.

Text: {request.text}"""
        
        translate_response = copilot.chat(message=translate_prompt, model="gpt-4.1")
        translation = translate_response.get("content", "").strip()
        
        return TranslateResponse(
            text=request.text,
            translation=translation,
            detected_lang=detected_lang
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Translation failed: {str(e)}")



@app.post("/api/generate-from-german", response_model=GenerateResponse)
async def generate_from_german(request: GenerateFromGermanRequest):
    """Generate flashcard content from a German word - translates to Slovene and generates all content."""
    copilot = get_copilot()
    
    prompt = f"""Du bist ein Sprachlehrer für Slowenisch. Ein Benutzer gibt ein deutsches Wort ein und möchte die slowenische Übersetzung plus einen vollständigen Wörterbucheintrag.

Deutsches Wort: {request.german_word}

Erstelle:
1. Das slowenische Wort (die beste Übersetzung)
2. Bedeutung/Definition: Kurze Erklärung auf Deutsch (2-3 Sätze)
3. Grammatik: Detaillierte Grammatikinfo im Wörterbuchstil:
   - Für Substantive: Genus (m/f/n), alle 6 Fälle (Nominativ, Genitiv, Dativ, Akkusativ, Lokativ, Instrumental) im Singular und Plural
   - Für Verben: Infinitiv, 1./2./3. Person Singular Präsens, Perfekt
   - Für Adjektive: Grundform, Steigerung (Komparativ, Superlativ)
4. Drei verschiedene Beispielsätze auf Slowenisch
5. Synonyme: 2-3 ähnliche Wörter auf Slowenisch mit deutscher Übersetzung
6. Verwendung: Wann/Wie man dieses Wort typisch verwendet (auf Deutsch)

Antworte NUR mit diesem JSON (keine anderen Texte):
{{
    "word": "slowenisches Wort",
    "translation": "{request.german_word}",
    "meaning": "Bedeutung und Definition auf Deutsch",
    "grammar": "Genus: m|f|n\\nSingular: Nom: X, Gen: X, Dat: X, Akk: X, Lok: X, Instr: X\\nPlural: Nom: X, Gen: X, Dat: X, Akk: X, Lok: X, Instr: X",
    "examples": [
        "Erster Beispielsatz auf Slowenisch",
        "Zweiter Beispielsatz auf Slowenisch",
        "Dritter Beispielsatz auf Slowenisch"
    ],
    "synonyms": [
        {{"word": "synonym1", "translation": "Übersetzung1"}},
        {{"word": "synonym2", "translation": "Übersetzung2"}}
    ],
    "usage": "Erklärung, wann und wie das Wort verwendet wird"
}}"""

    try:
        response = copilot.chat(message=prompt, model="gpt-4.1")
        content = response.get("content", "")
        
        # Parse JSON from response
        import json
        start = content.find("{")
        end = content.rfind("}") + 1
        if start >= 0 and end > start:
            data = json.loads(content[start:end])
            return GenerateResponse(
                word=data.get("word", ""),
                translation=data.get("translation", request.german_word),
                grammar=data.get("grammar", ""),
                examples=data.get("examples", []),
                synonyms=data.get("synonyms", []),
                usage=data.get("usage", ""),
                meaning=data.get("meaning", ""),
            )
        else:
            raise HTTPException(status_code=500, detail="Could not parse AI response")
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=500, detail=f"JSON parse error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Generation failed: {str(e)}")


@app.get("/api/audio/{word}")
async def get_audio(word: str, lang: str = "sl"):
    """Generate TTS audio for a word using gTTS.
    Falls back to Croatian (hr) for Slovene since gTTS doesn't support sl.
    """
    import hashlib
    from gtts import gTTS
    
    # Map unsupported languages to closest alternatives
    lang_map = {
        "sl": "hr",  # Slovene -> Croatian (closest supported)
        "sk": "cs",  # Slovak -> Czech
    }
    tts_lang = lang_map.get(lang, lang)
    
    # Create a safe filename from the word
    word_hash = hashlib.md5(f"{word}_{lang}".encode()).hexdigest()[:12]
    safe_word = "".join(c if c.isalnum() else "_" for c in word)[:20]
    audio_file = AUDIO_CACHE_DIR / f"{safe_word}_{word_hash}.mp3"
    
    # Check if audio is already cached
    if not audio_file.exists():
        try:
            tts = gTTS(text=word, lang=tts_lang)
            tts.save(str(audio_file))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"TTS generation failed: {str(e)}")
    
    # Return the URL to the cached audio file
    return {"audio_url": f"/audio_cache/{audio_file.name}"}


# Mount audio cache directory
app.mount("/audio_cache", StaticFiles(directory=str(AUDIO_CACHE_DIR)), name="audio_cache")


@app.get("/api/stats")
async def get_stats(db: Session = Depends(get_db)):
    """Get learning statistics."""
    total = db.query(CardDB).count()
    due = db.query(CardDB).filter(CardDB.next_review <= datetime.utcnow()).count()
    new = db.query(CardDB).filter(CardDB.repetitions == 0).count()
    learning = db.query(CardDB).filter(
        CardDB.repetitions > 0,
        CardDB.interval < 21
    ).count()
    mature = db.query(CardDB).filter(CardDB.interval >= 21).count()
    
    return {
        "total": total,
        "due": due,
        "new": new,
        "learning": learning,
        "mature": mature,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
