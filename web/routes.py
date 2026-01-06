# web/routes.py
from flask import render_template, request, session, redirect, url_for
from functools import wraps
import os

# These will be set from bot.py
r = None  # Redis client
ADMINS = []
SYNC_GROUPS = set()
REQUIRED_CHANNELS = []
OWNER_ID = None
save_data = None
app_tg = None

def init_routes_context(redis_client, admins_list, sync_groups, required_channels, owner_id, save_func, telegram_app):
    """Initialize the context needed for routes"""
    global r, ADMINS, SYNC_GROUPS, REQUIRED_CHANNELS, OWNER_ID, save_data, app_tg
    r = redis_client
    ADMINS = admins_list
    SYNC_GROUPS = sync_groups
    REQUIRED_CHANNELS = required_channels
    OWNER_ID = owner_id
    save_data = save_func
    app_tg = telegram_app

def admin_required(f):
    """Decorator to require admin authentication"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Check if already logged in via session
        if session.get('admin_id'):
            return f(*args, **kwargs)
        
        # Check URL token
        token = request.args.get('token')
        if token and r:
            user_id_bytes = r.get(f"admin_token:{token}")
            if user_id_bytes:
                user_id = int(user_id_bytes.decode('utf-8'))
                if user_id in ADMINS:
                    # Set session
                    session['admin_id'] = user_id
                    # Delete used token
                    r.delete(f"admin_token:{token}")
                    return f(*args, **kwargs)
        
        # Authentication failed
        return "⛔ 无权访问，请通过机器人获取链接", 403
    return decorated_function

def setup_routes(app):
    """Setup all admin routes"""
    
    @app.route('/admin')
    @admin_required
    def admin_dashboard():
        """Admin dashboard"""
        stats = {
            'groups': len(SYNC_GROUPS),
            'channels': len(REQUIRED_CHANNELS),
            'admins': len(ADMINS)
        }
        recent_groups = list(SYNC_GROUPS)[:5]
        return render_template('dashboard.html', stats=stats, recent_groups=recent_groups)
    
    @app.route('/admin/groups')
    @admin_required
    def admin_groups():
        """Group management page"""
        groups = sorted(list(SYNC_GROUPS))
        return render_template('groups.html', groups=groups)
    
    @app.route('/admin/groups/add', methods=['POST'])
    @admin_required
    def add_group():
        """Add a group"""
        group_id = request.form.get('group_id')
        if group_id:
            try:
                group_id = int(group_id)
                SYNC_GROUPS.add(group_id)
                save_data()
            except ValueError:
                pass
        return redirect(url_for('admin_groups'))
    
    @app.route('/admin/groups/delete', methods=['POST'])
    @admin_required
    def delete_group():
        """Delete a group"""
        group_id = request.form.get('group_id')
        if group_id:
            try:
                group_id = int(group_id)
                SYNC_GROUPS.discard(group_id)
                save_data()
            except ValueError:
                pass
        return redirect(url_for('admin_groups'))
    
    @app.route('/admin/groups/addall', methods=['POST'])
    @admin_required
    def add_all_groups():
        """Add all groups - Note: This is a placeholder, actual functionality via bot command"""
        # Since we can't easily make async calls in Flask, users should use /addall command in bot
        # This just redirects back with no action
        # In a production setup, you could use task queues or other async mechanisms
        return redirect(url_for('admin_groups'))
    
    @app.route('/admin/channels')
    @admin_required
    def admin_channels():
        """Channel management page"""
        return render_template('channels.html', channels=REQUIRED_CHANNELS)
    
    @app.route('/admin/channels/add', methods=['POST'])
    @admin_required
    def add_channel():
        """Add a channel"""
        channel = request.form.get('channel', '').strip()
        if channel:
            # Ensure it starts with @
            if not channel.startswith('@'):
                channel = '@' + channel
            if channel not in REQUIRED_CHANNELS:
                REQUIRED_CHANNELS.append(channel)
                save_data()
        return redirect(url_for('admin_channels'))
    
    @app.route('/admin/channels/delete', methods=['POST'])
    @admin_required
    def delete_channel():
        """Delete a channel"""
        channel = request.form.get('channel')
        if channel and channel in REQUIRED_CHANNELS:
            REQUIRED_CHANNELS.remove(channel)
            save_data()
        return redirect(url_for('admin_channels'))
    
    @app.route('/admin/channels/clear', methods=['POST'])
    @admin_required
    def clear_channels():
        """Clear all channels"""
        REQUIRED_CHANNELS.clear()
        save_data()
        return redirect(url_for('admin_channels'))
    
    @app.route('/admin/admins')
    @admin_required
    def admin_admins():
        """Admin management page"""
        return render_template('admins.html', admins=ADMINS, owner_id=OWNER_ID)
    
    @app.route('/admin/admins/add', methods=['POST'])
    @admin_required
    def add_admin():
        """Add an admin"""
        user_id = request.form.get('user_id', '').strip()
        if user_id:
            try:
                # Check if it's @username format
                if user_id.startswith('@'):
                    # For now, just show error - would need async to resolve username
                    return redirect(url_for('admin_admins'))
                else:
                    user_id = int(user_id)
                    if user_id not in ADMINS:
                        ADMINS.append(user_id)
                        save_data()
            except ValueError:
                pass
        return redirect(url_for('admin_admins'))
    
    @app.route('/admin/admins/delete', methods=['POST'])
    @admin_required
    def delete_admin():
        """Delete an admin"""
        user_id = request.form.get('user_id')
        if user_id:
            try:
                user_id = int(user_id)
                if user_id != OWNER_ID and user_id in ADMINS:
                    ADMINS.remove(user_id)
                    save_data()
            except ValueError:
                pass
        return redirect(url_for('admin_admins'))
    
    @app.route('/admin/logout')
    def admin_logout():
        """Logout"""
        session.pop('admin_id', None)
        return "已退出登录。请通过机器人重新获取访问链接。", 200
