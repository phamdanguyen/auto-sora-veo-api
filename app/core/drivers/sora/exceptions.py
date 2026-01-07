class QuotaExhaustedException(Exception):
    """Raised when account has exhausted its video generation quota"""
    pass

class VerificationRequiredException(Exception):
    """Raised when account requires verification (checkpoint, 2FA, login challenge)"""
    pass

class LoginFailedException(Exception):
    """Raised when automation fails to login for other reasons"""
    pass
