from PIL import Image, ImageDraw, ImageFont, ImageFilter
import os
import random
import glob

def generate_points_table(lobby_name, host_name, teams_data, logo_path=None):
    """
    Points Table with Random Background Rotation & Clean Rounded UI.
    """
    # Portrait Resolution (High Quality)
    W, H = 1080, 1350
    
    # --- 1. BACKGROUND SELECTION ---
    # Look for backgrounds in assets/backgrounds/
    bg_dir = os.path.join(os.path.dirname(__file__), "assets", "backgrounds")
    bg_files = glob.glob(os.path.join(bg_dir, "*.png")) + glob.glob(os.path.join(bg_dir, "*.jpg"))
    
    if bg_files:
        selected_bg = random.choice(bg_files)
        try:
            bg = Image.open(selected_bg).resize((W, H), Image.Resampling.LANCZOS)
        except:
            bg = Image.new('RGB', (W, H), (20, 20, 30))
    else:
        # Fallback dark background
        bg = Image.new('RGB', (W, H), (15, 15, 25))
        
    draw = ImageDraw.Draw(bg)
    
    # Dark Vignette/Overlay for readability
    overlay = Image.new('RGBA', (W, H), (0,0,0,0))
    o_draw = ImageDraw.Draw(overlay)
    # Gradient from bottom up
    for y in range(H):
        alpha = int(200 * (y/H)) # Darker at bottom
        o_draw.line([(0, y), (W, y)], fill=(0, 0, 0, 50 + int(alpha*0.8)))
    # Solid dark tint overall
    o_draw.rectangle([0,0,W,H], fill=(0,0,0,80))
    bg.paste(overlay, (0,0), overlay)

    # --- FONTS ---
    def get_font(name_list, size):
        for name in name_list:
            try:
                return ImageFont.truetype(name, size)
            except:
                continue
        return ImageFont.load_default()

    font_title = get_font(["segoeuib.ttf", "arialbd.ttf"], 48)
    font_bold = get_font(["segoeuib.ttf", "arialbd.ttf"], 23)  # Smaller Team Names
    font_data = get_font(["segoeuib.ttf", "arialbd.ttf"], 25)  # Smaller Stats
    font_header = get_font(["segoeui.ttf", "arial.ttf"], 18)
    font_sub = get_font(["segoeui.ttf", "arial.ttf"], 32)
    font_logo = get_font(["segoeuib.ttf", "arialbd.ttf"], 36)

    # --- HEADER SECTION ---
    # Layout: [Logo]  [Host Name] (Centered together)
    # 1. Load Logo
    # 1. Load Logo
    import requests
    import io
    
    if not logo_path:
        # Fallback to local default
        logo_path = os.path.join(os.path.dirname(__file__), "assets", "logo.png")
        
    logo_img = None
    
    try:
        # Check if URL
        if logo_path.startswith("http"):
            resp = requests.get(logo_path)
            if resp.status_code == 200:
                logo_img = Image.open(io.BytesIO(resp.content))
        elif os.path.exists(logo_path):
            logo_img = Image.open(logo_path)
            
        if logo_img:
            logo_img.thumbnail((120, 120), Image.Resampling.LANCZOS)
    except Exception as e:
        print(f"Error loading logo: {e}")
        pass

    # 2. Prepare Text
    font_host_big = get_font(["segoeuib.ttf", "arialbd.ttf"], 65) # Slightly smaller to fit side-by-side
    mask_bbox = draw.textbbox((0, 0), host_name.upper(), font=font_host_big)
    text_w = mask_bbox[2] - mask_bbox[0]
    text_h = mask_bbox[3] - mask_bbox[1]
    
    # 3. Calculate Layout
    logo_w = logo_img.width if logo_img else 0
    padding = 30 if logo_img else 0
    total_w = logo_w + padding + text_w
    
    start_x = (W - total_w) // 2
    header_base_y = 120
    
    # 4. Draw
    if logo_img:
        # Center logo vertically relative to text
        logo_y = header_base_y + (text_h - logo_img.height) // 2 - 10 # Slight visual tweak
        bg.paste(logo_img, (start_x, logo_y), logo_img if logo_img.mode == 'RGBA' else None)
        
    draw.text((start_x + logo_w + padding, header_base_y), host_name.upper(), font=font_host_big, fill=(255, 255, 255), anchor="lt")
    
    # 5. "Overall Standings" Subtitle
    draw.text((W//2, header_base_y + text_h + 30), "OVERALL STANDINGS", font=font_sub, fill=(200, 200, 200), anchor="mt")
    
    header_bottom_y = header_base_y + text_h + 50

    # --- TABLE LAYOUT (Bottom Anchored) ---
    BOTTOM_MARGIN = 140 # More footer space
    ROW_HEIGHT = 60      # More compact rows
    ROW_SPACING = 10     # Tighter spacing
    
    num_teams = len(teams_data)
    total_table_height = num_teams * (ROW_HEIGHT + ROW_SPACING)
    
    # Anchor to bottom
    TABLE_START_Y = H - BOTTOM_MARGIN - total_table_height
    
    if TABLE_START_Y < (header_bottom_y + 100):
        TABLE_START_Y = header_bottom_y + 100

    cols = [
        {"label": "RANK", "x": 80, "align": "mm"},
        {"label": "TEAM NAME", "x": 160, "align": "lm"}, 
        {"label": "BOOYAH", "x": 620, "align": "mm"},
        {"label": "MATCH", "x": 720, "align": "mm"},
        {"label": "PLACE", "x": 820, "align": "mm"},
        {"label": "KILL", "x": 920, "align": "mm"},
        {"label": "TOTAL", "x": 1020, "align": "mm"}
    ]

    # Draw Column Headers with Background
    header_y = TABLE_START_Y - 45
    # Centered background bar
    header_bg_rect = [20, header_y - 20, W - 20, header_y + 20]
    draw.rounded_rectangle(header_bg_rect, radius=8, fill=(0, 0, 0, 180)) 
    
    for col in cols:
        draw.text((col["x"], header_y), col["label"], font=font_header, fill=(255, 255, 255), anchor=col["align"])

    # --- ROWS ---
    curr_y = TABLE_START_Y
    
    for i, team in enumerate(teams_data):
        rank = i + 1
        
        row_bg_color = (255, 255, 255, 240) 
        rank_bg_color = (255, 140, 0) if rank <= 3 else (220, 220, 220)
        rank_text_color = (0,0,0)
        
        # Common outline settings for "Polish"
        outline_color = (0, 0, 0, 50)
        outline_width = 1

        # 1. Rank Box
        rank_rect = [40, curr_y, 120, curr_y + ROW_HEIGHT]
        draw.rounded_rectangle(rank_rect, radius=8, fill=rank_bg_color, outline=outline_color, width=outline_width)
        draw.text((80, curr_y + ROW_HEIGHT//2), f"{rank:02d}", font=font_bold, fill=rank_text_color, anchor="mm")
        
        # 2. Team Name Box
        name_rect = [135, curr_y, 550, curr_y + ROW_HEIGHT]
        draw.rounded_rectangle(name_rect, radius=8, fill=row_bg_color, outline=outline_color, width=outline_width)
        draw.text((160, curr_y + ROW_HEIGHT//2), team['team'].upper(), font=font_bold, fill=(20, 20, 20), anchor="lm")
        
        # 3. Stats Boxes
        stats_vals = [
            (team['booyah'], 620),
            (team['matches'], 720),
            (team['pts'] - team['kills'], 820),
            (team['kills'], 920),
            (team['pts'], 1020)
        ]
        
        for val, cx in stats_vals:
            box_rect = [cx - 40, curr_y, cx + 40, curr_y + ROW_HEIGHT]
            # Highlight Total Points
            box_color = row_bg_color
            if cx == 1020: 
                box_color = (255, 140, 0) 
            
            draw.rounded_rectangle(box_rect, radius=8, fill=box_color, outline=outline_color, width=outline_width)
            draw.text((cx, curr_y + ROW_HEIGHT//2), f"{val:02d}", font=font_data, fill=(20,20,20), anchor="mm")
            
        curr_y += ROW_HEIGHT + ROW_SPACING

    # --- FOOTER (FF MAX LOGO) ---
    footer_y = H - 50 # Lowered to bottom edge
    
    ff_logo_path = os.path.join(os.path.dirname(__file__), "assets", "ffmax_logo.png")
    if os.path.exists(ff_logo_path):
        try:
            ff_logo = Image.open(ff_logo_path)
            # Resize
            ff_logo.thumbnail((400, 100), Image.Resampling.LANCZOS)
            ff_x = (W - ff_logo.width) // 2
            ff_y = H - ff_logo.height - 20
            bg.paste(ff_logo, (ff_x, ff_y), ff_logo if ff_logo.mode == 'RGBA' else None)
        except:
            draw.text((W//2, footer_y), "FREE FIRE MAX", font=font_logo, fill=(255, 255, 255), anchor="mm")
    else:
        # Text fallback if no logo
        draw.text((W//2, footer_y), "FREE FIRE MAX", font=font_logo, fill=(255, 255, 255), anchor="mm")
    
    # Save with unique filename to prevent race conditions
    import uuid
    output_path = f"points_table_{uuid.uuid4().hex[:8]}.png"
    bg.save(output_path)
    return output_path