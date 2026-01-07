from sqlalchemy.orm import Session
from sqlalchemy import func
from .. import models
import random
from typing import Optional, Set
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

# Track accounts currently being used by workers (in-memory)
_busy_accounts: Set[int] = set()


def get_available_account(db: Session, platform: str, exclude_ids: list[int] = None) -> Optional[models.Account]:
    """
    Get a 'live' account that is not currently busy.
    exclude_ids: Optional list of account IDs to ignore (e.g. recently failed).
    """
    query = db.query(models.Account).filter(
        models.Account.platform == platform,
        models.Account.status == "live"  # Only 'live' accounts, not 'quota_exhausted', 'die', etc.
    )

    if exclude_ids:
        query = query.filter(models.Account.id.notin_(exclude_ids))

    # Also exclude currently busy accounts
    if _busy_accounts:
        query = query.filter(models.Account.id.notin_(list(_busy_accounts)))

    accounts = query.all()

    if not accounts:
        return None

    # Prefer accounts that haven't been used recently
    accounts_sorted = sorted(accounts, key=lambda a: a.last_used or datetime.min)

    # Return the least recently used account
    return accounts_sorted[0]


def mark_account_busy(account_id: int):
    """Mark an account as currently in use"""
    _busy_accounts.add(account_id)
    logger.debug(f"Account #{account_id} marked as busy. Busy accounts: {_busy_accounts}")


def mark_account_free(account_id: int):
    """Mark an account as no longer in use"""
    _busy_accounts.discard(account_id)
    logger.debug(f"Account #{account_id} marked as free. Busy accounts: {_busy_accounts}")


def mark_account_quota_exhausted(db: Session, account: models.Account):
    """Mark an account as having exhausted its quota"""
    account.status = "quota_exhausted"
    account.last_used = datetime.utcnow()
    db.commit()
    logger.warning(f"Account #{account.id} ({account.email}) marked as quota_exhausted")


def mark_account_verification_needed(db: Session, account: models.Account):
    """Mark an account as requiring verification/checkpoint"""
    account.status = "checkpoint"
    account.last_used = datetime.utcnow()
    db.commit()
    logger.warning(f"Account #{account.id} ({account.email}) marked as checkpoint/verification_needed")



def reset_quota_exhausted_accounts(db: Session, hours: int = 24):
    """
    Reset accounts that have been quota_exhausted/cooldown for more than X hours.
    Sora typically resets free quota daily.
    """
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    # Handle both old "cooldown" status and new "quota_exhausted" status
    updated = db.query(models.Account).filter(
        models.Account.status.in_(["quota_exhausted", "cooldown"]),
        models.Account.last_used < cutoff
    ).update({"status": "live"}, synchronize_session=False)
    db.commit()
    if updated > 0:
        logger.info(f"Reset {updated} quota_exhausted/cooldown accounts back to live")
    return updated


def get_available_account_count(db: Session, platform: str) -> int:
    """Get count of available accounts"""
    count = db.query(func.count(models.Account.id)).filter(
        models.Account.platform == platform,
        models.Account.status == "live"
    ).scalar()

    # Subtract busy accounts
    return max(0, count - len(_busy_accounts))


def get_busy_account_ids() -> Set[int]:
    """Get the set of currently busy account IDs"""
    return _busy_accounts.copy()
