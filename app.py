from flask import Flask, render_template, request, redirect, url_for, flash, session, make_response
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
import os
import logging
from functools import wraps
import sqlalchemy
import json

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///blog.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.permanent_session_lifetime = timedelta(days=30)

logger.debug("初始化 Flask 应用")

instance_path = os.path.join(os.path.dirname(__file__), 'instance')
if not os.path.exists(instance_path):
    try:
        os.makedirs(instance_path)
        logger.debug("创建 instance 目录")
    except Exception as e:
        logger.error(f"创建 instance 目录失败: {e}")

db = SQLAlchemy(app)

global_users = []
global_posts = []
global_comments = []


class ValidationError(Exception):
    pass


class DatabaseError(Exception):
    pass


class PermissionDeniedError(Exception):
    pass


class User(db.Model):
    __tablename__ = 'user'
    id = db.Column(db.Integer, primary_key=True)
    firebase_uid = db.Column(db.String(120), unique=True, nullable=False)  # Firebase用户ID
    username = db.Column(db.String(80), unique=True, nullable=False)  # 用户昵称
    role = db.Column(db.String(20), default='user')  # 角色：user, admin, master
    is_banned = db.Column(db.Boolean, default=False)  # 是否被封禁
    is_muted = db.Column(db.Boolean, default=False)  # 是否被禁言
    theme_preference = db.Column(db.String(10), default='light')  # 主题偏好
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)  # 创建时间
    signature = db.Column(db.String(200), default='')  # 个性签名
    avatar_url = db.Column(db.String(200), default='')  # 头像URL
    last_login_ip = db.Column(db.String(45), default='')  # 最近登录IP
    contact_info = db.Column(db.String(500), default='')  # 联系方式
    age = db.Column(db.Integer, nullable=True)  # 年龄
    gender = db.Column(db.String(10), nullable=True)  # 性别
    birthday = db.Column(db.Date, nullable=True)  # 生日
    
    def __repr__(self):
        return f"User('{self.username}', '{self.role}')"


class Post(db.Model):
    __tablename__ = 'post'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    content = db.Column(db.Text, nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    date_posted = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    is_update_log = db.Column(db.Boolean, default=False)

    author = db.relationship('User', backref=db.backref('posts', lazy=True))

    def __repr__(self):
        return f"Post('{self.title}', '{self.date_posted}')"


class Comment(db.Model):
    __tablename__ = 'comment'
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    parent_id = db.Column(db.Integer, db.ForeignKey('comment.id'), nullable=True)
    date_posted = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    post = db.relationship('Post', backref=db.backref('comments', lazy=True))
    author = db.relationship('User', backref=db.backref('comments', lazy=True))
    replies = db.relationship('Comment', backref=db.backref('parent', remote_side=[id]), lazy='dynamic')

    def __repr__(self):
        return f"Comment('{self.content[:20]}...', '{self.date_posted}')"


class Report(db.Model):
    __tablename__ = 'report'
    id = db.Column(db.Integer, primary_key=True)
    reporter_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=True)
    comment_id = db.Column(db.Integer, db.ForeignKey('comment.id'), nullable=True)
    reason = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default='pending')
    date_reported = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    reporter = db.relationship('User', foreign_keys=[reporter_id])
    post = db.relationship('Post', foreign_keys=[post_id])
    comment = db.relationship('Comment', foreign_keys=[comment_id])


class Friendship(db.Model):
    __tablename__ = 'friendship'
    id = db.Column(db.Integer, primary_key=True)
    follower_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    followed_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    status = db.Column(db.String(20), default='accepted')

    follower = db.relationship('User', foreign_keys=[follower_id])
    followed = db.relationship('User', foreign_keys=[followed_id])


class PrivateMessage(db.Model):
    __tablename__ = 'private_message'
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    is_read = db.Column(db.Boolean, default=False)

    sender = db.relationship('User', foreign_keys=[sender_id])
    receiver = db.relationship('User', foreign_keys=[receiver_id])


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)

    return decorated_function


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        # 检查用户是否具有管理员或站长权限
        user = db.session.get(User, session['user_id'])
        if not user or user.role not in ['admin', 'master']:
            flash('需要管理员权限才能访问此页面')
            return redirect(url_for('home'))
        return f(*args, **kwargs)
    return decorated_function


def master_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        # 检查用户是否具有站长权限
        user = db.session.get(User, session['user_id'])
        if not user or user.role != 'master':
            flash('需要站长权限才能访问此页面')
            return redirect(url_for('home'))
        return f(*args, **kwargs)
    return decorated_function


