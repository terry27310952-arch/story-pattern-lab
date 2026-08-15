from __future__ import annotations

import hashlib
from io import BytesIO

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageOps, ImageStat

import card_renderer
import story_renderer_v4 as legacy


STORY_RENDERER_VERSION = "story-renderer-v10.1"
ORANGE = card_renderer.ORANGE


def _scene_type(card: dict) -> str:
    return str((card.get("visual_direction") or {}).get("scene_type") or "documentary_editorial")


def _base_scene(width: int, height: int) -> Image.Image:
    """Neutral photographic canvas for v10 semantic scenes.

    v10 must not fall through the old archetype renderer for unknown semantic scene
    names. The old generic branch was both visually repetitive and had assumptions
    about its legacy color tuple. This base is intentionally content-neutral.
    """
    image = Image.new("RGBA", (width, height), (3, 5, 6, 255))
    d = ImageDraw.Draw(image, "RGBA")
    d.rectangle((0, 0, width, int(height * .58)), fill=(5, 7, 8, 255))
    d.rectangle((0, int(height * .42), width, int(height * .58)), fill=(18, 12, 7, 28))
    d.ellipse((int(width*.68), int(height*.02), int(width*1.08), int(height*.42)), fill=ORANGE+(18,))
    d.ellipse((int(width*-.16), int(height*.18), int(width*.32), int(height*.62)), fill=(90, 105, 110, 12))
    return image


