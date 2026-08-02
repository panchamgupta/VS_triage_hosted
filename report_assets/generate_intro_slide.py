from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter

W, H = 1920, 1080
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "report_assets" / "intro_slide_rgroup_report_1920x1080.png"


def load_font(size: int, bold: bool = False):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]
    for c in candidates:
        p = Path(c)
        if p.exists():
            return ImageFont.truetype(str(p), size)
    return ImageFont.load_default()


def panel(draw, xy, fill=(255, 255, 255, 245), radius=18, outline=(220, 228, 238), width=2):
    draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=width)


def fit_image(img: Image.Image, max_w: int, max_h: int) -> Image.Image:
    img = img.convert("RGBA")
    ratio = min(max_w / img.width, max_h / img.height)
    nw = max(1, int(img.width * ratio))
    nh = max(1, int(img.height * ratio))
    resample = getattr(Image, "Resampling", Image).LANCZOS
    return img.resize((nw, nh), resample)


def draw_mock_docking(draw: ImageDraw.ImageDraw, box):
    x1, y1, x2, y2 = box
    # Protein pocket cloud
    for i in range(30):
        px = x1 + 40 + (i * 23) % (x2 - x1 - 80)
        py = y1 + 65 + ((i * 37) % (y2 - y1 - 120))
        r = 10 + (i % 4) * 4
        draw.ellipse((px - r, py - r, px + r, py + r), fill=(208, 222, 238, 180))

    # Ligand sticks
    ligand = [
        (x1 + 110, y1 + 190),
        (x1 + 155, y1 + 160),
        (x1 + 205, y1 + 185),
        (x1 + 255, y1 + 150),
        (x1 + 305, y1 + 178),
        (x1 + 355, y1 + 140),
    ]
    for a, b in zip(ligand[:-1], ligand[1:]):
        draw.line((a, b), fill=(200, 76, 9, 255), width=7)
    for p in ligand:
        draw.ellipse((p[0] - 8, p[1] - 8, p[0] + 8, p[1] + 8), fill=(232, 104, 34, 255), outline=(150, 52, 8, 255), width=2)

    # Interaction lines
    anchors = [(x1 + 220, y1 + 95), (x1 + 290, y1 + 105), (x1 + 340, y1 + 115)]
    targets = [ligand[2], ligand[3], ligand[4]]
    for a, t in zip(anchors, targets):
        draw.line((a, t), fill=(11, 110, 79, 220), width=3)


def main():
    # Background
    bg = Image.new("RGBA", (W, H), (245, 247, 251, 255))
    grad = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(grad)
    for y in range(H):
        alpha = int(52 * (1 - y / H))
        gd.line([(0, y), (W, y)], fill=(17, 34, 51, alpha))
    canvas = Image.alpha_composite(bg, grad)
    draw = ImageDraw.Draw(canvas)

    # Header strip
    draw.rectangle((0, 0, W, 72), fill=(17, 34, 51, 245))
    f_head = load_font(24, bold=True)
    f_title = load_font(58, bold=True)
    f_sub = load_font(30, bold=False)
    f_lbl = load_font(24, bold=True)
    f_micro = load_font(20, bold=False)

    draw.text((42, 21), "Interactive Cheminformatics Report", font=f_head, fill=(236, 242, 249, 255))

    # Title
    draw.text((58, 106), "R-Group Docking Insight Report", font=f_title, fill=(17, 34, 51, 255))
    draw.text((60, 181), "Scaffold Prioritization, Pose Visualization, and Property-Guided Filtering", font=f_sub, fill=(48, 72, 93, 255))

    # Panels layout
    left = (48, 250, 1090, 992)
    top_right = (1125, 250, 1872, 660)
    bottom_right = (1125, 690, 1872, 992)

    panel(draw, left)
    panel(draw, top_right)
    panel(draw, bottom_right)

    # Panel labels
    draw.text((74, 268), "Scaffold Panel", font=f_lbl, fill=(11, 110, 79, 255))
    draw.text((1152, 268), "Docking Pose Viewer", font=f_lbl, fill=(11, 110, 79, 255))
    draw.text((1152, 708), "Property Analytics", font=f_lbl, fill=(11, 110, 79, 255))

    # Load and place scaffold assets
    scaffold_example = ROOT / "scaffold_example.png"
    scaffold_dir = ROOT / "scaffold_images"
    scaffold_files = sorted(scaffold_dir.glob("*.png"))[:4]

    y0 = 315
    if scaffold_example.exists():
        im = fit_image(Image.open(scaffold_example), 980, 300)
        canvas.alpha_composite(im, (72, y0))

    y_row = 650
    x = 78
    for sf in scaffold_files:
        try:
            sim = fit_image(Image.open(sf), 230, 230)
            canvas.alpha_composite(sim, (x, y_row))
            x += 245
        except Exception:
            continue

    # Add motif chips / metrics on left panel
    chips = [
        "Central Ideas", "Deep Dive", "Interaction Filters", "R-Group Variants"
    ]
    cx, cy = 72, 918
    for c in chips:
        tw = draw.textlength(c, font=f_micro)
        draw.rounded_rectangle((cx, cy, cx + tw + 26, cy + 34), radius=12, fill=(226, 236, 247, 255), outline=(201, 215, 232, 255), width=1)
        draw.text((cx + 13, cy + 8), c, font=f_micro, fill=(33, 56, 78, 255))
        cx += int(tw + 40)

    # Docking viewer mock panel
    draw_mock_docking(draw, (1145, 305, 1852, 640))
    draw.rounded_rectangle((1158, 319, 1838, 347), radius=10, fill=(230, 236, 244, 255), outline=(208, 218, 230, 255), width=1)
    draw.text((1174, 326), "Protein | Ligand | H-bonds | Pi-Pi", font=f_micro, fill=(61, 82, 102, 255))

    # Analytics panel using existing plot image if present
    corr = ROOT / "plotly_2d_corr.png"
    if corr.exists():
        cim = fit_image(Image.open(corr), 700, 210)
        canvas.alpha_composite(cim, (1148, 752))
    else:
        # fallback mini chart
        bx1, by1, bx2, by2 = 1148, 752, 1846, 960
        draw.rectangle((bx1, by1, bx2, by2), fill=(248, 251, 255, 255), outline=(218, 228, 239, 255), width=2)
        bars = [0.28, 0.5, 0.34, 0.72, 0.42, 0.61, 0.49]
        bw = 70
        for i, v in enumerate(bars):
            x1 = bx1 + 26 + i * (bw + 14)
            x2 = x1 + bw
            h = int((by2 - by1 - 36) * v)
            y1 = by2 - 18 - h
            draw.rounded_rectangle((x1, y1, x2, by2 - 18), radius=8, fill=(78, 138, 197, 220))

    # footer
    draw.text((58, 1018), "Automated scaffold discovery, docking-pose review, and medicinal-chemistry triage in one report", font=f_micro, fill=(78, 97, 114, 255))

    # Soft shadow + save
    final = canvas.convert("RGB")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    final.save(OUT, format="PNG", optimize=True)
    print(OUT)


if __name__ == "__main__":
    main()
