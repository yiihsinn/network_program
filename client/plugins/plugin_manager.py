#!/usr/bin/env python3
"""
Plugin Manager - 管理客戶端 Plugin 的安裝與狀態
每個用戶有獨立的 installed.json
"""

import os
import json
from datetime import datetime

class PluginManager:
    def __init__(self, plugins_dir=None, user_dir=None):
        if plugins_dir is None:
            plugins_dir = os.path.dirname(__file__)
        self.plugins_dir = plugins_dir
        self.available_path = os.path.join(plugins_dir, 'available.json')
        
        # User-specific installed.json (each user has their own)
        if user_dir:
            self.installed_path = os.path.join(user_dir, 'plugins_installed.json')
        else:
            # Fallback to global (for testing)
            self.installed_path = os.path.join(plugins_dir, 'installed.json')
        
    def get_available_plugins(self):
        """Get list of all available plugins"""
        try:
            with open(self.available_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return []
    
    def get_installed_plugins(self):
        """Get dict of installed plugins"""
        try:
            with open(self.installed_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    
    def _save_installed(self, installed):
        """Save installed plugins to file"""
        # Ensure directory exists
        os.makedirs(os.path.dirname(self.installed_path), exist_ok=True)
        with open(self.installed_path, 'w', encoding='utf-8') as f:
            json.dump(installed, f, indent=2)
    
    def is_installed(self, plugin_id):
        """Check if a plugin is installed"""
        installed = self.get_installed_plugins()
        return plugin_id in installed
    
    def get_plugin_info(self, plugin_id):
        """Get plugin info by ID"""
        for p in self.get_available_plugins():
            if p['id'] == plugin_id:
                return p
        return None
    
    def install(self, plugin_id):
        """Install a plugin"""
        plugin = self.get_plugin_info(plugin_id)
        if not plugin:
            return False, "Plugin not found"
        
        if self.is_installed(plugin_id):
            return False, "Already installed"
        
        installed = self.get_installed_plugins()
        installed[plugin_id] = {
            'version': plugin['version'],
            'installed_at': datetime.now().isoformat()
        }
        self._save_installed(installed)
        return True, "Installed successfully"
    
    def uninstall(self, plugin_id):
        """Uninstall a plugin"""
        if not self.is_installed(plugin_id):
            return False, "Not installed"
        
        installed = self.get_installed_plugins()
        del installed[plugin_id]
        self._save_installed(installed)
        return True, "Uninstalled successfully"
    
    def list_with_status(self):
        """Get all plugins with their install status"""
        available = self.get_available_plugins()
        installed = self.get_installed_plugins()
        
        result = []
        for p in available:
            status = 'installed' if p['id'] in installed else 'not_installed'
            result.append({
                **p,
                'status': status,
                'installed_version': installed.get(p['id'], {}).get('version')
            })
        return result


# Per-user manager cache
_managers = {}

def get_manager(user_dir=None):
    """Get plugin manager for specific user directory"""
    global _managers
    if user_dir not in _managers:
        _managers[user_dir] = PluginManager(user_dir=user_dir)
    return _managers[user_dir]
