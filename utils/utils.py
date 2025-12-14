
import os
import zipfile
import base64
import json
import io
import shutil

class FileUtils:
    @staticmethod
    def zip_directory(dir_path: str) -> str:
        """
        Compress the entire directory into a zip file in memory and return base64 string.
        Excludes __pycache__ and git files.
        """
        bio = io.BytesIO()
        abs_src = os.path.abspath(dir_path)
        with zipfile.ZipFile(bio, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(dir_path):
                # Filter dirs
                dirs[:] = [d for d in dirs if d not in ('__pycache__', '.git', '.vscode')]
                
                for file in files:
                    if file.endswith('.pyc') or file == '.DS_Store':
                        continue
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, abs_src)
                    
                    # Ensure arcname is safe and not empty
                    if not arcname or arcname == '.':
                        continue
                        
                    zipf.write(file_path, arcname)
        
        return base64.b64encode(bio.getvalue()).decode('utf-8')

    @staticmethod
    def unzip_data(base64_data: str, dest_dir: str) -> bool:
        """
        Decode base64 string and unzip content to destination directory.
        """
        try:
            zip_bytes = base64.b64decode(base64_data)
            bio = io.BytesIO(zip_bytes)
            
            if not os.path.exists(dest_dir):
                os.makedirs(dest_dir)
                
            with zipfile.ZipFile(bio, 'r') as zipf:
                # Security check: Prevent path traversal
                for member in zipf.infolist():
                    file_path = os.path.join(dest_dir, member.filename)
                    if not os.path.abspath(file_path).startswith(os.path.abspath(dest_dir)):
                        raise Exception(f"Path traversal attempt: {member.filename}")
                
                zipf.extractall(dest_dir)
            return True
        except Exception as e:
            print(f"Unzip error: {e}")
            return False

class ConfigValidator:
    REQUIRED_FIELDS = ['name', 'version', 'exe_cmd', 'min_players', 'max_players']
    
    @staticmethod
    def validate_game_config(config: dict) -> tuple[bool, str]:
        for field in ConfigValidator.REQUIRED_FIELDS:
            if field not in config:
                return False, f"Missing required field: {field}"
        
        if not isinstance(config['exe_cmd'], list) or not config['exe_cmd']:
            return False, "exe_cmd must be a non-empty list"
            
        try:
            min_p = int(config['min_players'])
            max_p = int(config['max_players'])
            if min_p < 1 or max_p < min_p:
                return False, "Invalid player count range"
        except ValueError:
            return False, "Player counts must be integers"
            
        return True, ""
