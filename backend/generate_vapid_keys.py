"""
VAPID Key Generator for Web Push

Usage: python generate_vapid_keys.py

Copy the output keys into Render environment variables:
  VAPID_PRIVATE_KEY  -> the private key
  VAPID_PUBLIC_KEY   -> the public key
  VAPID_CONTACT      -> mailto:your@email.com
"""

from py_vapid import Vapid
import base64

def main():
    vapid = Vapid()
    vapid.generate_keys()

    # Export in the format pywebpush expects (PEM for private, base64url uncompressed point for public)
    private_pem = vapid.private_key.private_bytes(
        encoding=__import__('cryptography').hazmat.primitives.serialization.Encoding.PEM,
        format=__import__('cryptography').hazmat.primitives.serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=__import__('cryptography').hazmat.primitives.serialization.NoEncryption()
    ).decode('utf-8').strip()

    pub_numbers = vapid.private_key.public_key().public_numbers()
    x = pub_numbers.x.to_bytes(32, 'big')
    y = pub_numbers.y.to_bytes(32, 'big')
    public_b64 = base64.urlsafe_b64encode(b'\x04' + x + y).rstrip(b'=').decode('ascii')

    print('=' * 60)
    print('Copy these into Render Environment Variables:')
    print('=' * 60)
    print(f'VAPID_PRIVATE_KEY (PEM — copy the full block including BEGIN/END lines):')
    print(private_pem)
    print()
    print(f'VAPID_PUBLIC_KEY={public_b64}')
    print()
    print(f'VAPID_CONTACT=mailto:your@email.com')
    print('=' * 60)
    print(f'\nAlso update FALLBACK_VAPID_PUBLIC_KEY in frontend/app.js with:')
    print(public_b64)

if __name__ == '__main__':
    main()
