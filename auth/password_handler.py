import bcrypt

def hash_password(password: str | bytes) -> str:
    """
    Hash a password using bcrypt directly, handling str or bytes input.
    """
    if isinstance(password, bytes):
        password_bytes = password
    else:
        password_bytes = password.encode('utf-8')

    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode('utf-8')


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a password against its hash using bcrypt directly
    """
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8')) 