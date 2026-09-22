# Writing a claudlet creature

A creature is a package the pet wears. The pet sends it **one thing** — which
state to be in, and which frame — and everything about how that looks belongs
to the creature. Draw it with code, play a GIF, blit a sprite sheet: the pet
never asks.

This is the whole contract:

```python
class MyCreature:
    name    = "mycat"       # id the config stores; must match the folder
    grid    = (22, 17)      # art-pixel box. The PET'S WINDOW IS SIZED FROM THIS
    states  = ("idle", ...) # what you can draw (see the list below)
    hats    = C.HAT_KINDS   # hats your companions may wear, or () for none
    palette  = "#33CC66"    # YOUR default colour, until the user picks one
    foot_row = 15.8         # where your feet are, in art rows — the pet stands
                            # you on windows by this line (omit to use 15.8)
    hearts  = (4.5, 3, 1.6) # where the petting hearts go, in art units:
                            # (out to each side, head height, size). Omit and
                            # the built-in's numbers are used — which are cut
                            # for a 22-wide grid, so a denser one wants its own
    scale   = 5             # the size you OPEN at, until the user picks one.
                            # 5 suits a 22x17 box; a box declared in finer dots
                            # wants 1, or it opens five times life size
    fractional_scale = False  # True if your art survives a fractional size —
                            # see "Size" below. Sprite sheets do; rectangles
                            # placed by hand do not

    def draw(self, p, ox, oy, u, state, frame, **kw): ...
    def set_lang(self, lang): ...

AVATAR = MyCreature         # the entry point the loader looks for
```

Install it at `~/.config/claudlet/creatures/<name>/__init__.py`. A creature
that fails to import is skipped, never fatal — check `claudlet-config ui`, which
lists what loaded and renders each one.

## draw()

`(ox, oy)` is the top-left of your art box in device pixels; `u` is how many
device pixels one art pixel is (5 by default, 2–12 configurable). So art pixel
`(col, row)` is at `ox + col * u, oy + row * u`. Never assume `u` is 5, and
never assume the grid is 22×17 — yours is whatever you declared.

`frame` counts up while the state is held. It is the only clock you get.

Keyword arguments are optional dressing. **Ignore what you don't support rather
than raising** — the pet passes everything it knows:

| kw | meaning |
|---|---|
| `facing` | `+1` right, `-1` left |
| `autonomous` | Claude is running unattended. **What that looks like is yours** — the built-in wears a VR visor, yours might glow, or ignore it |
| `palette` | a name or `{body, hi, lo, bang}`; `creature.palette_colors()` turns either into QColors |
| `energy` | `1.0` fresh … `0.0` exhausted |
| `happy` | being petted right now |
| `gaze` | `(dx, dy)`, roughly −1…1, where the cursor is |
| `cap` | a hat kind, for companion creatures |
| `hovering` | parked out of the way. The built-in peeks out of a slit in the screen; yours may float, fade or shrink |

Paint with `p.fillRect(...)`; the pet has already set the pen to `NoPen` and
antialiasing off.

## What you get for free

Three things in `claudlet.core.creature` are **tools, not rules**. The built-in
creature uses them. A GIF-backed creature ignores them entirely.

### `state_rig(state, frame, energy=1.0, happy=False, autonomous=False, gaze=(0,0))`

Twenty-nine states' worth of tuned motion, as plain numbers. Use it and your
creature moves like claudlet does without you inventing any of it:

| key | meaning |
|---|---|
| `bob` | whole-body vertical offset, art pixels |
| `baseline_lift` | how far off its own baseline it sits (tired sinks, celebrate rises) |
| `sx`, `sy` | squash / stretch about the body centre |
| `tilt` | degrees. Big ones are a real lurch (`error` −16, `doze` 10) |
| `legphase` | 0…1 through the walk cycle — **only means a stride when `walking`** |
| `walking` | whether `legphase` is a stride. `jump`/`doze` reuse 0.5 to mean "legs tucked" |
| `front_tap` | front legs tapping keys |
| `eyes` | `open blink sleep focus squint up wide x happy` |
| `autonomous` | the flag, passed straight back through |
| `arm` | `side up wave tap none` — **`none` means don't draw arms at all** (hands are on the laptop) |
| `arm_swing` | arm swing while walking |
| `prop` | what to hand to `draw_prop`, or `None` |
| `droop` | 0 fresh … 1 tired |

