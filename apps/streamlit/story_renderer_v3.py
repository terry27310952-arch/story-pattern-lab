from __future__ import annotations

import hashlib
import math
import random
from io import BytesIO

from PIL import Image, ImageDraw, ImageFilter, ImageOps

import card_renderer


STORY_RENDERER_VERSION = "story-renderer-v8.0"
ORANGE = card_renderer.ORANGE
OFF_WHITE = card_renderer.OFF_WHITE
MUTED = card_renderer.MUTED
BG = card_renderer.BG


def _seed(card: dict) -> int:
    raw = "|".join(str(v or "") for v in [card.get("story_id"), card.get("story_role"), card.get("slide"), (card.get("visual_direction") or {}).get("scene_type")])
    return int(hashlib.sha1(raw.encode("utf-8", errors="ignore")).hexdigest()[:12], 16)


def _base(width: int, height: int, warm: bool = False) -> Image.Image:
    return card_renderer._gradient_background(width, height, warm=warm).convert("RGBA")


def _lights(image: Image.Image, seed: int, warm: bool, density: int = 16) -> None:
    rng = random.Random(seed)
    layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer, "RGBA")
    w, h = image.size
    palette = [ORANGE, (230, 190, 120), (120, 145, 165)] if warm else [(86, 132, 166), (178, 204, 218), ORANGE]
    for _ in range(density):
        r = rng.randint(max(8, w // 90), max(18, w // 28))
        x = rng.randint(-r, w + r)
        y = rng.randint(0, int(h * 0.60))
        draw.ellipse((x-r, y-r, x+r, y+r), fill=rng.choice(palette) + (rng.randint(12, 42),))
    image.alpha_composite(layer.filter(ImageFilter.GaussianBlur(radius=max(6, w // 36))))


def _scene_data_center_exterior(image: Image.Image, card: dict) -> None:
    w, h = image.size
    _lights(image, _seed(card), True, 12)
    d = ImageDraw.Draw(image, "RGBA")
    horizon = int(h * 0.47)
    d.rectangle((0, horizon, w, int(h * 0.62)), fill=(2, 3, 4, 230))
    # long hyperscale campus, perspective and service lights
    for idx in range(4):
        x0 = int(w * (0.06 + idx * 0.22))
        y0 = int(h * (0.18 + 0.025 * (idx % 2)))
        x1 = x0 + int(w * 0.26)
        y1 = horizon
        d.polygon([(x0, y0), (x1, y0+12), (x1, y1), (x0, y1-4)], fill=(8, 12, 14, 245), outline=(120, 132, 138, 38))
        for r in range(3):
            yy = y0 + int((r+1) * (y1-y0)/4)
            d.line((x0+12, yy, x1-12, yy+4), fill=(160, 170, 174, 30), width=2)
        for c in range(7):
            xx = x0 + 18 + c * max(12, int((x1-x0-36)/7))
            d.rectangle((xx, y1-22, xx+5, y1-14), fill=ORANGE + (95,))
    # power feed
    d.line((int(w*.05), int(h*.16), int(w*.33), int(h*.09), int(w*.58), int(h*.14), int(w*.92), int(h*.06)), fill=ORANGE+(78,), width=max(2,w//380))


def _scene_mining_hall(image: Image.Image, card: dict) -> None:
    w, h = image.size
    _lights(image, _seed(card), False, 8)
    d = ImageDraw.Draw(image, "RGBA")
    van_x, van_y = w//2, int(h*.42)
    for side in (-1, 1):
        for row in range(5):
            near_x = int(w*(0.06 if side < 0 else 0.94))
            far_x = van_x + side * int(w*(0.08 + row*.018))
            top_y = int(h*(0.08 + row*.012))
            bottom_y = int(h*(0.54 - row*.012))
            d.polygon([(near_x, top_y), (far_x, int(h*.22)), (far_x, int(h*.48)), (near_x, bottom_y)], fill=(7,10,12,225), outline=(130,150,160,45))
            # ASIC rows
            for j in range(6):
                t = (j+1)/7
                x = int(near_x*(1-t)+far_x*t)
                y = int(top_y*(1-t)+int(h*.25)*t)
                rr = max(3, int(w*(0.012*(1-t)+0.004)))
                d.ellipse((x-rr,y-rr,x+rr,y+rr), outline=(120,145,160,60), width=2)
                d.ellipse((x-rr//2,y-rr//2,x+rr//2,y+rr//2), fill=ORANGE+(55,))
    d.line((van_x, int(h*.10), van_x, int(h*.54)), fill=(255,255,255,28), width=2)


def _scene_power_grid(image: Image.Image, card: dict) -> None:
    w,h=image.size
    _lights(image,_seed(card),True,8)
    d=ImageDraw.Draw(image,"RGBA")
    ground=int(h*.54)
    d.rectangle((0,ground,w,int(h*.62)),fill=(2,3,3,220))
    for idx, x in enumerate([int(w*.18), int(w*.48), int(w*.78)]):
        top=int(h*(.11+.02*(idx%2)))
        d.line((x,top,x,ground),fill=(180,175,160,80),width=max(2,w//300))
        span=int(w*.08)
        for yy in [top+30,top+70,top+110]:
            d.line((x-span,yy,x+span,yy),fill=(190,185,170,72),width=2)
            d.line((x-span,yy,x,yy-26,x+span,yy),fill=(190,185,170,46),width=2)
    for yoff in [0,30,60]:
        pts=[]
        for x in range(0,w+1,max(20,w//24)):
            y=int(h*.20)+yoff+int(18*math.sin(x/w*math.pi*2))
            pts.append((x,y))
        d.line(pts,fill=ORANGE+(60 if yoff else 95,),width=2)


def _scene_ai_server_hall(image: Image.Image, card: dict) -> None:
    w,h=image.size
    _lights(image,_seed(card),False,12)
    d=ImageDraw.Draw(image,"RGBA")
    center=w//2
    for side in (-1,1):
        for idx in range(5):
            near = int(w*(0.04 if side<0 else .96))
            far = center+side*int(w*(.06+idx*.02))
            y0=int(h*(.08+idx*.012)); y1=int(h*(.55-idx*.008))
            d.polygon([(near,y0),(far,int(h*.18)),(far,int(h*.49)),(near,y1)],fill=(5,10,14,232),outline=(110,155,180,48))
            for k in range(8):
                t=(k+1)/9
                x=int(near*(1-t)+far*t)
                yy=int(y0*(1-t)+int(h*.23)*t)
                d.rectangle((x-2,yy,x+2,yy+7),fill=((100,170,210,85) if k%2 else ORANGE+(65,)))
    d.polygon([(center-30,int(h*.55)),(center+30,int(h*.55)),(center+5,int(h*.20)),(center-5,int(h*.20))],fill=(180,190,200,16))


def _scene_aerial_scale(image: Image.Image, card: dict) -> None:
    w,h=image.size
    d=ImageDraw.Draw(image,"RGBA")
    _lights(image,_seed(card),True,7)
    rng=random.Random(_seed(card))
    for r in range(5):
        for c in range(7):
            x=int(w*.08+c*w*.13 + (r%2)*w*.03)
            y=int(h*.10+r*h*.075)
            bw=int(w*(.07+r*.004)); bh=int(h*.045)
            d.polygon([(x,y),(x+bw,y-8),(x+bw+18,y+bh-12),(x+18,y+bh)],fill=(10,12,12,210),outline=(200,180,140,28))
    d.arc((int(w*.08),int(h*.05),int(w*.92),int(h*.56)),200,338,fill=ORANGE+(95,),width=max(2,w//280))


def _scene_split_mining_ai(image: Image.Image, card: dict) -> None:
    w,h=image.size
    left=_base(w//2,h,False); right=_base(w-w//2,h,False)
    _scene_mining_hall(left,card); _scene_ai_server_hall(right,{**card,"story_id":str(card.get("story_id"))+"ai"})
    image.alpha_composite(left,(0,0)); image.alpha_composite(right,(w//2,0))
    d=ImageDraw.Draw(image,"RGBA")
    d.line((w//2,int(h*.06),w//2,int(h*.56)),fill=ORANGE+(105,),width=max(2,w//360))


def _scene_construction_timeline(image: Image.Image, card: dict) -> None:
    w,h=image.size
    _lights(image,_seed(card),True,8)
    d=ImageDraw.Draw(image,"RGBA")
    y=int(h*.36)
    d.line((int(w*.10),y,int(w*.90),y),fill=(230,225,212,55),width=2)
    for i in range(4):
        x=int(w*(.14+i*.24)); r=max(5,w//130)
        d.ellipse((x-r,y-r,x+r,y+r),fill=ORANGE+(160 if i in {1,3} else 90,))
        d.line((x,y-r,x,y-int(h*(.08+.03*(i%2)))),fill=ORANGE+(70,),width=2)
    # crane silhouette
    d.line((int(w*.18),int(h*.52),int(w*.18),int(h*.13)),fill=(200,195,180,50),width=3)
    d.line((int(w*.18),int(h*.16),int(w*.48),int(h*.16)),fill=(200,195,180,50),width=3)
    d.line((int(w*.42),int(h*.16),int(w*.42),int(h*.31)),fill=ORANGE+(55,),width=2)


def _scene_archive(image: Image.Image, card: dict, variant: str) -> None:
    w,h=image.size
    _lights(image,_seed(card),True,8)
    d=ImageDraw.Draw(image,"RGBA")
    paper=(212,199,172,42); ink=(236,228,208,60)
    if variant in {"archival_wall_street","historical_newspaper","historical_market_aftermath"}:
        for i in range(3):
            x=int(w*(.08+i*.27)); y=int(h*(.08+.03*(i%2))); x1=x+int(w*.30); y1=int(h*.48)
            d.rounded_rectangle((x,y,x1,y1),radius=max(5,w//160),fill=paper,outline=(255,255,255,25),width=1)
            yy=y+25
            for j in range(8):
                d.rectangle((x+18,yy,x+int((x1-x)*(.55+.1*(j%3))),yy+3),fill=ink)
                yy+=max(16,h//48)
        if variant=="historical_market_aftermath":
            d.line([(int(w*.12),int(h*.21)),(int(w*.30),int(h*.27)),(int(w*.48),int(h*.23)),(int(w*.66),int(h*.39)),(int(w*.86),int(h*.47))],fill=(210,95,80,130),width=max(3,w//280))
    elif variant=="modern_valuation_display":
        d.rectangle((int(w*.08),int(h*.08),int(w*.92),int(h*.52)),fill=(4,7,8,200),outline=(255,255,255,24))
        pts=[]
        for i in range(24):
            x=int(w*.12+i*w*.032); y=int(h*(.43-.11*math.sin(i/3.3)-i*.006))
            pts.append((x,y))
        d.line(pts,fill=ORANGE+(180,),width=max(3,w//250))
    elif variant=="past_present_split":
        d.rectangle((0,0,w//2,int(h*.56)),fill=(115,90,60,24)); d.rectangle((w//2,0,w,int(h*.56)),fill=(35,65,85,30))
        d.line((w//2,int(h*.06),w//2,int(h*.54)),fill=ORANGE+(90,),width=2)
        for side in [0,1]:
            x0=int(w*(.08 if side==0 else .58)); pts=[]
            for i in range(8): pts.append((x0+i*int(w*.04),int(h*(.24+.05*math.sin(i/1.5)+i*.008))))
            d.line(pts,fill=(230,225,210,105),width=2)
    else:
        _scene_construction_timeline(image,card)


def _scene_money_flow(image: Image.Image, card: dict, variant: str) -> None:
    w,h=image.size
    _lights(image,_seed(card),False,12)
    d=ImageDraw.Draw(image,"RGBA")
    rng=random.Random(_seed(card))
    nodes=[]
    for i in range(7):
        x=int(w*(.10+i*.13)); y=int(h*(.16+.25*rng.random()))
        nodes.append((x,y))
    for i in range(len(nodes)-1):
        d.line((*nodes[i],*nodes[i+1]),fill=ORANGE+(75+i*12,),width=max(2,w//320))
    for i,(x,y) in enumerate(nodes):
        r=max(5,w//130) if i not in {0,len(nodes)-1} else max(8,w//95)
        d.ellipse((x-r,y-r,x+r,y+r),fill=((220,225,220,150) if i==0 else ORANGE+(155,)))
    if variant in {"capital_scale","flow_vs_price_split"}:
        for i,ht in enumerate([.18,.28,.38,.58,.78]):
            x=int(w*(.16+i*.13)); base=int(h*.51); top=base-int(h*.32*ht)
            d.rounded_rectangle((x,top,x+int(w*.065),base),radius=4,fill=ORANGE+(28+i*12,),outline=ORANGE+(60,))


def _scene_policy(image: Image.Image, card: dict, variant: str) -> None:
    w,h=image.size
    _lights(image,_seed(card),True,8)
    d=ImageDraw.Draw(image,"RGBA")
    x0,y0,x1,y1=int(w*.16),int(h*.08),int(w*.84),int(h*.50)
    d.rounded_rectangle((x0,y0,x1,y1),radius=max(8,w//120),fill=(225,217,196,35),outline=(255,255,255,40),width=2)
    yy=y0+35
    for i,ratio in enumerate([.82,.66,.88,.58,.72,.46]):
        d.rectangle((x0+30,yy,x0+30+int((x1-x0-60)*ratio),yy+3),fill=(245,238,220,65)); yy+=max(20,h//38)
    if "new" in variant or "timeline" in variant or "calendar" in variant:
        cx,cy=int(w*.71),int(h*.18); r=max(25,w//26)
        d.ellipse((cx-r,cy-r,cx+r,cy+r),outline=ORANGE+(150,),width=3); d.line((cx-r//2,cy,cx+r//2,cy),fill=ORANGE+(120,),width=3)


def _scene_crisis(image: Image.Image, card: dict, variant: str) -> None:
    w,h=image.size
    _lights(image,_seed(card),False,7)
    d=ImageDraw.Draw(image,"RGBA")
    cx,cy=int(w*.5),int(h*.28); rng=random.Random(_seed(card))
    for i in range(9):
        a=i/9*math.pi*2; rad=int(w*(.15+.04*(i%2))); x=int(cx+math.cos(a)*rad); y=int(cy+math.sin(a)*rad*.7)
        d.line((cx,cy,x,y),fill=(220,90,78,55),width=2); d.ellipse((x-5,y-5,x+5,y+5),fill=(220,90,78,120))
    d.ellipse((cx-22,cy-22,cx+22,cy+22),outline=(220,90,78,160),width=3)


def _draw_scene(card: dict, width: int, height: int) -> Image.Image:
    external = card_renderer._load_visual_asset(card,width,height)
    if external is not None:
        return external.convert("RGBA")
    scene=str((card.get("visual_direction") or {}).get("scene_type") or "editorial_generic")
    warm=any(k in scene for k in ["exterior","archive","power","construction","brand"])
    image=_base(width,height,warm)
    if scene=="industrial_data_center_exterior": _scene_data_center_exterior(image,card)
    elif scene=="bitcoin_mining_hall": _scene_mining_hall(image,card)
    elif scene=="power_grid_infrastructure": _scene_power_grid(image,card)
    elif scene=="ai_server_hall": _scene_ai_server_hall(image,card)
    elif scene=="industrial_aerial_scale": _scene_aerial_scale(image,card)
    elif scene=="ai_compute_power_demand": _scene_ai_server_hall(image,card); _scene_power_grid(image,{**card,"story_id":str(card.get("story_id"))+"p"})
    elif scene=="mining_vs_ai_split": _scene_split_mining_ai(image,card)
    elif scene=="construction_timeline": _scene_construction_timeline(image,card)
    elif scene in {"archival_wall_street","historical_newspaper","historical_market_aftermath","modern_valuation_display","past_present_split","modern_liquidity_context","valuation_watchboard"}: _scene_archive(image,card,scene)
    elif scene in {"institutional_asset_manager","fund_desk","capital_scale","capital_flow_network","flow_vs_price_split","institutional_market","flow_monitor"}: _scene_money_flow(image,card,scene)
    elif "policy" in scene or "regulator" in scene or "institution" in scene and card.get("story_archetype")=="policy_change": _scene_policy(image,card,scene)
    elif scene in {"forensic_scene","incident_detail","asset_exposure_map","contagion_network","forensic_evidence","risk_market_bridge","risk_monitor"}: _scene_crisis(image,card,scene)
    else:
        # Generic story fallback is an editorial object/architecture scene, never a chart.
        _lights(image,_seed(card),warm,14)
        d=ImageDraw.Draw(image,"RGBA"); rng=random.Random(_seed(card))
        for i in range(5):
            x=int(width*(.08+i*.18)); y=int(height*(.11+.05*(i%3))); ww=int(width*(.12+.03*rng.random())); hh=int(height*(.18+.08*rng.random()))
            d.rounded_rectangle((x,y,x+ww,y+hh),radius=8,fill=(18,20,20,115),outline=ORANGE+(35 if i==2 else 18),width=2)
    return image


def _brand(draw: ImageDraw.ImageDraw, scale: float, x: int, y: int) -> None:
    draw.text((x,y),"キヨサキ",font=card_renderer._font(int(27*scale),True),fill=OFF_WHITE)


def _footer(card: dict) -> str:
    source=card.get("source") or {}
    values=["キヨサキ",source.get("publisher"),source.get("short_title")]
    return " · ".join(str(v) for v in values if v)[:120]


def _copy(image: Image.Image, card: dict, box: tuple[int,int,int,int], scale: float, align: str="left") -> None:
    d=ImageDraw.Draw(image,"RGBA"); l,t,r,b=box
    hf=card_renderer._font(int(50*scale),True); bf=card_renderer._font(int(25*scale),True)
    headline=str(card.get("headline") or ""); body=card_renderer._body(card)
    hlines=card_renderer._wrap(d,headline,hf,r-l,3); blines=card_renderer._wrap(d,body,bf,r-l,4)
    y=t
    for line in hlines:
        tw=int(d.textlength(line,font=hf)); x=l if align=="left" else l+max(0,(r-l-tw)//2)
        d.text((x,y),line,font=hf,fill=ORANGE); y+=int(62*scale)
    y+=int(16*scale)
    for line in blines:
        tw=int(d.textlength(line,font=bf)); x=l if align=="left" else l+max(0,(r-l-tw)//2)
        d.text((x,y),line,font=bf,fill=OFF_WHITE); y+=int(38*scale)


def _compose(card: dict, scene: Image.Image, width: int, height: int) -> Image.Image:
    scale=width/1080.0; layout=str((card.get("visual_direction") or {}).get("layout_variant") or "full_bleed_bottom")
    if layout=="split_left":
        image=Image.new("RGBA",(width,height),BG+(255,)); vw=int(width*.57)
        image.alpha_composite(ImageOps.fit(scene,(vw,height),method=Image.Resampling.LANCZOS),(0,0))
        d=ImageDraw.Draw(image,"RGBA"); d.rectangle((vw,0,width,height),fill=(4,5,5,255)); d.line((vw,int(height*.08),vw,int(height*.92)),fill=ORANGE+(55,),width=max(1,int(2*scale)))
        _brand(d,scale,vw+int(42*scale),int(55*scale)); _copy(image,card,(vw+int(42*scale),int(height*.31),width-int(38*scale),int(height*.82)),scale)
    elif layout in {"split_top","top_caption"}:
        image=Image.new("RGBA",(width,height),BG+(255,)); visual_h=int(height*(.56 if layout=="split_top" else .68)); visual_y=0 if layout=="split_top" else int(height*.30)
        image.alpha_composite(ImageOps.fit(scene,(width,visual_h),method=Image.Resampling.LANCZOS),(0,visual_y)); d=ImageDraw.Draw(image,"RGBA")
        if layout=="top_caption": d.rectangle((0,0,width,visual_y+5),fill=(4,5,5,255)); copy_box=(int(70*scale),int(height*.10),width-int(70*scale),visual_y-int(12*scale))
        else: d.rectangle((0,visual_h,width,height),fill=(4,5,5,252)); copy_box=(int(70*scale),visual_h+int(38*scale),width-int(70*scale),int(height*.88))
        _brand(d,scale,int(70*scale),int(55*scale)); _copy(image,card,copy_box,scale)
    elif layout=="poster_center":
        image=ImageOps.fit(scene,(width,height),method=Image.Resampling.LANCZOS).convert("RGBA"); overlay=Image.new("RGBA",(width,height),(0,0,0,0)); od=ImageDraw.Draw(overlay,"RGBA"); od.rectangle((0,int(height*.48),width,height),fill=(0,0,0,155)); image.alpha_composite(overlay); d=ImageDraw.Draw(image,"RGBA"); _brand(d,scale,int(70*scale),int(55*scale)); _copy(image,card,(int(90*scale),int(height*.58),width-int(90*scale),int(height*.88)),scale,"center")
    elif layout=="newspaper_panel":
        image=ImageOps.fit(scene,(width,height),method=Image.Resampling.LANCZOS).convert("RGBA"); d=ImageDraw.Draw(image,"RGBA"); panel=(int(width*.07),int(height*.53),int(width*.93),int(height*.92)); d.rounded_rectangle(panel,radius=max(8,int(12*scale)),fill=(7,7,6,238),outline=ORANGE+(38,),width=2); _brand(d,scale,int(70*scale),int(55*scale)); _copy(image,card,(panel[0]+int(34*scale),panel[1]+int(30*scale),panel[2]-int(34*scale),panel[3]-int(30*scale)),scale)
    elif layout=="data_monument":
        image=Image.new("RGBA",(width,height),BG+(255,)); vh=int(height*.48); image.alpha_composite(ImageOps.fit(scene,(width,vh),method=Image.Resampling.LANCZOS),(0,0)); d=ImageDraw.Draw(image,"RGBA"); _brand(d,scale,int(70*scale),int(55*scale)); # one evidence value as monument
        value=""; ev=str(card.get("evidence_excerpt") or ""); m=__import__('re').search(r"(?:約?\d[\d,.]*億ドル|\$\s?\d[\d,.]*(?:\s?(?:billion|million))?|\d[\d,.]*\s?(?:MW|メガワット)|\d+(?:\.\d+)?%)",ev,flags=__import__('re').I); value=m.group(0) if m else ""
        if value: d.text((int(70*scale),int(height*.52)),value,font=card_renderer._font(int(72*scale),True),fill=ORANGE)
        _copy(image,card,(int(70*scale),int(height*(.64 if value else .56)),width-int(70*scale),int(height*.90)),scale)
    else:
        image=ImageOps.fit(scene,(width,height),method=Image.Resampling.LANCZOS).convert("RGBA"); card_renderer._draw_bottom_gradient(image,top_ratio=.48); d=ImageDraw.Draw(image,"RGBA"); _brand(d,scale,int(70*scale),int(55*scale)); _copy(image,card,(int(70*scale),int(height*.66),width-int(70*scale),int(height*.90)),scale)
    d=ImageDraw.Draw(image,"RGBA"); d.text((int(70*scale),height-int(42*scale)),_footer(card),font=card_renderer._font(int(15*scale)),fill=(145,140,133,205)); card_renderer._film_grain(image,strength=6); return image


def _brand_outro(card: dict, width: int, height: int) -> Image.Image:
    external=card_renderer._load_visual_asset(card,width,height)
    if external is not None:
        scene=external.convert("RGBA")
    else:
        scene=_base(width,height,True); _lights(scene,_seed(card),True,12); d=ImageDraw.Draw(scene,"RGBA"); cx=width//2
        # layered soft rim to mimic a photographic silhouette rather than a flat icon
        glow=Image.new("RGBA",scene.size,(0,0,0,0)); gd=ImageDraw.Draw(glow,"RGBA")
        for rr,a in [(int(width*.19),18),(int(width*.14),30),(int(width*.10),48)]: gd.ellipse((cx-rr,int(height*.08),cx+rr,int(height*.08)+2*rr),fill=ORANGE+(a,))
        scene.alpha_composite(glow.filter(ImageFilter.GaussianBlur(radius=max(8,width//28))))
        # head, shoulders, tailored torso
        head=(int(width*.42),int(height*.11),int(width*.58),int(height*.29)); d.ellipse(head,fill=(1,1,1,255)); d.arc(head,195,345,fill=ORANGE+(205,),width=max(2,width//300)); d.arc(head,15,165,fill=ORANGE+(205,),width=max(2,width//300))
        d.rectangle((int(width*.465),int(height*.27),int(width*.535),int(height*.36)),fill=(2,2,2,255))
        d.polygon([(int(width*.22),int(height*.64)),(int(width*.27),int(height*.42)),(int(width*.35),int(height*.34)),(int(width*.45),int(height*.31)),(int(width*.55),int(height*.31)),(int(width*.65),int(height*.34)),(int(width*.73),int(height*.42)),(int(width*.78),int(height*.64))],fill=(3,3,3,255))
        # lapels and textile sheen
        d.polygon([(int(width*.35),int(height*.35)),(int(width*.47),int(height*.45)),(int(width*.49),int(height*.62)),(int(width*.39),int(height*.48))],fill=(16,16,15,255)); d.polygon([(int(width*.65),int(height*.35)),(int(width*.53),int(height*.45)),(int(width*.51),int(height*.62)),(int(width*.61),int(height*.48))],fill=(13,13,12,255))
        d.polygon([(int(width*.485),int(height*.36)),(int(width*.515),int(height*.36)),(int(width*.522),int(height*.42)),(int(width*.507),int(height*.57)),(int(width*.493),int(height*.57)),(int(width*.478),int(height*.42))],fill=(0,0,0,255))
        d.line((int(width*.35),int(height*.34),int(width*.27),int(height*.42)),fill=ORANGE+(85,),width=max(2,width//360)); d.line((int(width*.65),int(height*.34),int(width*.73),int(height*.42)),fill=ORANGE+(85,),width=max(2,width//360))
        # clasped gloves with finger creases
        gy=int(height*.57); lg=(cx-int(width*.11),gy-int(height*.025),cx+int(width*.008),gy+int(height*.035)); rg=(cx-int(width*.008),gy-int(height*.025),cx+int(width*.11),gy+int(height*.035)); d.ellipse(lg,fill=(2,2,2,255),outline=(90,85,78,120),width=2); d.ellipse(rg,fill=(2,2,2,255),outline=(90,85,78,120),width=2)
        for dx in [-70,-50,-30,30,50,70]: d.line((cx+int(dx*width/1080),gy-5,cx+int((dx+(8 if dx<0 else -8))*width/1080),gy+14),fill=(110,105,95,65),width=1)
    card_renderer._draw_bottom_gradient(scene,top_ratio=.60); scale=width/1080; d=ImageDraw.Draw(scene,"RGBA"); _brand(d,scale,int(70*scale),int(55*scale)); _copy(scene,card,(int(70*scale),int(height*.72),width-int(70*scale),int(height*.91)),scale); d.text((int(70*scale),height-int(42*scale)),"キヨサキ",font=card_renderer._font(int(15*scale)),fill=(145,140,133,205)); card_renderer._film_grain(scene,strength=6); return scene


def render_story_card_image(card: dict, width: int=1080, height: int=1350) -> Image.Image:
    if card.get("card_type")=="brand_outro": return _brand_outro(card,width,height).convert("RGB")
    scene=_draw_scene(card,width,height); return _compose(card,scene,width,height).convert("RGB")


def render_story_card_png(card: dict, width: int=1080, height: int=1350) -> bytes:
    out=BytesIO(); render_story_card_image(card,width,height).save(out,format="PNG",optimize=True); return out.getvalue()
