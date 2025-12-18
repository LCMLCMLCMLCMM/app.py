from app import app, db, User

with app.app_context():
    db.create_all()

    # 创建默认管理员账户（如果不存在）
    if not User.query.filter_by(username='root').first():
        admin = User(username='root', password='@120818lcm', role='admin')
        db.session.add(admin)
        db.session.commit()
        print("创建默认管理员账户成功")
    else:
        print("默认管理员账户已存在")

    # 检查并创建站长账户（如果不存在）
    if not User.query.filter_by(username='LCM_MC').first():
        master = User(username='LCM_MC', password='master_password', role='master', theme_preference='dark')
        db.session.add(master)
        db.session.commit()
        print("创建默认站长账户成功")
    else:
        # 确保现有LCM_MC用户具有站长角色
        master_user = User.query.filter_by(username='LCM_MC').first()
        if master_user and master_user.role != 'master':
            master_user.role = 'master'
            db.session.commit()
        print("站长账户已存在")

    # 检查管理员账户信息
    user = User.query.filter_by(username='root').first()
    print(f"Root用户存在: {user is not None}")
    print(f"Root用户角色: {getattr(user, 'role', None)}")
    print(f"Root用户密码: {getattr(user, 'password', None)}")

    master = User.query.filter_by(username='LCM_MC').first()
    print(f"LCM_MC用户存在: {master is not None}")
    print(f"LCM_MC用户角色: {getattr(master, 'role', None)}")
    print(f"LCM_MC用户密码: {getattr(master, 'password', None)}")