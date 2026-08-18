# app.py
import os
import re
import html
import unicodedata
from html.parser import HTMLParser
from functools import wraps
from datetime import datetime

from flask import Flask, render_template, redirect, url_for, flash, request, abort, jsonify
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
from sqlalchemy.orm import joinedload
from sqlalchemy.exc import IntegrityError

# Импорт моделей и форм
from models import db, User, Category, Post, Comment, PostLike, Notification, CommentVote
from forms import (
    RegistrationForm, LoginForm, PostForm, CommentForm, CategoryForm,
    SearchForm, EditProfileForm, ChangeEmailForm, ChangePasswordForm
)

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-key')
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///forum.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

csrf = CSRFProtect(app)

# ========= ЗАГРУЗКА ФАЙЛОВ =========
UPLOAD_FOLDER = os.path.join(app.static_folder, 'uploads')
AVATAR_FOLDER = os.path.join(UPLOAD_FOLDER, 'avatars')
BANNER_FOLDER = os.path.join(UPLOAD_FOLDER, 'banners')
POSTS_MEDIA_FOLDER = os.path.join(UPLOAD_FOLDER, 'posts')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

os.makedirs(AVATAR_FOLDER, exist_ok=True)
os.makedirs(BANNER_FOLDER, exist_ok=True)
os.makedirs(POSTS_MEDIA_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

db.init_app(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ========= ДЕКОРАТОРЫ =========
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role not in ('admin', 'moderator'):
            abort(403)
        return f(*args, **kwargs)
    return decorated_function

def admin_only(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'admin':
            abort(403)
        return f(*args, **kwargs)
    return decorated_function

# ========= СОБСТВЕННАЯ ФУНКЦИЯ ДЛЯ SLUG (без внешних библиотек) =========
def slugify_text(text):
    """
    Преобразует строку в slug (транслитерация, удаление диакритики, замена пробелов на дефисы).
    """
    if not text:
        return ''
    # Нормализация Unicode (разбиение диакритических знаков)
    text = unicodedata.normalize('NFKD', text)
    # Удаляем всё, кроме букв, цифр, пробелов и дефисов
    text = re.sub(r'[^\w\s-]', '', text, flags=re.UNICODE)
    # Приводим к нижнему регистру и заменяем пробелы/дефисы
    text = text.strip().lower()
    text = re.sub(r'[-\s]+', '-', text)
    return text

# ========= ГЕНЕРАЦИЯ УНИКАЛЬНОГО SLUG =========
def generate_slug(text, model, slug_field='slug'):
    base = slugify_text(text)
    if not base:
        base = str(int(datetime.utcnow().timestamp()))
    slug = base
    counter = 1
    while model.query.filter(getattr(model, slug_field) == slug).first():
        slug = f"{base}-{counter}"
        counter += 1
    return slug

def create_notification(user_id, message, link=None):
    notif = Notification(user_id=user_id, message=message, link=link)
    db.session.add(notif)
    db.session.commit()

# ========= САМОПИСНАЯ САНИТИЗАЦИЯ HTML (без bleach) =========
ALLOWED_TAGS = {
    'p': {'class'},
    'br': set(),
    'strong': set(),
    'b': set(),
    'em': set(),
    'i': set(),
    'u': set(),
    'strike': set(),
    'del': set(),
    'a': {'href', 'title', 'target'},
    'img': {'src', 'alt', 'width', 'height'},
    'ul': {'class'},
    'ol': {'class'},
    'li': set(),
    'blockquote': {'class'},
    'code': set(),
    'pre': set(),
    'h1': set(),
    'h2': set(),
    'h3': set(),
    'h4': set(),
    'h5': set(),
    'h6': set(),
}

def sanitize_html(content):
    """Очищает HTML от опасных тегов и атрибутов, используя HTMLParser."""
    if not content:
        return ''

    class SanitizerParser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.result = []
            self.allowed_tags = ALLOWED_TAGS

        def handle_starttag(self, tag, attrs):
            if tag in self.allowed_tags:
                allowed_attrs = self.allowed_tags[tag]
                filtered_attrs = [(k, v) for k, v in attrs if k in allowed_attrs]
                attrs_str = ' ' + ' '.join(f'{k}="{html.escape(v)}"' for k, v in filtered_attrs) if filtered_attrs else ''
                self.result.append(f'<{tag}{attrs_str}>')

        def handle_endtag(self, tag):
            if tag in self.allowed_tags:
                self.result.append(f'</{tag}>')

        def handle_data(self, data):
            self.result.append(html.escape(data))

        def handle_comment(self, data):
            pass

        def handle_decl(self, decl):
            pass

        def handle_pi(self, data):
            pass

        def unknown_decl(self, data):
            pass

    parser = SanitizerParser()
    try:
        parser.feed(content)
        parser.close()
        return ''.join(parser.result)
    except Exception:
        return html.escape(content)

# ========= ГЛОБАЛЬНЫЙ ОБРАБОТЧИК ОШИБОК =========
@app.errorhandler(Exception)
def handle_exception(e):
    app.logger.error(f'Unhandled exception: {e}', exc_info=True)
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify(success=False, message='Внутренняя ошибка сервера. Подробности в консоли Flask.'), 500
    if app.debug:
        raise e
    return "Internal Server Error", 500

# ========= КОНТЕКСТНЫЙ ПРОЦЕССОР =========
@app.context_processor
def inject_globals():
    search_form = SearchForm()
    login_form = LoginForm()
    register_form = RegistrationForm()

    unread_count = 0
    notifications = []
    if current_user.is_authenticated:
        notifications = Notification.query.filter_by(user_id=current_user.id).order_by(Notification.created_at.desc()).limit(5).all()
        unread_count = Notification.query.filter_by(user_id=current_user.id, is_read=False).count()
        current_user.last_seen = datetime.utcnow()
        db.session.commit()

    return dict(
        search_form=search_form,
        login_form=login_form,
        register_form=register_form,
        unread_count=unread_count,
        notifications=notifications
    )

@app.template_filter('time_ago')
def time_ago_filter(dt):
    if not dt:
        return ''
    now = datetime.utcnow()
    diff = now - dt
    if diff.days > 7:
        return dt.strftime('%d.%m.%Y')
    elif diff.days > 0:
        return f"{diff.days} дн. назад"
    elif diff.seconds > 3600:
        return f"{diff.seconds // 3600} ч. назад"
    elif diff.seconds > 60:
        return f"{diff.seconds // 60} мин. назад"
    else:
        return "только что"

@app.template_filter('pluralize')
def pluralize_filter(number, forms):
    if not isinstance(number, int):
        number = int(number) if number else 0
    n = number % 100
    if n > 20:
        n %= 10
    forms_list = forms.split(',')
    if n == 1:
        return forms_list[0]
    elif 2 <= n <= 4:
        return forms_list[1]
    else:
        return forms_list[2]

def ensure_default_data():
    admin = User.query.filter_by(email='admin@example.com').first()
    if not admin:
        admin = User(
            username='admin',
            email='admin@example.com',
            password_hash=generate_password_hash('admin'),
            role='admin'
        )
        db.session.add(admin)
    else:
        if admin.role != 'admin':
            admin.role = 'admin'
        if admin.username != 'admin':
            admin.username = 'admin'
    db.session.commit()

    admin = User.query.filter_by(email='admin@example.com').first()
    if not admin:
        return

    categories_data = [
        {'name': 'Комнатные джунгли', 'slug': 'houseplants', 'icon': 'fas fa-seedling'},
        {'name': 'Сад и огород', 'slug': 'garden', 'icon': 'fas fa-carrot'},
        {'name': 'Лекарственные травы', 'slug': 'herbs', 'icon': 'fas fa-leaf'},
        {'name': 'Редкие виды', 'slug': 'rare-plants', 'icon': 'fas fa-dragon'},
        {'name': 'Эко-привычки', 'slug': 'eco-habits', 'icon': 'fas fa-recycle'},
        {'name': 'Дикая природа', 'slug': 'wildlife', 'icon': 'fas fa-paw'},
        {'name': 'Мировой океан', 'slug': 'ocean', 'icon': 'fas fa-water'},
        {'name': 'Климат и изменения', 'slug': 'climate', 'icon': 'fas fa-temperature-high'},
        {'name': 'Ландшафтный дизайн', 'slug': 'landscape', 'icon': 'fas fa-tree'},
        {'name': 'Флористика и декор', 'slug': 'floristry', 'icon': 'fas fa-spa'},
        {'name': 'Городское фермерство', 'slug': 'urban-farming', 'icon': 'fas fa-city'},
        {'name': 'Био-лаборатория', 'slug': 'bio-lab', 'icon': 'fas fa-microscope'},
        {'name': 'Эко-туризм', 'slug': 'eco-tourism', 'icon': 'fas fa-hiking'},
    ]

    for cat_data in categories_data:
        cat = Category.query.filter_by(slug=cat_data['slug']).first()
        if cat:
            cat.name = cat_data['name']
            cat.icon_class = cat_data['icon']
        else:
            cat = Category(
                name=cat_data['name'],
                slug=cat_data['slug'],
                icon_class=cat_data['icon'],
                creator_id=admin.id
            )
            db.session.add(cat)
    db.session.commit()

# ========= МАРШРУТЫ =========
@app.route('/')
def index():
    sort = request.args.get('sort', 'new')
    category_slug = request.args.get('category')
    query = request.args.get('q')

    posts_query = Post.query
    if category_slug:
        category = Category.query.filter_by(slug=category_slug).first_or_404()
        posts_query = posts_query.filter_by(category_id=category.id)
    if query:
        posts_query = posts_query.filter(Post.title.contains(query) | Post.content.contains(query))

    if sort == 'old':
        posts_query = posts_query.order_by(Post.created_at.asc())
    elif sort == 'popular':
        posts_query = posts_query.order_by(Post.likes.desc())
    elif sort == 'updated':
        posts_query = posts_query.order_by(Post.updated_at.desc())
    else:
        posts_query = posts_query.order_by(Post.created_at.desc())

    page = request.args.get('page', 1, type=int)
    pagination = posts_query.paginate(page=page, per_page=10, error_out=False)
    posts = pagination.items
    return render_template('index.html', posts=posts, pagination=pagination, current_sort=sort)

@app.route('/categories')
def categories_list():
    all_cats = Category.query.order_by(Category.name).all()
    cats_with_counts = []
    for cat in all_cats:
        count = Post.query.filter_by(category_id=cat.id).count()
        cats_with_counts.append((cat, count))
    return render_template('categories.html', categories=cats_with_counts)

@app.route('/post/<string:slug>', methods=['GET', 'POST'])
def view_post(slug):
    post = Post.query.filter_by(slug=slug).first_or_404()
    post.views += 1
    db.session.commit()

    sort_type = request.args.get('sort', 'new')

    comments = Comment.query.filter_by(post_id=post.id).options(joinedload(Comment.author)).all()

    if sort_type == 'old':
        comments.sort(key=lambda c: c.created_at)
    elif sort_type == 'popular':
        comments.sort(key=lambda c: c.votes_total, reverse=True)
    else:
        comments.sort(key=lambda c: c.created_at, reverse=True)

    total_comments_count = len(comments)

    user_votes = {}
    if current_user.is_authenticated:
        votes = CommentVote.query.filter_by(user_id=current_user.id).filter(CommentVote.comment_id.in_([c.id for c in comments])).all()
        user_votes = {v.comment_id: v.value for v in votes}
    for c in comments:
        c.user_vote = user_votes.get(c.id, 0)

    form = CommentForm()
    liked = PostLike.query.filter_by(user_id=current_user.id, post_id=post.id).first() is not None if current_user.is_authenticated else False
    return render_template('post.html',
        post=post,
        comments=comments,
        total_comments_count=total_comments_count,
        form=form,
        liked=liked,
        current_sort=sort_type
    )

@app.route('/like_post/<int:post_id>', methods=['POST'])
@login_required
@csrf.exempt
def like_post(post_id):
    post = Post.query.get_or_404(post_id)
    if post.user_id == current_user.id:
        return jsonify({'error': 'Нельзя лайкать свой пост'}), 400

    like = PostLike.query.filter_by(user_id=current_user.id, post_id=post_id).first()
    if like:
        db.session.delete(like)
        post.likes -= 1
        liked = False
    else:
        new_like = PostLike(user_id=current_user.id, post_id=post_id)
        db.session.add(new_like)
        post.likes += 1
        liked = True
        create_notification(post.user_id, f"{current_user.username} лайкнул ваш пост «{post.title}»", url_for('view_post', slug=post.slug))
    db.session.commit()
    return jsonify({'likes': post.likes, 'liked': liked})

@app.route('/vote_comment/<int:comment_id>', methods=['POST'])
@login_required
@csrf.exempt
def vote_comment(comment_id):
    vote_type = request.args.get('type')
    if vote_type not in ('up', 'down'):
        return jsonify(success=False, error='Неверный тип голоса'), 400

    comment = Comment.query.get_or_404(comment_id)
    if comment.user_id == current_user.id:
        return jsonify(success=False, error='Нельзя голосовать за свой комментарий'), 400

    new_value = 1 if vote_type == 'up' else -1

    existing = CommentVote.query.filter_by(user_id=current_user.id, comment_id=comment_id).first()
    if existing:
        if existing.value == new_value:
            db.session.delete(existing)
            comment.votes_total -= existing.value
            voted = False
            vote_type = None
        else:
            comment.votes_total -= existing.value
            existing.value = new_value
            comment.votes_total += new_value
            db.session.add(existing)
            voted = True
    else:
        vote = CommentVote(user_id=current_user.id, comment_id=comment_id, value=new_value)
        db.session.add(vote)
        comment.votes_total = (comment.votes_total or 0) + new_value
        voted = True

    db.session.commit()
    return jsonify(success=True, new_score=comment.votes_total, voted=voted, vote_type=vote_type)

@app.route('/create-post', methods=['GET', 'POST'])
@login_required
def create_post():
    form = PostForm()
    form.category.choices = [(c.id, c.name) for c in Category.query.all()]
    if not form.category.choices:
        flash('Сначала создайте категорию', 'warning')
        return redirect(url_for('create_category_page'))

    if form.validate_on_submit():
        try:
            slug = generate_slug(form.title.data, Post)
            clean_content = sanitize_html(form.content.data)

            filename = None
            if form.media.data:
                file = form.media.data
                ext = file.filename.rsplit('.', 1)[1].lower()
                filename = secure_filename(f"post_{current_user.id}_{int(datetime.utcnow().timestamp())}.{ext}")
                file.save(os.path.join(POSTS_MEDIA_FOLDER, filename))

            post = Post(
                title=form.title.data,
                slug=slug,
                content=clean_content,
                user_id=current_user.id,
                category_id=form.category.data,
                media=filename
            )
            db.session.add(post)
            db.session.commit()
            flash('Пост опубликован', 'success')
            return redirect(url_for('view_post', slug=post.slug))

        except IntegrityError as e:
            db.session.rollback()
            app.logger.error(f'IntegrityError при создании поста: {e}')
            flash('Ошибка: такой заголовок уже существует или возникла проблема с базой данных.', 'danger')
        except Exception as e:
            db.session.rollback()
            app.logger.error(f'Ошибка при создании поста: {e}')
            flash(f'Произошла ошибка: {str(e)}', 'danger')

        return render_template('create_post.html', form=form)

    return render_template('create_post.html', form=form)

@app.route('/edit-post/<string:slug>', methods=['GET', 'POST'])
@login_required
def edit_post(slug):
    post = Post.query.filter_by(slug=slug).first_or_404()
    if post.user_id != current_user.id and current_user.role not in ('admin', 'moderator'):
        abort(403)
    form = PostForm()
    form.category.choices = [(c.id, c.name) for c in Category.query.all()]
    if form.validate_on_submit():
        post.title = form.title.data
        post.content = sanitize_html(form.content.data)
        post.category_id = form.category.data

        if form.media.data:
            if post.media:
                old_path = os.path.join(POSTS_MEDIA_FOLDER, post.media)
                if os.path.exists(old_path):
                    os.remove(old_path)
            file = form.media.data
            ext = file.filename.rsplit('.', 1)[1].lower()
            filename = secure_filename(f"post_{current_user.id}_{int(datetime.utcnow().timestamp())}.{ext}")
            file.save(os.path.join(POSTS_MEDIA_FOLDER, filename))
            post.media = filename

        db.session.commit()
        flash('Пост обновлён', 'success')
        return redirect(url_for('view_post', slug=post.slug))

    form.title.data = post.title
    form.content.data = post.content
    form.category.data = post.category_id
    return render_template('edit_post.html', form=form, post=post)

@app.route('/delete-post-media/<int:post_id>', methods=['POST'])
@login_required
def delete_post_media(post_id):
    post = Post.query.get_or_404(post_id)
    if post.user_id != current_user.id and current_user.role not in ('admin', 'moderator'):
        abort(403)
    if post.media:
        path = os.path.join(POSTS_MEDIA_FOLDER, post.media)
        if os.path.exists(path):
            os.remove(path)
        post.media = None
        db.session.commit()
        flash('Вложение удалено', 'success')
    return redirect(url_for('edit_post', slug=post.slug))

@app.route('/delete-post/<int:post_id>', methods=['POST'])
@login_required
def delete_post(post_id):
    post = Post.query.get_or_404(post_id)
    if post.user_id != current_user.id and current_user.role not in ('admin', 'moderator'):
        abort(403)
    if post.media:
        path = os.path.join(POSTS_MEDIA_FOLDER, post.media)
        if os.path.exists(path):
            os.remove(path)
    db.session.delete(post)
    db.session.commit()
    flash('Пост удалён', 'success')
    return redirect(url_for('index'))

@app.route('/add_comment/<int:post_id>', methods=['POST'])
@login_required
@csrf.exempt
def add_comment(post_id):
    post = Post.query.get_or_404(post_id)
    content = request.form.get('content')
    if not content or not content.strip():
        return jsonify(success=False, error='Пустой комментарий')

    clean_content = sanitize_html(content)
    comment = Comment(
        content=clean_content,
        user_id=current_user.id,
        post_id=post.id
    )
    db.session.add(comment)
    db.session.commit()

    if post.user_id != current_user.id:
        create_notification(post.user_id, f"{current_user.username} ответил в вашем посте «{post.title}»", url_for('view_post', slug=post.slug))

    return jsonify(success=True)

@app.route('/edit-comment/<int:comment_id>', methods=['GET', 'POST'])
@login_required
@csrf.exempt
def edit_comment(comment_id):
    comment = Comment.query.get_or_404(comment_id)
    if comment.user_id != current_user.id and current_user.role not in ('admin', 'moderator'):
        abort(403)
    if request.method == 'POST':
        comment.content = sanitize_html(request.form.get('content'))
        db.session.commit()
        flash('Комментарий обновлён', 'success')
        return redirect(url_for('view_post', slug=comment.post.slug))
    return render_template('edit_comment.html', comment=comment)

@app.route('/delete-comment/<int:comment_id>', methods=['POST'])
@login_required
def delete_comment(comment_id):
    comment = Comment.query.get_or_404(comment_id)
    if comment.user_id != current_user.id and current_user.role not in ('admin', 'moderator'):
        abort(403)
    post_slug = comment.post.slug
    db.session.delete(comment)
    db.session.commit()
    flash('Комментарий удалён', 'success')
    return redirect(url_for('view_post', slug=post_slug))

# ========= РЕГИСТРАЦИЯ =========
@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    form = RegistrationForm()
    if form.validate_on_submit():
        try:
            hashed = generate_password_hash(form.password.data)
            user = User(username=form.username.data, email=form.email.data, password_hash=hashed)
            db.session.add(user)
            db.session.commit()
            login_user(user)
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify(success=True, redirect=url_for('index'))
            flash('Регистрация успешна', 'success')
            return redirect(url_for('index'))
        except IntegrityError:
            db.session.rollback()
            error_msg = 'Пользователь с таким именем или email уже существует.'
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify(success=False, message=error_msg), 400
            flash(error_msg, 'danger')
            return redirect(url_for('register'))
        except Exception as e:
            db.session.rollback()
            app.logger.error(f'Registration error: {e}')
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify(success=False, message='Ошибка сервера. Попробуйте позже.'), 500
            flash('Ошибка сервера. Попробуйте позже.', 'danger')
            return redirect(url_for('register'))
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        errors = {}
        for field, err_list in form.errors.items():
            errors[field] = err_list[0] if err_list else 'Некорректное значение'
        return jsonify(success=False, errors=errors), 400
    return render_template('register.html', form=form)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user and check_password_hash(user.password_hash, form.password.data):
            if user.is_banned:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify(success=False, message='Ваш аккаунт заблокирован')
                flash('Ваш аккаунт заблокирован', 'danger')
                return redirect(url_for('login'))
            login_user(user, remember=form.remember.data)
            next_page = request.args.get('next') or request.form.get('next')
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify(success=True, redirect=next_page or url_for('index'))
            flash('Добро пожаловать!', 'success')
            return redirect(next_page or url_for('index'))
        else:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify(success=False, message='Неверное имя пользователя или пароль')
            flash('Неверные учётные данные', 'danger')
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify(success=False, errors=form.errors)
    return render_template('login.html', form=form)

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/profile/<string:username>')
def profile(username):
    user = User.query.filter_by(username=username).first_or_404()
    posts = Post.query.filter_by(user_id=user.id).order_by(Post.created_at.desc()).all()
    return render_template('profile.html', profile_user=user, posts=posts)

@app.route('/edit-profile', methods=['GET', 'POST'])
@login_required
def edit_profile():
    form = EditProfileForm(original_username=current_user.username)
    if form.validate_on_submit():
        current_user.username = form.username.data
        current_user.bio = form.bio.data
        if form.avatar.data and allowed_file(form.avatar.data.filename):
            filename = secure_filename(f"avatar_{current_user.id}_{form.avatar.data.filename}")
            form.avatar.data.save(os.path.join(AVATAR_FOLDER, filename))
            current_user.avatar = filename
        if form.remove_avatar.data:
            current_user.avatar = None
        if form.banner.data and allowed_file(form.banner.data.filename):
            filename = secure_filename(f"banner_{current_user.id}_{form.banner.data.filename}")
            form.banner.data.save(os.path.join(BANNER_FOLDER, filename))
            current_user.banner = filename
        if form.remove_banner.data:
            current_user.banner = None
        db.session.commit()
        flash('Профиль обновлён', 'success')
        return redirect(url_for('profile', username=current_user.username))
    form.username.data = current_user.username
    form.bio.data = current_user.bio
    return render_template('edit_profile.html', form=form)

@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    email_form = ChangeEmailForm()
    password_form = ChangePasswordForm()
    if email_form.validate_on_submit():
        if User.query.filter_by(email=email_form.email.data).first():
            flash('Email уже используется', 'danger')
        else:
            current_user.email = email_form.email.data
            db.session.commit()
            flash('Email изменён', 'success')
        return redirect(url_for('settings'))
    if password_form.validate_on_submit():
        if check_password_hash(current_user.password_hash, password_form.current_password.data):
            current_user.password_hash = generate_password_hash(password_form.new_password.data)
            db.session.commit()
            flash('Пароль изменён', 'success')
        else:
            flash('Неверный текущий пароль', 'danger')
        return redirect(url_for('settings'))
    return render_template('settings.html', email_form=email_form, password_form=password_form)

@app.route('/admin')
@admin_required
def admin_panel():
    users = User.query.order_by(User.id).all()
    return render_template('admin_panel.html', users=users)

@app.route('/admin/change_role/<int:user_id>', methods=['POST'])
@admin_only
def change_role(user_id):
    user = User.query.get_or_404(user_id)
    new_role = request.form.get('role')
    if new_role in ('user', 'moderator', 'admin'):
        old_role = user.role
        user.role = new_role
        db.session.commit()
        flash(f'Роль пользователя {user.username} изменена с "{old_role}" на "{new_role}".', 'success')
    else:
        flash('Некорректная роль', 'danger')
    return redirect(url_for('admin_panel'))

@app.route('/admin/ban_user/<int:user_id>', methods=['POST'])
@admin_required
def ban_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.is_banned:
        user.is_banned = False
        user.ban_reason = None
        flash(f'Пользователь {user.username} разблокирован.', 'success')
    else:
        reason = request.form.get('reason', '').strip()
        if not reason:
            flash('Укажите причину бана', 'danger')
            return redirect(url_for('admin_panel'))
        user.is_banned = True
        user.ban_reason = reason
        flash(f'Пользователь {user.username} заблокирован. Причина: {reason}', 'warning')
    db.session.commit()
    return redirect(url_for('admin_panel'))

@app.route('/update_theme', methods=['POST'])
@login_required
@csrf.exempt
def update_theme():
    data = request.get_json()
    theme = data.get('theme')
    if theme in ('light', 'dark'):
        current_user.theme = theme
        db.session.commit()
        return jsonify(success=True)
    return jsonify(success=False), 400

@app.route('/notifications/read', methods=['POST'])
@login_required
def mark_notifications_read():
    Notification.query.filter_by(user_id=current_user.id, is_read=False).update({'is_read': True})
    db.session.commit()
    return jsonify(success=True)

@app.route('/create-category-page', methods=['GET'])
@admin_only
def create_category_page():
    return render_template('create_category.html')

@app.route('/create-category', methods=['POST'])
@admin_only
@csrf.exempt
def create_category_ajax():
    data = request.get_json()
    name = data.get('name')
    color = data.get('color', '#4a6741')
    icon_class = data.get('icon_class', 'fas fa-folder')
    if not name:
        return jsonify({'error': 'Name required'}), 400
    slug = generate_slug(name, Category)
    category = Category(name=name, slug=slug, color=color, icon_class=icon_class, creator_id=current_user.id)
    db.session.add(category)
    db.session.commit()
    return jsonify({'success': True, 'slug': slug})

@app.route('/search')
def search():
    q = request.args.get('q', '')
    if not q:
        return redirect(url_for('index'))
    posts = Post.query.filter(Post.title.contains(q) | Post.content.contains(q)).all()
    return render_template('search_results.html', query=q, posts=posts)

@app.route('/delete-avatar', methods=['POST'])
@login_required
@csrf.exempt
def delete_avatar():
    if current_user.avatar:
        try:
            os.remove(os.path.join(AVATAR_FOLDER, current_user.avatar))
        except:
            pass
        current_user.avatar = None
        db.session.commit()
        return jsonify(success=True)
    return jsonify(success=False), 400

@app.route('/delete-banner', methods=['POST'])
@login_required
@csrf.exempt
def delete_banner():
    if current_user.banner:
        try:
            os.remove(os.path.join(BANNER_FOLDER, current_user.banner))
        except:
            pass
        current_user.banner = None
        db.session.commit()
        return jsonify(success=True)
    return jsonify(success=False), 400

# ========= ЗАПУСК =========
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        ensure_default_data()
    debug_mode = os.getenv('DEBUG', 'False').lower() == 'true'
    app.run(host='0.0.0.0', port=5000, debug=debug_mode)
    