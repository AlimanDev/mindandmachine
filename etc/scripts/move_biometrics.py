from src.recognition.api.recognition import Recognition
from src.recognition.models import UserConnecter

def move_biometrics(user_ids=[], delete_before_create=False):
    connecters = UserConnecter.objects.select_related('user')

    if user_ids:
        connecters = connecters.filter(user_id__in=user_ids)
    
    r = Recognition()

    for connecter in connecters:
        user = connecter.user
        photo = user.avatar.file if user.avatar else None
        if not photo:
            print(f'User {user.last_name} with id {user.id} has connecter but don\'t has avatar.')
            continue
        
        if delete_before_create:
            try:
                r.delete_person(connecter.partner_id)
                print(f'Succefully deleted {user} from tevian with partner_id {connecter.partner_id}')
            except:
                print(f'Failed to delete {user} from tevian with partner_id {connecter.partner_id}')
        
        partner_id = r.create_person({"id": user.id})
        r.upload_photo(partner_id, photo)
        connecter.partner_id = partner_id
        connecter.save()
        print(f'Succefully moved {user} with new partner_id {connecter.partner_id}')
