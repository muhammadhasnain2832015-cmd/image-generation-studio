import base64
import datetime
import io
import os
import random
import time

import requests
import streamlit as st
from PIL import Image

# ---------------- Settings ----------------
API_URL = "https://generativelanguage.googleapis.com/v1beta/interactions"
SAVE_DIR = "generated_images"

# Label -> Gemini image model ID
MODELS = {
    "Nano Banana 2 Lite (sabse sasta/tez)": "gemini-3.1-flash-lite-image",
    "Nano Banana 2 (balanced)": "gemini-3.1-flash-image",
    "Nano Banana Pro (best quality)": "gemini-3-pro-image",
}

# Sirf wahi aspect ratios jo API support karti hai
ASPECT_RATIOS = {
    "Landscape 16:9 (banners, presentations)": "16:9",
    "Square 1:1 (avatars, product grids)": "1:1",
    "Vertical 9:16 (reels, wallpapers)": "9:16",
}

# Style presets: ye text prompt ke saath jur jata hai
STYLES = {
    "None": "",
    "Cyberpunk": "cyberpunk style, neon lights, rainy futuristic city mood",
    "Minimalism": "minimalist style, clean composition, lots of empty space, soft colors",
    "Watercolor": "soft watercolor painting, gentle brush strokes",
    "Photorealistic": "ultra realistic photo, natural lighting, sharp details",
    "Anime": "anime style, vibrant colors, clean line art",
}

os.makedirs(SAVE_DIR, exist_ok=True)


class SafetyBlocked(Exception):
    """Prompt ya image safety filter mein phans gayi."""


# ---------------- API call ----------------
def extract_output(data):
    """Response se base64 images aur model ka text nikalo."""
    images, texts = [], []
    for step in data.get("steps") or []:
        if step.get("type") == "model_output":
            for block in step.get("content") or []:
                if block.get("type") == "image" and block.get("data"):
                    images.append(block["data"])
                elif block.get("type") == "text" and block.get("text"):
                    texts.append(block["text"])
    return images, " ".join(texts)


def generate_one(api_key, model, prompt, aspect_ratio, max_retries=4):
    """Ek image ke liye ek request. (base64 images ki list, model ka text) wapas deta hai."""
    headers = {"x-goog-api-key": api_key, "Content-Type": "application/json"}
    payload = {
        "model": model,
        "input": prompt,
        "response_format": {"type": "image", "aspect_ratio": aspect_ratio},
    }

    for attempt in range(1, max_retries + 1):
        try:
            # (connect timeout, read timeout): program kabhi hamesha ke liye nahi atkega
            resp = requests.post(API_URL, headers=headers, json=payload, timeout=(3.05, 120))
        except requests.exceptions.ConnectTimeout:
            # Fail fast: connection hi nahi bana, intezar ka faida nahi
            raise RuntimeError("Server se connection nahi ban paya. Internet check karein.")
        except requests.exceptions.ReadTimeout:
            if attempt == max_retries:
                raise RuntimeError("Server ne bohat der laga di. Thori dair baad try karein.")
            time.sleep(min(2 ** attempt + random.uniform(0, 1), 30))  # backoff + jitter
            continue
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Network error: {e}")

        # Server busy ya rate limit: ruk kar dobara try karo
        if resp.status_code in (429, 500, 503):
            try:
                server_msg = resp.json().get("error", {}).get("message", resp.text)
            except Exception:
                server_msg = resp.text
            # "limit: 0" ya quota ka zikr ho to retry ka faida nahi, seedha batao
            if "limit: 0" in server_msg or "billing" in server_msg.lower():
                raise RuntimeError(
                    "Is key ke free tier mein ye model available nahi hai (limit 0). "
                    f"Google ka message: {server_msg}"
                )
            if attempt == max_retries:
                raise RuntimeError(
                    f"Server busy hai ya limit khatam ({resp.status_code}). Google ka message: {server_msg}"
                )
            time.sleep(min(2 ** attempt + random.uniform(0, 1), 30))
            continue

        if resp.status_code >= 400:
            try:
                msg = resp.json().get("error", {}).get("message", resp.text)
            except Exception:
                msg = resp.text
            low = msg.lower()
            if "api key" in low or resp.status_code in (401, 403):
                raise RuntimeError(f"Gemini API key ka masla ya access nahi hai: {msg}")
            if "safety" in low or "blocked" in low or "prohibited" in low:
                raise SafetyBlocked(msg)
            raise RuntimeError(f"Request fail hui ({resp.status_code}): {msg}")

        data = resp.json()
        images, text = extract_output(data)
        if not images and not text:
            text = f"(Response mein image nahi mili. Response keys: {list(data.keys())})"
        return images, text

    raise RuntimeError("Request kamyab nahi hui.")


