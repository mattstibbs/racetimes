from django.http import HttpResponse
from django.shortcuts import render


def home(request):
    return render(request, 'home.html')


def ping(request):
    """Example HTMX endpoint: returns an HTML fragment, not a full page."""
    return HttpResponse('pong (htmx)' if request.htmx else 'pong')
