use std::io::{self, BufReader, BufWriter, Read, Write};
use std::panic::{AssertUnwindSafe, catch_unwind};
use std::sync::Arc;

use anyrender::render_to_buffer;
use anyrender_vello_cpu::VelloCpuImageRenderer;
use base64::Engine;
use blitz_dom::{DocumentConfig, FontContext};
use blitz_html::HtmlDocument;
use blitz_traits::net::{Bytes, NetHandler, NetProvider, Request};
use blitz_traits::shell::{ColorScheme, Viewport};

/// Serves data: URLs only. The bot writes every font, mark and jacket into the page itself, so a page can never make the
/// renderer reach the network or the disk
struct DataUrls;

impl NetProvider for DataUrls {
    fn fetch(&self, _doc_id: usize, request: Request, handler: Box<dyn NetHandler>) {
        let url = request.url.as_str().to_owned();
        match decode_data_url(&url) {
            Some(bytes) => handler.bytes(url, Bytes::from(bytes)),
            None => handler.error(url, "only data: URLs are served".into()),
        }
    }
}

fn decode_data_url(url: &str) -> Option<Vec<u8>> {
    let (head, body) = url.strip_prefix("data:")?.split_once(',')?;
    let raw: Vec<u8> = percent_encoding::percent_decode_str(body).collect();
    if head.ends_with(";base64") {
        let text: Vec<u8> = raw.into_iter().filter(|b| !b.is_ascii_whitespace()).collect();
        base64::engine::general_purpose::STANDARD.decode(text).ok()
    } else {
        Some(raw)
    }
}

/// Resolve until every font and image the page holds is in
fn settle(doc: &mut HtmlDocument) {
    for _ in 0..20 {
        doc.resolve(0.0);
        if !doc.has_pending_critical_resources() {
            doc.resolve(0.0);
            return;
        }
    }
}

/// The page drawn at the body's own width and the document's full height, as premultiplied RGBA, with its size
fn render(html: &str, fonts: &FontContext) -> (Vec<u8>, u32, u32) {
    let config = DocumentConfig {
        viewport: Some(Viewport::new(2400, 400, 1.0, ColorScheme::Dark)),
        net_provider: Some(Arc::new(DataUrls)),
        font_ctx: Some(fonts.clone()),
        ..Default::default()
    };
    let mut doc = HtmlDocument::from_html(html, config);
    settle(&mut doc);
    let body = doc.query_selector("body").ok().flatten().and_then(|id| doc.get_node(id)).expect("a page has a body");
    let width = body.final_layout().size.width.round().max(1.0) as u32;
    let height = body.scroll_height().max(doc.root_element().scroll_height()).round().max(1.0) as u32;
    doc.set_viewport(Viewport::new(width, height, 1.0, ColorScheme::Dark));
    settle(&mut doc);
    let rgba = render_to_buffer::<VelloCpuImageRenderer, _>(
        |scene| blitz_paint::paint_scene(scene, &mut doc, 1.0, width, height, 0, 0),
        width,
        height,
    );
    (rgba, width, height)
}

/// Premultiplied RGBA as a PNG, which stores it unpremultiplied
fn encode(mut rgba: Vec<u8>, width: u32, height: u32) -> io::Result<Vec<u8>> {
    for px in rgba.chunks_exact_mut(4) {
        let a = px[3] as u32;
        if a != 0 && a != 255 {
            for c in &mut px[..3] {
                *c = ((*c as u32 * 255 + a / 2) / a).min(255) as u8;
            }
        }
    }
    let mut out = Vec::new();
    let mut encoder = png::Encoder::new(&mut out, width, height);
    encoder.set_color(png::ColorType::Rgba);
    encoder.set_depth(png::BitDepth::Eight);
    encoder.set_compression(png::Compression::Fast);
    // zlib's fastest level: 13% smaller than the fast setting's own deflate for 12% more time, and still about a quarter
    // of Chromium's time. The bot keeps 12 images per player in memory, so the bytes add up
    encoder.set_deflate_compression(png::DeflateCompression::Level(1));
    encoder.write_header()?.write_image_data(&rgba)?;
    Ok(out)
}

/// Stylo's switches for the selectors and properties the images use, and the font context every page shares
fn font_context() -> FontContext {
    stylo_static_prefs::set_pref!("layout.css.has-selector.enabled", true);
    stylo_static_prefs::set_pref!("layout.css.text-overflow.enabled", true);
    FontContext::default()
}

