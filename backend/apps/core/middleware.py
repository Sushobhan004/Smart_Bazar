import logging
from .db_router import set_current_shop_db, reset_current_shop_db
from .database_provisioner import resolve_shop_db_alias_for_user, ensure_all_shop_databases_registered

logger = logging.getLogger(__name__)

class TenantDatabaseMiddleware:
    """
    Middleware that automatically resolves the tenant's dedicated database alias
    from the authenticated session or user role, setting it in thread-local context
    for transparent multi-database routing.
    """
    def __init__(self, get_response):
        self.get_response = get_response
        try:
            ensure_all_shop_databases_registered()
        except Exception as e:
            logger.debug(f"TenantDatabaseMiddleware init info: {e}")

    def __call__(self, request):
        user = getattr(request, 'user', None)
        session_db = request.session.get('shop_db') if hasattr(request, 'session') else None
        header_shop = request.headers.get('X-Shop-Code') or request.GET.get('shop_code')

        target_db = None
        if user and getattr(user, 'is_authenticated', False):
            target_db = resolve_shop_db_alias_for_user(user, header_shop)
        elif session_db:
            target_db = session_db
        elif header_shop:
            target_db = resolve_shop_db_alias_for_user(None, header_shop)

        if target_db:
            set_current_shop_db(target_db)
            request.active_shop_db = target_db
        else:
            set_current_shop_db('default')
            request.active_shop_db = 'default'

        try:
            response = self.get_response(request)
        finally:
            reset_current_shop_db()

        return response
