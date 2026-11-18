from django.apps import AppConfig

class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.core'

    def ready(self):
        from django.db.backends.signals import connection_created
        def set_sqlite_pragmas(sender, connection, **kwargs):
            if connection.vendor == 'sqlite':
                with connection.cursor() as cursor:
                    # In multi-database SQLite setup, disable foreign key enforcement to allow cross-database references
                    cursor.execute("PRAGMA foreign_keys = OFF;")
        connection_created.connect(set_sqlite_pragmas)

