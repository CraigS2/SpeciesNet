import hashlib
import secrets

from django.core import signing
from django.core.signing import BadSignature, SignatureExpired

TOKEN_SALT = 'pending-actions'


class PendingActionTokenError(Exception):
    pass


class PendingActionTokenExpired(PendingActionTokenError):
    pass


class PendingActionTokenInvalid(PendingActionTokenError):
    pass



def hash_token(token):
    return hashlib.sha256(token.encode('utf-8')).hexdigest()



def generate_signed_token(action_id):
    nonce = secrets.token_urlsafe(16)
    payload = {'action_id': action_id, 'nonce': nonce}
    return signing.dumps(payload, salt=TOKEN_SALT)



def load_signed_token(token, max_age):
    try:
        return signing.loads(token, salt=TOKEN_SALT, max_age=max_age)
    except SignatureExpired as exc:
        raise PendingActionTokenExpired('This link has expired.') from exc
    except BadSignature as exc:
        raise PendingActionTokenInvalid('This link is invalid.') from exc
