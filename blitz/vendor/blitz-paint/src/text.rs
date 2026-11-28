use anyrender::{AntiAliasing, PaintScene};
use blitz_dom::CopyStyleGetters;
use blitz_dom::{BaseDocument, NodeId, node::TextBrush};
use kurbo::{Affine, Rect};
use parley::{Affinity, Cursor, GlyphRun, Layout, Line, PositionedLayoutItem, Selection};
use peniko::Fill;
use std::sync::Arc;

use crate::color::{Color, ToColorColor as _};
use crate::text_decorations::{
    DecorationRunGeometry, DecorationStackEntry, LineDecoration, ResolvedDecoration,
    ResolvedTextShadow, WinAscentCache, draw_line_text_shadows, flush_line_decorations,
    resolve_decoration_entry,
};
use crate::{FONT_EMBOLDEN_ENABLED, SELECTION_COLOR};

/// Draw the backgrounds of inline elements (e.g. `<span style="background: ...">`).
///
/// Each glyph run carries the node id of the innermost inline element it belongs to
/// (via its brush). We look up that node's `background-color` and, if non-transparent,
/// fill a rectangle covering the run's advance and its font's ascent/descent so that the
/// background sits behind the text.
///
/// The inline root's own background is painted separately (as a normal block box), so
/// runs belonging to the root are skipped to avoid drawing it twice.
pub(crate) fn draw_inline_backgrounds<'a>(
    scene: &mut impl PaintScene,
    lines: impl Iterator<Item = Line<'a, TextBrush>>,
    doc: &BaseDocument,
    transform: Affine,
    inline_root_id: NodeId,
) {
    for line in lines {
        for item in line.items() {
            let PositionedLayoutItem::GlyphRun(glyph_run) = item else {
                continue;
            };

            let node_id = glyph_run.style().brush.id;
            if node_id == inline_root_id {
                continue;
            }

            let Some(styles) = doc.get_node(node_id).and_then(|node| node.primary_styles()) else {
                continue;
            };

            let current_color = styles.clone_color();
            let bg_color = styles
                .get_background()
                .background_color
                .resolve_to_absolute(&current_color)
                .as_srgb_color();
            if bg_color == Color::TRANSPARENT {
                continue;
            }

            let metrics = glyph_run.run().font_metrics();
            let x = glyph_run.offset() as f64;
            let w = glyph_run.advance() as f64;
            let baseline = glyph_run.baseline() as f64;
            let y0 = baseline - metrics.ascent as f64;
            let y1 = baseline + metrics.descent as f64;
            let rect = Rect::new(x, y0, x + w, y1);

            scene.fill(
                Fill::NonZero,
                transform,
                bg_color,
                None,
                &rect,
                AntiAliasing::Enabled,
            );
        }
    }
}

/// Per glyph run values recorded while walking a line, so the line can be painted in
/// passes (shadows beneath, then glyphs) without re-resolving styles.
pub(crate) struct RunRecord {
    pub(crate) fill_color: Color,
    pub(crate) shadows: Option<Arc<[ResolvedTextShadow]>>,
    pub(crate) stroke: Option<TextStroke>,
}

/// A run's `-webkit-text-stroke`, and whether `paint-order` puts it under the fill
#[derive(Clone, Copy)]
pub(crate) struct TextStroke {
    color: Color,
    width: f64,
    under_fill: bool,
}

fn resolve_text_stroke(doc: &BaseDocument, node_id: NodeId, scale: f64) -> Option<TextStroke> {
    use style::values::specified::svg::PaintOrder;
    let styles = doc.get_node(node_id)?.primary_styles()?;
    let text = styles.get_inherited_text();
    let width = text._webkit_text_stroke_width.to_f64_px() * scale;
    if width <= 0.0 {
        return None;
    }
    let color = text
        ._webkit_text_stroke_color
        .resolve_to_absolute(&styles.clone_color())
        .as_srgb_color();
    // the first of fill and stroke that `paint-order` names is painted first; `normal` is fill then stroke
    let order = styles.get_inherited_svg().paint_order;
    let under_fill = (0..3)
        .map(|pos| order.order_at(pos))
        .find(|kind| matches!(kind, PaintOrder::Fill | PaintOrder::Stroke))
        .is_some_and(|kind| kind == PaintOrder::Stroke);
    Some(TextStroke {
        color,
        width,
        under_fill,
    })
}

