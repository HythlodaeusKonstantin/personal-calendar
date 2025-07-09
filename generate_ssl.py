#!/usr/bin/env python3
"""
Скрипт для генерации самоподписанного SSL сертификата
"""
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from datetime import datetime, timedelta
import os
import ipaddress

def generate_self_signed_cert():
    """Генерирует самоподписанный SSL сертификат"""
    
    # Генерируем приватный ключ
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )
    
    # Создаём сертификат
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "RU"),
        x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "Moscow"),
        x509.NameAttribute(NameOID.LOCALITY_NAME, "Moscow"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "PersonalCalendar"),
        x509.NameAttribute(NameOID.COMMON_NAME, "localhost"),
    ])
    
    cert = x509.CertificateBuilder().subject_name(
        subject
    ).issuer_name(
        issuer
    ).public_key(
        private_key.public_key()
    ).serial_number(
        x509.random_serial_number()
    ).not_valid_before(
        datetime.utcnow()
    ).not_valid_after(
        datetime.utcnow() + timedelta(days=365)
    ).add_extension(
        x509.SubjectAlternativeName([
            x509.DNSName("localhost"),
            x509.IPAddress(ipaddress.IPv4Address("127.0.0.1")),
        ]),
        critical=False,
    ).sign(private_key, hashes.SHA256())
    
    # Сохраняем приватный ключ
    with open("key.pem", "wb") as f:
        f.write(private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        ))
    
    # Сохраняем сертификат
    with open("cert.pem", "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))
    
    print("✅ SSL сертификат создан успешно!")
    print("📁 Файлы:")
    print("   - cert.pem (сертификат)")
    print("   - key.pem (приватный ключ)")
    print("\n⚠️  ВНИМАНИЕ: Это самоподписанный сертификат!")
    print("   Браузер будет показывать предупреждение о безопасности.")
    print("   Для продакшена используйте Let's Encrypt.")

if __name__ == "__main__":
    generate_self_signed_cert() 