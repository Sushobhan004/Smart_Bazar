import threading
import logging

logger = logging.getLogger(__name__)

_thread_locals = threading.local()

def set_current_shop_db(db_alias: str):
    """Sets the active tenant database alias for the current request thread."""
    _thread_locals.active_shop_db = db_alias

def get_current_shop_db() -> str:
    """Returns the active tenant database alias for the current request thread, or None."""
    return getattr(_thread_locals, 'active_shop_db', None)

def reset_current_shop_db():
    """Clears the active tenant database alias for the current request thread."""
    if hasattr(_thread_locals, 'active_shop_db'):
        del _thread_locals.active_shop_db

class ShopDatabaseRouter:
    """
    Router that routes Central administrative models to 'default' (SmartBazaar_Core)
    and routes all tenant-specific business models (Products, Inventory, Sales, Staff,
    Customers, Receipts) to the authenticated shop's dedicated database.
    """

    CENTRAL_MODELS = {
        'user',
        'shop',
        'shopmembership',
        'customerprofile',
        'customerconsent',
        'otpverification',
        'emaildeliverylog',
        'shopdatabasemapping',
        'auditlog',
        'securityevent',
        'contenttype',
        'session',
        'permission',
        'group',
        'logentry'
    }

    def db_for_read(self, model, **hints):
        model_name = model._meta.model_name.lower()
        if model_name in self.CENTRAL_MODELS:
            return 'default'

        active_db = get_current_shop_db()
        if active_db:
            return active_db
        return 'default'

    def db_for_write(self, model, **hints):
        model_name = model._meta.model_name.lower()
        if model_name in self.CENTRAL_MODELS:
            return 'default'

        active_db = get_current_shop_db()
        if active_db:
            return active_db
        return 'default'

    def allow_relation(self, obj1, obj2, **hints):
        # Allow relations between models across databases
        return True

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        return True