# ---------------- Image helpers ----------------
def verify_image(raw):
    """Poori image decode karke check karo ke toot-phoot to nahi."""
    try:
        img = Image.open(io.BytesIO(raw))
        fmt = img.format
        img.load()  # sirf header nahi, poori image pixel-by-pixel decode hoti hai
        return img, fmt
    except Exception:
        return None, None


def save_image(raw, index, fmt):
    ext = "jpg" if fmt == "JPEG" else (fmt or "png").lower()
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(SAVE_DIR, f"img_{stamp}_{index}.{ext}")
    with open(path, "wb") as f:
        f.write(raw)
    return path, ext


def load_api_key():
    """Key sirf server se aati hai: pehle .streamlit/secrets.toml, phir environment variable."""
    try:
        key = st.secrets["GEMINI_API_KEY"]
    except Exception:
        key = os.getenv("GEMINI_API_KEY", "")
    return key


# ---------------- UI ----------------
st.set_page_config(page_title="Image Generation Studio", page_icon="🎨", layout="wide")
api_key = load_api_key()
st.title("🎨 Multimodal Image Generation Studio")

with st.sidebar:
    st.header("Settings")
    model_label = st.selectbox("Model", list(MODELS.keys()))
    ratio_label = st.selectbox("Image shape", list(ASPECT_RATIOS.keys()))
    style_name = st.selectbox("Style preset", list(STYLES.keys()))
    count = st.slider("Kitni images?", 1, 4, 1)

prompt = st.text_area("Apna prompt likhein", placeholder="A cat sitting on the moon, looking at Earth")

if st.button("Generate ✨", type="primary"):
    if not api_key:
        st.error("Server par API key set nahi hai. Admin se rabta karein.")
    elif not prompt.strip():
        st.warning("Prompt khali hai, kuch likhein.")
    else:
        style_text = STYLES[style_name]
        final_prompt = f"{prompt.strip()}. {style_text}" if style_text else prompt.strip()
        model = MODELS[model_label]
        ratio = ASPECT_RATIOS[ratio_label]

        try:
            cols = st.columns(min(count, 2))
            shown = 0
            with st.spinner("Images ban rahi hain, thora intezar..."):
                for i in range(1, count + 1):
                    images_b64, note = generate_one(api_key, model, final_prompt, ratio)

                    if not images_b64:
                        # Model ne image nahi di, aksar safety refusal hota hai
                        st.warning(f"Image {i} nahi bani. Model ka jawab: {note}")
                        continue

                    for b64 in images_b64:
                        raw = base64.b64decode(b64)
                        img, fmt = verify_image(raw)
                        if img is None:
                            st.warning(f"Image {i} kharab thi, skip kar di. Dobara generate karein.")
                            continue
                        path, ext = save_image(raw, i, fmt)
                        with cols[shown % len(cols)]:
                            st.image(img, caption=f"Saved: {path}", use_container_width=True)
                            st.download_button(
                                f"Download image {i}", raw, file_name=os.path.basename(path),
                                mime=f"image/{'jpeg' if ext == 'jpg' else ext}", key=f"dl_{path}",
                            )
                        shown += 1

        except SafetyBlocked:
            st.warning("Ye prompt safety rules ki wajah se block ho gaya. Kuch aur likh kar try karein.")
        except RuntimeError as e:
            st.error(str(e))import base64