/// Reusable scratch storage for drawing text across all inline formatting contexts in a
/// document. The vectors are cleared between uses without releasing their allocations.
#[derive(Default)]
pub(crate) struct DrawTextContext {
    stack: Vec<DecorationStackEntry>,
    path_scratch: Vec<NodeId>,
    deco_boxes: Vec<LineDecoration>,
    run_records: Vec<RunRecord>,
    win_ascent_ratios: WinAscentCache,
}

#[derive(Clone, Copy)]
pub(crate) struct TextPaintOptions {
    pub scale: f64,
    pub brush_override: Option<Color>,
}

pub(crate) fn stroke_text<'a>(
    scene: &mut impl PaintScene,
    lines: impl Iterator<Item = Line<'a, TextBrush>>,
    doc: &BaseDocument,
    transform: Affine,
    options: TextPaintOptions,
    inline_root_id: NodeId,
    context: &mut DrawTextContext,
) {
    let TextPaintOptions {
        scale,
        brush_override,
    } = options;
    let DrawTextContext {
        stack,
        path_scratch,
        deco_boxes,
        run_records,
        win_ascent_ratios,
    } = context;
    stack.clear();
    path_scratch.clear();
    deco_boxes.clear();
    run_records.clear();
    let ellipsis_at = ellipsis_limit(doc, inline_root_id, scale);

    // Persistent stack mirroring the ancestor path (inline root -> current run's
    // node) as we walk the runs. The `text-decoration-*` properties are *not*
    // inherited; instead a decoration set on an ancestor is propagated to the
    // descendant text it wraps. Rather than re-resolving styles for the whole
    // ancestor chain on every run, we cache each node's resolved values here and,
    // for each run, only resolve styles for the nodes newly descended into (popping
    // as we ascend). `path_scratch` is a reusable buffer for the run's node path.
    for line in lines {
        // Decorations accumulated for this line, keyed by decorating box, so each box is
        // painted once (spanning all its runs) using its own font — matching Firefox, which
        // draws one decoration per box rather than one stepped segment per differently-sized
        // run. Clearing preserves the allocation for the next line and inline context.
        deco_boxes.clear();
        run_records.clear();
        let mut line_has_shadows = false;
        // The underline of the text an input method is composing on this line, spanning its runs.
        let mut composing: Option<LineDecoration> = None;

        // Pass 1: resolve styles for every glyph run on the line (recording the values
        // needed to paint it) and accumulate decorations. Painting is deferred so text
        // shadows can be drawn beneath *all* of the line's text and decorations.
        for item in line.items() {
            let PositionedLayoutItem::GlyphRun(glyph_run) = item else {
                continue;
            };
            let run = glyph_run.run();
            let font = run.font();
            let font_size = run.font_size();
            let metrics = run.font_metrics();
            let style = glyph_run.style();

            let css_font_size = font_size as f64 / scale;

            // Reconcile the stack with this run's ancestor path. Build the path
            // (inline root -> run node), keep the shared prefix already on the stack,
            // pop the rest, and resolve styles only for the newly-descended nodes.
            path_scratch.clear();
            let mut walk_id = Some(style.brush.id);
            while let Some(node_id) = walk_id {
                path_scratch.push(node_id);
                if node_id == inline_root_id {
                    break;
                }
                walk_id = doc.get_node(node_id).and_then(|node| node.parent);
            }
            path_scratch.reverse();

            let shared = stack
                .iter()
                .zip(path_scratch.iter())
                .take_while(|(entry, node_id)| entry.node_id == **node_id)
                .count();
            stack.truncate(shared);
            for &node_id in &path_scratch[shared..] {
                let entry = resolve_decoration_entry(doc, node_id, stack.last(), scale);
                stack.push(entry);
            }

            // The glyph colour and `text-shadow` come from the run's own node (the stack
            // top): both inherit, so the innermost inline element already carries the
            // right values. Shadows are not part of a `background-clip: text` mask, so
            // they are dropped when the brush is overridden.
            let (fill_color, shadows) = stack
                .last()
                .map(|e| (e.fill_color, e.text_shadows.clone()))
                .unwrap_or((Color::BLACK, None));
            let fill_color = brush_override.unwrap_or(fill_color);
            let shadows = shadows.filter(|_| brush_override.is_none());
            line_has_shadows |= shadows.is_some();
            run_records.push(RunRecord {
                fill_color,
                shadows,
                stroke: resolve_text_stroke(doc, style.brush.id, scale)
                    .filter(|_| brush_override.is_none()),
            });

            // Accumulate this run's contribution to each decorating box on its ancestor
            // path. The decoration is drawn once per box after the whole line has been
            // walked (see `flush_line_decorations`), so mixed font sizes within a box
            // produce a single straight line rather than one stepped segment per run.
            let geometry = DecorationRunGeometry {
                baseline: glyph_run.baseline(),
                ascent: metrics.ascent,
                descent: metrics.descent,
                underline_offset: metrics.underline_offset,
                underline_size: metrics.underline_size,
                strikethrough_size: metrics.strikethrough_size,
                font: font.clone(),
                font_size,
                css_font_size,
            };
            let run_node_id = style.brush.id;
            let run_x0 = glyph_run.offset() as f64;
            let run_x1 = run_x0 + glyph_run.advance() as f64;

            for entry in stack.iter() {
                if entry.decoration.is_none() {
                    continue;
                }
                let idx = match deco_boxes.iter().position(|d| d.node_id == entry.node_id) {
                    Some(idx) => idx,
                    None => {
                        deco_boxes.push(LineDecoration {
                            node_id: entry.node_id,
                            deco: entry.decoration.clone().unwrap(),
                            min_x: f64::INFINITY,
                            max_x: f64::NEG_INFINITY,
                            own: None,
                            first: None,
                        });
                        deco_boxes.len() - 1
                    }
                };
                let acc = &mut deco_boxes[idx];
                acc.min_x = acc.min_x.min(run_x0);
                acc.max_x = acc.max_x.max(run_x1);
                if acc.first.is_none() {
                    acc.first = Some(geometry.clone());
                }
                // A run whose innermost node is the box itself is the box's own text, so
                // its font is the one Firefox positions and sizes the decoration with.
                if entry.node_id == run_node_id {
                    acc.own = Some(geometry.clone());
                }
            }

            // A text input's editor underlines the text an input method is composing.
            if style.underline.is_some() {
                let acc = composing.get_or_insert_with(|| LineDecoration {
                    node_id: run_node_id,
                    deco: ResolvedDecoration::composition_underline(fill_color),
                    min_x: f64::INFINITY,
                    max_x: f64::NEG_INFINITY,
                    own: None,
                    first: None,
                });
                acc.min_x = acc.min_x.min(run_x0);
                acc.max_x = acc.max_x.max(run_x1);
                acc.first.get_or_insert(geometry);
            }
        }

        // Pass 2: text shadows, beneath all of the line's text and decorations.
        if line_has_shadows {
            draw_line_text_shadows(
                scene,
                &line,
                run_records,
                deco_boxes,
                win_ascent_ratios,
                transform,
                options,
                inline_root_id,
            );
        }

        // Pass 3: the glyphs themselves. A line that runs past a `text-overflow: ellipsis` box keeps the glyphs that
        // fit with room for an ellipsis, and the ellipsis follows the last of them
        let ellipsis = ellipsis_at.and_then(|limit| line_ellipsis(&line, limit));
        let cut = ellipsis.as_ref().map(|e| e.cut);
        let mut ellipsis_run = None;
        let mut kept_end = 0.0f32;
        for (index, (glyph_run, record)) in glyph_runs(&line).zip(run_records.iter()).enumerate() {
            let stroke = |scene: &mut _| {
                if let Some(s) = record.stroke {
                    draw_glyph_run_with(scene, &glyph_run, s.color, transform, Some(s.width), cut);
                }
            };
            if record.stroke.is_some_and(|s| s.under_fill) {
                stroke(scene);
                draw_glyph_run_with(scene, &glyph_run, record.fill_color, transform, None, cut);
            } else {
                draw_glyph_run_with(scene, &glyph_run, record.fill_color, transform, None, cut);
                stroke(scene);
            }
            if let Some(ellipsis) = &ellipsis {
                for glyph in glyph_run.positioned_glyphs() {
                    if glyph.x + glyph.advance <= ellipsis.cut {
                        kept_end = kept_end.max(glyph.x + glyph.advance);
                    }
                }
                if index == ellipsis.run {
                    ellipsis_run = Some((glyph_run, record.fill_color));
                }
            }
        }
        if let (Some(ellipsis), Some((glyph_run, color))) = (ellipsis, ellipsis_run) {
            draw_ellipsis(
                scene,
                &glyph_run,
                color,
                transform,
                ellipsis.glyph_id,
                kept_end,
            );
        }

        // Pass 4: decorations, on top of the glyphs.
        flush_line_decorations(
            scene,
            transform,
            options,
            deco_boxes,
            win_ascent_ratios,
            inline_root_id,
            line.metrics().baseline,
            None,
        );
        if let Some(composing) = composing {
            flush_line_decorations(
                scene,
                transform,
                options,
                std::slice::from_ref(&composing),
                win_ascent_ratios,
                inline_root_id,
                line.metrics().baseline,
                None,
            );
        }
    }
}

