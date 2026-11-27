# The new image look: a jacket-first board

The images show a player's charts, and the charts already have art: their jackets. The board is built around them,
the way the community's best-50 boards are, and nothing else on it competes. Everything here applies to the new look
only; `classic/` keeps the old one.

## Ground and ink

| Token | Value | Role |
|---|---|---|
| `--ground` | `#0e1530`, on a night-sky gradient | what everything sits on, dark so jackets and difficulty colours carry the colour |
| `--tile` | `#19213f` | a chart's info block |
| `--ink` | `#f4f1ea` | text and figures |
| `--muted` | `#a3acd0` | labels, second lines |
| `--rule` | `#323d6a` | hairlines between figures and under section headings |
| `--tier` | the chart's difficulty colour (`DIFFICULTY_STYLES`) | the frame round a jacket; the game's own convention |

No other colour is decoration. The rating plate keeps its band colour.

## The versions' marks

The two maimai versions the look comes from sit dimmed behind the board: CiRCLE PLUS's rings in pink, violet and cyan, and
MAGiCAL's magic circles in green, teal and gold. Each image gets one of four layouts at random (`BACKDROPS` in `posters.py`),
and each shows both versions:

| Class | Top | Bottom |
|---|---|---|
| none | concentric rings at the top right | the magic circle at the bottom left |
| `bg-chain` | five linked rings hanging from the top edge, each passing over one neighbour and under the other | the seal at the bottom right |
| `bg-seal` | the rim of a magic seal (a tick ring round eight overlapping circles) hanging from the top edge | the rings at the bottom left |
| `bg-ripple` | wide ripples spreading from the player's corner | the magic circle at the bottom right |

They are the only background art, all original geometry, and they stay behind the tiles. The bg- layouts keep the player's
name (the first 700px) and the headline figure (the last 300px) clear; the default rings sit behind the headline, which the
rating plate covers on the wide board. No bright centre sits in the head.

## Type

The site's faces, embedded by `markup.py`: Zen Kaku Gothic New for words (400, 700) and Zen Maru Gothic 900 for every
figure. Labels are sentence case and not letter-spaced. Sizes: name 54, section heading 30, figures 22 to 30, words 15 to 17.

## Layout

- Frame: at least 16:9, the shape of a screen. Boards are 2400×1350 and cards 1920×1080. A page with less to show keeps the
  frame with its footer at the bottom; one with more grows taller.
- Head: the player's icon, a small label naming the board over the player's name, and the headline figure on the right.
- Banner: the board's sums as figures on the ground, split by hairlines. No box round it.
- Sections: a heading and a short note on one line over a hairline, then the tiles. No coloured bands or washed panels.
- Tile: a little wider than tall (5:4), the jacket filling it inside a 4px border of its difficulty colour, so a board of 50 fits at 16:9.
  On the jacket, the place in the list at top left and the difficulty mark at top right. Over its lower part, on a dark
  fade, the title, then the score and the loud figure (rating, gain, chance) on one line, then the level, constant and marks.

## Signature

The difficulty-colour frame. It is how the game itself tells charts apart, so a board reads as maimai at a glance.

## Not used

Sparkles, confetti, bunting, ticket notches and tear lines, a cream outline on every element,
letter-spaced capital labels, key boxes explaining the marks.