import datetime
import io
import os
import random
import time

import requests
import streamlit as st
from PIL import Image

# ---------------- Settings ----------------
API_URL = "https://generativelanguage.googleapis.com/v1beta/interactions"
SAVE_DIR = "generated_images"

# Label -> Gemini image model ID
MODELS = {
    "Nano Banana 2 Lite (sabse sasta/tez)": "gemini-3.1-flash-lite-image",
    "Nano Banana 2 (balanced)": "gemini-3.1-flash-image",
    "Nano Banana Pro (best quality)": "gemini-3-pro-image",
}

# Sirf wahi aspect ratios jo API support karti hai
ASPECT_RATIOS = {
    "Landscape 16:9 (banners, presentations)": "16:9",
    "Square 1:1 (avatars, product grids)": "1:1",
    "Vertical 9:16 (reels, wallpapers)": "9:16",
}

# Style presets: ye text prompt ke saath jur jata hai
STYLES = {
    "None": "",
    "Cyberpunk": "cyberpunk style, neon lights, rainy futuristic city mood",
    "Minimalism": "minimalist style, clean composition, lots of empty space, soft colors",
    "Watercolor": "soft watercolor painting, gentle brush strokes",
    "Photorealistic": "ultra realistic photo, natural lighting, sharp details",
    "Anime": "anime style, vibrant colors, clean line art",
}

os.makedirs(SAVE_DIR, exist_ok=True)


class SafetyBlocked(Exception):
    """Prompt ya image safety filter mein phans gayi."""


# ---------------- API call ----------------
def extract_output(data):
    """Response se base64 images aur model ka text nikalo."""
    images, texts = [], []
    for step in data.get("steps") or []:
        if step.get("type") == "model_output":
            for block in step.get("content") or []:
                if block.get("type") == "image" and block.get("data"):
                    images.append(block["data"])
                elif block.get("type") == "text" and block.get("text"):
                    texts.append(block["text"])
    return images, " ".join(texts)


def generate_one(api_key, model, prompt, aspect_ratio, max_retries=4):
    """Ek image ke liye ek request. (base64 images ki list, model ka text) wapas deta hai."""
    headers = {"x-goog-api-key": api_key, "Content-Type": "application/json"}
    payload = {
        "model": model,
        "input": prompt,
        "response_format": {"type": "image", "aspect_ratio": aspect_ratio},
    }

    for attempt in range(1, max_retries + 1):
        try:
            # (connect timeout, read timeout): program kabhi hamesha ke liye nahi atkega
            resp = requests.post(API_URL, headers=headers, json=payload, timeout=(3.05, 120))
        except requests.exceptions.ConnectTimeout:
            # Fail fast: connection hi nahi bana, intezar ka faida nahi
            raise RuntimeError("Server se connection nahi ban paya. Internet check karein.")
        except requests.exceptions.ReadTimeout:
            if attempt == max_retries:
                raise RuntimeError("Server ne bohat der laga di. Thori dair baad try karein.")
            time.sleep(min(2 ** attempt + random.uniform(0, 1), 30))  # backoff + jitter
            continue
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Network error: {e}")

        # Server busy ya rate limit: ruk kar dobara try karo
        if resp.status_code in (429, 500, 503):
            try:
                server_msg = resp.json().get("error", {}).get("message", resp.text)
            except Exception:
                server_msg = resp.text
            # "limit: 0" ya quota ka zikr ho to retry ka faida nahi, seedha batao
            if "limit: 0" in server_msg or "billing" in server_msg.lower():
                raise RuntimeError(
                    "Is key ke free tier mein ye model available nahi hai (limit 0). "
                    f"Google ka message: {server_msg}"
                )
            if attempt == max_retries:
                raise RuntimeError(
                    f"Server busy hai ya limit khatam ({resp.status_code}). Google ka message: {server_msg}"
                )
            time.sleep(min(2 ** attempt + random.uniform(0, 1), 30))
            continue

        if resp.status_code >= 400:
            try:
                msg = resp.json().get("error", {}).get("message", resp.text)
            except Exception:
                msg = resp.text
            low = msg.lower()
            if "api key" in low or resp.status_code in (401, 403):
                raise RuntimeError(f"Gemini API key ka masla ya access nahi hai: {msg}")
            if "safety" in low or "blocked" in low or "prohibited" in low:
                raise SafetyBlocked(msg)
            raise RuntimeError(f"Request fail hui ({resp.status_code}): {msg}")

        data = resp.json()
        images, text = extract_output(data)
        if not images and not text:
            text = f"(Response mein image nahi mili. Response keys: {list(data.keys())})"
        return images, text

    raise RuntimeError("Request kamyab nahi hui.")


