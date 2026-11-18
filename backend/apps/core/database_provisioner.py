import os
import re
import logging
from pathlib import Path
from django.conf import settings
from django.db import connections, transaction
from django.core.management import call_command
from django.utils import timezone

logger = logging.getLogger(__name__)

def get_shop_db_alias(shop_code: str) -> str:
    """Returns a valid Django database alias for a shop code (e.g. 'SB-SHOP-001' -> 'shop_001')."""
    clean = re.sub(r'[^a-zA-Z0-9]', '_', str(shop_code).strip()).lower()
    clean = re.sub(r'_+', '_', clean).strip('_')
    if clean.startswith('sb_shop_'):
        clean = 'shop_' + clean[len('sb_shop_'):]
    elif not clean.startswith('shop_'):
        clean = f"shop_{clean}"
    return clean

def get_shop_db_name(shop_code: str) -> str:
    """Returns the dedicated database name (e.g. 'SB-SHOP-001' -> 'SmartBazaar_Shop_001')."""
    match = re.search(r'(\d+)', str(shop_code))
    suffix = match.group(1).zfill(3) if match else re.sub(r'[^a-zA-Z0-9]', '', str(shop_code))
    return f"SmartBazaar_Shop_{suffix}"

def build_database_config(db_name: str, db_alias: str) -> dict:
    """Builds standard Django database configuration dictionary."""
    is_postgres = (
        getattr(settings, 'DB_ENGINE', '') == 'postgresql' or
        bool(os.getenv('POSTGRES_DB')) or
        bool(os.getenv('POSTGRES_HOST'))
    )
    if is_postgres:
        return {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': db_name,
            'USER': os.getenv('POSTGRES_USER', 'postgres'),
            'PASSWORD': os.getenv('POSTGRES_PASSWORD', 'postgres'),
            'HOST': os.getenv('POSTGRES_HOST', 'localhost'),
            'PORT': os.getenv('POSTGRES_PORT', '5432'),
            'TIME_ZONE': 'Asia/Kolkata',
            'CONN_MAX_AGE': 600,
            'CONN_HEALTH_CHECKS': True,
            'OPTIONS': {},
            'AUTOCOMMIT': True,
            'ATOMIC_REQUESTS': False,
            'TEST': {},
        }
    else:
        # SQLite multi-database deployment in backend/databases/
        db_dir = Path(settings.BASE_DIR) / 'databases'
        db_dir.mkdir(parents=True, exist_ok=True)
        db_file = db_dir / f"{db_name}.sqlite3"
        return {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': str(db_file),
            'TIME_ZONE': None,
            'USER': '',
            'PASSWORD': '',
            'HOST': '',
            'PORT': '',
            'CONN_MAX_AGE': 0,
            'CONN_HEALTH_CHECKS': False,
            'OPTIONS': {},
            'AUTOCOMMIT': True,
            'ATOMIC_REQUESTS': False,
            'TEST': {},
        }

def register_database_connection(db_alias: str, db_config: dict) -> None:
    """Dynamically registers database configuration into Django settings and connections."""
    settings.DATABASES[db_alias] = db_config
    connections.databases[db_alias] = db_config

def provision_shop_database(shop, force_remigrate: bool = False):
    """
    PROVISION A COMPLETELY INDEPENDENT SHOP DATABASE.
    1. Generates unique DB name and alias.
    2. Provisions physical database (PostgreSQL database or SQLite file).
    3. Executes all Django migrations on that database.
    4. Initializes an empty shop profile inside the tenant database.
    5. Saves the mapping securely in Central Core database.
    """
    from apps.shops.models import Shop, ShopDatabaseMapping

    db_alias = get_shop_db_alias(shop.code)
    db_name = get_shop_db_name(shop.code)
    db_config = build_database_config(db_name, db_alias)

    # Register into runtime connection pool
    register_database_connection(db_alias, db_config)

    # 1. Physical DB Creation for PostgreSQL if applicable
    if db_config['ENGINE'] == 'django.db.backends.postgresql':
        try:
            import psycopg
            admin_conn = psycopg.connect(
                dbname='postgres',
                user=db_config['USER'],
                password=db_config['PASSWORD'],
                host=db_config['HOST'],
                port=db_config['PORT'],
                autocommit=True
            )
            with admin_conn.cursor() as cur:
                cur.execute(f'SELECT 1 FROM pg_database WHERE datname = %s', [db_name])
                if not cur.fetchone():
                    cur.execute(f'CREATE DATABASE "{db_name}"')
                    logger.info(f"Created PostgreSQL database: {db_name}")
            admin_conn.close()
        except Exception as e:
            logger.warning(f"PostgreSQL physical DB creation note (or fallback): {e}")

    # 2. Run migrations on this dedicated database
    try:
        call_command('migrate', database=db_alias, interactive=False, verbosity=0)
    except Exception as e:
        logger.error(f"Migration error for {db_alias}: {e}")
        # Record failure if central DB accessible
        try:
            ShopDatabaseMapping.objects.using('default').update_or_create(
                shop=shop,
                defaults={
                    'shop_id_code': shop.code,
                    'database_name': db_name,
                    'database_alias': db_alias,
                    'status': ShopDatabaseMapping.ProvisioningStatus.FAILED,
                    'error_message': str(e)
                }
            )
        except Exception:
            pass
        raise e

    # 3. Create or sync initial empty Shop profile in the tenant DB
    try:
        if 'sqlite' in db_config.get('ENGINE', ''):
            with connections[db_alias].cursor() as cursor:
                cursor.execute("PRAGMA foreign_keys = OFF;")

        from apps.accounts.models import User
        if shop.owner:
            User.objects.using(db_alias).update_or_create(
                id=shop.owner.id,
                defaults={
                    'username': shop.owner.username,
                    'email': shop.owner.email,
                    'role': shop.owner.role,
                    'phone_number': shop.owner.phone_number,
                    'first_name': shop.owner.first_name,
                    'is_active': shop.owner.is_active
                }
            )
        with transaction.atomic(using=db_alias):
            Shop.objects.using(db_alias).update_or_create(
                id=shop.id,
                defaults={
                    'owner_id': shop.owner_id,
                    'name': shop.name,
                    'code': shop.code,
                    'category': shop.category,
                    'description': shop.description,
                    'phone': shop.phone,
                    'email': shop.email,
                    'address': shop.address,
                    'city': shop.city,
                    'state': shop.state,
                    'pincode': shop.pincode,
                    'gstin': shop.gstin,
                    'status': shop.status,
                    'upi_vpa': shop.upi_vpa,
                    'upi_name': shop.upi_name,
                    'settings': shop.settings or {}
                }
            )
    except Exception as e:
        logger.warning(f"Tenant shop record setup note for {db_alias}: {e}")

    # 4. Save/Update Central Mapping
    mapping, _ = ShopDatabaseMapping.objects.using('default').update_or_create(
        shop=shop,
        defaults={
            'shop_id_code': shop.code,
            'database_name': db_name,
            'database_alias': db_alias,
            'db_engine': 'postgresql' if 'postgresql' in db_config['ENGINE'] else 'sqlite3',
            'db_path': str(db_config.get('NAME', '')),
            'db_host': str(db_config.get('HOST', '')),
            'db_port': str(db_config.get('PORT', '')),
            'db_user': str(db_config.get('USER', '')),
            'status': ShopDatabaseMapping.ProvisioningStatus.ACTIVE,
            'last_migrated_at': timezone.now(),
            'error_message': ''
        }
    )
    return mapping

