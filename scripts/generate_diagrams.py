"""
scripts/generate_diagrams.py
Generates clean, professional high-resolution architectural diagrams and verification figures
for embedding into both Word (.docx) and PDF (.pdf) internship reports.
"""

import os
from PIL import Image, ImageDraw, ImageFont

os.makedirs("docs/figures/generated", exist_ok=True)

def get_fonts():
    try:
        title_font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 24)
        body_font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 16)
        mono_font = ImageFont.truetype("/System/Library/Fonts/Courier.dfont", 14)
        small_font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 12)
    except Exception:
        title_font = ImageFont.load_default()
        body_font = ImageFont.load_default()
        mono_font = ImageFont.load_default()
        small_font = ImageFont.load_default()
    return title_font, body_font, mono_font, small_font

title_font, body_font, mono_font, small_font = get_fonts()

def draw_rounded_rect(draw, xy, fill, outline, radius=8, width=2):
    draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=width)

def generate_erd():
    width, height = 1400, 900
    img = Image.new("RGBA", (width, height), (255, 255, 255, 255))
    draw = ImageDraw.Draw(img)

    draw.rectangle([0, 0, width, 50], fill=(245, 247, 250, 255))
    draw.text((width // 2, 25), "Figure 4.3: Magicpin AI Agent — PostgreSQL Relational Schema (ERD)",
              font=title_font, fill=(30, 41, 59, 255), anchor="mm")

    tables = [
        {
            "name": "users", "x": 60, "y": 80, "w": 280, "h": 220,
            "cols": ["id: UUID (PK)", "email: VARCHAR(255) (UNIQUE)", "hashed_password: TEXT (Argon2id)",
                     "is_active: BOOLEAN", "created_at: TIMESTAMPTZ", "updated_at: TIMESTAMPTZ"]
        },
        {
            "name": "merchant_profiles", "x": 400, "y": 80, "w": 320, "h": 240,
            "cols": ["id: UUID (PK)", "user_id: UUID (FK -> users.id)", "business_name: VARCHAR(255)",
                     "category: VARCHAR(100)", "city: VARCHAR(100)", "contact_email: VARCHAR(255)",
                     "created_at: TIMESTAMPTZ", "updated_at: TIMESTAMPTZ"]
        },
        {
            "name": "user_sessions", "x": 60, "y": 340, "w": 280, "h": 200,
            "cols": ["id: UUID (PK)", "user_id: UUID (FK -> users.id)", "token_hash: VARCHAR(64) (UNIQUE)",
                     "expires_at: TIMESTAMPTZ", "created_at: TIMESTAMPTZ", "last_active_at: TIMESTAMPTZ"]
        },
        {
            "name": "context_items", "x": 780, "y": 80, "w": 320, "h": 240,
            "cols": ["id: UUID (PK)", "merchant_id: UUID (FK)", "item_type: VARCHAR(50)",
                     "content: TEXT", "version: INTEGER (Optimistic Lock)", "is_active: BOOLEAN",
                     "created_at: TIMESTAMPTZ", "updated_at: TIMESTAMPTZ"]
        },
        {
            "name": "conversations", "x": 400, "y": 380, "w": 320, "h": 200,
            "cols": ["id: UUID (PK)", "merchant_id: UUID (FK)", "status: VARCHAR(30)",
                     "created_at: TIMESTAMPTZ", "updated_at: TIMESTAMPTZ", "archived_at: TIMESTAMPTZ"]
        },
        {
            "name": "messages", "x": 780, "y": 380, "w": 320, "h": 240,
            "cols": ["id: UUID (PK)", "conversation_id: UUID (FK)", "role: VARCHAR(20) (user/assistant)",
                     "content: TEXT", "status: VARCHAR(20)", "created_at: TIMESTAMPTZ",
                     "idempotency_key: VARCHAR(64)"]
        },
        {
            "name": "suggested_actions", "x": 1140, "y": 380, "w": 230, "h": 240,
            "cols": ["id: UUID (PK)", "conversation_id: UUID (FK)", "action_type: VARCHAR(50)",
                     "draft_text: TEXT", "status: VARCHAR(20) (pending)", "reviewed_at: TIMESTAMPTZ",
                     "created_at: TIMESTAMPTZ"]
        },
        {
            "name": "audit_events", "x": 60, "y": 580, "w": 280, "h": 200,
            "cols": ["id: UUID (PK)", "event_type: VARCHAR(100)", "client_ip: VARCHAR(45)",
                     "details: JSONB", "created_at: TIMESTAMPTZ"]
        }
    ]

    for t in tables:
        x, y, w, h = t["x"], t["y"], t["w"], t["h"]
        draw_rounded_rect(draw, [x, y, x + w, y + h], fill=(255, 255, 255, 255), outline=(203, 213, 225, 255))
        draw.rounded_rectangle([x, y, x + w, y + 36], radius=6, fill=(30, 41, 59, 255))
        draw.text((x + 12, y + 18), t["name"], font=body_font, fill=(255, 255, 255, 255), anchor="lm")
        cur_y = y + 48
        for c in t["cols"]:
            draw.text((x + 12, cur_y), c, font=small_font, fill=(51, 65, 85, 255))
            cur_y += 24

    # Connectors
    draw.line([(340, 160), (400, 160)], fill=(37, 99, 235, 255), width=2)
    draw.polygon([(395, 155), (405, 160), (395, 165)], fill=(37, 99, 235, 255))

    draw.line([(200, 300), (200, 340)], fill=(37, 99, 235, 255), width=2)
    draw.polygon([(195, 335), (200, 345), (205, 335)], fill=(37, 99, 235, 255))

    draw.line([(720, 160), (780, 160)], fill=(37, 99, 235, 255), width=2)
    draw.polygon([(775, 155), (785, 160), (775, 165)], fill=(37, 99, 235, 255))

    draw.line([(560, 320), (560, 380)], fill=(37, 99, 235, 255), width=2)
    draw.polygon([(555, 375), (560, 385), (565, 375)], fill=(37, 99, 235, 255))

    draw.line([(720, 460), (780, 460)], fill=(37, 99, 235, 255), width=2)
    draw.polygon([(775, 455), (785, 460), (775, 465)], fill=(37, 99, 235, 255))

    draw.line([(1100, 460), (1140, 460)], fill=(37, 99, 235, 255), width=2)
    draw.polygon([(1135, 455), (1145, 460), (1135, 465)], fill=(37, 99, 235, 255))

    img.save("docs/figures/generated/figure_4_3_erd.png")
    print("Generated: docs/figures/generated/figure_4_3_erd.png")

def generate_hitl_workflow():
    width, height = 1200, 500
    img = Image.new("RGBA", (width, height), (255, 255, 255, 255))
    draw = ImageDraw.Draw(img)

    draw.rectangle([0, 0, width, 50], fill=(245, 247, 250, 255))
    draw.text((width // 2, 25), "Figure 4.4: Human-in-the-Loop Suggested Actions Review State Machine",
              font=title_font, fill=(30, 41, 59, 255), anchor="mm")

    boxes = [
        {"text": ["Customer Inquiry Turn", "Inbound Support Query"], "x": 60, "y": 140, "w": 200, "h": 90, "fill": (241, 245, 249, 255)},
        {"text": ["Intent Classifier &", "Deterministic Heuristics"], "x": 320, "y": 140, "w": 220, "h": 90, "fill": (224, 231, 255, 255)},
        {"text": ["Suggested Action Created", "status = 'pending'"], "x": 600, "y": 140, "w": 240, "h": 90, "fill": (254, 243, 199, 255)},
        {"text": ["Action Approved", "status = 'approved'", "reviewed_at = UTC NOW"], "x": 920, "y": 90, "w": 220, "h": 85, "fill": (220, 252, 231, 255)},
        {"text": ["Action Dismissed", "status = 'dismissed'", "reviewed_at = UTC NOW"], "x": 920, "y": 210, "w": 220, "h": 85, "fill": (254, 226, 226, 255)},
    ]

    for b in boxes:
        draw_rounded_rect(draw, [b["x"], b["y"], b["x"] + b["w"], b["y"] + b["h"]], fill=b["fill"], outline=(148, 163, 184, 255))
        cy = b["y"] + b["h"] // 2 - (len(b["text"]) - 1) * 10
        for line in b["text"]:
            draw.text((b["x"] + b["w"] // 2, cy), line, font=body_font, fill=(30, 41, 59, 255), anchor="mm")
            cy += 20

    draw.line([(260, 185), (320, 185)], fill=(71, 85, 105, 255), width=2)
    draw.polygon([(315, 180), (325, 185), (315, 190)], fill=(71, 85, 105, 255))

    draw.line([(540, 185), (600, 185)], fill=(71, 85, 105, 255), width=2)
    draw.polygon([(595, 180), (605, 185), (595, 190)], fill=(71, 85, 105, 255))

    draw.line([(840, 160), (920, 132)], fill=(22, 101, 52, 255), width=2)
    draw.polygon([(915, 127), (925, 132), (918, 137)], fill=(22, 101, 52, 255))

    draw.line([(840, 210), (920, 252)], fill=(153, 27, 27, 255), width=2)
    draw.polygon([(918, 247), (925, 252), (915, 257)], fill=(153, 27, 27, 255))

    draw_rounded_rect(draw, [60, 350, 1140, 440], fill=(248, 250, 252, 255), outline=(225, 29, 72, 255), width=2)
    draw.text((width // 2, 380), "STRICT HUMAN-IN-THE-LOOP / ZERO EXTERNAL SIDE-EFFECTS GUARANTEE",
              font=body_font, fill=(225, 29, 72, 255), anchor="mm")
    draw.text((width // 2, 410), "Approving or dismissing an action exclusively updates PostgreSQL review records. The system NEVER triggers unreviewed external dispatches.",
              font=small_font, fill=(71, 85, 105, 255), anchor="mm")

    img.save("docs/figures/generated/figure_4_4_hitl.png")
    print("Generated: docs/figures/generated/figure_4_4_hitl.png")

def generate_whatsapp_future():
    width, height = 1200, 480
    img = Image.new("RGBA", (width, height), (255, 255, 255, 255))
    draw = ImageDraw.Draw(img)

    draw.rectangle([0, 0, width, 50], fill=(245, 247, 250, 255))
    draw.text((width // 2, 25), "Figure 4.5: Proposed Future WhatsApp Business Integration Architecture",
              font=title_font, fill=(30, 41, 59, 255), anchor="mm")

    steps = [
        ("1. Customer", "WhatsApp User sends message"),
        ("2. Meta Webhook", "Verified HMAC SHA-256 ingress"),
        ("3. Backend Ingress", "Identify merchant & session"),
        ("4. Grounded AI", "Inject policies & draft response"),
        ("5. Review Queue", "Merchant edits & approves"),
        ("6. Cloud API", "Dispatch approved reply")
    ]

    x = 40
    step_width = 160
    gap = 35
    y = 120
    h = 100

    for idx, (title, desc) in enumerate(steps):
        draw_rounded_rect(draw, [x, y, x + step_width, y + h], fill=(240, 253, 250, 255), outline=(13, 148, 136, 255))
        draw.text((x + step_width // 2, y + 25), title, font=body_font, fill=(15, 118, 110, 255), anchor="mm")
        words = desc.split()
        l1 = " ".join(words[:2])
        l2 = " ".join(words[2:])
        draw.text((x + step_width // 2, y + 55), l1, font=small_font, fill=(51, 65, 85, 255), anchor="mm")
        draw.text((x + step_width // 2, y + 75), l2, font=small_font, fill=(51, 65, 85, 255), anchor="mm")

        if idx < len(steps) - 1:
            arr_x = x + step_width
            draw.line([(arr_x, y + h // 2), (arr_x + gap, y + h // 2)], fill=(13, 148, 136, 255), width=2)
            draw.polygon([(arr_x + gap - 5, y + h // 2 - 5), (arr_x + gap, y + h // 2), (arr_x + gap - 5, y + h // 2 + 5)], fill=(13, 148, 136, 255))
        x += step_width + gap

    draw_rounded_rect(draw, [60, 300, 1140, 400], fill=(254, 252, 232, 255), outline=(202, 138, 4, 255), width=2)
    draw.text((width // 2, 330), "PLANNED ENHANCEMENT / FUTURE ROADMAP ONLY", font=body_font, fill=(161, 98, 7, 255), anchor="mm")
    draw.text((width // 2, 365), "Subject to Meta Developer registration, WABA verification, official webhook approval, and merchant tenant isolation.", font=small_font, fill=(113, 63, 18, 255), anchor="mm")

    img.save("docs/figures/generated/figure_4_5_whatsapp.png")
    print("Generated: docs/figures/generated/figure_4_5_whatsapp.png")

if __name__ == "__main__":
    generate_erd()
    generate_hitl_workflow()
    generate_whatsapp_future()
    print("All diagrams generated successfully.")