/// The glyph runs of a line, in order (matching the order of the recorded `RunRecord`s).
pub(crate) fn glyph_runs<'a, 'b>(
    line: &'b Line<'a, TextBrush>,
) -> impl Iterator<Item = GlyphRun<'a, TextBrush>> + 'b {
    line.items().filter_map(|item| match item {
        PositionedLayoutItem::GlyphRun(glyph_run) => Some(glyph_run),
        PositionedLayoutItem::InlineBox(_) => None,
    })
}

/// Draw a glyph run's glyphs in a single colour.
pub(crate) fn draw_glyph_run(
    scene: &mut impl PaintScene,
    glyph_run: &GlyphRun<'_, TextBrush>,
    color: Color,
    transform: Affine,
) {
    draw_glyph_run_with(scene, glyph_run, color, transform, None, None);
}

/// Draw a glyph run's glyphs in a single colour, filled, or stroked `stroke` wide, leaving out any that end past `cut`.
fn draw_glyph_run_with(
    scene: &mut impl PaintScene,
    glyph_run: &GlyphRun<'_, TextBrush>,
    color: Color,
    transform: Affine,
    stroke: Option<f64>,
    cut: Option<f32>,
) {
    let stroke = stroke.map(kurbo::Stroke::new);
    let style: peniko::StyleRef<'_> = match &stroke {
        Some(stroke) => stroke.into(),
        None => Fill::NonZero.into(),
    };
    let run = glyph_run.run();
    let font_size = run.font_size();
    // Zero-size text is invisible, but hinting can give its glyphs ink. Fully
    // transparent text is skipped too: backends draw color (emoji) glyphs opaque.
    if font_size <= 0.0 || color.components[3] <= 0.0 {
        return;
    }
    let glyph_xform = run
        .synthesis()
        .skew()
        .map(|angle| Affine::skew(-angle.to_radians().tan() as f64, 0.0));

    let embolden = if FONT_EMBOLDEN_ENABLED {
        font_embolden(font_size as f64, color, transform)
    } else {
        kurbo::Vec2::default()
    };

    let normalized_coords: &[i16] = bytemuck::cast_slice(run.normalized_coords());
    scene.draw_glyphs(
        run.font(),
        font_size,
        !FONT_EMBOLDEN_ENABLED,
        normalized_coords,
        embolden,
        style,
        &anyrender::Paint::from(color),
        1.0,
        transform,
        glyph_xform,
        glyph_run
            .positioned_glyphs()
            .filter(|glyph| cut.is_none_or(|cut| glyph.x + glyph.advance <= cut))
            .map(|glyph| anyrender::Glyph {
                id: glyph.id as _,
                x: glyph.x,
                y: glyph.y,
            }),
        AntiAliasing::Enabled,
    );
}