def check_banned(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' in session:
            user = db.session.get(User, session['user_id'])
            if user and user.is_banned:
                flash('用户已被封禁')
                return render_template('banned.html')
        return f(*args, **kwargs)

    return decorated_function


def check_muted(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' in session:
            user = db.session.get(User, session['user_id'])
            if user and user.is_muted:
                flash('用户已被禁言，无法执行此操作')
                return redirect(url_for('home'))
        return f(*args, **kwargs)

    return decorated_function


@app.errorhandler(400)
def bad_request_error(error):
    logger.error(f"400 错误: {error}")
    return render_template('400.html'), 400


@app.errorhandler(403)
def forbidden_error(error):
    logger.error(f"403 错误: {error}")
    return render_template('403.html'), 403


@app.errorhandler(404)
def not_found_error(error):
    logger.error(f"404 错误: {error}")
    return render_template('404.html'), 404


@app.errorhandler(405)
def method_not_allowed_error(error):
    logger.error(f"405 错误: {error}")
    return render_template('405.html'), 405


@app.errorhandler(429)
def too_many_requests_error(error):
    logger.error(f"429 错误: {error}")
    return render_template('429.html'), 429


@app.errorhandler(500)
def internal_error(error):
    logger.error(f"500 错误: {error}")
    db.session.rollback()
    return render_template('500.html'), 500


@app.errorhandler(503)
def service_unavailable_error(error):
    logger.error(f"503 错误: {error}")
    return render_template('503.html'), 503


@app.errorhandler(sqlalchemy.exc.SQLAlchemyError)
def database_error(error):
    logger.error(f"数据库错误: {error}")
    db.session.rollback()
    flash("系统暂时无法处理您的请求，请稍后再试", "error")
    return redirect(request.referrer or url_for('home'))


@app.errorhandler(ValidationError)
def handle_validation_error(error):
    logger.warning(f"验证错误: {error}")
    flash(str(error), "error")
    return redirect(request.referrer or url_for('home'))


@app.errorhandler(DatabaseError)
def handle_database_error(error):
    logger.error(f"数据库错误: {error}")
    db.session.rollback()
    flash("数据库操作失败，请稍后再试", "error")
    return redirect(request.referrer or url_for('home'))


@app.errorhandler(PermissionDeniedError)
def handle_permission_denied_error(error):
    logger.warning(f"权限拒绝错误: {error}")
    flash("您没有权限执行此操作", "error")
    return redirect(request.referrer or url_for('home'))


@app.template_filter('from_json')
def from_json(value):
    try:
        return json.loads(value)
    except:
        return {}


@app.route('/')
@check_banned
def home():
    try:
        # 检查生日
        check_birthday()
        
        logger.debug("访问主页路由")
        all_posts = db.session.query(Post).join(User).order_by(
            db.case(
                (User.role == 'master', 1),
                (User.role == 'admin', 2),
                else_=3
            ),
            Post.date_posted.desc()
        ).all()

        users_count = User.query.count()
        comments_count = Comment.query.count()
        latest_update_log = Post.query.filter_by(is_update_log=True).order_by(Post.date_posted.desc()).first()
        logger.debug(f"查询到 {len(all_posts)} 篇文章")

        global global_posts
        global_posts = all_posts

        response = make_response(render_template('home.html',
                                                 all_posts=all_posts,
                                                 latest_update_log=latest_update_log,
                                                 users_count=users_count,
                                                 comments_count=comments_count))

        if 'user_id' in session:
            user = db.session.get(User, session['user_id'])
            if user:
                response.set_cookie('theme', user.theme_preference, max_age=30 * 24 * 60 * 60)
        elif 'theme' not in request.cookies:
            response.set_cookie('theme', 'light', max_age=30 * 24 * 60 * 60)

        return response
    except sqlalchemy.exc.SQLAlchemyError as e:
        logger.error(f"数据库错误: {e}", exc_info=True)
        flash("数据加载失败，请稍后再试", "error")
        return render_template('home.html', all_posts=[], latest_update_log=None), 500
    except Exception as e:
        logger.error(f"主页路由错误: {e}", exc_info=True)
        flash("系统遇到问题，请稍后再试", "error")
        return render_template('home.html', all_posts=[], latest_update_log=None), 500


@app.route('/register', methods=['GET', 'POST'])
def register():
    logger.debug("访问注册页面")
    if request.method == 'POST':
        # 检查是否是传统的注册方式（为了向后兼容）
        if 'identifier' not in request.form:
            try:
                username = request.form['username']
                password = request.form['password']
                invite_code = request.form['invite_code']

                if not username or not password or not invite_code:
                    flash('请填写所有必填字段')
                    return redirect(url_for('register'))

                contact_fields = [
                    'bilibili', 'phone', 'email', 'qq', 'wechat', 'weibo',
                    'telegram', 'youtube', 'twitter', 'xiaohongshu', 'douyin', 'other'
                ]

                contact_info = {}
                for field in contact_fields:
                    value = request.form.get(field, '').strip()
                    if value:
                        contact_info[field] = value

                if not contact_info:
                    flash('请至少填写一种联系方式')
                    return redirect(url_for('register'))

                invite = InviteCode.query.filter_by(code=invite_code).first()
                if not invite or invite.used_at:
                    flash('无效或已被使用的邀请码')
                    return redirect(url_for('register'))

                if User.query.filter_by(username=username).first():
                    flash('用户名已存在')
                    return redirect(url_for('register'))

                all_users = User.query.all()
                for user in all_users:
                    if user.contact_info:
                        try:
                            existing_contacts = json.loads(user.contact_info)
                            for key, value in contact_info.items():
                                if key in existing_contacts and existing_contacts[key] == value:
                                    flash(f'联系方式 {key}: {value} 已被其他用户使用')
                                    return redirect(url_for('register'))
                        except:
                            continue

                user = User(
                    username=username,
                    password=password,
                    contact_info=json.dumps(contact_info, ensure_ascii=False)
                )
                db.session.add(user)
                db.session.flush()

                invite.used_at = datetime.utcnow()
                invite.used_by = user.id
                invite.used_ip = request.environ.get('HTTP_X_REAL_IP', request.remote_addr)

                db.session.commit()

                master = User.query.filter_by(role='master').first()
                if master:
                    friendship = Friendship(follower_id=user.id, followed_id=master.id)
                    db.session.add(friendship)
                    db.session.commit()

                flash('注册成功，请登录')
                return redirect(url_for('login'))
            except sqlalchemy.exc.SQLAlchemyError as e:
                logger.error(f"数据库错误: {e}")
                db.session.rollback()
                flash('注册失败，请稍后再试', 'error')
                return redirect(url_for('register'))
            except Exception as e:
                logger.error(f"注册过程发生错误: {e}")
                db.session.rollback()
                flash('注册过程中发生错误，请稍后再试', 'error')
                return redirect(url_for('register'))
        else:
            # 这里是为了向后兼容，实际上应该由前端Firebase处理
            flash('请使用页面上的注册表单进行注册')
    
    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    logger.debug("访问登录页面")
    if request.method == 'POST':
        # 检查是否是传统的登录方式（为了向后兼容）
        if 'identifier' not in request.form:
            username = request.form['username']
            password = request.form['password']
            remember = request.form.get('remember')

            user = User.query.filter_by(username=username).first()

            if user and user.password == password:
                if user.is_banned:
                    flash('用户已被封禁')
                    return render_template('banned.html')

                session['user_id'] = user.id
                session['username'] = user.username
                session['role'] = user.role

                user.last_login_ip = request.environ.get('HTTP_X_REAL_IP', request.remote_addr)
                db.session.commit()

                if remember:
                    session.permanent = True

                logger.info(f"用户 {user.username} 登录成功，上次登录IP: {user.last_login_ip}")
                response = make_response(redirect(url_for('home')))
                response.set_cookie('theme', user.theme_preference, max_age=30 * 24 * 60 * 60)
                return response
            else:
                flash('用户名或密码错误')
        else:
            # 这里是为了向后兼容，实际上应该由前端Firebase处理
            flash('请使用页面上的登录表单进行登录')
    
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))


@app.route('/post/<int:post_id>')
@check_banned
def post(post_id):
    try:
        logger.debug(f"访问文章 {post_id}")
        post = Post.query.get_or_404(post_id)
        logger.debug(f"找到文章: {post.title}")
        return render_template('post.html', post=post)
    except Exception as e:
        logger.error(f"文章页面路由错误: {e}", exc_info=True)
        return "Internal Server Error", 500