/// One long-lived worker: each page arrives on stdin as a little-endian u32 byte count and that much UTF-8 HTML, and
/// leaves on stdout as a u32 byte count and the PNG. A count of 0 means the page could not be drawn, and why goes to
/// stderr; the worker carries on with the next page. It stops when stdin closes.
fn main() -> io::Result<()> {
    let fonts = font_context();
    let mut input = BufReader::new(io::stdin().lock());
    let mut output = BufWriter::new(io::stdout().lock());
    loop {
        let mut size = [0u8; 4];
        match input.read_exact(&mut size) {
            Ok(()) => {}
            Err(e) if e.kind() == io::ErrorKind::UnexpectedEof => return Ok(()),
            Err(e) => return Err(e),
        }
        let mut html = vec![0u8; u32::from_le_bytes(size) as usize];
        input.read_exact(&mut html)?;
        let png = match String::from_utf8(html) {
            Ok(html) => catch_unwind(AssertUnwindSafe(|| {
                let (rgba, width, height) = render(&html, &fonts);
                encode(rgba, width, height)
            }))
            .map_err(|panic| panic.downcast_ref::<&str>().map_or("the renderer panicked".to_owned(), |s| s.to_string()))
            .and_then(|png| png.map_err(|e| e.to_string())),
            Err(e) => Err(e.to_string()),
        };
        let png = png.unwrap_or_else(|why| {
            eprintln!("blitz: {why}");
            Vec::new()
        });
        output.write_all(&(png.len() as u32).to_le_bytes())?;
        output.write_all(&png)?;
        output.flush()?;
    }
}

#[cfg(test)]
mod tests {
    use super::{font_context, render};

    /// The colour of one pixel of a 40px-wide page whose body is `body`, styled by `css`
    fn pixel(css: &str, body: &str, x: u32, y: u32) -> [u8; 3] {
        let html = format!(
            "<!DOCTYPE html><html><head><style>body {{ margin: 0; width: 40px; background: #fff; }} {css}</style></head><body>{body}</body></html>"
        );
        let (rgba, w, _) = render(&html, &font_context());
        let i = ((y * w + x) * 4) as usize;
        [rgba[i], rgba[i + 1], rgba[i + 2]]
    }

    fn near(got: [u8; 3], want: [u8; 3]) -> bool {
        got.iter().zip(want).all(|(g, w)| g.abs_diff(w) <= 12)
    }

    #[test]
    fn page_css_reaches_inline_svg() {
        let got = pixel(".a { fill: #ff0000; }", r#"<svg width="40" height="40"><rect class="a" width="40" height="40"/></svg>"#, 20, 20);
        assert!(near(got, [255, 0, 0]), "{got:?}");
    }

    #[test]
    fn a_use_copy_inherits_from_the_use() {
        let body = r##"<svg width="40" height="40"><defs><rect id="r" width="40" height="40"/></defs><use href="#r" fill="#00ff00"/></svg>"##;
        let got = pixel("", body, 20, 20);
        assert!(near(got, [0, 255, 0]), "{got:?}");
    }

    #[test]
    fn a_stop_placed_before_the_last_makes_a_hard_edge() {
        let css = ".g { height: 40px; background: linear-gradient(90deg, #ff0000 50%, #0000ff 0); }";
        assert!(near(pixel(css, r#"<div class="g"></div>"#, 10, 20), [255, 0, 0]));
        assert!(near(pixel(css, r#"<div class="g"></div>"#, 30, 20), [0, 0, 255]));
    }

    #[test]
    fn an_svg_background_repeats() {
        let svg = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='10'%3E%3Crect width='5' height='10' fill='%23ff0000'/%3E%3C/svg%3E";
        let css = format!(".t {{ height: 10px; background: url(\"{svg}\") 0 0 / 10px 10px repeat-x; }}");
        assert!(near(pixel(&css, r#"<div class="t"></div>"#, 32, 5), [255, 0, 0]), "the fourth tile");
        assert!(near(pixel(&css, r#"<div class="t"></div>"#, 37, 5), [255, 255, 255]), "the gap in it");
    }

    #[test]
    fn a_filter_list_runs_every_filter() {
        let css = ".f { height: 40px; background: #ff0000; filter: grayscale(1) brightness(0.5); }";
        let [r, g, b] = pixel(css, r#"<div class="f"></div>"#, 20, 20);
        assert!(r.abs_diff(g) <= 2 && g.abs_diff(b) <= 2 && r < 40, "{:?}", [r, g, b]);
    }
}
