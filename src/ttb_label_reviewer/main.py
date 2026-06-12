from fastapi import FastAPI
from fastapi.responses import HTMLResponse

app = FastAPI(title="TTB Label Reviewer")


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>TTB Label Reviewer</title>
  <style>
    body { font-family: system-ui, sans-serif; max-width: 40rem;
           margin: 4rem auto; padding: 0 1rem; color: #1a1a1a; }
    h1 { font-size: 1.5rem; }
  </style>
</head>
<body>
  <h1>TTB Label Reviewer</h1>
  <p>AI-powered alcohol label verification &mdash; the AI extracts,
     the code decides.</p>
  <p>Prototype skeleton (milestone 1). Single and batch review coming
     in later milestones.</p>
</body>
</html>
"""
