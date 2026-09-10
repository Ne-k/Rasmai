from typing import Optional

import discord
from discord import app_commands

from rasmai.bot.builders.charts import LEVEL_PATTERN
from rasmai.bot.core import bot, heavy_cooldown
from rasmai.engine.analysis import constant_span
from rasmai.bot.state.prefs import get_prefs
from rasmai.bot.builders.results import run_view_command
from rasmai.bot.commands.choices import CHALLENGE_CHOICES, CHALLENGE_HELP, DIFFICULTY_CHOICES, FOCUS_CHOICES, OUTPUT_CHOICES, OUTPUT_HELP, _challenge_value, _output_value, constant_autocomplete, level_autocomplete


@bot.tree.command(name="analyze", description="Get score recommendations picked for how you play")
@heavy_cooldown
@app_commands.describe(output=OUTPUT_HELP, challenge=CHALLENGE_HELP,
                       level="Only charts at one level (13+), one constant (13.2) or a range (13.0-13.4)")
@app_commands.autocomplete(level=constant_autocomplete)
@app_commands.choices(output=OUTPUT_CHOICES, challenge=CHALLENGE_CHOICES)
async def analyze(interaction: discord.Interaction, output: Optional[app_commands.Choice[str]] = None,
                  challenge: Optional[app_commands.Choice[str]] = None, level: Optional[str] = None):
    chosen = (level or "").strip() or None
    if chosen and constant_span(chosen) is None:
        await interaction.response.send_message(f"`{chosen[:16]}` is not a level, a constant or a range. Try `13+`, `13.2` or `13.0-13.4`.", ephemeral=True)
        return
    await run_view_command(interaction, "analyze", "Something went wrong while analyzing your account.",
                           output=_output_value(output, interaction.user.id),
                           challenge=_challenge_value(challenge, interaction.user.id), level=chosen)


@bot.tree.command(name="profile", description="See how you play and what to hit next")
@heavy_cooldown
@app_commands.describe(output=OUTPUT_HELP)
@app_commands.choices(output=OUTPUT_CHOICES)
async def profile(interaction: discord.Interaction, output: Optional[app_commands.Choice[str]] = None):
    await run_view_command(interaction, "profile", "Something went wrong reading your profile.",
                           output=_output_value(output, interaction.user.id))


@bot.tree.command(name="plan", description="Your route to the next rating milestone")
@heavy_cooldown
@app_commands.describe(
    target="Rating to aim for (defaults to the next thousand)",
    difficulty="Only route through this difficulty",
    min_level="Only charts at this level or above, like 13+",
    stretch="Allow long-shot targets well above your usual scores",
    output=OUTPUT_HELP,
    challenge=CHALLENGE_HELP,
)
@app_commands.autocomplete(min_level=level_autocomplete)
@app_commands.choices(difficulty=DIFFICULTY_CHOICES[:5], output=OUTPUT_CHOICES, challenge=CHALLENGE_CHOICES)
async def plan_command(interaction: discord.Interaction, target: Optional[int] = None,
                       difficulty: Optional[app_commands.Choice[str]] = None, min_level: Optional[str] = None,
                       stretch: bool = False,
                       output: Optional[app_commands.Choice[str]] = None,
                       challenge: Optional[app_commands.Choice[str]] = None):
    level = (min_level or "").strip()
    if level and level not in LEVEL_PATTERN:
        await interaction.response.send_message(f"`{level[:12]}` is not a maimai level. Try one like `13` or `13+`.", ephemeral=True)
        return
    await run_view_command(interaction, "plan", "Something went wrong building your route.",
                           target=target, stretch=stretch, page=0, output=_output_value(output, interaction.user.id),
                           challenge=_challenge_value(challenge, interaction.user.id),
                           difficulty=difficulty.value if difficulty else None, min_level=level or None)


@bot.tree.command(name="session", description="Tonight's credits, each spent where it is worth the most rating")
@heavy_cooldown
@app_commands.describe(credits="How many credits you will play (default 6)", output=OUTPUT_HELP, challenge=CHALLENGE_HELP,
                       difficulty="Only charts of this difficulty")
@app_commands.choices(difficulty=DIFFICULTY_CHOICES[:5], output=OUTPUT_CHOICES, challenge=CHALLENGE_CHOICES)
async def session_command(interaction: discord.Interaction, credits: app_commands.Range[int, 1, 20] = 6,
                          difficulty: Optional[app_commands.Choice[str]] = None,
                          output: Optional[app_commands.Choice[str]] = None,
                          challenge: Optional[app_commands.Choice[str]] = None):
    await run_view_command(interaction, "session", "Something went wrong planning the session.",
                           credits=credits, difficulty=difficulty.value if difficulty else None,
                           output=_output_value(output, interaction.user.id), challenge=_challenge_value(challenge, interaction.user.id))


@bot.tree.command(name="new", description="Charts you haven't played yet that fit your level")
@heavy_cooldown
@app_commands.describe(
    difficulty="Which difficulty to look at (default: your /settings choice, else Expert and up)",
    level="Only charts at this exact level, like 13 or 13+ (instead of the range your scores suggest)",
    focus="Lean the picks toward your weak spots or your strengths",
    output=OUTPUT_HELP,
    challenge=CHALLENGE_HELP,
)
@app_commands.autocomplete(level=level_autocomplete)
@app_commands.choices(difficulty=DIFFICULTY_CHOICES, output=OUTPUT_CHOICES, challenge=CHALLENGE_CHOICES, focus=FOCUS_CHOICES)
async def new_charts(interaction: discord.Interaction, difficulty: Optional[app_commands.Choice[str]] = None,
                     level: Optional[str] = None,
                     focus: Optional[app_commands.Choice[str]] = None,
                     output: Optional[app_commands.Choice[str]] = None,
                     challenge: Optional[app_commands.Choice[str]] = None):
    wanted = difficulty.value if difficulty else get_prefs(str(interaction.user.id))["new_difficulty"]
    chosen_level = (level or "").strip()
    if chosen_level and chosen_level not in LEVEL_PATTERN:
        await interaction.response.send_message(f"`{chosen_level[:12]}` is not a maimai level. Try one like `13` or `13+`.", ephemeral=True)
        return
    await run_view_command(interaction, "new", "Something went wrong looking for new charts.",
                           difficulty=None if wanted == "any" else wanted, level=chosen_level or None,
                           focus=focus.value if focus else None,
                           output=_output_value(output, interaction.user.id),
                           challenge=_challenge_value(challenge, interaction.user.id))


@bot.tree.command(name="refresh", description="Read your scores from maimai DX NET now, instead of the saved copy")
@heavy_cooldown
@app_commands.describe(output=OUTPUT_HELP, challenge=CHALLENGE_HELP)
@app_commands.choices(output=OUTPUT_CHOICES, challenge=CHALLENGE_CHOICES)
async def refresh_command(interaction: discord.Interaction, output: Optional[app_commands.Choice[str]] = None,
                          challenge: Optional[app_commands.Choice[str]] = None):
    await run_view_command(interaction, "analyze", "Something went wrong reading your scores.", force=True,
                           output=_output_value(output, interaction.user.id),
                           challenge=_challenge_value(challenge, interaction.user.id))
