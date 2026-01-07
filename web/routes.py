from functools import wraps
from flask import session, request, render_template, redirect, url_for, flash
import logging
import time

logger = logging.getLogger(__name__)

# Session timeout in seconds (30 minutes)
SESSION_TIMEOUT = 30 * 60

def admin_required(f):
    """Decorator to check if user is authenticated as admin"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        from bot import r, ADMINS
        
        # Check if session has logged-in admin
        if session.get('admin_id'):
            # Check session timeout
            last_activity = session.get('last_activity', 0)
            current_time = time.time()
            
            if current_time - last_activity > SESSION_TIMEOUT:
                # Session expired
                expired_admin_id = session.get('admin_id')
                session.clear()
                logger.info(f"Session expired for admin {expired_admin_id}")
                return "⏱️ 会话已过期，请通过机器人 /admin 命令重新获取链接", 403
            
            # Update last activity time
            session['last_activity'] = current_time
            return f(*args, **kwargs)
        
        # Check token in URL
        token = request.args.get('token')
        if token and r:
            try:
                user_id = r.get(f"admin_token:{token}")
                if user_id:
                    user_id = int(user_id)
                    if user_id in ADMINS:
                        # Set session
                        session['admin_id'] = user_id
                        session['last_activity'] = time.time()
                        # Delete used token
                        r.delete(f"admin_token:{token}")
                        logger.info(f"Admin {user_id} logged in via token")
                        return f(*args, **kwargs)
            except Exception as e:
                logger.error(f"Error validating token: {e}")
        
        # Authentication failed
        return "⛔ 无权访问，请通过机器人 /admin 命令获取链接", 403
    
    return decorated_function

def init_routes(app):
    """Initialize all admin routes"""
    from bot import SYNC_GROUPS, REQUIRED_CHANNELS, ADMINS, OWNER_ID, save_sync_groups, save_channels, save_admins, app_tg
    
    @app.route('/admin')
    @admin_required
    def admin_dashboard():
        """Admin dashboard"""
        stats = {
            'groups': len(SYNC_GROUPS),
            'channels': len(REQUIRED_CHANNELS),
            'admins': len(ADMINS)
        }
        return render_template('dashboard.html', 
                             stats=stats, 
                             admin_id=session.get('admin_id'))
    
    @app.route('/admin/groups')
    @admin_required
    def admin_groups():
        """Group management page"""
        message = session.pop('message', None)
        message_type = session.pop('message_type', None)
        return render_template('groups.html', 
                             groups=sorted(list(SYNC_GROUPS)),
                             message=message,
                             message_type=message_type)
    
    @app.route('/admin/groups/add', methods=['POST'])
    @admin_required
    def admin_groups_add():
        """Add a group"""
        group_id = request.form.get('group_id')
        try:
            group_id = int(group_id)
            if group_id in SYNC_GROUPS:
                session['message'] = f"群组 {group_id} 已存在！"
                session['message_type'] = 'warning'
            else:
                SYNC_GROUPS.add(group_id)
                save_sync_groups()
                session['message'] = f"✓ 已添加群组 {group_id}"
                session['message_type'] = 'success'
                logger.info(f"Admin {session.get('admin_id')} added group {group_id}")
        except ValueError:
            session['message'] = "❌ 无效的群组 ID 格式！"
            session['message_type'] = 'error'
        
        return redirect(url_for('admin_groups'))
    
    @app.route('/admin/groups/delete', methods=['POST'])
    @admin_required
    def admin_groups_delete():
        """Delete a group"""
        group_id = request.form.get('group_id')
        try:
            group_id = int(group_id)
            if group_id in SYNC_GROUPS:
                SYNC_GROUPS.remove(group_id)
                save_sync_groups()
                session['message'] = f"✓ 已删除群组 {group_id}"
                session['message_type'] = 'success'
                logger.info(f"Admin {session.get('admin_id')} deleted group {group_id}")
            else:
                session['message'] = "群组不存在！"
                session['message_type'] = 'warning'
        except ValueError:
            session['message'] = "❌ 无效的群组 ID！"
            session['message_type'] = 'error'
        
        return redirect(url_for('admin_groups'))
    
    @app.route('/admin/groups/addall', methods=['POST'])
    @admin_required
    def admin_groups_addall():
        """Add all groups (not recommended, use bot command instead)"""
        session['message'] = "⚠️ 此功能需要在机器人私聊中使用 /addall 命令执行"
        session['message_type'] = 'warning'
        return redirect(url_for('admin_groups'))
    
    @app.route('/admin/channels')
    @admin_required
    def admin_channels():
        """Channel management page"""
        message = session.pop('message', None)
        message_type = session.pop('message_type', None)
        return render_template('channels.html',
                             channels=REQUIRED_CHANNELS,
                             message=message,
                             message_type=message_type)
    
    @app.route('/admin/channels/add', methods=['POST'])
    @admin_required
    def admin_channels_add():
        """Add a channel"""
        channel = request.form.get('channel', '').strip()
        if not channel:
            session['message'] = "❌ 频道不能为空！"
            session['message_type'] = 'error'
        else:
            # Ensure @ prefix
            if not channel.startswith('@'):
                channel = '@' + channel
            
            if channel in REQUIRED_CHANNELS:
                session['message'] = f"频道 {channel} 已存在！"
                session['message_type'] = 'warning'
            else:
                REQUIRED_CHANNELS.append(channel)
                save_channels()
                session['message'] = f"✓ 已添加频道 {channel}"
                session['message_type'] = 'success'
                logger.info(f"Admin {session.get('admin_id')} added channel {channel}")
        
        return redirect(url_for('admin_channels'))
    
    @app.route('/admin/channels/delete', methods=['POST'])
    @admin_required
    def admin_channels_delete():
        """Delete a channel"""
        channel = request.form.get('channel')
        if channel in REQUIRED_CHANNELS:
            REQUIRED_CHANNELS.remove(channel)
            save_channels()
            session['message'] = f"✓ 已删除频道 {channel}"
            session['message_type'] = 'success'
            logger.info(f"Admin {session.get('admin_id')} deleted channel {channel}")
        else:
            session['message'] = "频道不存在！"
            session['message_type'] = 'warning'
        
        return redirect(url_for('admin_channels'))
    
    @app.route('/admin/channels/clear', methods=['POST'])
    @admin_required
    def admin_channels_clear():
        """Clear all channels"""
        REQUIRED_CHANNELS.clear()
        save_channels()
        session['message'] = "✓ 已清空所有频道"
        session['message_type'] = 'success'
        logger.info(f"Admin {session.get('admin_id')} cleared all channels")
        return redirect(url_for('admin_channels'))
    
    @app.route('/admin/admins')
    @admin_required
    def admin_admins():
        """Admin management page"""
        message = session.pop('message', None)
        message_type = session.pop('message_type', None)
        return render_template('admins.html',
                             admins=ADMINS,
                             owner_id=OWNER_ID,
                             message=message,
                             message_type=message_type)
    
    @app.route('/admin/admins/add', methods=['POST'])
    @admin_required
    def admin_admins_add():
        """Add an admin"""
        admin_input = request.form.get('admin_input', '').strip()
        
        if not admin_input:
            session['message'] = "❌ 输入不能为空！"
            session['message_type'] = 'error'
            return redirect(url_for('admin_admins'))
        
        try:
            # Check if it's a username or user ID
            if admin_input.startswith('@'):
                # Username - needs async operation, not supported in web interface
                session['message'] = "⚠️ 添加用户名需要在机器人私聊中使用 /addadmin @username 命令"
                session['message_type'] = 'warning'
            else:
                # User ID
                user_id = int(admin_input)
                if user_id in ADMINS:
                    session['message'] = f"用户 {user_id} 已经是管理员！"
                    session['message_type'] = 'warning'
                else:
                    ADMINS.append(user_id)
                    save_admins()
                    session['message'] = f"✓ 已添加管理员 {user_id}"
                    session['message_type'] = 'success'
                    logger.info(f"Admin {session.get('admin_id')} added admin {user_id}")
        except ValueError:
            session['message'] = "❌ 无效的用户 ID 格式！"
            session['message_type'] = 'error'
        
        return redirect(url_for('admin_admins'))
    
    @app.route('/admin/admins/delete', methods=['POST'])
    @admin_required
    def admin_admins_delete():
        """Delete an admin"""
        admin_id = request.form.get('admin_id')
        try:
            admin_id = int(admin_id)
            if admin_id == OWNER_ID:
                session['message'] = "❌ 不能删除 OWNER！"
                session['message_type'] = 'error'
            elif admin_id in ADMINS:
                ADMINS.remove(admin_id)
                save_admins()
                session['message'] = f"✓ 已删除管理员 {admin_id}"
                session['message_type'] = 'success'
                logger.info(f"Admin {session.get('admin_id')} deleted admin {admin_id}")
            else:
                session['message'] = "管理员不存在！"
                session['message_type'] = 'warning'
        except ValueError:
            session['message'] = "❌ 无效的管理员 ID！"
            session['message_type'] = 'error'
        
        return redirect(url_for('admin_admins'))
    
    @app.route('/admin/logout')
    @admin_required
    def admin_logout():
        """Logout"""
        admin_id = session.get('admin_id')
        session.clear()
        logger.info(f"Admin {admin_id} logged out")
        return "✓ 已退出登录，请关闭此页面", 200
