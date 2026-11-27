use anyrender::{
    Filter,
    filters::{EdgeMode, FilterEffect},
};
use vello_common::filter_effects::FilterPrimitive;

pub(crate) fn convert_filter(filter: &Filter) -> Option<vello_common::filter_effects::Filter> {
    let nodes = filter.nodes();
    if nodes.is_empty() {
        return None;
    }

    // Vello CPU applies a graph's primitives one after another, so a CSS filter list (a chain, each node taking the one
    // before as input) maps on directly. A list with a primitive Vello cannot draw is dropped whole, as a single one is.
    let mut graph = vello_common::filter_effects::FilterGraph::new();
    for node in nodes {
        let id = graph.add(convert_filter_effect(&node.effect)?, None);
        graph.set_output(id);
    }
    Some(vello_common::filter_effects::Filter {
        graph: std::sync::Arc::new(graph),
    })
}

pub(crate) fn convert_filter_effect(effect: &FilterEffect) -> Option<FilterPrimitive> {
    Some(match effect {
        FilterEffect::Flood(color) => FilterPrimitive::Flood { color: *color },
        FilterEffect::GaussianBlur(blur) => FilterPrimitive::GaussianBlur {
            std_deviation_x: blur.std_deviation_x,
            std_deviation_y: blur.std_deviation_y,
            edge_mode: convert_edge_mode(blur.edge_mode),
        },
        // Vello has one standard deviation for both axes.
        FilterEffect::DropShadow(shadow) if shadow.std_deviation_x != shadow.std_deviation_y => {
            return None;
        }
        FilterEffect::DropShadow(shadow) => FilterPrimitive::DropShadow {
            dx: shadow.dx,
            dy: shadow.dy,
            std_deviation: shadow.std_deviation_x,
            color: shadow.color,
            edge_mode: convert_edge_mode(shadow.edge_mode),
        },
        FilterEffect::Offset(offset) => FilterPrimitive::Offset {
            dx: offset.x as f32,
            dy: offset.y as f32,
        },
        FilterEffect::ColorMatrix(matrix) => FilterPrimitive::ColorMatrix { matrix: matrix.0 },
        FilterEffect::ComponentTransfer(_component_transfer_filter) => return None,
        FilterEffect::Blend(_mode) => return None,
        FilterEffect::Composite(_composite_operator) => return None,
        FilterEffect::Morphology(_morphology_filter) => return None,
        FilterEffect::ConvolveMatrix(_convolution_kernel) => return None,
        FilterEffect::Turbulence(_turbulence_filter) => return None,
        FilterEffect::DisplacementMap(_displacement_map_filter) => return None,
        FilterEffect::Image(_external_image_source) => return None,
        FilterEffect::Tile => return None,
        FilterEffect::DiffuseLighting(_diffuse_lighting_filter) => return None,
        FilterEffect::SpecularLighting(_specular_lighting_filter) => return None,
    })
}

fn convert_edge_mode(edge_mode: EdgeMode) -> vello_common::filter_effects::EdgeMode {
    match edge_mode {
        EdgeMode::Duplicate => vello_common::filter_effects::EdgeMode::Duplicate,
        EdgeMode::Wrap => vello_common::filter_effects::EdgeMode::Wrap,
        EdgeMode::Mirror => vello_common::filter_effects::EdgeMode::Mirror,
        EdgeMode::None => vello_common::filter_effects::EdgeMode::None,
    }
}