### `draw_hat(px, cap, frame, crown_row=3.0, cx=10.5, head_w=15.0)`

Companions wear a hat so they read as somebody else's sidekick rather than a
small copy of the pet. Declare `hats` to be given one, and call this where you
draw your head:

```python
if cap:
    C.draw_hat(px, cap, frame, crown_row=4.3, cx=CX, head_w=6.0)
```

It takes YOUR `px`, not the painter, so the hat inherits whatever squash, lean
and mirror you apply — a hat sits on a head and has to move with it, which a
prop never has to do. The three numbers are your head's geometry: where its
crown is, where its centre is, how wide it is. The art is cut for the built-in's
15-pixel head, so a narrower head gets a narrower hat rather than a brim out
past its shoulders.

### `draw_prop(p, ox, oy, u, prop, frame, state, body_dy=0, facing=1, palette=None)`

The objects: `laptop magnify phone clones clones_v hat speech zzz note balls
gear bulb ponder spark dizzy window bang`. Props are what most of a creature's
character lives in, and drawing seventeen of them across every state is a job
nobody finishes. Pass `body_dy = bob + baseline_lift` so the prop rides along.

`speech` draws a typed-out bubble; its text comes from `creature.speech(state)`
and follows the pet's language, which is what `set_lang` is for.

## States

Twenty-nine. You do not have to draw them all — list only what you support in
`states` and the pet falls back for the rest.

```
idle walk work_computer work_search work_web work_agent work_skill
autopilot thinking attention asking error angry celebrate sleeping
held falling jump wave sing juggle float climbdown strain leap
observe tic settle doze
```

There is no separate set of states for running unattended. That used to be six
`auto_*` twins that differed only in wearing a visor, which was the engine
deciding how a creature looks; it is the `autonomous` flag now, and showing it
(or not) is yours.

## Things that cost a day to learn

- **Whole device pixels or it crawls.** Round every rect to whole device pixels,
  and round a shared vertical offset to a whole number of them *before* using it
  (`creature._snap_offset`). A fractional offset re-splits every art pixel each
  frame and the silhouette visibly breathes.
- **Snap boundaries, not origin-and-size.** Rounding a cell's position and its
  width separately lets neighbours miss each other and rules seams through the
  body. Share the edge: cell `c` spans `round(x(c))`…`round(x(c+1))`.
- **Don't rotate small things.** At this size a limb is two to four pixels;
  rotating it shreds the edges and buys nothing translation doesn't give. A big
  lean of the *whole* creature is worth it — bake it flat first, then rotate the
  picture, or every cell edge shows.
- **Mirror the body, not the text.** Faced left, the body flips but props and
  speech must stay upright, or the bubble reads backwards.
- **Vary the eyes.** Eyes are the expression, and they are not one shape moved
  around: in the built-in each is its own size, the closed one wide and flat,
  the surprised one bigger both ways. A constant box reads as one face pulling
  the same expression forever. Asymmetric shapes mirror per side — `strain` is
  `>` `<` pointing at the nose, not `>` `>`.
- **Leave room above the head.** Props are drawn in the box too; the built-in
  keeps rows 0–4 mostly clear for bubbles and z's.

## Size

`scale` is device pixels per art unit, and the user sets it per creature. Yours
is what they get before they touch anything — the same idea as `palette`. The
default of 5 assumes the built-in's 22x17 box; if you declare a box in your own
finer dots, 5 means five pixels per dot and a pet the size of a window. Declare
what life size is for you.

The scale is a WHOLE number unless you say otherwise:

```python
fractional_scale = True     # my frames are a sprite sheet
```

Say it only if it is true of your art. A fractional unit re-rounds every
rectangle, so a creature drawn with `p.fillRect` gets art pixels that alternate
2px and 3px wide — which is why whole numbers are the default. Scaling a sprite
sheet is a resample of an image and has no such problem.

Declaring it buys two things. The user's size slider moves in tenths instead of
whole steps, which matters at the small end: if life size is 1, the next whole
step is twice as big. And your companions — the sidekicks that appear while
subagents run — can be drawn at 0.6 of you instead of being rounded up to your
own size.

## Petting hearts

When the user strokes you, the PET draws three hearts rising past your head —
you do not draw them, but you can say where they belong:

```python
hearts = (11.0, 5.0, 4.5)   # out to each side, head height, size (art units)
```

