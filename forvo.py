"""
Forvo audio scraper - uses simple requests instead of botasaurus
"""
import requests
import re
import base64


def load_word(word: str, lang: str = "sl"):
    """
    Get audio URL for a word from Forvo.
    
    Args:
        word: The word to find audio for
        lang: Language code (sl=Slovene, de=German, etc.)
    
    Returns:
        Audio URL string, or False if not found
    """
    try:
        response = requests.get(
            f"https://de.forvo.com/search/{word}/{lang}/",
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": "https://www.google.com/",
            },
            timeout=10
        )
        html = response.text
        
        # Find all play buttons with the expected onclick
        matches = re.findall(
            r'<div class="play\s+icon-size-l"[^>]*onclick="([^"]+)"[^>]*>', html
        )
        if not matches:
            return False
            
        for onclick in matches:
            # Extract the 5th parameter from Play(...)
            play_match = re.search(r"Play\(([^)]*)\)", onclick)
            if play_match:
                params = [p.strip().strip("'") for p in play_match.group(1).split(",")]
                if len(params) >= 5:
                    fifth_param = params[4]
                    try:
                        decode = base64.b64decode(fifth_param)
                        return "https://audio12.forvo.com/audios/mp3/" + decode.decode("utf-8")
                    except Exception:
                        continue
        return False
    except Exception as e:
        print(f"Forvo error: {e}")
        return False


if __name__ == "__main__":
    import time

    word = load_word("hrana")
    print(word)
    time.sleep(2)
    word = load_word("kruh")
    print(word)
    time.sleep(2)
    word = load_word("nepostojano a")
    print(word)