/// The ellipsis that ends a line cut short by `text-overflow`: where the kept glyphs stop, the glyph drawn after them,
/// and the glyph run (by its order in the line) whose font that glyph was looked up in and is drawn with
pub(crate) struct LineEllipsis {
    cut: f32,
    glyph_id: u32,
    run: usize,
}

/// Where lines of this inline root end for `text-overflow: ellipsis`: the end of its content box, in layout units.
/// `None` when the box shows its overflow or clips it bare.
fn ellipsis_limit(doc: &BaseDocument, inline_root_id: NodeId, scale: f64) -> Option<f32> {
    use style::computed_values::overflow_x::T as Overflow;
    use style::values::specified::text::TextOverflowSide;
    let node = doc.get_node(inline_root_id)?;
    let styles = node.primary_styles()?;
    if styles.clone_overflow_x() == Overflow::Visible
        || !matches!(
            styles.get_text().text_overflow.second,
            TextOverflowSide::Ellipsis
        )
    {
        return None;
    }
    let layout = node.final_layout();
    let content_width = layout.size.width
        - layout.padding.left
        - layout.padding.right
        - layout.border.left
        - layout.border.right;
    Some((content_width as f64 * scale) as f32)
}

/// The ellipsis for a line wider than `limit`, set in the font of the run the line overflows in, as browsers set it in the
/// font of the text it follows. Left to right only: the cut is at the right.
fn line_ellipsis(line: &Line<'_, TextBrush>, limit: f32) -> Option<LineEllipsis> {
    use skrifa::{
        MetadataProvider as _,
        instance::{LocationRef, Size},
        raw::FontRef,
    };
    let end = glyph_runs(line)
        .map(|run| run.offset() + run.advance())
        .fold(0.0, f32::max);
    // a line that fits keeps every glyph: layout rounds a box's edges to whole pixels, so its width can come out up to a pixel short of its text
    if end <= limit + 1.0 {
        return None;
    }
    let (index, overflowing) = glyph_runs(line)
        .enumerate()
        .take_while(|(_, run)| run.offset() < limit)
        .last()?;
    let run = overflowing.run();
    let font = run.font();
    let font_ref = FontRef::from_index(font.data.as_ref(), font.index).ok()?;
    let glyph_id = font_ref.charmap().map('\u{2026}')?;
    let advance = font_ref
        .glyph_metrics(Size::new(run.font_size()), LocationRef::default())
        .advance_width(glyph_id)?;
    Some(LineEllipsis {
        cut: limit - advance,
        glyph_id: glyph_id.to_u32(),
        run: index,
    })
}