The defaults are `(4.5, 3, 1.6)`, measured on the built-in's 22-wide grid. A
creature with a much denser grid gets them in the wrong place for the same
reason `foot_row` exists: on an 88-wide grid those numbers put three-dot hearts
on the creature's face. Give your own if your head is not where the built-in's
is, and check them at the size the pet actually runs — they are drawn in art
units, so they shrink with everything else.

## Colour and size

The user sets these **per creature** in `claudlet-config ui`, so your colour and
your size are not dragged around by whatever they set on another creature. Your
`palette` attribute is the default they see before touching anything — a slime
opening in claudlet's orange is wrong.

Take the colour from `kw["palette"]` through `creature.palette_colors()`, which
accepts a name or a `{body, hi, lo, bang}` dict, and never hard-code your own
colours if you want the picker to work.

## A worked example

Two ship with the pet and neither is shaped like the built-in. Read them
alongside this.

`avatars/astronaut.py` is a **humanoid** — helmet, torso, two arms, two legs, a
pack on its back. It keeps the 22x17 grid on purpose (`draw_prop` hangs the
laptop and bubbles in those coordinates), declares `foot_row` because its boots
end well above the built-in's, and answers the unattended flag with a lit visor
and a blinking antenna rather than a headset.

`avatars/slime.py` is a legless jelly dome. What it does differently is
instructive —

- **legless**: the walk cycle becomes a hop, squashed at the bottom and
  stretched at the top, because a stride is what reads as walking and it has no
  legs to stride with.
- **no rotation, a shear instead**: its body is a stack of thin slabs, and
  rotating that smears every slab edge. Leaning each slab sideways in
  proportion to its height is both cleaner and what jelly actually does.
- **its own unattended look**: a band across the dome rather than a visor,
  pulled down over the eyes while working and resting on the crown otherwise.

## Creatures made from a sprite sheet

Everything above assumes you draw with `p.fillRect`. You do not have to. The pet
sends a state and a frame and asks nothing else, so a creature can just as well
keep its frames as DATA — a character per dot against a palette — and blit them.
At the size where a face is a dozen dots, hand-placed rectangles cannot put the
dots where a face needs them, and a sheet can.

Such a creature declares `fractional_scale = True` (see **Size**), because
resizing it is a resample of an image rather than a re-rounding of every
rectangle.

The art has to get from the sheet into the file, and that path has a handful of
traps that each cost a day:

- **Give the sheet a background that is not in the character.** Magenta
  (`#FF00FF`) works. A cream page looks natural and is the worst choice: pale
  skin and blonde hair ARE that colour, so cutting by colour distance punches
  holes straight through the character. A flood fill from the EDGE saves it,
  but only if the background is reachable — an enclosed loop of hair keeps its
  hole.
- **Shrink by the most common value in each block, not the average.** Averaging
  invents in-between colours along every edge, and each one then snaps to
  whatever palette entry happens to be nearest. That speckle is what makes
  downscaled art look broken.
- **Fit the palette with k-means, not median cut or frequency.** Both of the
  others dropped the purple lining of a kimono outright — a few hundred dots
  against thirty thousand. k-means spends a centre on it because it sits far
  from everything else.
- **Scale each sheet by its own ruler, and hold it constant within the sheet.**
  Sheets drawn at different times come back at different sizes; measuring per
  CELL instead makes a walk cycle bob by a dot between frames.
- **Cut cells by connected component, not by assuming a grid.** Ask for a 4x2
  grid and you may get cells of another height, and a fixed grid then slices
  two of them through the middle.
- **Ask for each pose by what it is FOR.** A sheet asked for "straining,
  pulling something heavy" came back leaning forward — correct to the words,
  useless for the state it was meant for, which is stretching UP for a cursor
  just out of reach.
- **Say that animation pairs must differ in one thing only.** "The same pose,
  breathing" came back with the hands in a different place, and alternating the
  two read as fidgeting rather than breathing.

![a creature drawn from a sprite sheet](https://raw.githubusercontent.com/YeeDochi/Claudlet/master/docs/sprite-creature.gif)

## Checking it

```bash
claudlet-config ui       # lists creatures, renders each, click to switch
CLAUDLET_AVATAR=mycat claudlet    # run a pet as it, without changing config
```

Render every state to one sheet and look at it — that is how every bug above was
found. `python3 app/src/claudlet/core/creature.py out.png` does it for the built-in;
do the same for yours and compare.