@app.route('/create', methods=['GET', 'POST'])
@login_required
@check_banned
@check_muted
def create_post():
    try:
        logger.debug(f"访问创建文章页面，方法: {request.method}")
        if request.method == 'POST':
            title = request.form['title']
            content = request.form['content']

            user_id = session['user_id']

            logger.debug(f"创建文章: {title}")
            logger.debug(f"正在创建新文章: 用户ID - {user_id}, 标题 - {title}, 内容长度 - {len(content)}")
            post = Post(title=title, content=content, author_id=user_id)
            db.session.add(post)
            try:
                db.session.commit()
                logger.info(f"文章 {post.id} 创建成功")
            except Exception as e:
                logger.error(f"创建文章失败: 用户ID - {user_id}, 错误 - {e}")
                db.session.rollback()
                flash("创建文章失败，请稍后再试", "error")
                return redirect(url_for('create_post'))
            logger.info(f"文章 {post.id} 创建后重定向到主页")
            logger.debug("文章保存成功")

            return redirect(url_for('home'))

        username = session.get('username', 'Anonymous')
        return render_template('create_post.html', author=username)
    except Exception as e:
        logger.error(f"创建文章路由错误: {e}", exc_info=True)
        db.session.rollback()
        return "Internal Server Error", 500


@app.route('/post/<int:post_id>/edit', methods=['GET', 'POST'])
@login_required
@check_banned
def edit_post(post_id):
    try:
        logger.debug(f"访问编辑文章页面 {post_id}，方法: {request.method}")
        post = Post.query.get_or_404(post_id)

        if post.author_id != session['user_id'] and session.get('role') != 'admin':
            flash('您没有权限编辑此文章')
            return redirect(url_for('post', post_id=post.id))

        if request.method == 'POST':
            old_title = post.title
            old_content = post.content
            post.title = request.form['title']
            post.content = request.form['content']

            try:
                db.session.commit()
                logger.info(
                    f"文章 {post.id} 更新成功: 旧标题 - {old_title}, 新标题 - {post.title}, 旧内容长度 - {len(old_content)}, 新内容长度 - {len(post.content)}")
            except Exception as e:
                logger.error(f"更新文章失败: 文章ID - {post.id}, 错误 - {e}")
                db.session.rollback()
                flash("更新文章失败，请稍后再试", "error")
                return redirect(url_for('edit_post', post_id=post.id))
            logger.info(f"文章 {post.id} 更新后重定向到文章页面")
            return redirect(url_for('post', post_id=post.id))

        return render_template('edit_post.html', post=post)
    except Exception as e:
        logger.error(f"编辑文章路由错误: {e}", exc_info=True)
        db.session.rollback()
        return "Internal Server Error", 500


@app.route('/post/<int:post_id>/delete', methods=['POST'])
@login_required
@check_banned
def delete_post(post_id):
    try:
        logger.debug(f"删除文章 {post_id}")
        post = Post.query.get_or_404(post_id)

        if post.author_id != session['user_id'] and session.get('role') != 'admin':
            flash('您没有权限删除此文章')
            return redirect(url_for('post', post_id=post.id))

        db.session.delete(post)
        db.session.commit()
        logger.debug("文章删除成功")

        return redirect(url_for('home'))
    except Exception as e:
        logger.error(f"删除文章路由错误: {e}", exc_info=True)
        db.session.rollback()
        return "Internal Server Error", 500


@app.route('/toggle_dark_mode')
def toggle_dark_mode():
    current_mode = 'light'
    if 'user_id' in session:
        user = db.session.get(User, session['user_id'])
        current_mode = user.theme_preference
        new_mode = 'dark' if current_mode == 'light' else 'light'
        user.theme_preference = new_mode
        db.session.commit()
        session['theme'] = new_mode
    else:
        current_mode = request.cookies.get('theme', 'light')
        new_mode = 'dark' if current_mode == 'light' else 'light'

    response = make_response(redirect(request.referrer or url_for('home')))
    response.set_cookie('theme', new_mode, max_age=30 * 24 * 60 * 60)
    return response


@app.route('/user/<int:user_id>')
@check_banned
def user_home(user_id):
    user = User.query.get_or_404(user_id)
    user_posts = Post.query.filter_by(author_id=user_id).order_by(Post.date_posted.desc()).all()
    return render_template('user_home.html', user=user, user_posts=user_posts)


@app.route('/profile/<int:user_id>')
@check_banned
def profile(user_id):
    profile_user = User.query.get_or_404(user_id)
    user_posts = Post.query.filter_by(author_id=user_id).order_by(Post.date_posted.desc()).all()

    is_following = False
    friendship_status = 'none'
    friendship_direction = 'none'

    if 'user_id' in session:
        following = Friendship.query.filter_by(
            follower_id=session['user_id'],
            followed_id=user_id,
            status='accepted'
        ).first()
        is_following = following is not None

        friendship = Friendship.query.filter(
            db.or_(
                db.and_(Friendship.follower_id == session['user_id'], Friendship.followed_id == user_id),
                db.and_(Friendship.follower_id == user_id, Friendship.followed_id == session['user_id'])
            )
        ).first()

        if friendship:
            friendship_status = friendship.status
            if friendship.follower_id == session['user_id']:
                friendship_direction = 'outgoing'
            else:
                friendship_direction = 'incoming'

    return render_template('profile.html',
                           profile_user=profile_user,
                           user_posts=user_posts,
                           is_following=is_following,
                           friendship_status=friendship_status,
                           friendship_direction=friendship_direction)


@app.route('/follow/<int:user_id>', methods=['POST'])
@login_required
@check_banned
def follow_user(user_id):
    if user_id == session['user_id']:
        flash('不能关注自己')
        return redirect(url_for('profile', user_id=user_id))

    existing_follow = Friendship.query.filter_by(
        follower_id=session['user_id'],
        followed_id=user_id,
        status='accepted'
    ).first()

    if existing_follow:
        flash('您已经关注了该用户')
    else:
        follow = Friendship(
            follower_id=session['user_id'],
            followed_id=user_id,
            status='accepted'
        )
        db.session.add(follow)
        db.session.commit()
        flash('关注成功')

    return redirect(url_for('profile', user_id=user_id))


