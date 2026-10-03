"""Create a private production env, without printing any generated secrets."""
import argparse
import base64
import ipaddress
import os
import re
import secrets
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--domain", required=True)
    parser.add_argument("--release", required=True)
    parser.add_argument("--output", type=Path, default=Path(".env.production"))
    args = parser.parse_args()
    try:
        public_ip = ipaddress.ip_address(args.domain)
    except ValueError:
        public_ip = None
    if public_ip is not None:
        if public_ip.version != 4 or not public_ip.is_global:
            parser.error("use a globally routable public IPv4 address")
    elif (len(args.domain) > 253 or "." not in args.domain
          or re.fullmatch(r"[0-9.]+", args.domain)
          or not all(re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
                     for label in args.domain.split("."))):
        parser.error("use a public IPv4 or lowercase DNS hostname without scheme/path/port")
    if args.domain in ("example.com", "localhost"):
        parser.error("use the actual application domain")
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,100}", args.release):
        parser.error("release must be a Git SHA or safe release name")
    password = secrets.token_hex(24)  # URL/env-safe, independently generated.
    replacements = {
        "DOMAIN": args.domain, "APP_PUBLIC_URL": f"https://{args.domain}",
        "APP_SECRET": secrets.token_hex(32), "POSTGRES_DB": "ozon", "POSTGRES_USER": "ozon",
        "POSTGRES_PASSWORD": password,
        "DATABASE_URL": f"postgresql+psycopg://ozon:{password}@127.0.0.1:5432/ozon",
        "OZON_CREDENTIALS_MASTER_KEY": base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),
        "OZON_WEBHOOK_TRUSTED_PROXIES": "127.0.0.1/32",
    }
    template = Path(__file__).resolve().parents[1] / ".env.production.example"
    lines = [f"{line.split('=', 1)[0]}={replacements[line.split('=', 1)[0]]}"
             if "=" in line and line.split("=", 1)[0] in replacements else line
             for line in template.read_text(encoding="utf-8").splitlines()]
    descriptor = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as output:
        output.write("\n".join(lines) + "\n")
    print("Private native production env created; secrets were not printed.")


if __name__ == "__main__":
    main()
