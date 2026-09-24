from .roles import is_committee


def roles(request):
    """Lets templates show links by role, without repeating the rules."""
    return {"is_committee": is_committee(request.user)}
