import os
import json
import uuid
import secrets
from datetime import datetime, timedelta
from functools import wraps

from flask import (
    Flask, render_template, request, redirect, url_for, flash,
    jsonify, abort, make_response, session
)
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
import bcrypt
import stripe
from dotenv import load_dotenv

load_dotenv()

# Stripe config
stripe.api_key = os.getenv('STRIPE_SECRET_KEY', '')
STRIPE_PUBLISHABLE_KEY = os.getenv('STRIPE_PUBLISHABLE_KEY', '')
STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET', '')
STRIPE_PRO_PRICE_ID = os.getenv('STRIPE_PRO_PRICE_ID', '')
STRIPE_BIZ_PRICE_ID = os.getenv('STRIPE_BIZ_PRICE_ID', '')

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', secrets.token_hex(32))

# Database URI — support Render-style postgres:// and sqlite fallback
db_uri = os.getenv('DATABASE_URL', 'sqlite:///praiso.db')
if db_uri.startswith('postgres://'):
    db_uri = db_uri.replace('postgres://', 'postgresql://', 1)
app.config['SQLALCHEMY_DATABASE_URI'] = db_uri
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# ========== MODELS ==========

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    company_name = db.Column(db.String(255), default='')
    api_key = db.Column(db.String(64), unique=True, default=lambda: secrets.token_hex(24))
    plan = db.Column(db.String(20), default='free')  # free, pro, business
    stripe_customer_id = db.Column(db.String(255))
    stripe_subscription_id = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    projects = db.relationship('Project', backref='owner', lazy=True)

    def set_password(self, password):
        self.password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    def check_password(self, password):
        return bcrypt.checkpw(password.encode(), self.password_hash.encode())

    @property
    def testimonial_limit(self):
        if self.plan == 'free':
            return 10
        elif self.plan == 'pro':
            return 500
        else:
            return 99999

    @property
    def project_limit(self):
        if self.plan == 'free':
            return 1
        elif self.plan == 'pro':
            return 10
        else:
            return 99999


