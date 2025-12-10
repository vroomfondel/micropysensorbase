# this is NOT to be run in micropython- this is to be run via "normal" python
import os
import json

def install_and_import(packagename: str, pipname: str) -> None:
    import importlib
    try:
        importlib.import_module(packagename)
    except ImportError:
        import pip
        pip.main(['install', pipname])
    finally:
        globals()[packagename] = importlib.import_module(packagename)

install_and_import(packagename="github", pipname="pygithub")

from github import Github, InputFileContent, Clones, Auth

def main() -> None:
    print("update_badge.py::main()")

    # --- KONFIGURATION ---
    gist_token: str = os.environ["GIST_TOKEN"]  # type: ignore
    gist_id: str = os.environ["GIST_ID"]  # type: ignore
    repo_token: str = os.environ["REPO_TOKEN"]  # type: ignore
    repo_name: str = os.environ["GITHUB_REPOSITORY"]  # type: ignore # needs full repo-name with username e.g. vroomfondel/micropysensorbase

    pn: str = repo_name.split("/")[1]
    history_filename = f"{pn}_clone_history.json"
    badge_filename = f"{pn}_clone_count.json"

    # --- 1. VERBINDUNG HERSTELLEN ---
    # Instanz für Gist (Schreibrechte via PAT)
    g_gist = Github(auth=Auth.Token(gist_token))
    # Instanz für Repo (Leserechte via Standard Token reichen meist)
    g_repo = Github(auth=Auth.Token(repo_token))

    # --- 2. DATEN HOLEN ---
    print(f"Hole Daten für Repo: {repo_name}")
    repo = g_repo.get_repo(repo_name)

    # Clones der letzten 14 Tage holen
    clones_data: Clones.Clones|None = repo.get_clones_traffic()

    ndata: int = len(clones_data.clones) if clones_data else 0
    print(f"Datenpunkte erhalten: {ndata}")

    # Alte Historie vom Gist holen
    gist = g_gist.get_gist(gist_id)
    history = {}

    try:
        if history_filename in gist.files:
            content = gist.files[history_filename].content
            history = json.loads(content)
            print("Bestehende Historie geladen.")
        else:
            print("Keine Historie gefunden, starte neu.")
    except Exception as e:
        print(f"Fehler beim Laden der Historie: {e}")

    # --- 3. DATEN MERGEN (Zusammenführen) ---
    # Wir nutzen den Timestamp als Key, um Duplikate zu vermeiden
    if clones_data is not None:
        for c in clones_data.clones:
            # Timestamp zu String konvertieren für JSON Key
            key = str(c.timestamp)
            history[key] = {
                "count": c.count,
                "uniques": c.uniques
            }

    # --- 4. SUMME BERECHNEN ---
    total_clones = sum(d["count"] for d in history.values())
    print(f"Neue Gesamtsumme Clones: {total_clones}")

    # --- 5. JSON FÜR SHIELDS.IO BAUEN ---
    badge_data = {
        "schemaVersion": 1,
        "label": "Clones",
        "message": str(total_clones),
        "color": "blue",
        "namedLogo": "github",
        "logoColor": "white"
    }

    # --- 6. UPDATE DURCHFÜHREN ---
    gist.edit(
        files={
            history_filename: InputFileContent(json.dumps(history, indent=2)),  # type: ignore
            badge_filename: InputFileContent(json.dumps(badge_data))
        }
    )
    print("Gist erfolgreich aktualisiert!")


if __name__ == "__main__":
    main()