@app.route('/unfollow/<int:user_id>', methods=['POST'])
@login_required
@check_banned
def unfollow_user(user_id):
    if user_id == session['user_id']:
        flash('不能取消关注自己')
        return redirect(url_for('profile', user_id=user_id))

    follow = Friendship.query.filter_by(
        follower_id=session['user_id'],
        followed_id=user_id,
        status='accepted'
    ).first()

    if follow:
        db.session.delete(follow)
        db.session.commit()
        flash('已取消关注')
    else:
        flash('您还没有关注该用户')

    return redirect(url_for('profile', user_id=user_id))


@app.route('/friend_request/<int:user_id>', methods=['POST'])
@login_required
@check_banned
def send_friend_request(user_id):
    if user_id == session['user_id']:
        flash('不能向自己发送好友申请')
        return redirect(url_for('profile', user_id=user_id))

    existing_friendship = Friendship.query.filter(
        db.or_(
            db.and_(Friendship.follower_id == session['user_id'], Friendship.followed_id == user_id),
            db.and_(Friendship.follower_id == user_id, Friendship.followed_id == session['user_id'])
        )
    ).first()

    if existing_friendship:
        if existing_friendship.status == 'accepted':
            flash('你们已经是好友了')
        elif existing_friendship.status == 'pending':
            flash('已有待处理的好友申请')
        else:
            friend_request = Friendship(
                follower_id=session['user_id'],
                followed_id=user_id,
                status='pending'
            )
            db.session.add(friend_request)
            db.session.commit()
            flash('好友申请已发送')
    else:
        friend_request = Friendship(
            follower_id=session['user_id'],
            followed_id=user_id,
            status='pending'
        )
        db.session.add(friend_request)
        db.session.commit()
        flash('好友申请已发送')

    return redirect(url_for('profile', user_id=user_id))


@app.route('/accept_friend_request/<int:user_id>', methods=['POST'])
@login_required
@check_banned
def accept_friend_request(user_id):
    friendship = Friendship.query.filter_by(
        follower_id=user_id,
        followed_id=session['user_id'],
        status='pending'
    ).first()

    if friendship:
        friendship.status = 'accepted'
        reverse_friendship = Friendship(
            follower_id=session['user_id'],
            followed_id=user_id,
            status='accepted'
        )
        db.session.add(reverse_friendship)
        db.session.commit()
        flash('已接受好友申请')
    else:
        flash('未找到好友申请')

    return redirect(url_for('profile', user_id=user_id))


@app.route('/reject_friend_request/<int:user_id>', methods=['POST'])
@login_required
@check_banned
def reject_friend_request(user_id):
    friendship = Friendship.query.filter_by(
        follower_id=user_id,
        followed_id=session['user_id'],
        status='pending'
    ).first()

    if friendship:
        friendship.status = 'rejected'
        db.session.commit()
        flash('已拒绝好友申请')
    else:
        flash('未找到好友申请')

    return redirect(url_for('profile', user_id=user_id))


@app.route('/user/profile', methods=['GET', 'POST'])
@login_required
@check_banned
def user_profile():
    logger.debug(f"用户 {session['username']} 访问个人资料页面")
    user = db.session.get(User, session['user_id'])

    contact_info = {}
    if user.contact_info:
        try:
            contact_info = json.loads(user.contact_info)
        except:
            contact_info = {}

    if request.method == 'POST':
        form_type = request.form.get('form_type')

        if form_type != 'password':
            new_username = request.form.get('username')
            signature = request.form.get('signature')
            age = request.form.get('age')
            gender = request.form.get('gender')
            birthday = request.form.get('birthday')

            contact_fields = [
                'bilibili', 'phone', 'email', 'qq', 'wechat', 'weibo',
                'telegram', 'youtube', 'twitter', 'xiaohongshu', 'douyin', 'other'
            ]

            new_contact_info = {}
            for field in contact_fields:
                value = request.form.get(field, '').strip()
                if value:
                    new_contact_info[field] = value

            if not new_contact_info:
                flash('请至少填写一种联系方式', 'error')
                return redirect(url_for('user_profile'))

            if new_username != user.username:
                if User.query.filter_by(username=new_username).first():
                    flash('用户名已被使用', 'error')
                    return redirect(url_for('user_profile'))
                user.username = new_username

            all_users = User.query.filter(User.id != user.id).all()
            for other_user in all_users:
                if other_user.contact_info:
                    try:
                        existing_contacts = json.loads(other_user.contact_info)
                        for key, value in new_contact_info.items():
                            if key in existing_contacts and existing_contacts[key] == value:
                                flash(f'联系方式 {key}: {value} 已被其他用户使用', 'error')
                                return redirect(url_for('user_profile'))
                    except:
                        continue

            user.signature = signature
            user.contact_info = json.dumps(new_contact_info, ensure_ascii=False)
            user.age = int(age) if age else None
            user.gender = gender or None
            
            # 设置生日
            if birthday:
                try:
                    user.birthday = datetime.strptime(birthday, '%Y-%m-%d').date()
                except ValueError:
                    pass  # 如果日期格式不正确，忽略它

            db.session.commit()
            flash('个人信息已更新')
            return redirect(url_for('user_profile'))
        else:
            # 处理密码修改
            old_password = request.form.get('old_password')
            new_password = request.form.get('new_password')
            confirm_password = request.form.get('confirm_password')

            # 验证新密码
            if new_password != confirm_password:
                flash('新密码和确认密码不匹配', 'error')
                return redirect(url_for('user_profile'))

            if not validate_password(new_password):
                flash('密码必须包含字母和数字，不少于6位', 'error')
                return redirect(url_for('user_profile'))

            # 更新Firebase中的密码
            try:
                firebase_user = auth.get_user(user.firebase_uid)
                if firebase_user.email:
                    # 通过邮箱更新密码
                    auth.update_user(user.firebase_uid, password=new_password)
                else:
                    # 通过手机号更新密码（这在Firebase中比较复杂，简化处理）
                    flash('手机号用户请通过Firebase控制台重置密码', 'error')
                    return redirect(url_for('user_profile'))
            except Exception as e:
                logger.error(f"更新Firebase密码失败: {e}")
                flash('密码更新失败，请稍后再试', 'error')
                return redirect(url_for('user_profile'))

            flash('密码修改成功')
            return redirect(url_for('user_profile'))

    return render_template('user_profile.html', user=user, contact_info=contact_info)


