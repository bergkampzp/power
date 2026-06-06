import sys, sqlite3, getpass
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import DB
from .schema import ensure_schema
from .auth import create_super

def main():
    u = sys.argv[1] if len(sys.argv) > 1 else input("超级用户名: ")
    p = sys.argv[2] if len(sys.argv) > 2 else getpass.getpass("密码: ")
    c = sqlite3.connect(DB); ensure_schema(c); create_super(c, u, p)
    print(f"已创建超级用户: {u}")

if __name__ == "__main__":
    main()
