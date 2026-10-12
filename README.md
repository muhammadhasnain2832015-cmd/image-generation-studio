# 🎨 Multimodal Image Generation Studio

[![CI](https://github.com/muhammadhasnain2832015-cmd/image-generation-studio/actions/workflows/ci.yml/badge.svg)](https://github.com/muhammadhasnain2832015-cmd/image-generation-studio/actions/workflows/ci.yml)

A Streamlit web app that turns natural-language text descriptions into digital artwork using the Google Gemini image API. Built as **Project 3** of the DecodeLabs Generative AI Industrial Training Kit.

## Features

- **Text-to-image generation** with Gemini image models (Nano Banana 2 Lite, Nano Banana 2, Nano Banana Pro)
- **Aspect ratio control:** 16:9 landscape, 1:1 square, 9:16 vertical
- **Multiple images** per request (1 to 4)
- **Style presets:** Cyberpunk, Minimalism, Watercolor, Photorealistic, Anime
- **Automatic local saving** to the `generated_images/` folder, plus a download button for each image
- **Image integrity check:** every image is fully decoded with Pillow (`Image.open().load()`), so truncated or corrupted images are detected and skipped
- **Resilient networking:**
  - Split timeouts: `(3.05s connect, 120s read)`, so the app never hangs forever
  - Retries with exponential backoff and jitter on `429`, `500` and `503`
  - Fail-fast on connection timeouts
- **Safety handling:** content-filter rejections are caught and shown as friendly messages instead of crashing the app
- **API key stays on the server:** it is never entered in, or exposed to, the browser UI

## How it works

```
Prompt + style + aspect ratio
        │
        ▼
Build payload ──► Gemini API (timeouts, retries, safety handling)
                        │
                        ▼
          Base64 image ──► Decode ──► Verify with Pillow
                                          │
                                          ▼
                              Save locally + display + download
```

## Tech stack

- Python 3.11
- [Streamlit](https://streamlit.io/) for the UI
- [Requests](https://requests.readthedocs.io/) for API calls
- [Pillow](https://python-pillow.org/) for image verification
- GitHub Actions for CI

## Getting started

### 1. Clone the repository

```bash
git clone https://github.com/muhammadhasnain2832015-cmd/image-generation-studio.git
cd image-generation-studio
```

### 2. Create a virtual environment and install dependencies

```bash
python -m venv .venv

# Windows (PowerShell)
.venv\Scripts\Activate.ps1
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

### 3. Add your API key

Get a key from [Google AI Studio](https://aistudio.google.com/apikey), then create the file `.streamlit/secrets.toml`:

```toml
GEMINI_API_KEY = "your-key-here"
```

Alternatively, set it as an environment variable:

```bash
# Windows (PowerShell)
$env:GEMINI_API_KEY="your-key-here"
# macOS / Linux
export GEMINI_API_KEY="your-key-here"
```

> ⚠️ `.streamlit/secrets.toml` is listed in `.gitignore`. Never commit your API key.

### 4. Run the app

```bash
python -m streamlit run app.py
```

The app opens at `http://localhost:8501`.

## Project structure

```
.
├── app.py                      # Main Streamlit application
├── requirements.txt            # Python dependencies
├── .gitignore                  # Keeps secrets and generated files out of git
├── .github/workflows/ci.yml    # CI pipeline (syntax check + lint)
└── README.md
```

## CI pipeline

On every push and pull request to `main`, GitHub Actions:

1. Checks out the code
2. Sets up Python 3.11
3. Installs dependencies
4. Runs a syntax check (`py_compile`)
5. Lints with Ruff (syntax errors, undefined and unused names)

## Notes and limitations

- Image generation through the Gemini API may require a billing-enabled Google account. If your key's free tier does not include image models, the app will show Google's quota message.
- Available model IDs can change over time. If a model is not found, update the `MODELS` dictionary in `app.py`.

## Roadmap

- [ ] Automated quality scoring (CLIP aesthetic score) with auto-regeneration of low-scoring images
- [ ] Semantic alignment check between prompt and image
- [ ] Negative prompts and more style presets
- [ ] Deployment to Streamlit Community Cloud

## Acknowledgements

Built during the DecodeLabs Generative AI industrial training program (Batch 2026).