@app.route('/admin')
@login_required
@check_banned
def admin_panel():
    try:
        current_user = db.session.get(User, session['user_id'])
        
        if current_user.role == 'master':
            users = User.query.all()
            posts = Post.query.all()
            reports = Report.query.filter_by(status='pending').all()
            invite_codes = InviteCode.query.all()
            used_invite_codes = InviteCode.query.filter(InviteCode.used_at.isnot(None)).all()
        else:
            users = User.query.all()
            posts = Post.query.all()
            reports = Report.query.filter_by(status='pending').all()
            invite_codes = []
            used_invite_codes = []
        
        return render_template('admin_panel.html',
                               users=users,
                               posts=posts,
                               reports=reports,
                               invite_codes=invite_codes,
                               used_invite_codes=used_invite_codes)
    except Exception as e:
        logger.error(f"管理员面板错误: {e}")
        flash("加载管理员面板时发生错误", "error")
        return redirect(url_for('home'))


@app.route('/admin/invite_code/add', methods=['POST'])
@login_required
@check_banned
def add_invite_code():
    try:
        current_user = db.session.get(User, session['user_id'])

        if current_user.role != 'master':
            flash('权限不足')
            return redirect(url_for('admin_panel'))

        code = request.form.get('code')
        if code:
            if InviteCode.query.filter_by(code=code).first():
                flash('邀请码已存在')
            else:
                invite_code = InviteCode(code=code)
                db.session.add(invite_code)
                db.session.commit()
                flash('邀请码添加成功')
        else:
            flash('请输入有效的邀请码')

        return redirect(url_for('admin_panel'))
    except Exception as e:
        logger.error(f"添加邀请码错误: {e}")
        db.session.rollback()
        flash("添加邀请码时发生错误", "error")
        return redirect(url_for('admin_panel'))


@app.route('/admin/invite_code/delete/<int:code_id>', methods=['POST'])
@login_required
@check_banned
def delete_invite_code(code_id):
    try:
        current_user = db.session.get(User, session['user_id'])

        if current_user.role != 'master':
            flash('权限不足')
            return redirect(url_for('admin_panel'))

        invite_code = InviteCode.query.get_or_404(code_id)
        db.session.delete(invite_code)
        db.session.commit()
        flash('邀请码已删除')

        return redirect(url_for('admin_panel'))
    except Exception as e:
        logger.error(f"删除邀请码错误: {e}")
        db.session.rollback()
        flash("删除邀请码时发生错误", "error")
        return redirect(url_for('admin_panel'))


@app.route('/admin/user/<int:user_id>/toggle_ban', methods=['POST'])
@admin_required
@check_banned
def toggle_user_ban(user_id):
    try:
        user = User.query.get_or_404(user_id)
        if user.id == session['user_id']:
            flash('不能封禁自己')
            return redirect(url_for('admin_panel'))

        user.is_banned = not user.is_banned
        db.session.commit()

        action = "封禁" if user.is_banned else "解封"
        flash(f'用户 {user.username} 已被{action}')
        return redirect(url_for('admin_panel'))
    except Exception as e:
        logger.error(f"切换用户封禁状态错误: {e}")
        db.session.rollback()
        flash("操作失败，请重试", "error")
        return redirect(url_for('admin_panel'))


@app.route('/admin/user/<int:user_id>/toggle_mute', methods=['POST'])
@admin_required
@check_banned
def toggle_user_mute(user_id):
    try:
        user = User.query.get_or_404(user_id)
        if user.id == session['user_id']:
            flash('不能禁言自己')
            return redirect(url_for('admin_panel'))

        user.is_muted = not user.is_muted
        db.session.commit()

        action = "禁言" if user.is_muted else "解除禁言"
        flash(f'用户 {user.username} 已被{action}')
        return redirect(url_for('admin_panel'))
    except Exception as e:
        logger.error(f"切换用户禁言状态错误: {e}")
        db.session.rollback()
        flash("操作失败，请重试", "error")
        return redirect(url_for('admin_panel'))


@app.route('/admin/user/<int:user_id>/delete', methods=['POST'])
@admin_required
@check_banned
def delete_user(user_id):
    try:
        user = User.query.get_or_404(user_id)
        if user.id == session['user_id']:
            flash('不能删除自己')
            return redirect(url_for('admin_panel'))

        Post.query.filter_by(author_id=user.id).delete()
        Comment.query.filter_by(author_id=user.id).delete()

        db.session.delete(user)
        db.session.commit()

        flash(f'用户 {user.username} 已被删除')
        return redirect(url_for('admin_panel'))
    except Exception as e:
        logger.error(f"删除用户错误: {e}")
        db.session.rollback()
        flash("删除用户失败，请重试", "error")
        return redirect(url_for('admin_panel'))


@app.route('/admin/user/<int:user_id>/toggle_admin', methods=['POST'])
@admin_required
@check_banned
def toggle_admin(user_id):
    try:
        user = User.query.get_or_404(user_id)
        if user.id == session['user_id']:
            flash('不能操作自己的权限')
            return redirect(url_for('admin_panel'))

        current_user = db.session.get(User, session['user_id'])
        if current_user.username != 'LCM_MC' and user.role in ['admin', 'master']:
            flash('您没有权限操作管理员')
            return redirect(url_for('admin_panel'))

        if user.role == 'admin':
            user.role = 'user'
            flash(f'用户 {user.username} 的管理员权限已被撤销')
        else:
            user.role = 'admin'
            flash(f'用户 {user.username} 已被授予管理员权限')

        db.session.commit()
        return redirect(url_for('admin_panel'))
    except Exception as e:
        logger.error(f"切换管理员权限错误: {e}")
        db.session.rollback()
        flash("操作失败，请重试", "error")
        return redirect(url_for('admin_panel'))


@app.route('/report', methods=['POST'])
@login_required
@check_banned
def report():
    try:
        reporter_id = session['user_id']
        post_id = request.form.get('post_id')
        comment_id = request.form.get('comment_id')
        reason = request.form.get('reason')

        if not reason:
            flash('请填写举报原因')
            return redirect(request.referrer or url_for('home'))

        report = Report(
            reporter_id=reporter_id,
            post_id=post_id if post_id else None,
            comment_id=comment_id if comment_id else None,
            reason=reason
        )

        db.session.add(report)
        db.session.commit()
        flash('举报已提交，管理员会尽快处理')
        return redirect(request.referrer or url_for('home'))
    except Exception as e:
        logger.error(f"提交举报错误: {e}")
        db.session.rollback()
        flash("提交举报失败，请重试", "error")
        return redirect(request.referrer or url_for('home'))


