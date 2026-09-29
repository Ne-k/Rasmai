from typing import Any, Dict
import logging
import re

logger = logging.getLogger(__name__)


def _covers(db: Any):
    return ((key, data['cover']) for key, data in db.songs_data.items() if isinstance(data, dict) and data.get('cover'))


def search_song(db: Any, song_name: str) -> Dict:
    if not song_name:
        return {}

    logger.debug(f"Searching for song: '{song_name}'")
    song_name_lower = song_name.lower().strip()

    cleaned_search = song_name_lower
    cleaned_search = cleaned_search.replace('◆', '')
    cleaned_search = cleaned_search.replace('☆', '')
    cleaned_search = cleaned_search.replace('★', '')
    cleaned_search = cleaned_search.replace('♪', '')
    cleaned_search = cleaned_search.replace('♡', '')
    cleaned_search = cleaned_search.replace('♢', '')
    cleaned_search = re.sub(r'\s+', ' ', cleaned_search).strip()

    logger.debug(f"Cleaned search: '{cleaned_search}'")

    if song_name_lower in db.songs_data:
        logger.debug(f"Exact match found for '{song_name_lower}'")
        result = db.songs_data[song_name_lower]
        if isinstance(result, dict):
            return result

    if cleaned_search in db.songs_data:
        logger.debug(f"Cleaned match found for '{cleaned_search}'")
        result = db.songs_data[cleaned_search]
        if isinstance(result, dict):
            return result

    best_match = None
    best_score = 0

    search_normalized = re.sub(r'[◆☆★♪♡♢•·−\s]', '', cleaned_search)
    logger.debug(f"Normalized search: '{search_normalized}'")

    for title, data in db.songs_data.items():
        if not isinstance(data, dict):
            continue

        title_lower = data.get('title', '').lower()
        alt_title = data.get('alt_title', '').lower()

        title_normalized = re.sub(r'[◆☆★♪♡♢•·−\s]', '', title_lower)

        match_score = 0

        if search_normalized and search_normalized == title_normalized:
            match_score = 1000
            logger.debug(f"Normalized exact match: '{title}' (score: {match_score})")
        elif song_name_lower in title_lower:
            match_score = 200 + (len(song_name_lower) / max(1, len(title_lower))) * 50
        elif title_lower in song_name_lower:
            match_score = 150 + (len(title_lower) / max(1, len(song_name_lower))) * 50
        elif cleaned_search in title_lower:
            match_score = 100 + (len(cleaned_search) / max(1, len(title_lower))) * 50
        elif search_normalized and search_normalized in title_normalized:
            match_score = 80 + (len(search_normalized) / max(1, len(title_normalized))) * 40
        elif title_normalized and title_normalized in search_normalized:
            match_score = 70 + (len(title_normalized) / max(1, len(search_normalized))) * 40
        elif alt_title and (song_name_lower in alt_title or alt_title in song_name_lower):
            match_score = 60
        elif data.get('artist', '').lower() and (
                song_name_lower in data.get('artist', '').lower() or data.get('artist',
                                                                              '').lower() in song_name_lower):
            match_score = 30

        if song_name_lower == title_lower:
            match_score = max(match_score, 500)

        if match_score > best_score:
            best_score = match_score
            best_match = data
            logger.debug(f"New best match: '{title}' (score: {match_score})")

    if best_match and best_score > 0:
        logger.debug(f"Best match found: '{best_match.get('title')}' with score {best_score}")

        if best_match.get('cover'):
            logger.debug(f"  Cover already in data: {best_match['cover']}")
        else:
            for key, cover in _covers(db):
                key_normalized = re.sub(r'[◆☆★♪♡♢•·−\s]', '', key.lower())
                if search_normalized and (
                        search_normalized == key_normalized or search_normalized in key_normalized):
                    best_match['cover'] = cover
                    logger.debug(f"  Found cover in cache by normalized key: {cover}")
                    break
                elif song_name_lower in key or key in song_name_lower:
                    best_match['cover'] = cover
                    logger.debug(f"  Found cover in cache by partial match: {cover}")
                    break

        return best_match

    if search_normalized:
        for key, cover in _covers(db):
            key_normalized = re.sub(r'[◆☆★♪♡♢•·−\s]', '', key.lower())
            if search_normalized == key_normalized:
                logger.debug(f"Found in cover cache by normalized key: {cover}")
                return {'cover': cover}

    logger.debug(f"No match found for '{song_name}'")
    return {}