class Project(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    uid = db.Column(db.String(36), unique=True, default=lambda: str(uuid.uuid4()))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    name = db.Column(db.String(255), nullable=False)
    website_url = db.Column(db.String(500), default='')
    collect_page_title = db.Column(db.String(255), default='What do you think?')
    collect_page_desc = db.Column(db.Text, default='We would love to hear your feedback!')
    thank_you_message = db.Column(db.Text, default='Thank you for your testimonial!')
    widget_style = db.Column(db.String(20), default='carousel')  # carousel, grid, wall, badge
    widget_theme = db.Column(db.String(20), default='light')  # light, dark, auto
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    testimonials = db.relationship('Testimonial', backref='project', lazy=True)


class Testimonial(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    uid = db.Column(db.String(36), unique=True, default=lambda: str(uuid.uuid4()))
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False)
    author_name = db.Column(db.String(255), nullable=False)
    author_email = db.Column(db.String(255), default='')
    author_title = db.Column(db.String(255), default='')
    author_company = db.Column(db.String(255), default='')
    author_avatar_url = db.Column(db.String(500), default='')
    content = db.Column(db.Text, nullable=False)
    rating = db.Column(db.Integer, default=5)  # 1-5
    source = db.Column(db.String(50), default='form')  # form, import, manual
    status = db.Column(db.String(20), default='pending')  # pending, approved, rejected
    featured = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# ========== AUTH ==========

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        if not email or not password:
            flash('Email and password required.', 'error')
            return render_template('signup.html')
        if len(password) < 8:
            flash('Password must be at least 8 characters.', 'error')
            return render_template('signup.html')
        if User.query.filter_by(email=email).first():
            flash('Email already registered.', 'error')
            return render_template('signup.html')
        user = User(email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        login_user(user)
        # Create default project
        project = Project(user_id=user.id, name='My First Project')
        db.session.add(project)
        db.session.commit()
        return redirect(url_for('dashboard'))
    return render_template('signup.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            login_user(user, remember=True)
            return redirect(url_for('dashboard'))
        flash('Invalid email or password.', 'error')
    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('landing'))


# ========== LANDING PAGE ==========

@app.route('/')
def landing():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return render_template('landing.html')


# ========== DASHBOARD ==========

@app.route('/dashboard')
@login_required
def dashboard():
    projects = Project.query.filter_by(user_id=current_user.id).all()
    total_testimonials = sum(len(p.testimonials) for p in projects)
    approved = Testimonial.query.join(Project).filter(
        Project.user_id == current_user.id,
        Testimonial.status == 'approved'
    ).count()
    pending = Testimonial.query.join(Project).filter(
        Project.user_id == current_user.id,
        Testimonial.status == 'pending'
    ).count()
    return render_template('dashboard.html',
        projects=projects,
        total=total_testimonials,
        approved=approved,
        pending=pending
    )


@app.route('/project/<uid>')
@login_required
def project_detail(uid):
    project = Project.query.filter_by(uid=uid).first_or_404()
    if project.user_id != current_user.id:
        abort(403)
    testimonials = Testimonial.query.filter_by(project_id=project.id).order_by(Testimonial.created_at.desc()).all()
    base_url = request.host_url.rstrip('/')
    return render_template('project.html', project=project, testimonials=testimonials, base_url=base_url)


@app.route('/project/new', methods=['POST'])
@login_required
def project_new():
    count = Project.query.filter_by(user_id=current_user.id).count()
    if count >= current_user.project_limit:
        flash(f'Project limit reached ({current_user.project_limit}). Upgrade to add more.', 'error')
        return redirect(url_for('dashboard'))
    name = request.form.get('name', 'New Project').strip()
    project = Project(user_id=current_user.id, name=name)
    db.session.add(project)
    db.session.commit()
    return redirect(url_for('project_detail', uid=project.uid))


@app.route('/project/<uid>/settings', methods=['POST'])
@login_required
def project_settings(uid):
    project = Project.query.filter_by(uid=uid).first_or_404()
    if project.user_id != current_user.id:
        abort(403)
    project.name = request.form.get('name', project.name).strip()
    project.website_url = request.form.get('website_url', '').strip()
    project.collect_page_title = request.form.get('collect_page_title', project.collect_page_title).strip()
    project.collect_page_desc = request.form.get('collect_page_desc', project.collect_page_desc).strip()
    project.thank_you_message = request.form.get('thank_you_message', project.thank_you_message).strip()
    project.widget_style = request.form.get('widget_style', project.widget_style)
    project.widget_theme = request.form.get('widget_theme', project.widget_theme)
    db.session.commit()
    flash('Settings saved.', 'success')
    return redirect(url_for('project_detail', uid=uid))


# ========== TESTIMONIAL MANAGEMENT ==========

@app.route('/testimonial/<uid>/approve', methods=['POST'])
@login_required
def testimonial_approve(uid):
    t = Testimonial.query.filter_by(uid=uid).first_or_404()
    project = Project.query.get(t.project_id)
    if project.user_id != current_user.id:
        abort(403)
    t.status = 'approved'
    db.session.commit()
    return redirect(url_for('project_detail', uid=project.uid))


@app.route('/testimonial/<uid>/reject', methods=['POST'])
@login_required
def testimonial_reject(uid):
    t = Testimonial.query.filter_by(uid=uid).first_or_404()
    project = Project.query.get(t.project_id)
    if project.user_id != current_user.id:
        abort(403)
    t.status = 'rejected'
    db.session.commit()
    return redirect(url_for('project_detail', uid=project.uid))


@app.route('/testimonial/<uid>/feature', methods=['POST'])
@login_required
def testimonial_feature(uid):
    t = Testimonial.query.filter_by(uid=uid).first_or_404()
    project = Project.query.get(t.project_id)
    if project.user_id != current_user.id:
        abort(403)
    t.featured = not t.featured
    db.session.commit()
    return redirect(url_for('project_detail', uid=project.uid))


@app.route('/testimonial/<uid>/delete', methods=['POST'])
@login_required
def testimonial_delete(uid):
    t = Testimonial.query.filter_by(uid=uid).first_or_404()
    project = Project.query.get(t.project_id)
    if project.user_id != current_user.id:
        abort(403)
    db.session.delete(t)
    db.session.commit()
    flash('Testimonial deleted.', 'success')
    return redirect(url_for('project_detail', uid=project.uid))


@app.route('/testimonial/add/<project_uid>', methods=['POST'])
@login_required
def testimonial_add_manual(project_uid):
    project = Project.query.filter_by(uid=project_uid).first_or_404()
    if project.user_id != current_user.id:
        abort(403)
    t = Testimonial(
        project_id=project.id,
        author_name=request.form.get('author_name', '').strip(),
        author_title=request.form.get('author_title', '').strip(),
        author_company=request.form.get('author_company', '').strip(),
        content=request.form.get('content', '').strip(),
        rating=int(request.form.get('rating', 5)),
        source='manual',
        status='approved'
    )
    db.session.add(t)
    db.session.commit()
    flash('Testimonial added.', 'success')
    return redirect(url_for('project_detail', uid=project_uid))


# ========== PUBLIC COLLECTION PAGE ==========

@app.route('/collect/<project_uid>', methods=['GET', 'POST'])
def collect(project_uid):
    project = Project.query.filter_by(uid=project_uid).first_or_404()
    if request.method == 'POST':
        # Check limits
        user = User.query.get(project.user_id)
        count = Testimonial.query.join(Project).filter(Project.user_id == user.id).count()
        if count >= user.testimonial_limit:
            return render_template('collect_limit.html', project=project)
        t = Testimonial(
            project_id=project.id,
            author_name=request.form.get('name', '').strip(),
            author_email=request.form.get('email', '').strip(),
            author_title=request.form.get('title', '').strip(),
            author_company=request.form.get('company', '').strip(),
            content=request.form.get('content', '').strip(),
            rating=int(request.form.get('rating', 5)),
            source='form'
        )
        db.session.add(t)
        db.session.commit()
        return render_template('collect_thanks.html', project=project)
    return render_template('collect.html', project=project)


# ========== EMBEDDABLE WIDGET API ==========

@app.route('/api/widget/<project_uid>')
def widget_data(project_uid):
    project = Project.query.filter_by(uid=project_uid).first_or_404()
    testimonials = Testimonial.query.filter_by(
        project_id=project.id,
        status='approved'
    ).order_by(Testimonial.featured.desc(), Testimonial.created_at.desc()).all()

    data = {
        'project': {
            'name': project.name,
            'style': project.widget_style,
            'theme': project.widget_theme
        },
        'testimonials': [{
            'author_name': t.author_name,
            'author_title': t.author_title,
            'author_company': t.author_company,
            'content': t.content,
            'rating': t.rating,
            'featured': t.featured,
            'created_at': t.created_at.isoformat()
        } for t in testimonials]
    }
    response = make_response(jsonify(data))
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Cache-Control'] = 'public, max-age=300'
    return response


@app.route('/embed/<project_uid>.js')
def widget_js(project_uid):
    base_url = request.host_url.rstrip('/')
    js = render_template('widget.js', project_uid=project_uid, base_url=base_url)
    response = make_response(js)
    response.headers['Content-Type'] = 'application/javascript'
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Cache-Control'] = 'public, max-age=300'
    return response


# ========== SEO & pSEO ENGINE ==========

PSEO_VERTICALS = [
    {"slug": "saas", "title": "SaaS Companies", "desc": "Boost trial-to-paid conversion with customer testimonials on your SaaS landing page.", "keyword": "testimonial widget for SaaS"},
    {"slug": "agencies", "title": "Marketing Agencies", "desc": "Win more clients by showcasing results. Display testimonials from happy clients.", "keyword": "testimonial widget for agencies"},
    {"slug": "freelancers", "title": "Freelancers", "desc": "Build trust and win proposals with social proof from past clients on your portfolio.", "keyword": "testimonial widget for freelancers"},
    {"slug": "ecommerce", "title": "E-commerce Stores", "desc": "Increase product trust and reduce returns with verified customer reviews.", "keyword": "testimonial widget for ecommerce"},
    {"slug": "coaches", "title": "Coaches & Consultants", "desc": "Show transformation stories from past clients to fill your coaching calendar.", "keyword": "testimonial widget for coaches"},
    {"slug": "real-estate", "title": "Real Estate Agents", "desc": "Let happy homebuyers sell your next listing. Testimonials that close deals.", "keyword": "testimonial widget for real estate"},
    {"slug": "restaurants", "title": "Restaurants", "desc": "Turn rave reviews into more reservations with an embeddable testimonial wall.", "keyword": "testimonial widget for restaurants"},
    {"slug": "dentists", "title": "Dentists & Clinics", "desc": "Patient testimonials that build trust before the first appointment.", "keyword": "testimonial widget for dentists"},
    {"slug": "fitness", "title": "Fitness & Gyms", "desc": "Before-and-after stories from real members. The best marketing a gym can have.", "keyword": "testimonial widget for fitness"},
    {"slug": "lawyers", "title": "Law Firms", "desc": "Client testimonials that establish credibility for your legal practice.", "keyword": "testimonial widget for lawyers"},
    {"slug": "photographers", "title": "Photographers", "desc": "Couples and clients sharing their experience. Social proof that books shoots.", "keyword": "testimonial widget for photographers"},
    {"slug": "startups", "title": "Startups", "desc": "Early customer love that convinces investors and new users alike.", "keyword": "testimonial widget for startups"},
    {"slug": "wordpress", "title": "WordPress Sites", "desc": "One line of code. Beautiful testimonial widget on any WordPress site.", "keyword": "testimonial widget for WordPress"},
    {"slug": "shopify", "title": "Shopify Stores", "desc": "Add customer reviews and testimonials to your Shopify store in seconds.", "keyword": "testimonial widget for Shopify"},
    {"slug": "webflow", "title": "Webflow Sites", "desc": "Embed a testimonial carousel or wall of love in Webflow with one script tag.", "keyword": "testimonial widget for Webflow"},
    {"slug": "nonprofits", "title": "Nonprofits", "desc": "Donor and volunteer stories that inspire more giving.", "keyword": "testimonial widget for nonprofits"},
    {"slug": "b2b", "title": "B2B Companies", "desc": "Enterprise testimonials and case study snippets that shorten sales cycles.", "keyword": "B2B testimonial widget"},
    {"slug": "course-creators", "title": "Course Creators", "desc": "Student success stories that sell your next cohort.", "keyword": "testimonial widget for online courses"},
    {"slug": "therapists", "title": "Therapists", "desc": "Trusted client reviews that help new patients choose you with confidence.", "keyword": "testimonial widget for therapists"},
    {"slug": "weddings", "title": "Wedding Vendors", "desc": "Happy couple testimonials that book your next season.", "keyword": "testimonial widget for wedding vendors"},
]

BLOG_POSTS = [
    {"slug": "why-testimonials-increase-conversions", "title": "Why Testimonials Increase Conversions by 34%", "keyword": "testimonials increase conversions", "meta_desc": "Research shows testimonials boost conversion rates by 34%. Learn why social proof works and how to collect testimonials that convert."},
    {"slug": "how-to-collect-testimonials", "title": "How to Collect Testimonials From Customers (2026 Guide)", "keyword": "how to collect testimonials", "meta_desc": "Step-by-step guide to collecting customer testimonials. Templates, timing, and tools that work."},
    {"slug": "best-testimonial-widgets", "title": "7 Best Testimonial Widgets for Your Website (2026)", "keyword": "best testimonial widget", "meta_desc": "Compare the top testimonial widgets. Features, pricing, and which one is best for your site."},
    {"slug": "testimonial-examples", "title": "50 Powerful Testimonial Examples That Convert", "keyword": "testimonial examples", "meta_desc": "Real testimonial examples from SaaS, e-commerce, agencies, and freelancers. Copy-paste templates included."},
    {"slug": "social-proof-guide", "title": "The Complete Guide to Social Proof in 2026", "keyword": "social proof guide", "meta_desc": "Everything about social proof: types, psychology, and how to add it to your website."},
    {"slug": "testimonial-request-email-templates", "title": "12 Testimonial Request Email Templates", "keyword": "testimonial request email", "meta_desc": "Copy-paste email templates to request testimonials from happy customers. Includes follow-up sequences."},
]

GEO_FAQS = [
    {"q": "What is a testimonial widget?", "a": "A testimonial widget is an embeddable component that displays customer reviews and testimonials on your website. It typically shows the customer's name, photo, rating, and review text in a visually appealing format like a carousel, grid, or wall of love. Tools like Praiso let you collect testimonials via a shareable link, moderate them, and embed them on any website with one line of code."},
    {"q": "How do I add testimonials to my website?", "a": "The easiest way is to use a testimonial collection tool like Praiso. Step 1: Create a free account and get a shareable collection link. Step 2: Send the link to your customers. Step 3: Approve the best testimonials in your dashboard. Step 4: Copy one line of embed code and paste it into your website HTML. The widget loads automatically and displays your approved testimonials."},
    {"q": "What is the best testimonial widget for websites?", "a": "The best testimonial widgets in 2026 are Praiso, Senja, Testimonial.to, and Famewall. Praiso stands out for its simplicity: free tier with 10 testimonials, one-line embed code, star ratings, and carousel/grid/wall layouts. It works with any website including WordPress, Shopify, Webflow, and custom sites."},
    {"q": "How many testimonials do I need on my website?", "a": "Research suggests 3-5 testimonials on your landing page is optimal. More than 10 can feel overwhelming. Quality matters more than quantity: one specific, detailed testimonial with metrics outperforms five generic ones. For product pages, 3 relevant testimonials near the CTA button typically increases conversion by 15-34%."},
    {"q": "Do testimonials increase sales?", "a": "Yes. Studies show testimonials increase conversion rates by 34% on average. 92% of consumers read testimonials before making a purchase. Testimonials featuring specific results (numbers, timeframes, outcomes) perform 2-3x better than generic praise."},
    {"q": "How do I ask customers for a testimonial?", "a": "The best time to ask is right after a positive interaction: a successful project delivery, a 5-star support ticket, or when they share praise spontaneously. Use a specific prompt like 'What specific result did you get from working with us?' and provide a simple link (like a Praiso collection page) where they can submit in 30 seconds."},
]


@app.route('/robots.txt')
def robots():
    base_url = request.host_url.rstrip('/')
    txt = f"""User-agent: *
Allow: /

Sitemap: {base_url}/sitemap.xml
"""
    return make_response(txt), 200, {'Content-Type': 'text/plain'}


@app.route('/sitemap.xml')
def sitemap():
    base_url = request.host_url.rstrip('/')
    pages = [
        ('/', '1.0', 'weekly'),
        ('/pricing', '0.8', 'monthly'),
        ('/faq', '0.8', 'monthly'),
    ]
    for v in PSEO_VERTICALS:
        pages.append((f'/for/{v["slug"]}', '0.7', 'monthly'))
    for p in BLOG_POSTS:
        pages.append((f'/blog/{p["slug"]}', '0.7', 'weekly'))

    xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
    xml += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    for path, priority, freq in pages:
        xml += f'  <url><loc>{base_url}{path}</loc><priority>{priority}</priority><changefreq>{freq}</changefreq></url>\n'
    xml += '</urlset>'
    return make_response(xml), 200, {'Content-Type': 'application/xml'}


@app.route('/for/<slug>')
def pseo_page(slug):
    vertical = next((v for v in PSEO_VERTICALS if v['slug'] == slug), None)
    if not vertical:
        abort(404)
    return render_template('pseo_page.html', v=vertical, faqs=GEO_FAQS[:3])


@app.route('/use-cases')
def use_cases():
    return render_template('use_cases.html', verticals=PSEO_VERTICALS)


@app.route('/blog/<slug>')
def blog_post(slug):
    post = next((p for p in BLOG_POSTS if p['slug'] == slug), None)
    if not post:
        abort(404)
    return render_template('blog_post.html', post=post)


@app.route('/blog')
def blog_index():
    return render_template('blog_index.html', posts=BLOG_POSTS)


@app.route('/faq')
def faq_page():
    return render_template('faq_page.html', faqs=GEO_FAQS)


# ========== BILLING ==========

@app.route('/pricing')
def pricing():
    return render_template('pricing.html')


@app.route('/billing')
@login_required
def billing():
    return render_template('billing.html')


@app.route('/checkout/<plan>')
@login_required
def checkout(plan):
    """Create a Stripe Checkout Session for Pro or Business plan."""
    if not stripe.api_key:
        flash('Stripe is not configured yet. Contact support.', 'error')
        return redirect(url_for('billing'))

    price_id = STRIPE_PRO_PRICE_ID if plan == 'pro' else STRIPE_BIZ_PRICE_ID
    if not price_id:
        flash(f'Price ID for {plan} plan is not configured.', 'error')
        return redirect(url_for('billing'))

    try:
        # Create or reuse Stripe customer
        if not current_user.stripe_customer_id:
            customer = stripe.Customer.create(email=current_user.email)
            current_user.stripe_customer_id = customer.id
            db.session.commit()

        base_url = request.host_url.rstrip('/')
        checkout_session = stripe.checkout.Session.create(
            customer=current_user.stripe_customer_id,
            payment_method_types=['card'],
            line_items=[{'price': price_id, 'quantity': 1}],
            mode='subscription',
            success_url=base_url + '/billing?success=1',
            cancel_url=base_url + '/billing?canceled=1',
            metadata={'user_id': str(current_user.id), 'plan': plan}
        )
        return redirect(checkout_session.url, code=303)
    except Exception as e:
        flash(f'Checkout error: {str(e)}', 'error')
        return redirect(url_for('billing'))


@app.route('/billing/portal')
@login_required
def billing_portal():
    """Redirect to Stripe Customer Portal to manage subscription."""
    if not stripe.api_key or not current_user.stripe_customer_id:
        flash('No active subscription found.', 'error')
        return redirect(url_for('billing'))
    try:
        base_url = request.host_url.rstrip('/')
        portal_session = stripe.billing_portal.Session.create(
            customer=current_user.stripe_customer_id,
            return_url=base_url + '/billing'
        )
        return redirect(portal_session.url, code=303)
    except Exception as e:
        flash(f'Portal error: {str(e)}', 'error')
        return redirect(url_for('billing'))


@app.route('/webhook/stripe', methods=['POST'])
def stripe_webhook():
    """Handle Stripe webhook events for subscription lifecycle."""
    payload = request.get_data()
    sig_header = request.headers.get('Stripe-Signature', '')

    if STRIPE_WEBHOOK_SECRET:
        try:
            event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
        except (ValueError, stripe.error.SignatureVerificationError):
            abort(400)
    else:
        try:
            event = json.loads(payload)
        except json.JSONDecodeError:
            abort(400)

    event_type = event.get('type', '')
    data = event.get('data', {}).get('object', {})

    if event_type == 'checkout.session.completed':
        customer_id = data.get('customer')
        subscription_id = data.get('subscription')
        plan = data.get('metadata', {}).get('plan', 'pro')
        user = User.query.filter_by(stripe_customer_id=customer_id).first()
        if user:
            user.plan = plan
            user.stripe_subscription_id = subscription_id
            db.session.commit()

    elif event_type in ('customer.subscription.updated', 'customer.subscription.deleted'):
        customer_id = data.get('customer')
        status = data.get('status')
        user = User.query.filter_by(stripe_customer_id=customer_id).first()
        if user:
            if status in ('canceled', 'unpaid', 'past_due', 'incomplete_expired'):
                user.plan = 'free'
                user.stripe_subscription_id = None
            elif status == 'active':
                # Determine plan from price
                items = data.get('items', {}).get('data', [])
                if items:
                    price_id = items[0].get('price', {}).get('id', '')
                    if price_id == STRIPE_BIZ_PRICE_ID:
                        user.plan = 'business'
                    else:
                        user.plan = 'pro'
            db.session.commit()

    return jsonify({'status': 'ok'}), 200


# ========== INIT ==========

with app.app_context():
    db.create_all()
    # Seed pSEO verticals if not exist
    if not os.path.exists(os.path.join(app.root_path, 'templates', 'pages')):
        os.makedirs(os.path.join(app.root_path, 'templates', 'pages'), exist_ok=True)
    if not os.path.exists(os.path.join(app.root_path, 'templates', 'blog')):
        os.makedirs(os.path.join(app.root_path, 'templates', 'blog'), exist_ok=True)


if __name__ == '__main__':
    app.run(debug=True, port=5111)
