# Deploy IPL Analytics Engine

Best option for this Streamlit app: **Streamlit Community Cloud** (free).

> Netlify is not a fit here — this is a Python/Streamlit server app, not a static site.

---

## 1) Streamlit Community Cloud (recommended)

### Prerequisites
- GitHub repo with this project (already on `cursor/ipl-analytics-engine-3a6e`)
- Free account at [share.streamlit.io](https://share.streamlit.io)

### Steps
1. Push / merge your branch to GitHub (already done if you pulled latest).
2. Open [https://share.streamlit.io](https://share.streamlit.io) → **Sign in with GitHub**.
3. Click **Create app**.
4. Fill in:
   - **Repository:** `Viv3ksah/Projects`
   - **Branch:** `cursor/ipl-analytics-engine-3a6e`  
     (or `main` after you merge the PR)
   - **Main file path:** `app/streamlit_app.py`
5. Click **Deploy**.

First boot may take a few minutes — the app **auto-builds** the SQLite warehouse and ML models if they are missing.

### After deploy
- You’ll get a public URL like `https://share.streamlit.io/user/app`
- Share that link on your resume / LinkedIn

### If deploy fails
- Confirm `requirements.txt` is at repo root
- Confirm main file is exactly `app/streamlit_app.py`
- Open **Manage app → Logs** and check for missing-module errors
- Reboot the app after fixing

---

## 2) Local “production-like” run

```powershell
cd "C:\Users\sahvi\OneDrive\chapter 1\Desktop\IPL Engine\Projects"
python -m pip install -r requirements.txt
python scripts/bootstrap_deploy.py
streamlit run app/streamlit_app.py
```

---

## 3) Render / Railway (optional alternative)

1. Create a new Web Service from the GitHub repo.
2. Start command:

```bash
streamlit run app/streamlit_app.py --server.port=$PORT --server.address=0.0.0.0
```

3. Build command:

```bash
pip install -r requirements.txt && python scripts/bootstrap_deploy.py
```

---

## Notes
- DB + models are gitignored; cloud bootstrap creates them on first run.
- For a lighter first deploy, bootstrap uses ~55 matches/season (still 200K+ balls).
- Merge PR #1 into `main` if you want Streamlit Cloud to track `main`.
