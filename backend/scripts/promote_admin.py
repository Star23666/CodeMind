import argparse
import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import SessionLocal


def promote_user(
    db: Session,
    *,
    username: str | None = None,
    email: str | None = None,
) -> str:
    if (username is None) == (email is None):
        raise ValueError("请且仅提供用户名或邮箱。")

    if username is not None:
        identity_column = "username"
        identity = username.strip()
    else:
        identity_column = "email"
        identity = str(email).strip().lower()

    if not identity:
        raise ValueError("用户标识不能为空。")

    row = db.execute(
        text(
            f"SELECT id, username, role FROM users "
            f"WHERE {identity_column} = :identity"
        ),
        {"identity": identity},
    ).mappings().first()
    if row is None:
        raise LookupError("未找到对应用户。请先通过注册页面创建账号。")

    if row["role"] != "admin":
        db.execute(
            text("UPDATE users SET role = 'admin' WHERE id = :user_id"),
            {"user_id": int(row["id"])},
        )
        db.commit()
    return str(row["username"])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Promote an existing CodeMind user to administrator.",
    )
    identity = parser.add_mutually_exclusive_group(required=True)
    identity.add_argument("--username", help="Existing CodeMind username")
    identity.add_argument("--email", help="Existing CodeMind email address")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    db = SessionLocal()
    try:
        username = promote_user(db, username=args.username, email=args.email)
    except (ValueError, LookupError) as exc:
        db.rollback()
        print(f"错误：{exc}")
        return 1
    finally:
        db.close()

    print(f"用户 {username} 已设置为管理员。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
