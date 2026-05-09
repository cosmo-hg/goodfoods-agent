import json
from config import get_db


def get_corporate_account(account_code=None, company_name=None, db_path=None):
    if not account_code and not company_name:
        return {"error": "Provide either account_code or company_name"}

    conn = get_db(db_path)
    cursor = conn.cursor()

    if account_code:
        cursor.execute(
            "SELECT * FROM corporate_accounts WHERE account_code = ?",
            (account_code,),
        )
    else:
        cursor.execute(
            "SELECT * FROM corporate_accounts WHERE company_name LIKE ?",
            (f"%{company_name}%",),
        )

    row = cursor.fetchone()
    conn.close()

    if not row:
        return {
            "found": False,
            "message": "No corporate account found. Please contact your GoodFoods account manager.",
        }

    account = dict(row)
    if account.get("preferred_branches"):
        try:
            account["preferred_branches"] = json.loads(account["preferred_branches"])
        except (json.JSONDecodeError, TypeError):
            pass

    account["found"] = True
    return account
