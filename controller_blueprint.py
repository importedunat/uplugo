# SPDX-License-Identifier: GPL-3.0-only
"""Live front-view schematic; the physical geometry is a separately licensed SVG.

Geometry © 2024 the_al, MIT; see assets/dualsense-blueprint.LICENSE.txt.
The front view follows the player's left/right. L2/R2 are exploded above the
shoulders so their travel is visible. This is not a dimensioned engineering plan.
"""
from functools import lru_cache
from i18n import _
from html import escape
from pathlib import Path
from input_state import TOUCH_WIDTH, TOUCH_HEIGHT
import re
import xml.etree.ElementTree as ET

WIDTH, HEIGHT = 900, 560
INK = '#90bed4'
DIM = '#42687f'
FILL = '#122e42'
PRESSED = '#087eae'
SEEN = '#8ce6f3'
# The imported shapes use the original unscaled 910 × 735 coordinate system.
SCALE, OFFSET_X, OFFSET_Y = .62, 168, 40
GEOMETRY = Path(__file__).resolve().parent/'assets/dualsense-blueprint.svg'


@lru_cache(maxsize=1)
def geometry():
    root = ET.parse(GEOMETRY).getroot()
    nodes = {}
    for node in root.iter():
        nodes.setdefault(node.get('id'), node)
        node.tag = node.tag.rsplit('}', 1)[-1]
    result = {}
    for key, node in nodes.items():
        if key:
            result[key] = ''.join(ET.tostring(child, encoding='unicode') for child in node) if node.tag == 'g' else ET.tostring(node, encoding='unicode')
    # The compound outline includes the left/right shell panels and inner seam.
    outline = nodes['Controller_outline'].get('d')
    regions = re.split(r'(?=M)', outline)
    result['shell_fill'] = f'<path d="{regions[1]}"/>'
    result['panels_fill'] = ''.join(f'<path d="{region}"/>' for region in regions
                                   if region.startswith(('M63.74,', 'M902.84,')))
    return result


def position(x, y):
    return round(OFFSET_X+x*SCALE, 2), round(OFFSET_Y+y*SCALE, 2)


def text(x, y, value, size=16, color='#d4ecf6', anchor='middle'):
    return (f'<text x="{x}" y="{y}" text-anchor="{anchor}" dominant-baseline="central" '
            f'font-family="sans-serif" font-size="{size}" fill="{color}">{escape(value)}</text>')


