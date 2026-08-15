from __future__ import annotations

import math
import random

from PIL import Image, ImageDraw, ImageFilter


STORY_RENDER_RUNTIME_VERSION = "story-render-v5.0"


def _seed(card: dict) -> int:
    raw = f"{card.get('story_id')}|{card.get('story_role')}|{card.get('slide')}|{card.get('headline')}"
    value = 0
    for ch in raw:
        value = (value * 131 + ord(ch)) & 0xFFFFFFFF
    return value


def _safe_region(image: Image.Image) -> tuple[int, int, int, int]:
    w, h = image.size
    return int(w * 0.07), int(h * 0.10), int(w * 0.93), int(h * 0.48)


def _draw_contradiction(overlay: Image.Image, card: dict, accent, green, red) -> None:
    draw = ImageDraw.Draw(overlay, "RGBA")
    left, top, right, bottom = _safe_region(overlay)
    mid = (left + right) // 2
    y1 = int(top + (bottom-top)*0.72)
    y2 = int(top + (bottom-top)*0.25)
    draw.line((left, y1, mid-18, y2), fill=red+(150,), width=max(3, overlay.width//240))
    draw.line((mid+18, y2, right, y1-30), fill=green+(150,), width=max(3, overlay.width//240))
    for x, y, color in [(left,y1,red),(mid-18,y2,red),(mid+18,y2,green),(right,y1-30,green)]:
        r=max(5,overlay.width//120)
        draw.ellipse((x-r,y-r,x+r,y+r), fill=color+(220,))
    draw.rectangle((mid-3, top+20, mid+3, bottom-20), fill=accent+(85,))


def _draw_money_flow(overlay: Image.Image, card: dict, accent, green, red) -> None:
    draw = ImageDraw.Draw(overlay, "RGBA")
    left, top, right, bottom = _safe_region(overlay)
    rng = random.Random(_seed(card))
    nodes=[]
    for i in range(8):
        x=int(left+(right-left)*(0.08+i/9))
        y=int(top+(bottom-top)*(0.25+rng.random()*0.5))
        nodes.append((x,y))
    for i in range(len(nodes)-1):
        x1,y1=nodes[i]; x2,y2=nodes[i+1]
        control_y=min(y1,y2)-int((bottom-top)*0.18)
        pts=[]
        for step in range(20):
            t=step/19
            x=int((1-t)*x1+t*x2)
            y=int((1-t)*(1-t)*y1+2*(1-t)*t*control_y+t*t*y2)
            pts.append((x,y))
        draw.line(pts, fill=accent+(85+i*8,), width=max(2,overlay.width//300))
    for i,(x,y) in enumerate(nodes):
        r=max(7,overlay.width//95) if i in {0,len(nodes)-1} else max(4,overlay.width//150)
        fill=(green if i==len(nodes)-1 else accent)+(180,)
        draw.ellipse((x-r,y-r,x+r,y+r), fill=fill, outline=(255,255,255,35))


def _draw_policy(overlay: Image.Image, card: dict, accent, green, red) -> None:
    draw = ImageDraw.Draw(overlay, "RGBA")
    w,h=overlay.size
    left, top, right, bottom=_safe_region(overlay)
    doc_left=int(left+(right-left)*0.22); doc_right=int(right-(right-left)*0.15)
    draw.rounded_rectangle((doc_left,top+20,doc_right,bottom), radius=max(8,w//120), fill=(235,231,220,22), outline=(255,255,255,55), width=max(1,w//600))
    y=top+int((bottom-top)*0.20)
    for i,ratio in enumerate([0.72,0.84,0.58,0.77,0.48]):
        draw.rounded_rectangle((doc_left+30,y,doc_left+30+int((doc_right-doc_left-60)*ratio),y+max(3,w//360)), radius=2, fill=(255,255,255,55))
        y+=max(22,w//38)
    cx=doc_right-max(55,w//14); cy=top+max(55,w//13); r=max(22,w//28)
    draw.ellipse((cx-r,cy-r,cx+r,cy+r), outline=accent+(150,), width=max(2,w//300))
    draw.line((cx-r//2,cy,cx+r//2,cy), fill=accent+(120,), width=max(2,w//360))


def _draw_power_shift(overlay: Image.Image, card: dict, accent, green, red) -> None:
    draw=ImageDraw.Draw(overlay,"RGBA")
    left,top,right,bottom=_safe_region(overlay)
    mid=(left+right)//2
    gap=max(24,overlay.width//30)
    draw.rounded_rectangle((left+30,top+70,mid-gap,bottom), radius=18, fill=(255,255,255,15), outline=(255,255,255,35), width=2)
    draw.rounded_rectangle((mid+gap,top+20,right-30,bottom), radius=18, fill=accent+(20,), outline=accent+(65,), width=2)
    y=int(top+(bottom-top)*0.58)
    draw.line((left+60,y,right-60,y), fill=(255,255,255,45), width=2)
    arrow_y=int(top+(bottom-top)*0.42)
    draw.line((mid-80,arrow_y,mid+90,arrow_y), fill=accent+(155,), width=max(3,overlay.width//250))
    draw.polygon([(mid+90,arrow_y),(mid+58,arrow_y-18),(mid+58,arrow_y+18)], fill=accent+(180,))


def _draw_timeline(overlay: Image.Image, card: dict, accent, green, red) -> None:
    draw=ImageDraw.Draw(overlay,"RGBA")
    left,top,right,bottom=_safe_region(overlay)
    y=int(top+(bottom-top)*0.56)
    draw.line((left+30,y,right-30,y), fill=(255,255,255,50), width=max(2,overlay.width//400))
    for i in range(5):
        x=int(left+60+(right-left-120)*i/4)
        r=max(6,overlay.width//125)
        color=accent if i in {2,4} else (210,210,205)
        draw.ellipse((x-r,y-r,x+r,y+r), fill=color+(185,))
        stem=int((35+18*(i%2))*overlay.height/1350)
        draw.line((x,y-r,x,y-r-stem), fill=color+(80,), width=2)


def _draw_hidden_giant(overlay: Image.Image, card: dict, accent, green, red) -> None:
    draw=ImageDraw.Draw(overlay,"RGBA")
    left,top,right,bottom=_safe_region(overlay)
    widths=[0.12,0.18,0.10,0.22,0.14]
    heights=[0.42,0.70,0.50,0.96,0.62]
    x=left+20
    total=right-left-40
    gap=max(10,overlay.width//80)
    unit=(total-gap*(len(widths)-1))/sum(widths)
    for i,(wr,hr) in enumerate(zip(widths,heights)):
        bw=int(unit*wr)
        bh=int((bottom-top)*hr)
        color=accent if i==3 else (190,190,185)
        draw.rounded_rectangle((x,bottom-bh,x+bw,bottom), radius=max(4,overlay.width//200), fill=color+(35 if i!=3 else 65), outline=color+(70 if i!=3 else 120), width=2)
        x+=bw+gap


def _draw_crisis(overlay: Image.Image, card: dict, accent, green, red) -> None:
    draw=ImageDraw.Draw(overlay,"RGBA")
    left,top,right,bottom=_safe_region(overlay)
    rng=random.Random(_seed(card))
    x=left+int((right-left)*0.18); y=top+int((bottom-top)*0.25)
    pts=[(x,y)]
    for i in range(7):
        x+=int((right-left)*0.09)
        y+=rng.randint(-55,65)
        pts.append((x,y))
    draw.line(pts, fill=red+(150,), width=max(3,overlay.width//280))
    cx=int(right-(right-left)*0.17); cy=int(top+(bottom-top)*0.45); r=max(30,overlay.width//18)
    draw.ellipse((cx-r,cy-r,cx+r,cy+r), outline=red+(95,), width=max(2,overlay.width//360))
    draw.ellipse((cx-r//2,cy-r//2,cx+r//2,cy+r//2), outline=accent+(85,), width=2)


def _draw_opportunity(overlay: Image.Image, card: dict, accent, green, red) -> None:
    draw=ImageDraw.Draw(overlay,"RGBA")
    left,top,right,bottom=_safe_region(overlay)
    cx=(left+right)//2; cy=int(top+(bottom-top)*0.48)
    for i in range(7):
        angle=-0.65+i*(1.3/6)
        length=int((right-left)*0.38)
        x2=int(cx+math.cos(angle)*length)
        y2=int(cy+math.sin(angle)*length)
        draw.line((cx,cy,x2,y2), fill=accent+(22+i*6,), width=max(2,overlay.width//420))
    r=max(28,overlay.width//25)
    draw.ellipse((cx-r,cy-r,cx+r,cy+r), fill=accent+(35,), outline=accent+(115,), width=max(2,overlay.width//320))


def _apply_story_overlay(image: Image.Image, card: dict) -> Image.Image:
    archetype=str(card.get("story_archetype") or "")
    if not archetype or card.get("card_type")=="brand_outro":
        return image
    accent=(246,159,25); green=(113,202,149); red=(227,105,90)
    overlay=Image.new("RGBA", image.size, (0,0,0,0))
    if archetype=="contradiction":
        _draw_contradiction(overlay,card,accent,green,red)
    elif archetype=="money_flow":
        _draw_money_flow(overlay,card,accent,green,red)
    elif archetype=="policy_change":
        _draw_policy(overlay,card,accent,green,red)
    elif archetype=="power_shift":
        _draw_power_shift(overlay,card,accent,green,red)
    elif archetype in {"origin_to_now","historical_parallel"}:
        _draw_timeline(overlay,card,accent,green,red)
    elif archetype=="hidden_giant":
        _draw_hidden_giant(overlay,card,accent,green,red)
    elif archetype=="crisis_or_risk":
        _draw_crisis(overlay,card,accent,green,red)
    elif archetype=="opportunity_window":
        _draw_opportunity(overlay,card,accent,green,red)
    else:
        return image
    overlay=overlay.filter(ImageFilter.GaussianBlur(radius=max(0.2,image.width/2400)))
    result=image.convert("RGBA")
    result.alpha_composite(overlay)
    return result.convert("RGB")


def apply_renderer_patch(card_renderer) -> None:
    if getattr(card_renderer,"_kiyosaki_story_render_version",None)==STORY_RENDER_RUNTIME_VERSION:
        return
    original_image=card_renderer.render_card_image

    def render_card_image(card: dict, width: int = 1080, height: int = 1350):
        image=original_image(card,width=width,height=height)
        return _apply_story_overlay(image,card)

    def render_card_png(card: dict, width: int = 1080, height: int = 1350) -> bytes:
        from io import BytesIO
        image=render_card_image(card,width=width,height=height)
        output=BytesIO()
        image.save(output,format="PNG",optimize=True)
        return output.getvalue()

    card_renderer.render_card_image=render_card_image
    card_renderer.render_card_png=render_card_png
    card_renderer._kiyosaki_story_render_version=STORY_RENDER_RUNTIME_VERSION