def _semantic_overlay(image: Image.Image, card: dict) -> Image.Image:
    image = image.convert("RGBA")
    w, h = image.size
    d = ImageDraw.Draw(image, "RGBA")
    scene = _scene_type(card)
    lw = max(2, w // 260)
    top_h = int(h * 0.58)

    if scene == "industrial_infrastructure":
        d.rectangle((int(w*.07), int(h*.23), int(w*.93), int(h*.48)), fill=(7, 10, 11, 190), outline=ORANGE+(55,), width=lw)
        for x in [int(w*.18), int(w*.34), int(w*.72), int(w*.84)]:
            d.rectangle((x, int(h*.12), x+int(w*.035), int(h*.48)), fill=(15, 18, 18, 205), outline=(180,180,170,45), width=lw)
        d.line((int(w*.05), int(h*.17), int(w*.95), int(h*.17)), fill=ORANGE+(70,), width=lw)

    elif scene == "policy_document":
        for i, dx in enumerate([.10, .21, .32]):
            x0 = int(w*dx); y0 = int(h*(.11+i*.025))
            d.rounded_rectangle((x0, y0, x0+int(w*.52), y0+int(h*.32)), radius=max(5,w//100), fill=(230,225,210,34), outline=(235,225,205,62), width=lw)
            for k in range(6):
                y = y0 + int(h*(.055+.035*k))
                d.line((x0+int(w*.04), y, x0+int(w*.42), y), fill=(220,215,200,55), width=lw)
        for x in [int(w*.72), int(w*.79), int(w*.86)]:
            d.rectangle((x, int(h*.18), x+int(w*.035), int(h*.49)), fill=(120,120,115,35))

    elif scene == "capital_flow":
        centers = [(int(w*.15),int(h*.28)),(int(w*.40),int(h*.14)),(int(w*.56),int(h*.39)),(int(w*.82),int(h*.22))]
        for a,b in zip(centers, centers[1:]):
            d.line((*a,*b), fill=ORANGE+(105,), width=max(3,lw))
        for i,(cx,cy) in enumerate(centers):
            r=max(13,w//32)
            d.ellipse((cx-r,cy-r,cx+r,cy+r), fill=(7,10,11,210), outline=ORANGE+((160 if i in {0,3} else 85),), width=lw)
        d.arc((int(w*.08),int(h*.06),int(w*.90),int(h*.55)), 205, 340, fill=(210,200,180,38), width=max(3,lw))

    elif scene == "archive_context":
        wash = Image.new("RGBA", image.size, (155, 106, 54, 22))
        image.alpha_composite(wash)
        d = ImageDraw.Draw(image, "RGBA")
        for i in range(3):
            x=int(w*(.06+i*.30)); y=int(h*(.08+.02*(i%2)))
            d.rectangle((x,y,x+int(w*.26),int(h*.48)),fill=(235,220,185,40),outline=(245,230,195,65),width=lw)
            d.rectangle((x+int(w*.025),y+int(h*.035),x+int(w*.21),y+int(h*.13)),fill=(45,38,30,55))
            for k in range(6):
                yy=y+int(h*(.17+.035*k))
                d.line((x+int(w*.025),yy,x+int(w*.22),yy),fill=(45,38,30,70),width=lw)

    elif scene == "security_forensics":
        d.rectangle((int(w*.08),int(h*.10),int(w*.56),int(h*.49)),fill=(5,8,9,210),outline=(190,195,190,55),width=lw)
        for y in [int(h*.17),int(h*.24),int(h*.31),int(h*.38)]:
            d.line((int(w*.13),y,int(w*.49),y),fill=(150,170,165,55),width=lw)
        nodes=[(int(w*.68),int(h*.17)),(int(w*.82),int(h*.30)),(int(w*.65),int(h*.43)),(int(w*.90),int(h*.46))]
        for a,b in [(0,1),(1,2),(1,3)]:
            d.line((*nodes[a],*nodes[b]),fill=ORANGE+(90,),width=lw)
        for cx,cy in nodes:
            r=max(8,w//55); d.ellipse((cx-r,cy-r,cx+r,cy+r),outline=ORANGE+(130,),width=lw)

    elif scene == "timeline_milestones":
        y=int(h*.35)
        d.line((int(w*.08),y,int(w*.92),y),fill=ORANGE+(145,),width=max(4,lw))
        for i in range(5):
            x=int(w*(.11+i*.195)); r=max(8,w//70)
            d.ellipse((x-r,y-r,x+r,y+r),fill=ORANGE+((165 if i in {1,3} else 90),))
            d.line((x,y-r,x,int(h*(.16 if i%2==0 else .50))),fill=(210,205,190,46),width=lw)

    elif scene == "numeric_evidence":
        d.rounded_rectangle((int(w*.09),int(h*.09),int(w*.91),int(h*.49)),radius=max(8,w//60),fill=(4,7,8,210),outline=ORANGE+(70,),width=max(3,lw))
        bars=[.22,.48,.76]
        for i,height in enumerate(bars):
            x0=int(w*(.19+i*.23)); y1=int(h*.44); y0=int(h*(.44-height*.31))
            d.rounded_rectangle((x0,y0,x0+int(w*.11),y1),radius=max(3,w//140),fill=ORANGE+((70+35*i),))

    elif scene == "split_comparison":
        d.rectangle((0,0,w//2,top_h),fill=(32,16,7,45))
        d.rectangle((w//2,0,w,top_h),fill=(5,14,22,55))
        d.line((w//2,int(h*.04),w//2,int(h*.55)),fill=ORANGE+(160,),width=max(4,lw))
        d.ellipse((int(w*.13),int(h*.19),int(w*.36),int(h*.42)),outline=(220,210,190,70),width=max(3,lw))
        d.rectangle((int(w*.64),int(h*.15),int(w*.85),int(h*.45)),outline=(125,170,195,75),width=max(3,lw))

    elif scene == "entity_environment":
        d.rectangle((int(w*.08),int(h*.26),int(w*.92),int(h*.50)),fill=(8,10,10,180),outline=(180,180,170,35),width=lw)
        for i in range(8):
            x=int(w*(.11+i*.10)); d.rectangle((x,int(h*.18),x+int(w*.055),int(h*.26)),fill=(45,48,48,70))
        d.ellipse((int(w*.39),int(h*.08),int(w*.61),int(h*.29)),fill=(2,3,3,145),outline=ORANGE+(50,),width=lw)

    elif scene == "transition_scene":
        d.rectangle((0,0,int(w*.43),top_h),fill=(25,18,12,42))
        d.rectangle((int(w*.57),0,w,top_h),fill=(5,15,20,52))
        d.polygon([(int(w*.39),int(h*.24)),(int(w*.56),int(h*.18)),(int(w*.56),int(h*.30))],fill=ORANGE+(135,))
        for x in [int(w*.11),int(w*.23),int(w*.68),int(w*.80)]:
            d.rectangle((x,int(h*.17),x+int(w*.08),int(h*.45)),outline=(175,180,175,60),width=lw)

    elif scene == "system_relationship":
        centers=[(int(w*.20),int(h*.34)),(int(w*.50),int(h*.15)),(int(w*.80),int(h*.34))]
        d.line((*centers[0],*centers[1]),fill=ORANGE+(95,),width=max(3,lw))
        d.line((*centers[1],*centers[2]),fill=ORANGE+(95,),width=max(3,lw))
        for i,(cx,cy) in enumerate(centers):
            r=max(23,w//23)
            d.rounded_rectangle((cx-r,cy-r,cx+r,cy+r),radius=max(8,w//70),fill=(4,7,8,195),outline=ORANGE+((145 if i==1 else 70),),width=lw)

    else:
        d.rectangle((int(w*.06),int(h*.09),int(w*.94),int(h*.50)),fill=(7,8,8,120),outline=(180,180,175,28),width=lw)
        d.polygon([(int(w*.08),int(h*.48)),(int(w*.44),int(h*.13)),(int(w*.63),int(h*.13)),(int(w*.31),int(h*.48))],fill=ORANGE+(22,))
        d.ellipse((int(w*.70),int(h*.14),int(w*.91),int(h*.35)),fill=(225,210,180,12))

    return image


def render_scene_image(card: dict, width: int = 540, height: int = 500) -> Image.Image:
    external = card_renderer._load_visual_asset(card, width, height)
    if external is not None:
        return external.convert("RGBA")
    return _semantic_overlay(_base_scene(width, height), card)


def render_story_card_image(card: dict, width: int = 1080, height: int = 1350) -> Image.Image:
    if card.get("card_type") == "brand_outro":
        return legacy.render_story_card_image(card, width, height).convert("RGB")
    scene = render_scene_image(card, width, height)
    return legacy.legacy._compose(card, scene, width, height).convert("RGB")


def render_story_card_png(card: dict, width: int = 1080, height: int = 1350) -> bytes:
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
    similarities: list[float] = []
    near_duplicates: list[list[float | int]] = []
    for i in range(len(content)):
        for j in range(i + 1, len(content)):
            sim = scene_similarity(content[i], content[j])
            similarities.append(sim)
            if sim >= 0.975:
                near_duplicates.append([i + 1, j + 1, sim])
    return {
        "render_signature_count": len(set(signatures)),
        "max_scene_similarity": max(similarities) if similarities else 0.0,
        "near_duplicate_scene_pairs": near_duplicates,
        "scene_signatures": signatures,
    }