/// Draw the ellipsis glyph `glyph_id` of `glyph_run`'s font at `x`, on that run's baseline.
fn draw_ellipsis(
    scene: &mut impl PaintScene,
    glyph_run: &GlyphRun<'_, TextBrush>,
    color: Color,
    transform: Affine,
    glyph_id: u32,
    x: f32,
) {
    let run = glyph_run.run();
    let normalized_coords: &[i16] = bytemuck::cast_slice(run.normalized_coords());
    scene.draw_glyphs(
        run.font(),
        run.font_size(),
        !FONT_EMBOLDEN_ENABLED,
        normalized_coords,
        kurbo::Vec2::default(),
        Fill::NonZero,
        &anyrender::Paint::from(color),
        1.0,
        transform,
        None,
        std::iter::once(anyrender::Glyph {
            id: glyph_id,
            x,
            y: glyph_run.baseline(),
        }),
        AntiAliasing::Enabled,
    );
}

/// The layout-space box covered by a glyph run: its advance horizontally and the font's
/// ascent/descent vertically.
pub(crate) fn glyph_run_rect(glyph_run: &GlyphRun<'_, TextBrush>) -> Rect {
    let metrics = glyph_run.run().font_metrics();
    let x0 = glyph_run.offset() as f64;
    let x1 = x0 + glyph_run.advance() as f64;
    let baseline = glyph_run.baseline() as f64;
    let y0 = baseline - metrics.ascent as f64;
    let y1 = baseline + metrics.descent as f64;
    Rect::new(x0.min(x1), y0.min(y1), x0.max(x1), y0.max(y1))
}

