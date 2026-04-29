from pathlib import Path
import xml.etree.ElementTree as ET
from PIL import Image, ImageDraw, ImageFont
import html
import re
import math

SRC = Path('/Users/ajithsai.kusal/Desktop/AIOps/diagrams/aiops-module-e2e-flows.drawio')
OUT_DIR = Path('/Users/ajithsai.kusal/Desktop/AIOps/diagrams/png')
OUT_DIR.mkdir(parents=True, exist_ok=True)

root = ET.fromstring(SRC.read_text())

FONT_CANDIDATES = [
    '/System/Library/Fonts/Supplemental/Arial.ttf',
    '/System/Library/Fonts/Supplemental/Helvetica.ttc',
    '/Library/Fonts/Arial.ttf',
]


def load_font(size: int):
    for font_path in FONT_CANDIDATES:
        try:
            return ImageFont.truetype(font_path, size=size)
        except Exception:
            pass
    return ImageFont.load_default()


FONT = load_font(24)
TITLE_FONT = load_font(34)
EDGE_LABEL_FONT = load_font(18)


def color_from_style(style: str, key: str, default: str) -> str:
    match = re.search(rf'{re.escape(key)}=([^;]+)', style or '')
    return match.group(1) if match else default


def shape_from_style(style: str) -> str:
    style = style or ''
    if 'rhombus' in style:
        return 'rhombus'
    if 'cylinder' in style:
        return 'cylinder'
    return 'rect'


def clean_text(value: str) -> str:
    if not value:
        return ''
    text = html.unescape(value)
    text = re.sub(r'<[^>]+>', '', text)
    return text.replace('\r', '')


def draw_wrapped_text(draw: ImageDraw.ImageDraw, text: str, box, font, fill='#111111', line_spacing=6):
    x, y, w, h = box
    logical_lines = text.split('\n') if text else ['']
    lines = []

    for logical_line in logical_lines:
        words = logical_line.split(' ')
        current = ''
        for word in words:
            candidate = (current + ' ' + word).strip()
            width = draw.textbbox((0, 0), candidate, font=font)[2]
            if width <= max(20, w - 20) or not current:
                current = candidate
            else:
                lines.append(current)
                current = word
        lines.append(current)

    line_height = draw.textbbox((0, 0), 'Ag', font=font)[3] + line_spacing
    total_height = max(0, len(lines) * line_height - line_spacing)
    cursor_y = y + (h - total_height) / 2

    for line in lines:
        text_width = draw.textbbox((0, 0), line, font=font)[2]
        cursor_x = x + (w - text_width) / 2
        draw.text((cursor_x, cursor_y), line, font=font, fill=fill)
        cursor_y += line_height


for index, diagram in enumerate(root.findall('diagram'), start=1):
    model = diagram.find('mxGraphModel')
    if model is None:
        continue

    nodes = {}
    edges = []

    for cell in model.findall('.//mxCell'):
        cell_id = cell.get('id')
        geometry = cell.find('mxGeometry')

        if cell.get('vertex') == '1' and geometry is not None:
            x = float(geometry.get('x', '0') or '0')
            y = float(geometry.get('y', '0') or '0')
            w = float(geometry.get('width', '0') or '0')
            h = float(geometry.get('height', '0') or '0')

            nodes[cell_id] = {
                'x': x,
                'y': y,
                'w': w,
                'h': h,
                'value': clean_text(cell.get('value', '')),
                'style': cell.get('style', ''),
            }

        if cell.get('edge') == '1':
            source = cell.get('source')
            target = cell.get('target')
            if source and target:
                edges.append((source, target, clean_text(cell.get('value', ''))))

    if not nodes:
        continue

    min_x = min(node['x'] for node in nodes.values())
    min_y = min(node['y'] for node in nodes.values())
    max_x = max(node['x'] + node['w'] for node in nodes.values())
    max_y = max(node['y'] + node['h'] for node in nodes.values())

    target_width = 2600
    target_height = 1600
    margin = 120

    content_width = max_x - min_x
    content_height = max_y - min_y
    scale_x = (target_width - 2 * margin) / content_width if content_width else 1
    scale_y = (target_height - 2 * margin) / content_height if content_height else 1
    scale = min(scale_x, scale_y)

    image = Image.new('RGB', (target_width, target_height), '#FFFFFF')
    draw = ImageDraw.Draw(image)

    def map_x(value):
        return margin + (value - min_x) * scale

    def map_y(value):
        return margin + (value - min_y) * scale

    for source, target, label in edges:
        if source not in nodes or target not in nodes:
            continue

        source_node = nodes[source]
        target_node = nodes[target]

        x1 = map_x(source_node['x'] + source_node['w'] / 2)
        y1 = map_y(source_node['y'] + source_node['h'] / 2)
        x2 = map_x(target_node['x'] + target_node['w'] / 2)
        y2 = map_y(target_node['y'] + target_node['h'] / 2)

        draw.line((x1, y1, x2, y2), fill='#4A5568', width=4)

        angle = math.atan2(y2 - y1, x2 - x1)
        arrow_size = 16
        p1 = (x2, y2)
        p2 = (x2 - arrow_size * math.cos(angle - math.pi / 6), y2 - arrow_size * math.sin(angle - math.pi / 6))
        p3 = (x2 - arrow_size * math.cos(angle + math.pi / 6), y2 - arrow_size * math.sin(angle + math.pi / 6))
        draw.polygon([p1, p2, p3], fill='#4A5568')

        if label:
            mx = (x1 + x2) / 2
            my = (y1 + y2) / 2
            draw.rectangle((mx - 30, my - 14, mx + 30, my + 14), fill='#FFFFFF')
            draw.text((mx - 22, my - 10), label, font=EDGE_LABEL_FONT, fill='#1A202C')

    for node in nodes.values():
        x = map_x(node['x'])
        y = map_y(node['y'])
        w = node['w'] * scale
        h = node['h'] * scale

        style = node['style']
        fill = color_from_style(style, 'fillColor', '#E2E8F0')
        stroke = color_from_style(style, 'strokeColor', '#4A5568')
        shape = shape_from_style(style)

        if shape == 'rhombus':
            points = [(x + w / 2, y), (x + w, y + h / 2), (x + w / 2, y + h), (x, y + h / 2)]
            draw.polygon(points, fill=fill, outline=stroke, width=4)
        elif shape == 'cylinder':
            radius = min(18, h * 0.14)
            draw.rounded_rectangle((x, y, x + w, y + h), radius=14, fill=fill, outline=stroke, width=4)
            draw.arc((x + 8, y - radius, x + w - 8, y + radius), start=0, end=180, fill=stroke, width=3)
            draw.arc((x + 8, y + h - radius, x + w - 8, y + h + radius), start=180, end=360, fill=stroke, width=3)
        else:
            if 'rounded=1' in style:
                draw.rounded_rectangle((x, y, x + w, y + h), radius=16, fill=fill, outline=stroke, width=4)
            else:
                draw.rectangle((x, y, x + w, y + h), fill=fill, outline=stroke, width=4)

        draw_wrapped_text(draw, node['value'], (x, y, w, h), FONT, fill='#111827')

    page_title = diagram.get('name', f'Page {index}')
    draw.text((60, 35), page_title, font=TITLE_FONT, fill='#111827')

    safe_name = re.sub(r'[^A-Za-z0-9]+', '-', page_title).strip('-').lower()
    output_file = OUT_DIR / f'{index:02d}-{safe_name}.png'
    image.save(output_file, 'PNG')
    print(output_file)

print('DONE')
