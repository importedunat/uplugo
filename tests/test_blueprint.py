# SPDX-License-Identifier: GPL-3.0-only
"""Input-to-picture behavior; no display server or controller required."""
import unittest
import xml.etree.ElementTree as ET

from controller_blueprint import blueprint_svg
from input_state import BUTTON_NAMES


def elements(svg):
    return {node.get('id'): node for node in ET.fromstring(svg).iter() if node.get('id')}


class BlueprintTests(unittest.TestCase):
    def test_pressed_and_observed_use_different_shapes_without_color(self):
        def markers(svg):
            return {node.get('data-marker'):node for node in ET.fromstring(svg).iter() if node.get('data-marker')}
        current=markers(blueprint_svg(held=['×'],seen=['×','○']))
        self.assertEqual(current['×'].get('data-state'),'pressed')
        self.assertEqual(len(list(current['×'].iter('{http://www.w3.org/2000/svg}circle'))),2)
        self.assertEqual(current['○'].get('data-state'),'observed')
        self.assertEqual(len(list(current['○'].iter('{http://www.w3.org/2000/svg}path'))),1)
        stale=markers(blueprint_svg(seen=['×']))
        self.assertEqual(stale['×'].get('data-state'),'observed')
        self.assertEqual(markers(blueprint_svg()),{})

    def test_touch_points_follow_player_coordinates_without_pressing_click(self):
        nodes=elements(blueprint_svg(touches=[(0,127,0,0),(1,0,1919,1079)]))
        self.assertEqual(nodes['touch-0'].get('data-contact'),'127')
        self.assertEqual(nodes['touch-1'].get('data-contact'),'0')
        first,second=list(nodes['touch-0'])[0],list(nodes['touch-1'])[0]
        self.assertLess(float(first.get('cx')),float(second.get('cx')))
        self.assertLess(float(first.get('cy')),float(second.get('cy')))
        self.assertEqual(nodes['key-Touchpad'].get('data-pressed'),'false')
        self.assertNotIn('touch-0',elements(blueprint_svg(touches=[])))
        self.assertNotIn('touch-0',elements(blueprint_svg(seen=['Touchpad'])))

    def test_invalid_touch_points_are_not_drawn_on_the_edges(self):
        nodes=elements(blueprint_svg(touches=[(0,0,-1,0),(1,1,1920,1080)]))
        self.assertNotIn('touch-0',nodes)
        self.assertNotIn('touch-1',nodes)

    def test_every_standard_button_has_one_independent_highlight(self):
        for pressed in BUTTON_NAMES:
            root = ET.fromstring(blueprint_svg([pressed], [pressed]))
            controls = [node for node in root.iter() if 'data-name' in node.attrib]
            self.assertEqual(len(controls), len(BUTTON_NAMES))
            self.assertEqual({node.get('data-name') for node in controls}, set(BUTTON_NAMES))
            self.assertEqual([node.get('data-name') for node in controls
                              if node.get('data-pressed') == 'true'], [pressed])

    def test_sticks_follow_player_direction_and_trigger_travel_is_independent(self):
        nodes = elements(blueprint_svg(sticks=[0, 255, 255, 0], triggers=[128, 255]))
        self.assertEqual((nodes['stick-0'].get('data-x'), nodes['stick-0'].get('data-y')), ('-18.0', '18.0'))
        self.assertEqual((nodes['stick-1'].get('data-x'), nodes['stick-1'].get('data-y')), ('18.0', '-18.0'))
        self.assertAlmostEqual(float(nodes['travel-L2'].get('width')), 20.08)
        self.assertEqual(float(nodes['travel-R2'].get('width')), 40)
        self.assertEqual(nodes['key-L2'].get('data-pressed'), 'false')

    def test_missing_sample_clears_motion_and_keeps_seen_only(self):
        svg = blueprint_svg(seen=['×', 'L3'])
        nodes = elements(svg)
        self.assertEqual(nodes['key-×'].get('data-seen'), 'true')
        self.assertEqual(nodes['key-×'].get('data-pressed'), 'false')
        self.assertEqual(nodes['stick-0'].get('data-x'), '0.0')
        self.assertNotIn('travel-L2', nodes)
        self.assertIn('X —   Y —', svg)

    def test_out_of_range_motion_cannot_escape_the_mechanism(self):
        nodes = elements(blueprint_svg(sticks=[-100, 400, 400, -100], triggers=[999, -1]))
        self.assertEqual(nodes['stick-0'].get('data-x'), '-18.0')
        self.assertEqual(nodes['stick-1'].get('data-y'), '-18.0')
        self.assertEqual(float(nodes['travel-L2'].get('width')), 40)
        self.assertNotIn('travel-R2', nodes)