@app.route('/admin/report/<int:report_id>/<action>', methods=['POST'])
@admin_required
@check_banned
def handle_report(report_id, action):
    try:
        report = Report.query.get_or_404(report_id)

        current_user = db.session.get(User, session['user_id'])
        if current_user.role not in ['admin', 'master'] or (
                current_user.role == 'admin' and report.post and report.post.author.role == 'master'):
            flash('您没有权限处理此举报')
            return redirect(url_for('admin_panel'))

        if action == 'resolve':
            report.status = 'resolved'
            flash('举报已处理')
        elif action == 'dismiss':
            report.status = 'dismissed'
            flash('举报已驳回')

        db.session.commit()
        return redirect(url_for('admin_panel'))
    except Exception as e:
        logger.error(f"处理举报错误: {e}")
        db.session.rollback()
        flash("处理举报失败，请重试", "error")
        return redirect(url_for('admin_panel'))


@app.route('/admin/update_log', methods=['POST'])
@admin_required
@check_banned
def add_update_log():
    try:
        current_user = db.session.get(User, session['user_id'])
        if current_user.username != 'LCM_MC':
            flash('只有站长可以发布更新日志')
            return redirect(url_for('admin_panel'))

        title = request.form.get('title', '系统更新')
        content = request.form.get('content')

        if not content:
            flash('请输入更新内容')
            return redirect(url_for('admin_panel'))

        update_log = Post(
            title=title,
            content=content,
            author_id=current_user.id,
            is_update_log=True
        )

        db.session.add(update_log)
        db.session.commit()
        flash('更新日志已发布')
        return redirect(url_for('admin_panel'))
    except Exception as e:
        logger.error(f"发布更新日志错误: {e}")
        db.session.rollback()
        flash("发布更新日志失败，请重试", "error")
        return redirect(url_for('admin_panel'))


@app.route('/mark_update_log_read/<int:post_id>')
def mark_update_log_read(post_id):
    response = make_response(redirect(request.referrer or url_for('home')))
    response.set_cookie(f'update_log_{post_id}_read', 'true', max_age=365 * 24 * 60 * 60)
    return response


@app.route('/post/<int:post_id>/comment', methods=['POST'])
@login_required
@check_banned
@check_muted
def add_comment(post_id):
    content = request.form['content']
    parent_id = request.form.get('parent_id', type=int)

    comment = Comment(
        content=content,
        post_id=post_id,
        author_id=session['user_id'],
        parent_id=parent_id
    )

    db.session.add(comment)
    db.session.commit()
    flash('评论发表成功')
    return redirect(url_for('post', post_id=post_id))


@app.route('/search')
@check_banned
def search():
    query = request.args.get('q', '')
    posts = []
    users = []

    if query:
        posts = Post.query.filter(
            db.or_(
                Post.title.contains(query),
                Post.content.contains(query)
            )
        ).order_by(Post.date_posted.desc()).all()

        users = User.query.filter(User.username.contains(query)).all()

    return render_template('search_results.html', query=query, posts=posts, users=users)


@app.route('/firebase-login', methods=['POST'])
def firebase_login():
    try:
        data = request.get_json()
        uid = data.get('uid')
        remember = data.get('remember', False)
        recaptcha_response = data.get('recaptcha')
        
        # Verify reCAPTCHA
        if recaptcha_response and recaptcha_response != 'GOOGLE_AUTH':
            recaptcha_secret = 'YOUR_RECAPTCHA_SECRET_KEY'  # You should store this in environment variables
            recaptcha_verification_url = 'https://www.google.com/recaptcha/api/siteverify'
            recaptcha_data = {
                'secret': recaptcha_secret,
                'response': recaptcha_response
            }
            
            recaptcha_result = requests.post(recaptcha_verification_url, data=recaptcha_data)
            recaptcha_result_json = recaptcha_result.json()
            
            if not recaptcha_result_json.get('success'):
                return "reCAPTCHA 验证失败，请重试", 400
        
        # 查找本地数据库中的用户
        user = User.query.filter_by(firebase_uid=uid).first()
        if not user:
            # 用户在本地数据库中不存在
            return "用户不存在，请先注册", 400
        
        # 登录用户
        session['user_id'] = user.id
        session['username'] = user.username
        session['role'] = user.role
        
        # 记录登录IP
        user.last_login_ip = request.environ.get('HTTP_X_REAL_IP', request.remote_addr)
        db.session.commit()
        
        # 记住我功能
        if remember:
            session.permanent = True
        
        # 设置主题cookie
        response = make_response(redirect(url_for('home')))
        response.set_cookie('theme', user.theme_preference, max_age=30*24*60*60)
        return response
    except Exception as e:
        logger.error(f"Firebase登录错误: {e}")
        db.session.rollback()
        return "登录失败，请重试", 500


@app.route('/firebase-register', methods=['POST'])
def firebase_register():
    try:
        data = request.get_json()
        uid = data.get('uid')
        username = data.get('username')
        identifier = data.get('identifier')
        password = data.get('password')
        age = data.get('age')
        gender = data.get('gender')
        birthday = data.get('birthday')
        contact_info = data.get('contact_info', {})
        recaptcha_response = data.get('recaptcha')
        
        # Verify reCAPTCHA (except for Google auth)
        if recaptcha_response and recaptcha_response != 'GOOGLE_AUTH':
            recaptcha_secret = 'YOUR_RECAPTCHA_SECRET_KEY'  # You should store this in environment variables
            recaptcha_verification_url = 'https://www.google.com/recaptcha/api/siteverify'
            recaptcha_data = {
                'secret': recaptcha_secret,
                'response': recaptcha_response
            }
            
            recaptcha_result = requests.post(recaptcha_verification_url, data=recaptcha_data)
            recaptcha_result_json = recaptcha_result.json()
            
            if not recaptcha_result_json.get('success'):
                return "reCAPTCHA 验证失败，请重试", 400
        
        # 验证必填字段
        if not username or not identifier:
            return "请填写所有必填字段", 400
        
        # 验证密码强度（除非是Google认证）
        if recaptcha_response != 'GOOGLE_AUTH':
            if not validate_password(password):
                return "密码必须包含字母和数字，不少于6位", 400
        
        # 检查用户名是否已存在
        if User.query.filter_by(username=username).first():
            return "用户名已存在", 400
        
        # 检查联系方式是否已被其他用户使用
        all_users = User.query.all()
        for user in all_users:
            if user.contact_info:
                try:
                    existing_contacts = json.loads(user.contact_info)
                    for key, value in contact_info.items():
                        if key in existing_contacts and existing_contacts[key] == value:
                            return f'联系方式 {key}: {value} 已被其他用户使用', 400
                except:
                    # 如果解析失败，跳过该用户
                    continue
        
        # 创建新用户
        user = User(
            firebase_uid=uid,
            username=username,
            contact_info=json.dumps(contact_info, ensure_ascii=False),
            age=age,
            gender=gender
        )
        
        # 设置生日
        if birthday:
            try:
                user.birthday = datetime.strptime(birthday, '%Y-%m-%d').date()
            except ValueError:
                pass  # 如果日期格式不正确，忽略它
        
        db.session.add(user)
        db.session.commit()
        
        # 默认关注站长
        master = User.query.filter_by(role='master').first()
        if master:
            friendship = Friendship(follower_id=user.id, followed_id=master.id)
            db.session.add(friendship)
            db.session.commit()
        
        return "注册成功", 200
    except Exception as e:
        logger.error(f"Firebase注册错误: {e}")
        db.session.rollback()
        return "注册过程中发生错误，请稍后再试", 500