# ---------------- Image helpers ----------------
def verify_image(raw):
    """Poori image decode karke check karo ke toot-phoot to nahi."""
    try:
        img = Image.open(io.BytesIO(raw))
        fmt = img.format
        img.load()  # sirf header nahi, poori image pixel-by-pixel decode hoti hai
        return img, fmt
    except Exception:
        return None, None


def save_image(raw, index, fmt):
    ext = "jpg" if fmt == "JPEG" else (fmt or "png").lower()
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(SAVE_DIR, f"img_{stamp}_{index}.{ext}")
    with open(path, "wb") as f:
        f.write(raw)
    return path, ext


def load_api_key():
    """Key sirf server se aati hai: pehle .streamlit/secrets.toml, phir environment variable."""
    try:
        key = st.secrets["GEMINI_API_KEY"]
    except Exception:
        key = os.getenv("GEMINI_API_KEY", "")
    return key


# ---------------- UI ----------------
st.set_page_config(page_title="Image Generation Studio", page_icon="🎨", layout="wide")
api_key = load_api_key()
st.title("🎨 Multimodal Image Generation Studio")

with st.sidebar:
    st.header("Settings")
    model_label = st.selectbox("Model", list(MODELS.keys()))
    ratio_label = st.selectbox("Image shape", list(ASPECT_RATIOS.keys()))
    style_name = st.selectbox("Style preset", list(STYLES.keys()))
    count = st.slider("Kitni images?", 1, 4, 1)

prompt = st.text_area("Apna prompt likhein", placeholder="A cat sitting on the moon, looking at Earth")

if st.button("Generate ✨", type="primary"):
    if not api_key:
        st.error("Server par API key set nahi hai. Admin se rabta karein.")
    elif not prompt.strip():
        st.warning("Prompt khali hai, kuch likhein.")
    else:
        style_text = STYLES[style_name]
        final_prompt = f"{prompt.strip()}. {style_text}" if style_text else prompt.strip()
        model = MODELS[model_label]
        ratio = ASPECT_RATIOS[ratio_label]

        try:
            cols = st.columns(min(count, 2))
            shown = 0
            with st.spinner("Images ban rahi hain, thora intezar..."):
                for i in range(1, count + 1):
                    images_b64, note = generate_one(api_key, model, final_prompt, ratio)

                    if not images_b64:
                        # Model ne image nahi di, aksar safety refusal hota hai
                        st.warning(f"Image {i} nahi bani. Model ka jawab: {note}")
                        continue

                    for b64 in images_b64:
                        raw = base64.b64decode(b64)
                        img, fmt = verify_image(raw)
                        if img is None:
                            st.warning(f"Image {i} kharab thi, skip kar di. Dobara generate karein.")
                            continue
                        path, ext = save_image(raw, i, fmt)
                        with cols[shown % len(cols)]:
                            st.image(img, caption=f"Saved: {path}", use_container_width=True)
                            st.download_button(
                                f"Download image {i}", raw, file_name=os.path.basename(path),
                                mime=f"image/{'jpeg' if ext == 'jpg' else ext}", key=f"dl_{path}",
                            )
                        shown += 1

        except SafetyBlocked:
            st.warning("Ye prompt safety rules ki wajah se block ho gaya. Kuch aur likh kar try karein.")
        except RuntimeError as e:
            st.error(str(e))