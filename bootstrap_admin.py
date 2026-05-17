"""
bootstrap_admin.py — One-time script to create the first Core admin.

Usage:
  python bootstrap_admin.py <TELEGRAM_ID> "Full Name"

Example:
  python bootstrap_admin.py 987654321 "Varun Sharma"
"""

import sys
import database as db

def main():
    if len(sys.argv) < 3:
        print("Usage: python bootstrap_admin.py <TELEGRAM_ID> \"Full Name\"")
        sys.exit(1)

    tg_id = int(sys.argv[1])
    name  = sys.argv[2]

    db.init_db()
    db.add_user(
        telegram_id=tg_id,
        name=name,
        username="",
        role="core",
        avenue=None,
    )
    # Ensure they are set to core even if already registered
    db.update_user_role(tg_id, "core")
    print(f"✅ Admin created: {name} (ID: {tg_id}) with role=core")

if __name__ == "__main__":
    main()