def blueprint_svg(held=(), seen=(), sticks=None, triggers=None, touches=None, layer='all'):
    held, seen = set(held), set(seen)
    live = sticks is not None and triggers is not None
    sticks = sticks if live else [127.5]*4
    triggers = triggers if live else [0, 0]
    shapes = geometry()
    header = f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}">'
    static = [f'''
<defs>
 <pattern id="grid" width="25" height="25" patternUnits="userSpaceOnUse"><path d="M25 0H0V25" fill="none" stroke="#284a60" stroke-width=".6"/></pattern>
 <pattern id="major" width="125" height="125" patternUnits="userSpaceOnUse"><rect width="125" height="125" fill="url(#grid)"/><path d="M125 0H0V125" fill="none" stroke="#3b6075" stroke-width=".7"/></pattern>
</defs>
<rect x="1" y="1" width="898" height="558" rx="14" fill="#0b2030" stroke="#33576d"/>
<rect x="14" y="14" width="872" height="532" rx="5" fill="url(#major)" opacity=".5"/>
<path d="M25 43V25H43 M857 25H875V43 M25 517V535H43 M857 535H875V517" fill="none" stroke="{DIM}"/>
<path d="M450 58V508 M145 222H757 M293 300H607" fill="none" stroke="#537b92" stroke-dasharray="5 7" opacity=".35"/>
''']
    static += [text(38, 42, 'DUALSENSE', 14, '#9cbdcf', 'start'),
              text(862, 42, _('VISTA FRONTAL'), 12, '#9cbdcf', 'end'),
              text(450, 73, _('L2 / R2 · vista expandida'), 12, '#9cbdcf')]
    transform = f'translate({OFFSET_X} {OFFSET_Y}) scale({SCALE})'
    static.append(f'<g transform="{transform}" fill="#0d2638">{shapes["shell_fill"]}</g>')
    static.append(f'<g transform="{transform}" fill="#17354a">{shapes["panels_fill"]}</g>')
    static.append(f'<g transform="{transform}" fill="{INK}">{shapes["Controller"]}</g>')
    parts = []

    def marker(x, y, active=False):
        return (f'<circle cx="{x}" cy="{y}" r="7" fill="#0b2939" stroke="{SEEN}"/>'
                +(f'<circle cx="{x}" cy="{y}" r="3" fill="{SEEN}"/>' if active else
                  f'<path d="M{x-3} {y}l2 2 4-4" fill="none" stroke="{SEEN}" stroke-width="1.5"/>'))

    def control(name, source, center=None, caption=None, check_at=None, dx=0, dy=0):
        active, observed = name in held, name in seen
        outline = source if source in ('L1', 'R1') else source+'_outline'
        parts.append(f'<g id="key-{escape(name, quote=True)}" data-name="{escape(name, quote=True)}" '
                     f'data-pressed="{str(active).lower()}" data-seen="{str(observed).lower()}" '
                     f'transform="{transform}"><g transform="translate({dx} {dy})">')
        parts.append(f'<g fill="{PRESSED if active else FILL}">{shapes[source+"_infill"]}</g>')
        parts.append(f'<g fill="{SEEN if active or observed else INK}">{shapes[outline]}</g></g></g>')
        if caption and center:
            parts.append(text(*position(center[0]+dx, center[1]+dy), caption, 14))
        if check_at and (active or observed):
            parts.append(f'<g data-marker="{escape(name, quote=True)}" data-state="{"pressed" if active else "observed"}">'
                         +marker(*position(*check_at),active=active)+'</g>')

    def leader(points, caption, x, y, anchor='middle'):
        static.append(f'<polyline points="{points}" fill="none" stroke="{DIM}" stroke-width="1"/>')
        static.append(text(x, y, caption, 13, '#accbdc', anchor))

    # Shoulder buttons retain the actual curved outline. The expanded trigger
    # view is explicitly labelled; no guess at their hidden front-view surface.
    for index, x in enumerate((160, 750)):
        name = ('L2', 'R2')[index]
        raw = max(0, min(255, triggers[index]))
        control(name, name, (x, 46), name, (x+43, 15))
        parts.append(text(*position(x, 83), f'{round(raw/255*100)}%' if live else '—', 13))
        px, py = position(x-32, 100)
        parts.append(f'<rect x="{px}" y="{py}" width="40" height="3" rx="1.5" fill="{DIM}"/>')
        if live and raw:
            parts.append(f'<rect id="travel-{name}" x="{px}" y="{py}" width="{raw/255*40:.2f}" height="3" rx="1.5" fill="{SEEN}"/>')
        control(('L1','R1')[index], ('L1','R1')[index], check_at=(x, 130))
    leader('269,132 224,105 197,105', 'L1', 185, 105)
    leader('632,132 676,105 703,105', 'R1', 715, 105)

    control('Touchpad', 'Trackpad', (454, 236), None if touches else 'TOUCHPAD', (595, 298))
    for slot, contact_id, x, y in touches or ():
        if slot not in (0, 1) or not (0 <= x < TOUCH_WIDTH and 0 <= y < TOUCH_HEIGHT):
            continue
        # Project the sensor surface inside the tapered physical outline.
        # This is a visual guide; raw sensor coordinates remain in Details.
        u, v = x / (TOUCH_WIDTH-1), y / (TOUCH_HEIGHT-1)
        px, py = position(280+25*v+u*(348-50*v), 166+143*v)
        color = '#8ce6f3' if slot == 0 else '#ffd27b'
        parts.append(f'<g id="touch-{slot}" data-contact="{contact_id}" data-x="{x}" data-y="{y}">'
                     f'<circle cx="{px:.2f}" cy="{py:.2f}" r="11" fill="#0b2030" stroke="{color}" stroke-width="2"/>'
                     + text(px, py+4, str(slot+1), 13, color) + '</g>')
    # Blue light rails flank the touchpad; speaker holes and shell seams remain
    # in the physical geometry rather than generic circles/rectangles.
    static.append(f'<g transform="{transform}" fill="none" stroke="#51bfe6" stroke-width="3" opacity=".8"><path d="M248 176L271 291Q277 325 305 337 M660 176L637 291Q631 325 603 337"/></g>')

    for name, source, center, mark in [
        ('↑','Up',(158,250),(186,229)), ('→','Right',(207,295),(229,274)),
        ('↓','Down',(158,342),(186,361)), ('←','Left',(109,295),(88,274)),
        ('△','Triangle',(751,235),(779,212)), ('○','Circle',(814,294),(842,271)),
        ('×','Cross',(751,352),(779,375)), ('□','Square',(689,294),(660,271))]:
        control(name, source, check_at=mark)
        x, y = position(*center)
        # Vector symbols keep the real shape independent of font substitution.
        if name == '△':symbol=f'<path d="M{x} {y-9}l10 17h-20Z"/>'
        elif name == '○':symbol=f'<circle cx="{x}" cy="{y}" r="9"/>'
        elif name == '×':symbol=f'<path d="M{x-7} {y-7}l14 14 M{x+7} {y-7}l-14 14"/>'
        elif name == '□':symbol=f'<rect x="{x-8}" y="{y-8}" width="16" height="16"/>'
        else:
            angle={'↑':0,'→':90,'↓':180,'←':270}[name]
            symbol=f'<path transform="rotate({angle} {x} {y})" d="M{x} {y-4}l4 6h-8Z"/>'
        parts.append(f'<g fill="none" stroke="#c4dfeb" stroke-width="1.5" stroke-linejoin="round">{symbol}</g>')

    control('Create','Create',check_at=(246,211))
    control('Options','Options',check_at=(667,211))
    leader('309,158 299,123 340,104','Create',355,99)
    leader('591,158 601,123 560,104','Options',545,99)

    for index, x in enumerate((295, 617)):
        dx=round((max(0,min(255,sticks[index*2]))-127.5)/127.5*18, 2)
        dy=round((max(0,min(255,sticks[index*2+1]))-127.5)/127.5*18, 2)
        name=('L3','R3')[index]
        static.append(f'<g transform="{transform}" fill="none" stroke="{DIM}" stroke-width="1.4"><path d="M{x-58} 420H{x+58} M{x} 362V478"/><circle cx="{x}" cy="420" r="52" stroke-dasharray="2 5"/></g>')
        control(name,name,(x,420),name,(x+50,375),dx,dy)
        px, py = position(x, 420)
        parts.append(f'<g id="stick-{index}" data-x="{dx}" data-y="{dy}"/>')
        values=[round((sticks[index*2+a]-127.5)/127.5*100) for a in (0,1)]
        leader(f'{px},{py+42} {px},405', _('ANALÓGICO ESQUERDO') if index==0 else _('ANALÓGICO DIREITO'), px, 425)
        parts.append(text(px, 447, f'X {values[0]:+d}%   Y {values[1]:+d}%' if live else 'X —   Y —', 13))

    control('PS','PS',(455,417),'PS',(483,397))
    control('Mute','Mute',check_at=(493,474))
    leader('450,341 450,366','Mute',450,380)
    static.append(text(450,529,_('Pressione os botões no controle físico'),13,'#9cbdcf'))
    return header+(''.join(static) if layer!='live' else '')+(''.join(parts) if layer!='static' else '')+'</svg>'
