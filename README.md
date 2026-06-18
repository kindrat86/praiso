# Praiso

**Collect and display testimonials that convert.**

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/kindrat86/praiso)

Praiso lets you collect testimonials from customers via a shareable link, moderate them in a dashboard, and display them on your website with one line of embed code.

## Features

- 🔗 Shareable collection pages (no signup required for customers)
- ⭐ Star ratings (1-5)
- ✅ Moderation (approve/reject/feature)
- 📋 One-line embeddable widget (carousel, grid, wall of love)
- 🎨 Light and dark themes
- 💳 Stripe billing (Pro $29/mo, Business $79/mo)
- 📱 Fully responsive

## Quick Start (Local)

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your Stripe keys
python app.py
# Open http://localhost:5111
```

## Deploy to Render (Free)

1. Fork this repo
2. Go to [render.com/new](https://render.com/new)
3. Connect your GitHub repo
4. Render will auto-detect `render.yaml` and set up web service + Postgres
5. Add Stripe env vars in Render dashboard
6. Done — your app is live

## Stripe Setup

1. Create a [Stripe account](https://dashboard.stripe.com/register)
2. Create two Products:
   - **Pro** — $29/month, recurring
   - **Business** — $79/month, recurring
3. Copy the Price IDs into your env vars
4. Set up a webhook endpoint: `https://your-domain.com/webhook/stripe`
   - Events: `checkout.session.completed`, `customer.subscription.updated`, `customer.subscription.deleted`
5. Copy the webhook signing secret into `STRIPE_WEBHOOK_SECRET`

## Pricing

| Plan | Price | Testimonials | Projects |
|------|-------|-------------|----------|
| Free | $0 | 10 | 1 |
| Pro | $29/mo | 500 | 10 |
| Business | $79/mo | Unlimited | Unlimited |

## Tech Stack

- Python/Flask
- SQLAlchemy (SQLite dev, Postgres prod)
- Stripe Checkout + Customer Portal
- Tailwind CSS (CDN)
- Vanilla JS embeddable widget

## License

MIT
