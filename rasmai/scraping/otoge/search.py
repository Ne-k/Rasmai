from typing import Any, Dict
import re


def search_song(db: Any, song_name: str) -> Dict:
    if not song_name:
        return {}

    db._log(f"Searching for song: '{song_name}'", "debug")
    song_name_lower = song_name.lower().strip()

    cleaned_search = song_name_lower
    cleaned_search = cleaned_search.replace('◆', '')
    cleaned_search = cleaned_search.replace('☆', '')
    cleaned_search = cleaned_search.replace('★', '')
    cleaned_search = cleaned_search.replace('♪', '')
    cleaned_search = cleaned_search.replace('♡', '')
    cleaned_search = cleaned_search.replace('♢', '')
    cleaned_search = re.sub(r'\s+', ' ', cleaned_search).strip()

    db._log(f"Cleaned search: '{cleaned_search}'", "debug")

    if song_name_lower in db.songs_data:
        db._log(f"Exact match found for '{song_name_lower}'", "debug")
        result = db.songs_data[song_name_lower]
        if isinstance(result, dict):
            if not result.get('cover') and song_name_lower in db.cover_cache:
                result['cover'] = db.cover_cache[song_name_lower]
                db._log(f"Added cover from cache for '{song_name_lower}': {result['cover']}", "debug")
            return result

    if cleaned_search in db.songs_data:
        db._log(f"Cleaned match found for '{cleaned_search}'", "debug")
        result = db.songs_data[cleaned_search]
        if isinstance(result, dict):
            if not result.get('cover') and cleaned_search in db.cover_cache:
                result['cover'] = db.cover_cache[cleaned_search]
                db._log(f"Added cover from cache for '{cleaned_search}': {result['cover']}", "debug")
            return result

    best_match = None
    best_score = 0
    best_match_key = None

    search_normalized = re.sub(r'[◆☆★♪♡♢•·−\s]', '', cleaned_search)
    db._log(f"Normalized search: '{search_normalized}'", "debug")

    for title, data in db.songs_data.items():
        if not isinstance(data, dict):
            continue

        title_lower = data.get('title', '').lower()
        alt_title = data.get('alt_title', '').lower()

        title_normalized = re.sub(r'[◆☆★♪♡♢•·−\s]', '', title_lower)

        match_score = 0

        if search_normalized and search_normalized == title_normalized:
            match_score = 1000
            db._log(f"Normalized exact match: '{title}' (score: {match_score})", "debug")
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
            best_match_key = title
            db._log(f"New best match: '{title}' (score: {match_score})", "debug")

    if best_match and best_score > 0:
        db._log(f"Best match found: '{best_match.get('title')}' with score {best_score}", "info")

        if best_match.get('cover'):
            db._log(f"  Cover already in data: {best_match['cover']}", "debug")
        elif best_match_key and best_match_key in db.cover_cache:
            best_match['cover'] = db.cover_cache[best_match_key]
            db._log(f"  Added cover from cache by key: {best_match['cover']}", "debug")
        else:
            for key, cover in db.cover_cache.items():
                key_normalized = re.sub(r'[◆☆★♪♡♢•·−\s]', '', key.lower())
                if search_normalized and (
                        search_normalized == key_normalized or search_normalized in key_normalized):
                    best_match['cover'] = cover
                    db._log(f"  Found cover in cache by normalized key: {cover}", "debug")
                    break
                elif song_name_lower in key or key in song_name_lower:
                    best_match['cover'] = cover
                    db._log(f"  Found cover in cache by partial match: {cover}", "debug")
                    break

        return best_match

    db._log("No match found, checking cover cache directly", "debug")
    if song_name_lower in db.cover_cache:
        db._log(f"Found in cover cache directly: {db.cover_cache[song_name_lower]}", "info")
        return {'cover': db.cover_cache[song_name_lower]}

    if search_normalized:
        for key, cover in db.cover_cache.items():
            key_normalized = re.sub(r'[◆☆★♪♡♢•·−\s]', '', key.lower())
            if search_normalized == key_normalized:
                db._log(f"Found in cover cache by normalized key: {cover}", "info")
                return {'cover': cover}

    db._log(f"No match found for '{song_name}'", "debug")
    return {}
