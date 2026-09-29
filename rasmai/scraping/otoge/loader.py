from typing import Any
import json
import logging

logger = logging.getLogger(__name__)

_TIERS = ('bas', 'adv', 'exp', 'mas', 'remas')
# copied from the song as they are, '' when missing, in the order the cached entries have always had them
_FIELDS = (
    tuple(f'lev_{t}' for t in _TIERS) + ('version', 'sort')
    + tuple(f'dx_lev_{t}' for t in _TIERS) + tuple(f'dx_lev_{t}_i' for t in _TIERS)
    + tuple(f'lev_{t}_i' for t in _TIERS) + tuple(f'lev_{t}_notes' for t in _TIERS)
    + tuple(f'dx_lev_{t}_notes' for t in _TIERS) + tuple(f'lev_{t}_designer' for t in _TIERS)
    + ('wiki_url', 'intl')
)


def load_songs_from_repo(db: Any) -> bool:
    """Read the songs out of the checkout into ``songs_data``.

    :returns: True when at least one song was read; on any failure the data already held is kept.
    :rtype: bool
    """
    try:
        # the database snapshots the live music-ex.json into music-ex-<version>-final.json every time
        # the game rolls over, so the set is found rather than listed and a new version needs no edit.
        # First file wins, so the live one leads and the deleted list trails: a song still in the game
        # must not be marked deleted because an older file also holds it.
        data_dir = db.repo_path / 'maimai' / 'data'
        finals = sorted(path.name for path in data_dir.glob('music-ex-*-final.json'))
        music_files = [('music-intl.json', 'intl'), ('music-ex.json', 'ex')]
        music_files += [(name, 'ex') for name in finals] + [('music-ex-deleted.json', 'ex')]

        all_music_data = {}
        source_stats = {}

        for music_file, file_type in music_files:
            music_json_path = db.repo_path / 'maimai' / 'data' / music_file
            if music_json_path.exists():
                logger.debug(f"Loading {music_file}...")
                try:
                    with open(music_json_path, 'r', encoding='utf-8') as f:
                        music_data = json.load(f)

                    count = 0
                    if isinstance(music_data, list):
                        for song in music_data:
                            title = song.get('title', song.get('name', ''))
                            if title:
                                title_key = title.lower()
                                # a second song with the same title (the two "Link"s) keeps its own entry
                                if title_key in all_music_data and str(all_music_data[title_key]['data'].get('artist', '')) != str(song.get('artist', '')):
                                    title_key = f"{title_key}|{str(song.get('artist', '')).lower()}"
                                if title_key not in all_music_data:
                                    all_music_data[title_key] = {
                                        'data': song,
                                        'source': file_type,
                                        'source_file': music_file
                                    }
                                else:
                                    existing = all_music_data[title_key]
                                    if file_type == 'ex' and existing['source'] != 'ex':
                                        existing['data'] = song
                                        existing['source'] = file_type
                                        existing['source_file'] = music_file
                        count = len(music_data)

                    elif isinstance(music_data, dict):
                        songs_list = None
                        if 'songs' in music_data:
                            songs_list = music_data['songs']
                        elif 'music' in music_data:
                            songs_list = music_data['music']
                        else:
                            for key, value in music_data.items():
                                if isinstance(value, list) and len(value) > 0:
                                    if isinstance(value[0], dict):
                                        if 'title' in value[0] or 'image_url' in value[0]:
                                            songs_list = value
                                            break

                        if songs_list:
                            for song in songs_list:
                                title = song.get('title', song.get('name', ''))
                                if title:
                                    title_key = title.lower()
                                    if title_key not in all_music_data:
                                        all_music_data[title_key] = {
                                            'data': song,
                                            'source': file_type,
                                            'source_file': music_file
                                        }
                                    else:
                                        existing = all_music_data[title_key]
                                        if file_type == 'ex' and existing['source'] != 'ex':
                                            existing['data'] = song
                                            existing['source'] = file_type
                                            existing['source_file'] = music_file
                            count = len(songs_list)

                    source_stats[music_file] = count
                    logger.debug(f"  Loaded {count} songs from {music_file}")

                except Exception as e:
                    logger.error(f"  Error loading {music_file}: {e}")
            else:
                logger.debug(f"  {music_file} not found")

        if not all_music_data:
            logger.error("No music data files found!")
            return False

        logger.debug(f"Total loaded {len(all_music_data)} unique songs from all sources")

        cover_count = 0
        songs_by_title = {}

        for title_lower, entry in all_music_data.items():
            song = entry['data'].copy()
            title = song.get('title', song.get('name', ''))
            if not title:
                continue

            alt_title = song.get('altTitle', song.get('title_kana', ''))
            alt_title_lower = alt_title.lower() if alt_title else ''

            cover = song.get('image_url', '')
            if not cover:
                cover = song.get('cover', '')
            if not cover:
                cover = song.get('jacket', '')

            if cover and '/' in cover:
                cover = cover.split('/')[-1]
                if '?' in cover:
                    cover = cover.split('?')[0]

            song_info = {
                'id': song.get('id'),
                'title': title,
                'alt_title': alt_title,
                'artist': song.get('artist', ''),
                'genre': song.get('catcode', song.get('genre', '')),
                'bpm': song.get('bpm'),
                'cover': cover,
                'charts': song.get('charts', []),
                **{field: song.get(field, '') for field in _FIELDS},
                'deleted': entry['source_file'] == 'music-ex-deleted.json',
            }

            songs_by_title[title_lower] = song_info
            if cover:
                cover_count += 1
            # an alternate title is only an alias while no song owns that title itself:
            # utage charts like "[音]snooze" carry alt title "SNOOZE" and must not
            # replace the real "snooze"
            alias = alt_title_lower if alt_title_lower and alt_title_lower != title_lower else ''
            if alias and alias not in all_music_data:
                songs_by_title[alias] = song_info

        db.songs_data = songs_by_title
        db._save_cache()
        logger.debug(f"Cached {len(db.songs_data)} song entries with {cover_count} covers")
        return bool(db.songs_data)

    except Exception as e:
        logger.exception(f"Error loading songs from repo: {e}")
        return False
