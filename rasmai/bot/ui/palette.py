import discord

# The stripe down a card's left edge says what kind of card it is, so the colours are named by kind here and
# nowhere else: the site's pink for the bot's own cards, and one colour each for lookups, ratings and the player.
BRAND = discord.Color.from_rgb(255, 61, 143)       # help, invite, support, the daily note
LOOKUP = discord.Color.from_rgb(92, 211, 232)      # charts, levels, traits, recent plays, areas, news
RATING = discord.Color.from_rgb(240, 192, 74)      # rating, best 50, progress, leaderboards, the road to a goal
PLAYER = discord.Color.from_rgb(162, 102, 232)     # one player's profile, settings, session, last play, compare
OK = discord.Color.from_rgb(75, 184, 95)           # connected, responding
WAIT = discord.Color.from_rgb(255, 182, 46)        # nothing found, slow, or waiting on the player

_DIFFICULTY = {"basic": (75, 184, 95), "advanced": (224, 160, 32), "expert": (226, 69, 90), "master": (162, 102, 232), "remaster": (203, 187, 232)}


def difficulty(name: str) -> discord.Color:
    """The colour the game gives a difficulty; master's for one it does not name (utage)."""
    return discord.Color.from_rgb(*_DIFFICULTY.get(name, _DIFFICULTY["master"]))
