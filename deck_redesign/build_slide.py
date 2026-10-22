# -*- coding: utf-8 -*-
"""Rebuild slide 'Alur Kerja AEGIS-Health' in the deck's editorial theme.

Palette (sampled from the deck): navy #003171, teal #007A70, white bg,
hairline #E4E1D8, muted gray text #55524B, arrow gray #9A978F.
Fonts: Arial (titles) + Inter (body) — matching the deck.
"""
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE, MSO_CONNECTOR
from pptx.enum.dml import MSO_LINE_DASH_STYLE
from pptx.oxml.ns import qn
import copy

NAVY = RGBColor(0x00, 0x31, 0x71)
TEAL = RGBColor(0x00, 0x7A, 0x70)
GRAY = RGBColor(0x55, 0x52, 0x4B)
LGRAY = RGBColor(0x8A, 0x87, 0x80)
HAIR = RGBColor(0xE4, 0xE1, 0xD8)
LINE = RGBColor(0xB5, 0xB2, 0xAA)
TEAL_TINT = RGBColor(0xEF, 0xF6, 0xF5)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)

prs = Presentation()
prs.slide_width = Inches(13.333)
prs.slide_height = Inches(7.5)
slide = prs.slides.add_slide(prs.slide_layouts[6])  # blank


def add_text(x, y, w, h, runs, size, color, bold=False, align=PP_ALIGN.LEFT,
             font="Inter", spacing=None, anchor=MSO_ANCHOR.TOP, line_spacing=None,
             space_after=0):
    """runs: str or list of (text, dict-overrides) tuples."""
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    p = tf.paragraphs[0]
    p.alignment = align
    if line_spacing:
        p.line_spacing = line_spacing
    if space_after:
        p.space_after = Pt(space_after)
    if isinstance(runs, str):
        runs = [(runs, {})]
    for text, ov in runs:
        r = p.add_run()
        r.text = text
        r.font.name = ov.get("font", font)
        r.font.size = Pt(ov.get("size", size))
        r.font.bold = ov.get("bold", bold)
        r.font.color.rgb = ov.get("color", color)
        spc = ov.get("spacing", spacing)
        if spc:
            r.font._rPr.set("spc", str(spc))
    return tb


def hairline(x, y, w, color=HAIR, weight=0.75, dashed=False):
    ln = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(x), Inches(y),
                                    Inches(x + w), Inches(y))
    ln.line.color.rgb = color
    ln.line.width = Pt(weight)
    if dashed:
        ln.line.dash_style = MSO_LINE_DASH_STYLE.DASH
    return ln


def add_arrowhead(connector, end=True):
    ln_el = connector.line._get_or_add_ln()
    head = ln_el.makeelement(qn("a:tailEnd"), {"type": "triangle", "w": "med", "len": "med"})
    ln_el.append(head)


def polyline_arrow(points, color=LINE, weight=1.0, dashed=False):
    """Draw connected segments; arrowhead on the last segment."""
    for i in range(len(points) - 1):
        (x1, y1), (x2, y2) = points[i], points[i + 1]
        ln = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(x1), Inches(y1),
                                        Inches(x2), Inches(y2))
        ln.line.color.rgb = color
        ln.line.width = Pt(weight)
        if dashed:
            ln.line.dash_style = MSO_LINE_DASH_STYLE.DASH
        if i == len(points) - 2:
            add_arrowhead(ln)


# ---------------- header ----------------
add_text(0.62, 0.40, 6.0, 0.26, "WORKFLOW AEGIS-HEALTH", 10.5, TEAL, bold=True,
         font="Arial", spacing=160)
add_text(9.2, 0.40, 3.51, 0.26, "AEGIS-HEALTH · E-JAK", 10.5, LGRAY, bold=True,
         font="Arial", spacing=160, align=PP_ALIGN.RIGHT)

add_text(0.62, 0.74, 11.6, 0.55, "Dari input klaim hingga keputusan verifier BPJS",
         29, NAVY, bold=True, font="Arial")
add_text(0.62, 1.26, 11.8, 0.30,
         "Delapan langkah dari input klaim sampai audit trail — keputusan akhir tetap di verifier BPJS.",
         11.5, GRAY, font="Inter")
hairline(0.62, 1.66, 12.09)

# ---------------- cards ----------------
MARGIN = 0.62
GAP = 0.30
CARD_W = (13.333 - 2 * MARGIN - 3 * GAP) / 4  # 2.823
ROW_Y = [1.92, 4.18]
CARD_H = 1.98