@app.route('/fallback-register', methods=['POST'])
def fallback_register():
    try:
        data = request.get_json()
        username = data.get('username')
        identifier = data.get('identifier')
        password = data.get('password')
        age = data.get('age')
        gender = data.get('gender')
        birthday = data.get('birthday')
        contact_info = data.get('contact_info', {})
        recaptcha_response = data.get('recaptcha')
        
        # Verify reCAPTCHA
        if recaptcha_response:
            recaptcha_secret = 'YOUR_RECAPTCHA_SECRET_KEY'  # You should store this in environment variables
            recaptcha_verification_url = 'https://www.google.com/recaptcha/api/siteverify'
            recaptcha_data = {
                'secret': recaptcha_secret,
                'response': recaptcha_response
            }
            
            recaptcha_result = requests.post(recaptcha_verification_url, data=recaptcha_data)
            recaptcha_result_json = recaptcha_result.json()
            
            if not recaptcha_result_json.get('success'):
                return "reCAPTCHA 验证失败，请重试", 400
        
        # 验证必填字段
        if not username or not identifier:
            return "请填写所有必填字段", 400
        
        # 验证密码强度
        if not validate_password(password):
            return "密码必须包含字母和数字，不少于6位", 400
        
        # 检查用户名是否已存在
        if User.query.filter_by(username=username).first():
            return "用户名已存在", 400
        
        # 检查联系方式是否已被其他用户使用
        all_users = User.query.all()
        for user in all_users:
            if user.contact_info:
                try:
                    existing_contacts = json.loads(user.contact_info)
                    for key, value in contact_info.items():
                        if key in existing_contacts and existing_contacts[key] == value:
                            return f'联系方式 {key}: {value} 已被其他用户使用', 400
                except:
                    # 如果解析失败，跳过该用户
                    continue
        
        # 生成一个模拟的 Firebase UID
        firebase_uid = "fallback_" + str(int(datetime.timestamp(datetime.now()))) + "_" + str(hash(username) % 10000)
        
        # 创建新用户
        user = User(
            firebase_uid=firebase_uid,
            username=username,
            contact_info=json.dumps(contact_info, ensure_ascii=False),
            age=age,
            gender=gender
        )
        
        # 设置生日
        if birthday:
            try:
                user.birthday = datetime.strptime(birthday, '%Y-%m-%d').date()
            except ValueError:
                pass  # 如果日期格式不正确，忽略它
        
        db.session.add(user)
        db.session.commit()
        
        # 默认关注站长
        master = User.query.filter_by(role='master').first()
        if master:
            friendship = Friendship(follower_id=user.id, followed_id=master.id)
            db.session.add(friendship)
            db.session.commit()
        
        return "注册成功", 200
    except Exception as e:
        logger.error(f"备用注册错误: {e}")
        db.session.rollback()
        return "注册过程中发生错误，请稍后再试", 500


@app.route('/reset-password', methods=['GET', 'POST'])
def reset_password():
    return render_template('reset_password.html')


def validate_password(password):
    """验证密码强度"""
    if len(password) < 6:
        return False
    if not any(c.isalpha() for c in password):
        return False
    if not any(c.isdigit() for c in password):
        return False
    return True


def check_birthday():
    """检查是否有用户今天过生日，如果有则自动发布生日祝福文章"""
    try:
        today = datetime.today().date()
        users_with_birthday = User.query.filter(
            db.func.strftime('%m-%d', User.birthday) == today.strftime('%m-%d')
        ).all()
        
        for user in users_with_birthday:
            # 检查是否已经发布了今天的生日祝福文章
            existing_post = Post.query.filter(
                Post.title == f'祝{user.username}生日快乐!',
                db.func.date(Post.date_posted) == today
            ).first()
            
            if not existing_post:
                # 创建生日祝福文章
                birthday_post = Post(
                    title=f'祝{user.username}生日快乐!',
                    content=f'今天是{today.strftime("%Y年%m月%d日")}，让我们祝{user.username}生日快乐！',
                    author_id=user.id,
                    is_update_log=False
                )
                db.session.add(birthday_post)
        
        db.session.commit()
    except Exception as e:
        logger.error(f"检查生日失败: {e}")
        db.session.rollback()


