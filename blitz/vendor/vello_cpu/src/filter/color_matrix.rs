//! `feColorMatrix`, on a premultiplied pixmap.

use vello_common::peniko::color::PremulRgba8;
use vello_common::pixmap::Pixmap;

/// Apply a 4x5 colour matrix to every pixel. The matrix works on unpremultiplied channels in 0 to 1, so each pixel is
/// unpremultiplied first and premultiplied again after.
pub(crate) fn apply(matrix: &[f32; 20], pixmap: &mut Pixmap) {
    for px in pixmap.data_mut() {
        let a = px.a as f32 / 255.0;
        let unpremul = |c: u8| if a > 0.0 { c as f32 / 255.0 / a } else { 0.0 };
        let input = [unpremul(px.r), unpremul(px.g), unpremul(px.b), a];
        let row = |i: usize| {
            let m = &matrix[i * 5..i * 5 + 5];
            (m[0] * input[0] + m[1] * input[1] + m[2] * input[2] + m[3] * input[3] + m[4])
                .clamp(0.0, 1.0)
        };
        let out_a = row(3);
        let premul = |v: f32| (v * out_a * 255.0 + 0.5) as u8;
        *px = PremulRgba8 {
            r: premul(row(0)),
            g: premul(row(1)),
            b: premul(row(2)),
            a: (out_a * 255.0 + 0.5) as u8,
        };
    }
}

#[cfg(test)]
mod tests {
    use super::apply;
    use vello_common::peniko::color::PremulRgba8;
    use vello_common::pixmap::Pixmap;

    #[test]
    fn grayscale_keeps_alpha_and_evens_the_channels() {
        let mut pixmap = Pixmap::new(1, 1);
        pixmap.set_pixel(
            0,
            0,
            PremulRgba8 {
                r: 128,
                g: 0,
                b: 0,
                a: 128,
            },
        );
        let g = [0.2126, 0.7152, 0.0722, 0.0, 0.0];
        let mut m = [0.0; 20];
        for row in 0..3 {
            m[row * 5..row * 5 + 5].copy_from_slice(&g);
        }
        m[18] = 1.0;
        apply(&m, &mut pixmap);
        let px = pixmap.sample(0, 0);
        assert_eq!(px.a, 128);
        assert!(
            px.r == px.g && px.g == px.b && (26..=28).contains(&px.r),
            "{px:?}"
        );
    }
}