def sync_shop_and_owner_to_tenant_db(shop, db_alias: str):
    """Guarantees that the Shop and Owner User exist in the tenant database to satisfy Foreign Key constraints."""
    from apps.shops.models import Shop, ShopDatabaseMapping
    from apps.accounts.models import User
    try:
        if db_alias not in settings.DATABASES:
            m = ShopDatabaseMapping.objects.using('default').filter(shop=shop).first()
            db_name = m.database_name if m else get_shop_db_name(shop.code)
            cfg = build_database_config(db_name, db_alias)
            register_database_connection(db_alias, cfg)

        if shop.owner:
            User.objects.using(db_alias).update_or_create(
                id=shop.owner.id,
                defaults={
                    'username': shop.owner.username,
                    'email': shop.owner.email,
                    'role': shop.owner.role,
                    'phone_number': shop.owner.phone_number or '',
                    'first_name': shop.owner.first_name or '',
                    'is_active': shop.owner.is_active
                }
            )
        Shop.objects.using(db_alias).update_or_create(
            id=shop.id,
            defaults={
                'owner_id': shop.owner_id,
                'name': shop.name,
                'code': shop.code,
                'category': shop.category or 'GENERAL_STORE',
                'description': shop.description or '',
                'phone': shop.phone or '',
                'email': shop.email or '',
                'address': shop.address or '',
                'city': shop.city or '',
                'state': shop.state or '',
                'pincode': shop.pincode or '',
                'gstin': shop.gstin or '',
                'status': shop.status or 'ACTIVE',
                'upi_vpa': shop.upi_vpa or '',
                'upi_name': shop.upi_name or '',
                'settings': shop.settings or {}
            }
        )
    except Exception as e:
        logger.warning(f"Note syncing shop {shop.code} to {db_alias}: {e}")

def ensure_all_shop_databases_registered():
    """Ensures all registered shop databases are loaded in django.db.connections and have shop records."""
    from apps.shops.models import Shop, ShopDatabaseMapping
    try:
        mappings = ShopDatabaseMapping.objects.using('default').select_related('shop').all()
        for m in mappings:
            if m.database_alias not in settings.DATABASES:
                cfg = build_database_config(m.database_name, m.database_alias)
                register_database_connection(m.database_alias, cfg)
            if m.shop:
                sync_shop_and_owner_to_tenant_db(m.shop, m.database_alias)
        
        # Also check any Shop without mapping
        for s in Shop.objects.using('default').all():
            if not hasattr(s, 'database_mapping') or not s.database_mapping:
                provision_shop_database(s)
    except Exception as e:
        logger.debug(f"ensure_all_shop_databases_registered info: {e}")

def resolve_shop_db_alias_for_user(user, shop_code: str = None) -> str:
    """Resolves the database alias for a given user or shop code."""
    from apps.shops.models import Shop, ShopMembership, ShopDatabaseMapping

    if shop_code:
        m = ShopDatabaseMapping.objects.using('default').filter(shop_id_code=shop_code).first()
        if m:
            return m.database_alias
        return get_shop_db_alias(shop_code)

    if not user or not user.is_authenticated:
        return 'default'

    if user.role == 'SUPER_ADMIN':
        return 'default'

    if user.role == 'SHOP_OWNER':
        shop = Shop.objects.using('default').filter(owner=user).first()
        if shop:
            m = getattr(shop, 'database_mapping', None) or ShopDatabaseMapping.objects.using('default').filter(shop=shop).first()
            if m:
                return m.database_alias
            return get_shop_db_alias(shop.code)

    if user.role == 'WORKER':
        mem = ShopMembership.objects.using('default').filter(user=user).select_related('shop').first()
        if mem and mem.shop:
            m = getattr(mem.shop, 'database_mapping', None) or ShopDatabaseMapping.objects.using('default').filter(shop=mem.shop).first()
            if m:
                return m.database_alias
            return get_shop_db_alias(mem.shop.code)

    return 'default'