def create_error_templates():
    error_dir = os.path.join(os.path.dirname(__file__), 'templates')
    if not os.path.exists(error_dir):
        os.makedirs(error_dir)

    not_found_content = '''
<!DOCTYPE html>
<html>
<head>
    <title>页面未找到</title>
    <style>
        body { font-family: Arial, sans-serif; text-align: center; margin-top: 50px; }
        .error-container { max-width: 600px; margin: 0 auto; }
        .error-code { font-size: 72px; color: #ff6b6b; margin-bottom: 20px; }
        .error-message { font-size: 24px; margin-bottom: 30px; }
        .back-link { 
            display: inline-block; 
            padding: 10px 20px; 
            background-color: #007bff; 
            color: white; 
            text-decoration: none; 
            border-radius: 5px;
        }
    </style>
</head>
<body>
    <div class="error-container">
        <div class="error-code">404</div>
        <div class="error-message">抱歉，您访问的页面不存在</div>
        <a href="/" class="back-link">返回首页</a>
    </div>
</body>
</html>
    '''

    not_found_path = os.path.join(error_dir, '404.html')
    if not os.path.exists(not_found_path):
        with open(not_found_path, 'w', encoding='utf-8') as f:
            f.write(not_found_content)

    error_content = '''
<!DOCTYPE html>
<html>
<head>
    <title>服务器内部错误</title>
    <style>
        body { font-family: Arial, sans-serif; text-align: center; margin-top: 50px; }
        .error-container { max-width: 600px; margin: 0 auto; }
        .error-code { font-size: 72px; color: #ff6b6b; margin-bottom: 20px; }
        .error-message { font-size: 24px; margin-bottom: 30px; }
        .back-link { 
            display: inline-block; 
            padding: 10px 20px; 
            background-color: #007bff; 
            color: white; 
            text-decoration: none; 
            border-radius: 5px;
        }
    </style>
</head>
<body>
    <div class="error-container">
        <div class="error-code">500</div>
        <div class="error-message">抱歉，服务器遇到了错误</div>
        <a href="/" class="back-link">返回首页</a>
    </div>
</body>
</html>
    '''

    error_path = os.path.join(error_dir, '500.html')
    if not os.path.exists(error_path):
        with open(error_path, 'w', encoding='utf-8') as f:
            f.write(error_content)

    banned_content = '''
<!DOCTYPE html>
<html>
<head>
    <title>用户已被封禁</title>
    <style>
        body { font-family: Arial, sans-serif; text-align: center; margin-top: 50px; }
        .error-container { max-width: 600px; margin: 0 auto; }
        .error-code { font-size: 72px; color: #ff6b6b; margin-bottom: 20px; }
        .error-message { font-size: 24px; margin-bottom: 30px; }
        .back-link { 
            display: inline-block; 
            padding: 10px 20px; 
            background-color: #007bff; 
            color: white; 
            text-decoration: none; 
            border-radius: 5px;
        }
    </style>
</head>
<body>
    <div class="error-container">
        <div class="error-code">禁止访问</div>
        <div class="error-message">您的账户已被封禁</div>
        <a href="/" class="back-link">返回首页</a>
    </div>
</body>
</html>
    '''

    banned_path = os.path.join(error_dir, 'banned.html')
    if not os.path.exists(banned_path):
        with open(banned_path, 'w', encoding='utf-8') as f:
            f.write(banned_content)


if __name__ == '__main__':
    with app.app_context():
        try:
            logger.debug("开始初始化数据库")
            db.create_all()

            inspector = sqlalchemy.inspect(db.engine)
            table_names = inspector.get_table_names()

            if 'user' in table_names:
                columns = [col['name'] for col in inspector.get_columns('user')]
                if 'theme_preference' not in columns:
                    try:
                        with db.engine.connect() as conn:
                            conn.execute(sqlalchemy.text(
                                'ALTER TABLE user ADD COLUMN theme_preference VARCHAR(10) DEFAULT "light"'))
                            conn.commit()
                        logger.debug("向user表添加theme_preference列")
                    except Exception as e:
                        logger.error(f"添加theme_preference列失败: {e}")

                user_columns_to_add = [
                    ('signature', 'VARCHAR(200) DEFAULT ""'),
                    ('avatar_url', 'VARCHAR(200) DEFAULT ""'),
                    ('last_login_ip', 'VARCHAR(45) DEFAULT ""'),
                    ('contact_info', 'VARCHAR(500) DEFAULT ""'),
                    ('age', 'INTEGER'),
                    ('gender', 'VARCHAR(10)'),
                    ('birthday', 'DATE')
                ]

                for col_name, col_def in user_columns_to_add:
                    if col_name not in columns:
                        try:
                            with db.engine.connect() as conn:
                                conn.execute(sqlalchemy.text(f'ALTER TABLE user ADD COLUMN {col_name} {col_def}'))
                                conn.commit()
                            logger.debug(f"向user表添加{col_name}列")
                        except Exception as e:
                            logger.error(f"添加{col_name}列失败: {e}")

            if 'post' in table_names:
                columns = [col['name'] for col in inspector.get_columns('post')]
                if 'is_update_log' not in columns:
                    try:
                        with db.engine.connect() as conn:
                            conn.execute(sqlalchemy.text('ALTER TABLE post ADD COLUMN is_update_log BOOLEAN DEFAULT 0'))
                            conn.commit()
                        logger.debug("向post表添加is_update_log列")
                    except Exception as e:
                        logger.error(f"添加is_update_log列失败: {e}")

            if 'comment' in table_names:
                columns = [col['name'] for col in inspector.get_columns('comment')]
                comment_columns_to_add = [
                    ('parent_id', 'INTEGER REFERENCES comment(id)')
                ]

                for col_name, col_def in comment_columns_to_add:
                    if col_name not in columns:
                        try:
                            with db.engine.connect() as conn:
                                conn.execute(sqlalchemy.text(f'ALTER TABLE comment ADD COLUMN {col_name} {col_def}'))
                                conn.commit()
                            logger.debug(f"向comment表添加{col_name}列")
                        except Exception as e:
                            logger.error(f"添加{col_name}列失败: {e}")

            # 检查并创建站长账户（如果不存在）
            master_user = User.query.filter_by(firebase_uid='rF8fQByTfdazOWZQNcaNYmlPK7h2').first()
            if not master_user:
                master = User(
                    firebase_uid='rF8fQByTfdazOWZQNcaNYmlPK7h2',
                    username='LCM_MC',
                    role='master',
                    theme_preference='dark'
                )
                db.session.add(master)
                db.session.commit()
                print("创建默认站长账户成功")
            else:
                # 确保现有站长用户具有站长角色
                if master_user.role != 'master':
                    master_user.role = 'master'
                    db.session.commit()
                print("站长账户已存在")

            master = User.query.filter_by(firebase_uid='rF8fQByTfdazOWZQNcaNYmlPK7h2').first()
            print(f"LCM_MC用户存在: {master is not None}")
            print(f"LCM_MC用户角色: {getattr(master, 'role', None)}")

        except Exception as e:
            logger.error(f"数据库初始化失败: {e}")

    mode = input("选择运行模式:\n1.部署运行(port=80,debug=false)\n2.测试运行(port=8080,debug=true)")
    if mode == '1':
        try:
            app.run(host='0.0.0.0', port=80, debug=False)
            logger.info("启动成功")
            logger.info(f"访问地址: http://{get_ip()}:80")
        except:
            logger.error('启动失败，尝试使用测试模式运行...')
            app.run(host='0.0.0.0', port=8080, debug=True)
    elif mode == '2':
        try:
            app.run(host='0.0.0.0', port=8080, debug=True)
            logger.info("启动成功")
            logger.info(f"访问地址: http://{get_ip()}:8080")
        except:
            logger.error('启动失败，请检查端口是否被占用')
    else:
        logger.error('请选择正确的模式')