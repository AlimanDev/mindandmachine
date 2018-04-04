from ..models import User


def create(username, email, password):
    u = User.objects.create_superuser(
        username,
        email,
        password
    )

    u.shop_id = 2
    u.first_name = 'Админ'
    u.last_name = 'Админский'
    u.permissions = 0xFFFFFFFF
    u.save()