steps = [
    ("01", "Input klaim di E-Klaim",
     "Diagnosis, tindakan, obat, lama rawat, biaya, dan dokumen pendukung."),
    ("02", "Klaim terkirim ke BPJS",
     "Klaim memiliki ID sumber dan waktu penerimaan."),
    ("03", "Klaim masuk ke AEGIS",
     "Dikonversi ke format klaim standar; provenance dicatat."),
    ("04", "Validasi otomatis",
     "Data quality, validasi tanggal & field, cek duplikasi."),
    ("05", "Tiga agen menganalisis paralel",
     "Clinical — diagnosis, severity, LOS.  Financial — benchmark, deviasi.  "
     "Pattern — similarity, unbundling."),
    ("06", "Hasil agen jadi evidence",
     "Coverage, sinyal yang saling mendukung, dan uncertainty."),
    ("07", "Risk Engine menghitung prioritas",
     "Skor risiko 0–100, kategori High / Medium / Low, rekomendasi aksi."),
    ("08", "Verifier memutuskan",
     "Valid · Klarifikasi · Eskalasi — tiap keputusan masuk audit trail."),
]

for idx, (num, title, body) in enumerate(steps):
    row, col = divmod(idx, 4)
    x = MARGIN + col * (CARD_W + GAP)
    y = ROW_Y[row]
    accent = (num == "07")
    box = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(x), Inches(y),
                                 Inches(CARD_W), Inches(CARD_H))
    box.fill.solid()
    box.fill.fore_color.rgb = TEAL_TINT if accent else WHITE
    box.line.color.rgb = TEAL if accent else HAIR
    box.line.width = Pt(1.25 if accent else 1.0)
    box.shadow.inherit = False
    # drop the theme style ref entirely so no preset shadow/effect can apply
    style_el = box._element.find(qn("p:style"))
    if style_el is not None:
        box._element.remove(style_el)
    pad = 0.16
    add_text(x + pad, y + 0.13, CARD_W - 2 * pad, 0.26, num, 13, TEAL, bold=True,
             font="Arial", spacing=100)
    add_text(x + pad, y + 0.42, CARD_W - 2 * pad, 0.62, title, 12.5, NAVY, bold=True,
             font="Arial", line_spacing=1.0)
    add_text(x + pad, y + 1.02, CARD_W - 2 * pad, 0.80, body, 9, GRAY, font="Inter",
             line_spacing=1.12)
    if accent:
        add_text(x + pad, y + CARD_H - 0.34, CARD_W - 2 * pad, 0.22,
                 "DETERMINISTIK · NON-LLM", 7.5, TEAL, bold=True, font="Arial",
                 spacing=120)

# arrows within rows
for row in range(2):
    ay = ROW_Y[row] + CARD_H / 2
    for col in range(3):
        x1 = MARGIN + col * (CARD_W + GAP) + CARD_W + 0.05
        x2 = x1 + GAP - 0.10
        ln = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(x1), Inches(ay),
                                        Inches(x2), Inches(ay))
        ln.line.color.rgb = LINE
        ln.line.width = Pt(1.0)
        add_arrowhead(ln)

# row 1 -> row 2 elbow (right end of row 1 down, across, into card 05)
x_end = MARGIN + 3 * (CARD_W + GAP) + CARD_W / 2   # card 04 center
x_start = MARGIN + CARD_W / 2                       # card 05 center
mid_y = (ROW_Y[0] + CARD_H + ROW_Y[1]) / 2          # between rows
polyline_arrow([(x_end, ROW_Y[0] + CARD_H + 0.02), (x_end, mid_y),
                (x_start, mid_y), (x_start, ROW_Y[1] - 0.04)])

# feedback loop (verifier -> evaluation), dashed
fb_y = ROW_Y[1] + CARD_H + 0.30
polyline_arrow([(x_end, ROW_Y[1] + CARD_H + 0.02), (x_end, fb_y),
                (x_start, fb_y), (x_start, ROW_Y[1] + CARD_H + 0.06)], dashed=True)
# label with white background so the dashes don't strike through the text
lbl = slide.shapes.add_textbox(Inches(4.47), Inches(fb_y - 0.13), Inches(4.4), Inches(0.26))
lbl.fill.solid()
lbl.fill.fore_color.rgb = WHITE
lbl.line.fill.background()
ltf = lbl.text_frame
ltf.word_wrap = False
ltf.margin_left = ltf.margin_right = Inches(0.08)
ltf.margin_top = ltf.margin_bottom = 0
p = ltf.paragraphs[0]
p.alignment = PP_ALIGN.CENTER
r = p.add_run()
r.text = "Feedback keputusan verifier → evaluasi model"
r.font.name = "Inter"
r.font.size = Pt(9)
r.font.italic = True
r.font.color.rgb = LGRAY

# ---------------- footer ----------------
hairline(0.62, 7.02, 12.09)
add_text(0.62, 7.10, 6.0, 0.24, "AEGIS-HEALTH · E-JAK", 8.5, LGRAY, font="Arial",
         spacing=140)
add_text(7.2, 7.10, 5.51, 0.24, "ALUR KERJA", 8.5, LGRAY, font="Arial", spacing=140,
         align=PP_ALIGN.RIGHT)

prs.save(r"C:\Users\Radith\E-Jak\deck_redesign\alur_kerja_aegis.pptx")
print("saved")
