import os
import json
import requests
from flask import Flask, render_template, request, jsonify
import anthropic

app = Flask(__name__)

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
BUFFER_ACCESS_TOKEN = os.environ.get("BUFFER_ACCESS_TOKEN", "")

BUFFER_API_BASE = "https://api.bufferapp.com/1"


def get_token(header_name: str, env_var: str) -> str:
    """Read credential from request header first, then fall back to env var."""
    from flask import request as _req
    return _req.headers.get(header_name) or os.environ.get(env_var, "")


def get_buffer_profiles():
    """Fetch connected Buffer profiles."""
    token = get_token("X-Buffer-Token", "BUFFER_ACCESS_TOKEN")
    if not token:
        return []
    try:
        resp = requests.get(
            f"{BUFFER_API_BASE}/profiles.json",
            params={"access_token": token},
            timeout=10,
        )
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return []


def buffer_post(profile_ids: list, text: str, media_url: str = "") -> dict:
    """Create a Buffer update scheduled for now."""
    token = get_token("X-Buffer-Token", "BUFFER_ACCESS_TOKEN")
    payload = {
        "access_token": token,
        "text": text,
        "profile_ids[]": profile_ids,
        "now": "true",
    }
    if media_url:
        payload["media[link]"] = media_url
    try:
        resp = requests.post(
            f"{BUFFER_API_BASE}/updates/create.json",
            data=payload,
            timeout=15,
        )
        return resp.json()
    except Exception as e:
        return {"error": str(e)}


def generate_captions(description: str, platform: str, tone: str, niche: str) -> str:
    """Call Claude to generate platform-optimised captions."""
    api_key = get_token("X-Anthropic-Key", "ANTHROPIC_API_KEY")
    client = anthropic.Anthropic(api_key=api_key)

    platform_guides = {
        "instagram": "Instagram Reels — max 2200 chars, hook in first line, 5-15 relevant hashtags, emoji-rich, call-to-action",
        "tiktok": "TikTok — punchy, conversational, 1-3 hashtags max, trending language, 150 chars ideal",
        "linkedin": "LinkedIn — professional tone, insight-led, 1-3 hashtags, no emoji overload, 700 chars max",
        "twitter": "Twitter/X — under 280 chars, witty, 1-2 hashtags, high shareability",
        "facebook": "Facebook — casual and warm, 1-2 hashtags, 500 chars ideal, encourage comments",
        "youtube": "YouTube Shorts — keyword-rich title + description, 3-5 tags, hook in first sentence",
    }

    guide = platform_guides.get(platform.lower(), "General social media post — engaging, clear, with hashtags")

    prompt = f"""You are a world-class social media copywriter. Generate ONE high-converting caption for a short-form video.

Platform guidelines: {guide}
Content niche: {niche}
Desired tone: {tone}
Video description: {description}

Requirements:
- Write ONLY the caption text (no labels, no explanations, no quotes around it)
- Include a compelling hook as the very first line
- Add relevant hashtags at the end
- Use line breaks naturally for readability
- End with a clear CTA (call-to-action)
"""

    message = client.messages.create(
        model="claude-opus-4-8",
        max_tokens=1024,
        thinking={"type": "adaptive"},
        messages=[{"role": "user", "content": prompt}],
    )

    for block in message.content:
        if block.type == "text":
            return block.text.strip()

    return ""


@app.route("/")
def index():
    return render_template("dashboard.html")


@app.route("/api/profiles")
def profiles():
    data = get_buffer_profiles()
    return jsonify(data)


@app.route("/api/generate", methods=["POST"])
def generate():
    body = request.get_json(force=True)
    description = body.get("description", "").strip()
    platform = body.get("platform", "instagram")
    tone = body.get("tone", "engaging")
    niche = body.get("niche", "general")

    if not description:
        return jsonify({"error": "Video description is required"}), 400
    if not get_token("X-Anthropic-Key", "ANTHROPIC_API_KEY"):
        return jsonify({"error": "ANTHROPIC_API_KEY not configured"}), 500

    caption = generate_captions(description, platform, tone, niche)
    return jsonify({"caption": caption, "platform": platform})


@app.route("/api/post", methods=["POST"])
def post_to_buffer():
    body = request.get_json(force=True)
    caption = body.get("caption", "").strip()
    profile_ids = body.get("profile_ids", [])
    media_url = body.get("media_url", "")

    if not caption:
        return jsonify({"error": "Caption is required"}), 400
    if not profile_ids:
        return jsonify({"error": "Select at least one social account"}), 400
    if not get_token("X-Buffer-Token", "BUFFER_ACCESS_TOKEN"):
        return jsonify({"error": "BUFFER_ACCESS_TOKEN not configured"}), 500

    result = buffer_post(profile_ids, caption, media_url)
    return jsonify(result)


if __name__ == "__main__":
    app.run(debug=True, port=5000)
