from cryptography.fernet import Fernet
import os
import logging

logger = logging.getLogger(__name__)

KEY_FILE = "data/secret.key"

def _load_or_create_key():
    if os.path.exists(KEY_FILE):
        with open(KEY_FILE, "rb") as f:
            return f.read()
    else:
        logger.warning("Generating new encryption key...")
        os.makedirs(os.path.dirname(KEY_FILE), exist_ok=True)
        key = Fernet.generate_key()
        with open(KEY_FILE, "wb") as f:
            f.write(key)
        return key

_key = _load_or_create_key()
_cipher = Fernet(_key)

def encrypt_password(password: str) -> str:
    if not password: return ""
    return _cipher.encrypt(password.encode()).decode()

def decrypt_password(encrypted_password: str) -> str:
    if not encrypted_password: return ""
    try:
        return _cipher.decrypt(encrypted_password.encode()).decode()
    except Exception as e:
        logger.error(f"Decryption failed: {e}")
        return encrypted_password # Return raw if fail (migration fallback?)
