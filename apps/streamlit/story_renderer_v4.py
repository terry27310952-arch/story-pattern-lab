from __future__ import annotations

import hashlib
from io import BytesIO

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageOps, ImageStat

import card_renderer
import story_renderer_v3 as legacy


STORY_RENDERER_VERSION = "story-renderer-v9.0"
ORANGE = card_renderer.ORANGE


def _scene_type(card: dict) -> str:
    return str((card.get("visual_direction") or {}).get("scene_type") or "editorial_generic")


def _reinforce_scene(image: Image.Image, card: dict) -> Image.Image:
    """Make the fallback scene visibly different by scene semantics.

    The v8 renderer had distinct scene names, but several dark procedural scenes could
    still collapse to the same visual impression after composition. These overlays are
    intentionally structural: building horizon, ASIC fan wall, pylons, server aisles,
    aerial campus, split comparison, archive sheets, etc. No chart is used as a generic
    fallback for Story mode.
    """
    image = image.convert("RGBA")
    w, h = image.size
    d = ImageDraw.Draw(image, "RGBA")
    scene = _scene_type(card)
    lw = max(2, w // 260)

    if scene == "industrial_data_center_exterior":
        base = int(h * 0.50)
        d.rectangle((int(w*.05), int(h*.24), int(w*.95), base), fill=(4, 7, 8, 180), outline=ORANGE+(65,), width=lw)
        for i in range(12):
            x = int(w*(.08+i*.072))
            d.rectangle((x, base-int(h*.035), x+max(4,w//120), base-int(h*.024)), fill=ORANGE+(125,))
        for i in range(5):
            x0 = int(w*(.10+i*.17))
            d.rectangle((x0, int(h*.20), x0+int(w*.10), int(h*.24)), fill=(65,70,72,90))

    elif scene == "bitcoin_mining_hall":
        # Repeating fan wall, unmistakably different from a line chart.
        for col in range(6):
            for row in range(4):
                cx = int(w*(.12+col*.145)); cy = int(h*(.14+row*.105)); r = max(10, w//34)
                d.rectangle((cx-r-7, cy-r-7, cx+r+7, cy+r+7), fill=(3,6,7,185), outline=(150,165,170,48), width=lw)
                d.ellipse((cx-r,cy-r,cx+r,cy+r), outline=(180,194,198,95), width=lw)
                d.ellipse((cx-r//3,cy-r//3,cx+r//3,cy+r//3), fill=ORANGE+(80,))

    elif scene == "power_grid_infrastructure":
        # Three large pylon silhouettes.
        for cx in [int(w*.22), int(w*.50), int(w*.78)]:
            top, ground = int(h*.09), int(h*.55)
            d.line((cx, top, cx-int(w*.07), ground), fill=(210,205,188,105), width=lw)
            d.line((cx, top, cx+int(w*.07), ground), fill=(210,205,188,105), width=lw)
            for yy, span in [(int(h*.20), .09), (int(h*.30), .12), (int(h*.40), .15)]:
                d.line((cx-int(w*span),yy,cx+int(w*span),yy), fill=ORANGE+(82,), width=lw)
        for yy in [int(h*.19), int(h*.29), int(h*.39)]:
            d.line((0,yy,w,yy+int(h*.018)), fill=(205,200,180,42), width=lw)

    elif scene == "ai_server_hall":
        # Tall rack doors with cold aisle perspective.
        for side in [0, 1]:
            for i in range(5):
                if side == 0:
                    x0 = int(w*(.03+i*.075)); x1 = x0 + int(w*.065)
                else:
                    x1 = int(w*(.97-i*.075)); x0 = x1 - int(w*.065)
                d.rectangle((x0,int(h*.09),x1,int(h*.55)), fill=(3,8,12,195), outline=(115,155,180,62), width=lw)
                for k in range(7):
                    y = int(h*(.13+k*.052))
                    d.rectangle((x0+5,y,x0+10,y+6), fill=(105,175,210,105) if k%2 else ORANGE+(90,))
        d.polygon([(int(w*.43),int(h*.55)),(int(w*.57),int(h*.55)),(int(w*.515),int(h*.12)),(int(w*.485),int(h*.12))], fill=(220,230,235,18))

    elif scene == "industrial_aerial_scale":
        # Top-down campus blocks and roads.
        d.rectangle((0,0,w,int(h*.58)), fill=(10,10,9,35))
        for r in range(4):
            for c in range(6):
                x = int(w*(.07+c*.15+(r%2)*.025)); y = int(h*(.09+r*.105))
                d.polygon([(x,y),(x+int(w*.09),y-int(h*.018)),(x+int(w*.105),y+int(h*.045)),(x+int(w*.015),y+int(h*.06))], fill=(14,17,17,175), outline=ORANGE+(34,), width=1)
        d.line((int(w*.04),int(h*.30),int(w*.96),int(h*.30)), fill=(210,205,190,45), width=max(3,lw))

    elif scene == "ai_compute_power_demand":
        # Left: grid. Right: server bank. The diagonal bridge makes the relation obvious.
        d.rectangle((0,0,w//2,int(h*.58)), fill=(18,10,4,45))
        d.rectangle((w//2,0,w,int(h*.58)), fill=(3,10,16,65))
        d.line((w//2,int(h*.05),w//2,int(h*.58)), fill=ORANGE+(120,), width=max(3,lw))
        for x in [int(w*.14),int(w*.31)]:
            d.line((x,int(h*.10),x-int(w*.06),int(h*.52)),fill=(210,200,180,90),width=lw)
            d.line((x,int(h*.10),x+int(w*.06),int(h*.52)),fill=(210,200,180,90),width=lw)
        for x0 in [int(w*.58),int(w*.70),int(w*.82)]:
            d.rectangle((x0,int(h*.12),x0+int(w*.075),int(h*.52)),fill=(4,9,13,190),outline=(120,170,200,70),width=lw)
        d.line((int(w*.37),int(h*.24),int(w*.63),int(h*.24)),fill=ORANGE+(150,),width=max(4,lw))

    elif scene == "mining_vs_ai_split":
        d.line((w//2,int(h*.04),w//2,int(h*.58)), fill=ORANGE+(170,), width=max(4,lw))
        # Left large ASIC fans.
        for i in range(3):
            cx=int(w*(.13+i*.12)); cy=int(h*.30); r=max(14,w//28)
            d.ellipse((cx-r,cy-r,cx+r,cy+r),outline=(210,215,210,95),width=lw)
            d.ellipse((cx-r//3,cy-r//3,cx+r//3,cy+r//3),fill=ORANGE+(80,))
        # Right tall AI racks.
        for i in range(3):
            x0=int(w*(.58+i*.11)); d.rectangle((x0,int(h*.14),x0+int(w*.07),int(h*.50)),fill=(4,9,13,190),outline=(105,170,205,80),width=lw)

    elif scene == "construction_timeline":
        y = int(h*.42)
        d.line((int(w*.08),y,int(w*.92),y), fill=ORANGE+(135,), width=max(4,lw))
        for i in range(4):
            x=int(w*(.14+i*.24)); r=max(7,w//95)
            d.ellipse((x-r,y-r,x+r,y+r),fill=ORANGE+(175 if i in {1,3} else 95,))
        # Huge crane silhouette.
        x=int(w*.18); d.line((x,int(h*.08),x,int(h*.53)),fill=(220,210,190,90),width=max(3,lw))
        d.line((x,int(h*.12),int(w*.62),int(h*.12)),fill=(220,210,190,90),width=max(3,lw))
        d.line((int(w*.52),int(h*.12),int(w*.52),int(h*.33)),fill=ORANGE+(88,),width=lw)

    elif scene in {"archival_wall_street","historical_newspaper","historical_market_aftermath","past_present_split"}:
        # Make archive cards materially brighter than dark market graphics.
        wash = Image.new("RGBA", image.size, (135, 103, 62, 18))
        image.alpha_composite(wash)
        d = ImageDraw.Draw(image, "RGBA")
        for i in range(3):
            x=int(w*(.07+i*.29)); y=int(h*(.07+.025*(i%2)))
            d.rectangle((x,y,x+int(w*.25),int(h*.49)),fill=(230,218,190,34),outline=(245,235,210,52),width=lw)

    elif scene in {"modern_valuation_display","valuation_watchboard"}:
        # One large numeric/evidence board, not a generic background chart.
        d.rounded_rectangle((int(w*.12),int(h*.10),int(w*.88),int(h*.48)),radius=max(8,w//80),fill=(3,6,7,205),outline=ORANGE+(72,),width=max(3,lw))
        ev=str(card.get("evidence_excerpt") or "")
        years = __import__("re").findall(r"\b(?:19|20)\d{2}\b", ev)
        if years:
            font=card_renderer._font(max(24,w//13),True)
            d.text((int(w*.17),int(h*.21))," / ".join(years[:2]),font=font,fill=ORANGE)

    return image


def render_scene_image(card: dict, width: int=540, height: int=500) -> Image.Image:
    external = card_renderer._load_visual_asset(card, width, height)
    if external is not None:
        return external.convert("RGBA")
    scene = legacy._draw_scene(card, width, height)
    return _reinforce_scene(scene, card)


def render_story_card_image(card: dict, width: int=1080, height: int=1350) -> Image.Image:
    if card.get("card_type") == "brand_outro":
        return legacy._brand_outro(card, width, height).convert("RGB")
    scene = render_scene_image(card, width, height)
    return legacy._compose(card, scene, width, height).convert("RGB")


def render_story_card_png(card: dict, width: int=1080, height: int=1350) -> bytes:
    out = BytesIO()
    render_story_card_image(card, width, height).save(out, format="PNG", optimize=True)
    return out.getvalue()


def _structural_vector(card: dict) -> Image.Image:
    scene = render_scene_image(card, 160, 120).convert("L")
    scene = ImageOps.autocontrast(scene)
    scene = scene.filter(ImageFilter.GaussianBlur(radius=0.8)).filter(ImageFilter.FIND_EDGES)
    return ImageOps.autocontrast(scene).resize((48, 36), Image.Resampling.LANCZOS)


def scene_similarity(a: dict, b: dict) -> float:
    ia, ib = _structural_vector(a), _structural_vector(b)
    diff = ImageChops.difference(ia, ib)
    mean = float(ImageStat.Stat(diff).mean[0])
    return round(max(0.0, min(1.0, 1.0 - mean / 255.0)), 4)


def scene_signature(card: dict) -> str:
    image = _structural_vector(card).resize((16, 12), Image.Resampling.BILINEAR)
    pixels = list(image.getdata())
    avg = sum(pixels) / max(1, len(pixels))
    bits = "".join("1" if p >= avg else "0" for p in pixels)
    value = int(bits, 2)
    return hashlib.sha1(f"{_scene_type(card)}|{value:x}".encode()).hexdigest()[:16]


def scene_diagnostics(cards: list[dict]) -> dict:
    content = [c for c in cards or [] if c.get("card_type") != "brand_outro"]
    signatures = [scene_signature(c) for c in content]
    similarities = []
    near_duplicates = []
    for i in range(len(content)):
        for j in range(i+1, len(content)):
            sim = scene_similarity(content[i], content[j])
            similarities.append(sim)
            if sim >= 0.975:
                near_duplicates.append([i+1, j+1, sim])
    return {
        "render_signature_count": len(set(signatures)),
        "max_scene_similarity": max(similarities) if similarities else 0.0,
        "near_duplicate_scene_pairs": near_duplicates,
        "scene_signatures": signatures,
    }
