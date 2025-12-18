import os
import sqlite3
from flask_sqlalchemy import SQLAlchemy
from contextlib import contextmanager
from app import User, Post, Comment, Report, Friendship, PrivateMessage, InviteCode, db, app
import logging

# 设置日志记录
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# 原始数据库路径
ORIGINAL_DB_PATH = 'blog.db'

# 新数据库路径
NEW_DATABASE_BINDS = {
    'users': 'sqlite:///users.db',
    'posts': 'sqlite:///posts.db',
    'comments': 'sqlite:///comments.db',
    'reports': 'sqlite:///reports.db',
    'friendships': 'sqlite:///friendships.db',
    'messages': 'sqlite:///messages.db',
    'invites': 'sqlite:///invites.db'
}

# 数据迁移函数
def migrate_data():
    # 连接到原始数据库
    if not os.path.exists(ORIGINAL_DB_PATH):
        logger.error(f"原始数据库文件 {ORIGINAL_DB_PATH} 不存在")
        return

    original_conn = sqlite3.connect(ORIGINAL_DB_PATH)
    original_cursor = original_conn.cursor()

    # 检查 user 表是否存在
    original_cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='user';")
    if not original_cursor.fetchone():
        logger.error(f"原始数据库 {ORIGINAL_DB_PATH} 中没有 user 表")
        original_conn.close()
        return

    # 迁移用户数据
    try:
        users = original_cursor.execute("SELECT * FROM user").fetchall()
        for user in users:
            existing_user = User.query.filter_by(id=user[0]).first()
            if not existing_user:
                new_user = User(
                    id=user[0],
                    username=user[1],
                    password=user[2],
                    role=user[3],
                    is_banned=user[4],
                    is_muted=user[5],
                    theme_preference=user[6],
                    created_at=user[7],
                    signature=user[8],
                    avatar_url=user[9],
                    last_login_ip=user[10],
                    contact_info=user[11]
                )
                db.session.add(new_user)
            else:
                existing_user.password = user[2]
                existing_user.role = user[3]
                existing_user.is_banned = user[4]
                existing_user.is_muted = user[5]
                existing_user.theme_preference = user[6]
                existing_user.created_at = user[7]
                existing_user.signature = user[8]
                existing_user.avatar_url = user[9]
                existing_user.last_login_ip = user[10]
                existing_user.contact_info = user[11]

        # 提交事务
        db.session.commit()
        logger.info("用户数据迁移成功")
    except Exception as e:
        logger.error(f"用户数据迁移失败: {e}")
        db.session.rollback()

    # 迁移其他数据
    for table, model in [
        ('post', Post),
        ('comment', Comment),
        ('report', Report),
        ('friendship', Friendship),
        ('private_message', PrivateMessage),
        ('invite_code', InviteCode)
    ]:
        try:
            data = original_cursor.execute(f"SELECT * FROM {table}").fetchall()
            for row in data:
                existing_record = model.query.filter_by(id=row[0]).first()
                if not existing_record:
                    new_record = model(*row)
                    db.session.add(new_record)
                else:
                    # 更新现有记录
                    for i, col in enumerate(model.__table__.columns):
                        setattr(existing_record, col.name, row[i])

            # 提交事务
            db.session.commit()
            logger.info(f"{table} 数据迁移成功")
        except Exception as e:
            logger.error(f"{table} 数据迁移失败: {e}")
            db.session.rollback()

    # 关闭连接
    original_conn.close()

if __name__ == '__main__':
    with app.app_context():  # 确保在 app 上下文中运行
        migrate_data()
