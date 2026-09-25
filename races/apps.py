from django.apps import AppConfig


class RacesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'races'

    def ready(self):
        from django.core.signals import request_finished, request_started

        from .logs import forget_club

        # Each request's log lines name its club and no other (races/logs.py).
        request_started.connect(forget_club, dispatch_uid="races.logs.started")
        request_finished.connect(forget_club, dispatch_uid="races.logs.finished")
