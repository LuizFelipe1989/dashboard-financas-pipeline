"""Write (or clear) Google Sheets cell notes — used to surface the daily
alert agent's findings directly on the flagged cells ("comentários").

Usage:
    python write_cell_notes.py notes.json

notes.json: a list of {"sheet": "DRE_Mensal", "row": 12, "col": 1, "note": "..."}
(row/col are 1-indexed, matching what you'd read off the sheet in the UI).
For each distinct sheet mentioned, all existing notes in its used range are
cleared first, then the new ones are applied — so stale alerts from a
previous day never linger.
"""
import json
import sys

from finlib import get_clients


def clear_notes(sheets_api, spreadsheet_id, sheet_id, n_rows, n_cols):
    sheets_api.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={"requests": [{
            "updateCells": {
                "range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": n_rows, "startColumnIndex": 0, "endColumnIndex": n_cols},
                "fields": "note",
            }
        }]},
    ).execute()


def write_notes(notes):
    """notes: list of {"sheet": str, "row": int, "col": int, "note": str} (1-indexed)."""
    sh, sheets_api = get_clients()
    by_sheet = {}
    for n in notes:
        by_sheet.setdefault(n["sheet"], []).append(n)

    for sheet_title, sheet_notes in by_sheet.items():
        ws = sh.worksheet(sheet_title)
        clear_notes(sheets_api, sh.id, ws.id, ws.row_count, ws.col_count)

        requests = []
        for n in sheet_notes:
            requests.append({
                "updateCells": {
                    "range": {
                        "sheetId": ws.id,
                        "startRowIndex": n["row"] - 1, "endRowIndex": n["row"],
                        "startColumnIndex": n["col"] - 1, "endColumnIndex": n["col"],
                    },
                    "rows": [{"values": [{"note": n["note"]}]}],
                    "fields": "note",
                }
            })
        if requests:
            sheets_api.spreadsheets().batchUpdate(spreadsheetId=sh.id, body={"requests": requests}).execute()
        print(f"{sheet_title}: {len(sheet_notes)} nota(s) escrita(s)")


def main():
    if len(sys.argv) != 2:
        print("uso: python write_cell_notes.py notes.json")
        sys.exit(1)
    with open(sys.argv[1]) as f:
        notes = json.load(f)
    write_notes(notes)


if __name__ == "__main__":
    main()
