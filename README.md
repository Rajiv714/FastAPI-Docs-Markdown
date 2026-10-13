# FastAPI OpenAPI to Markdown Converter

[![Live app](https://img.shields.io/badge/live%20app-streamlit-FF4B4B.svg)](https://fastapi-docs-markdown.streamlit.app/)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-yellow.svg)](LICENSE)

**Convert a FastAPI `/docs` URL or an `openapi.json` file into clean Markdown API documentation.**

Paste your FastAPI docs link or upload your OpenAPI 3.x spec and get a structured `API_DOCUMENTATION.md` you can commit, share or paste into a wiki.

### 🚀 Try it: [fastapi-docs-markdown.streamlit.app](https://fastapi-docs-markdown.streamlit.app/)

## Features

- Load a spec from a FastAPI `/docs` URL (auto-converted to `/openapi.json`) or an uploaded `openapi.json`
- Endpoints grouped by tag, with parameters, request bodies and responses
- Auto-generated example JSON, plus schema tables with types, enums, constraints and defaults
- Authentication schemes (HTTP, API key, OAuth2, OpenID Connect), webhooks and deprecation notices
- Live preview and one-click Markdown download
- Python library and command-line tool

## Use the web app

1. Open the [live app](https://fastapi-docs-markdown.streamlit.app/).
2. Enter your `/docs` URL, or upload `openapi.json`.
3. Download the generated Markdown.

> The live app can only reach publicly accessible URLs. For `localhost` or private-network APIs, save `/openapi.json` from your browser and use **Upload JSON**, or run the app locally.

## Install

```bash
pip install fastapi-openapi-to-markdown
```

**Command line**

```bash
openapi-to-markdown http://localhost:8000/docs -o API_DOCUMENTATION.md
openapi-to-markdown openapi.json -o API_DOCUMENTATION.md
```

**Python**

```python
import json
from openapi_to_markdown import openapi_to_markdown, fetch_openapi

# from a file
spec = json.load(open("openapi.json"))

# or from a running FastAPI app
spec, _ = fetch_openapi("http://localhost:8000/docs")

print(openapi_to_markdown(spec))
```

## Run the app locally

```bash
git clone https://github.com/YOUR_USERNAME/fastapi-openapi-to-markdown.git
cd fastapi-openapi-to-markdown
pip install -e ".[app]"
streamlit run app.py
```

## FAQ

**How do I convert FastAPI docs to Markdown?**
Paste your `/docs` URL into the app (or upload `openapi.json`) and download the `.md` file.

**How do I export FastAPI's `openapi.json`?**
Open `/openapi.json` on your running server and save it, or call `app.openapi()` in Python.

**Does it support Swagger 2.0?**
No. It supports OpenAPI 3.0 and 3.1, which is what FastAPI generates.

**Is my API spec stored?**
No. It is processed in memory for your session only.

## License

[MIT](LICENSE)
