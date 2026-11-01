"""Write transactions.json of the money-transactions case from money's TEST FIXTURE only (illustrative rows).

    ~/money/.venv/bin/python gallery/examples/money-transactions/source/make.py

Reads ~/money/tests/acceptance/fixture_home (synthetic: ACME WASTE, masks 9001; money's read-only acceptance
ruler), never ~/.local/share/money. Each posted transaction is booked by money's own code (src/money/ledger.py:
_read_item, then book_entity: a rules.toml rule first, then a matched transfer between two own accounts, then Plaid's
category, an unmatched transfer to Equity:Transfers), so a row's category is exactly the account money's ledger puts
it on. Amounts are signed the ledger's way for the bank account: money in positive, money out negative. Only
item_id, entity and institution are read from items.json; its access tokens are never read out or written.
"""

from __future__ import annotations

import json
import os
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
CASE = HERE.parent
MONEY = pathlib.Path(os.environ.get("MONEY", "~/money"))
FIXTURE = MONEY / "tests" / "acceptance" / "fixture_home"


def main() -> None:
    sys.path.insert(0, str(MONEY / "src"))
    from money import ledger  # noqa: E402

    rules = ledger.load_rules(FIXTURE / "rules.toml")
    items = json.loads((FIXTURE / "store" / "items.json").read_text())["items"]
    rows = []
    for entity in ledger.ENTITIES:
        book = ledger.EntityBook()
        for item in items:
            if item["entity"] == entity:
                ledger._read_item(FIXTURE / "store" / "raw" / item["item_id"], {"item_id": item["item_id"], "institution_name": item.get("institution_name"),
                                                                                 "institution_id": item.get("institution_id")}, book, entity)
        legs = {leg.tid: leg for leg in book.legs}
        for b in ledger.book_entity(book.legs, rules):
            own = {leg.account for tid in b.ids for leg in [legs[tid]]}
            for tid in b.ids:
                leg = legs[tid]
                counter = next(acct for acct, _amt, _cur in b.postings if acct != leg.account)
                ruled = ledger.rule_account(leg, rules)
                how = (f'rule "{next(r.match for r in rules if r.account == ruled and (not r.entity or r.entity == entity) and r.match.lower() in (leg.name + " " + (leg.merchant or "")).lower())}"'
                       if ruled else "matched transfer" if len(b.ids) == 2 else "unmatched transfer" if counter == ledger.TRANSFERS
                       else f"Plaid {leg.pfc.get('primary') or 'no category'}")
                rows.append({
                    "id": tid, "date": leg.day.isoformat(), "entity": entity, "account": leg.account, "name": leg.name, "merchant": leg.merchant,
                    "amount": float(-leg.amount), "currency": leg.currency, "category": counter, "group": "Transfers" if counter in own or counter == ledger.TRANSFERS else counter.split(":")[0],
                    "how": how, "plaid": leg.pfc.get("detailed"), "transfer_pair": len(b.ids) == 2 and counter in own,
                })
    rows.sort(key=lambda r: (r["date"], r["id"]), reverse=True)
    categories = sorted({*ledger.EXPENSE_BY_PRIMARY.values(), "Expenses:Other", "Income:Revenue", "Income:Salary", "Income:Interest",
                         "Income:Investment", "Income:Other", ledger.TRANSFERS, *(r.account for r in rules)} - {""})
    props = {
        "name": {"type": "text", "label": "Description", "readOnly": True},
        "date": {"type": "date", "label": "Date", "readOnly": True},
        "entity": {"type": "text", "label": "Entity", "display": "badge", "readOnly": True, "colors": {"bam": 1, "personal": 5}},
        "account": {"type": "text", "label": "Bank account", "readOnly": True},
        "merchant": {"type": "text", "label": "Merchant", "readOnly": True},
        "amount": {"type": "number", "label": "Amount", "unitText": "CAD", "decimals": 2, "readOnly": True, "note": "money in positive, money out negative"},
        "currency": {"type": "text", "label": "Currency", "hidden": True, "readOnly": True},
        "category": {"type": "text", "label": "Category", "constraints": {"enum": categories},
                     "note": "the ledger account money books it to; fix one with a rules.toml rule"},
        "group": {"type": "text", "label": "Kind", "display": "badge", "derived": "the category's top level; a transfer between own accounts, or to Equity:Transfers, is Transfers", "colors": {"Expenses": 2, "Income": 3, "Transfers": 0}},
        "how": {"type": "text", "label": "Categorised by", "derived": "money's precedence: rule, matched transfer, Plaid category"},
        "plaid": {"type": "text", "label": "Plaid category", "readOnly": True},
        "transfer_pair": {"type": "boolean", "label": "Between own accounts", "hidden": True, "readOnly": True},
    }
    data = {"id": "money-transactions-illustrative", "title": "Transactions (illustrative: money's test fixture)", "titleProperty": "name",
            "source": "ILLUSTRATIVE: ~/money/tests/acceptance/fixture_home (synthetic), booked by money's src/money/ledger.py; no real account data",
            "properties": props, "rows": rows}
    (CASE / "transactions.json").write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"transactions.json: {len(rows)} illustrative rows; categories: {sorted({r['category'] for r in rows})}")


if __name__ == "__main__":
    main()