/// Draw selection highlight rectangles for the given byte range in a layout.
/// Uses Parley's Selection type for accurate geometry calculation.
pub(crate) fn draw_text_selection(
    scene: &mut impl PaintScene,
    layout: &Layout<TextBrush>,
    transform: Affine,
    selection_start: usize,
    selection_end: usize,
) {
    let anchor = Cursor::from_byte_index(layout, selection_start, Affinity::Downstream);
    let focus = Cursor::from_byte_index(layout, selection_end, Affinity::Downstream);
    let selection = Selection::new(anchor, focus);

    selection.geometry_with(layout, |rect, _line_idx| {
        let rect = kurbo::Rect::new(rect.x0, rect.y0, rect.x1, rect.y1);
        scene.fill(
            Fill::NonZero,
            transform,
            SELECTION_COLOR,
            None,
            &rect,
            AntiAliasing::Enabled,
        );
    });
}

/// Approximates macOS font smoothing (stem dilation). CoreGraphics dilates each side by an amount
/// in device pixels that grows with the device ppem up to 0.3px (fitted to Safari's ink at 9-72px
/// and 1x-3x scale), and keeps dilating at large sizes, so there is no ppem cutoff. glifo applies
/// the embolden in user units, so the device amounts are divided by the transform's scale.
fn font_embolden(font_size: f64, color: Color, transform: Affine) -> kurbo::Vec2 {
    const MAX_DEVICE_EMBOLDEN: f64 = 0.3;
    let [a, b, c, d, _, _] = transform.as_coeffs();
    let (scale_x, scale_y) = (a.hypot(b), c.hypot(d));
    let device_ppem = font_size * (a * d - b * c).abs().sqrt();
    if scale_x == 0.0 || scale_y == 0.0 || !device_ppem.is_finite() {
        return kurbo::Vec2::default();
    }
    let fs = device_ppem * embolden_scale(color);
    kurbo::Vec2::new(
        (0.0121 * fs).min(MAX_DEVICE_EMBOLDEN) / scale_x,
        (0.015125 * fs).min(MAX_DEVICE_EMBOLDEN) / scale_y,
    )
}

/// Scales Pathfinder's stem-darkening factors by the text's relative luminance. CoreText
/// dilates light text more than dark text; the points are fitted to Safari's ink for text
/// colours from black to white on black and white backgrounds.
fn embolden_scale(color: Color) -> f64 {
    const POINTS: [(f64, f64); 4] = [(0.1, 0.5), (0.125, 0.72), (0.35, 0.72), (1.0, 1.3)];
    let lum = color.discard_alpha().relative_luminance() as f64;
    let mut prev = POINTS[0];
    if lum <= prev.0 {
        return prev.1;
    }
    for point in &POINTS[1..] {
        if lum <= point.0 {
            return prev.1 + (point.1 - prev.1) * (lum - prev.0) / (point.0 - prev.0);
        }
        prev = *point;
    }
    prev.1
}
