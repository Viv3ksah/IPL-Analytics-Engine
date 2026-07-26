"""Shared Streamlit visual theme for the IPL Analytics Engine."""

CUSTOM_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Bebas+Neue&family=Source+Sans+3:wght@400;600;700&display=swap');

:root {
  --ink: #10241c;
  --pitch: #0f3d2e;
  --turf: #1f7a4d;
  --lime: #c6f135;
  --sand: #f3efe3;
  --clay: #d9782d;
  --mist: rgba(16, 36, 28, 0.06);
}

html, body, [class*="css"] {
  font-family: 'Source Sans 3', sans-serif;
  color: var(--ink);
}

.stApp {
  background:
    radial-gradient(1200px 600px at 10% -10%, rgba(198, 241, 53, 0.22), transparent 55%),
    radial-gradient(900px 500px at 100% 0%, rgba(217, 120, 45, 0.18), transparent 50%),
    linear-gradient(180deg, #f7f4ec 0%, #e8f0e6 45%, #f3efe3 100%);
}

.block-container { padding-top: 1.4rem; max-width: 1200px; }

h1, h2, h3, .brand-title {
  font-family: 'Bebas Neue', sans-serif;
  letter-spacing: 0.03em;
  color: var(--pitch);
}

.hero {
  background:
    linear-gradient(120deg, rgba(15, 61, 46, 0.92), rgba(31, 122, 77, 0.78)),
    url('data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="160" height="160" viewBox="0 0 160 160"><circle cx="80" cy="80" r="70" fill="none" stroke="%23c6f135" stroke-width="2" stroke-dasharray="4 10" opacity="0.35"/></svg>');
  background-size: cover;
  color: #f7f4ec;
  padding: 2.2rem 2rem;
  border-radius: 0;
  margin-bottom: 1.2rem;
  animation: rise 700ms ease-out;
}

.hero h1 {
  color: var(--lime);
  font-size: clamp(2.6rem, 6vw, 4.2rem);
  margin: 0;
  line-height: 0.95;
}

.hero p {
  max-width: 38rem;
  font-size: 1.05rem;
  opacity: 0.92;
  margin: 0.85rem 0 0;
}

.metric-strip {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 0.75rem;
  margin: 0.5rem 0 1.25rem;
}

.metric-chip {
  background: rgba(255,255,255,0.65);
  border-left: 4px solid var(--turf);
  padding: 0.85rem 1rem;
  animation: fade 800ms ease-out;
}

.metric-chip span {
  display: block;
  font-size: 0.78rem;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  opacity: 0.7;
}

.metric-chip strong {
  font-family: 'Bebas Neue', sans-serif;
  font-size: 1.8rem;
  color: var(--pitch);
}

div[data-testid="stSidebar"] {
  background: linear-gradient(180deg, #10241c 0%, #0f3d2e 100%);
}

div[data-testid="stSidebar"] * { color: #eef6e8 !important; }

@keyframes rise {
  from { opacity: 0; transform: translateY(12px); }
  to { opacity: 1; transform: translateY(0); }
}

@keyframes fade {
  from { opacity: 0; }
  to { opacity: 1; }
}

@media (max-width: 768px) {
  .metric-strip { grid-template-columns: repeat(2, 1fr); }
}
"""


def inject(st) -> None:
    st.markdown(f"<style>{CUSTOM_CSS}</style>", unsafe_allow_html=True)
