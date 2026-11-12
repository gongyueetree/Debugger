#!/usr/bin/env python3
"""Write the KiCad project file (design rules, net classes).  usage: gen_pro.py <out.kicad_pro>"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import design as D


def netclass(name, width, priority):
    return {"name": name, "clearance": D.CLEARANCE, "track_width": width, "via_diameter": D.VIA_D,
            "via_drill": D.VIA_DRILL, "diff_pair_gap": 0.2, "diff_pair_via_gap": 0.25, "diff_pair_width": 0.2,
            "microvia_diameter": 0.3, "microvia_drill": 0.1, "bus_width": 12, "wire_width": 6, "line_style": 0,
            "pcb_color": "rgba(0, 0, 0, 0.000)", "schematic_color": "rgba(0, 0, 0, 0.000)", "priority": priority}


power = sorted(n for n, w in D.WIDTHS.items() if w >= 0.25)
pro = {
    "board": {
        "design_settings": {
            "defaults": {"board_outline_line_width": 0.1, "copper_line_width": 0.2, "silk_line_width": 0.12,
                         "silk_text_size_h": 0.8, "silk_text_size_v": 0.8, "silk_text_thickness": 0.12},
            "rules": {
                "min_clearance": D.CLEARANCE, "min_track_width": D.DEFAULT_WIDTH, "min_connection": 0.0,
                "min_copper_edge_clearance": 0.3, "min_hole_clearance": 0.2, "min_hole_to_hole": 0.25,
                "min_via_diameter": 0.5, "min_via_annular_width": 0.1, "min_through_hole_diameter": 0.3,
                "min_microvia_diameter": 0.2, "min_microvia_drill": 0.1, "min_resolved_spokes": 1,
                "min_silk_clearance": 0.0, "min_text_height": 0.6, "min_text_thickness": 0.08,
                "solder_mask_to_copper_clearance": 0.0, "max_error": 0.005,
                "allow_blind_buried_vias": False, "allow_microvias": False, "use_height_for_length_calcs": True},
            "rule_severities": {"silk_over_copper": "ignore", "silk_overlap": "warning", "silk_edge_clearance": "warning",
                                "lib_footprint_mismatch": "ignore", "lib_footprint_issues": "ignore"},
            "track_widths": [0.0, 0.15, 0.2, 0.25, 0.3, 0.4],
            "via_dimensions": [{"diameter": 0.0, "drill": 0.0}, {"diameter": D.VIA_D, "drill": D.VIA_DRILL}],
            "zones_allow_external_fillets": False},
        "layer_presets": [], "viewports": []},
    "boards": [],
    "libraries": {"pinned_footprint_libs": [D.LIB], "pinned_symbol_libs": []},
    "meta": {"filename": f"{D.PROJECT}.kicad_pro", "version": 3},
    "net_settings": {
        "classes": [netclass("Default", D.DEFAULT_WIDTH, 2147483647), netclass("Power", 0.4, 0)],
        "meta": {"version": 4},
        "net_colors": None,
        "netclass_assignments": None,
        "netclass_patterns": [{"netclass": "Power", "pattern": p if p[0] == '+' or p == 'GND' else '/' + p} for p in power]},
    "pcbnew": {"last_paths": {}, "page_layout_descr_file": ""},
    "schematic": {"legacy_lib_dir": "", "legacy_lib_list": []},
    "sheets": [],
    "text_variables": {},
}
with open(sys.argv[1], 'w') as f:
    json.dump(pro, f, indent=2)
    f.write('\n')
print('wrote', sys.argv[1])
