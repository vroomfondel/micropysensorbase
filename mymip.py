import urequests
import json
import gc

# import ssl
# ssl._create_default_context = lambda: ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)

def do_miplike_install(base_url: str = "https://raw.githubusercontent.com/vroomfondel/micropysensorbase/main") -> None:
    # 1. Lade package.json
    pkg_url = f"{base_url}/package.json"

    print("Lade package.json...")
    response = urequests.get(pkg_url)
    package_data = json.loads(response.text)
    response.close()

    print(f"Version: {package_data['version']}")
    print(f"{len(package_data['urls'])} Dateien gefunden")

    # 2. Lade jede Datei
    for source, target in package_data['urls']:
        gc.collect()
        file_url = f"{base_url}/{source}"
        print(f"Lade {source} -> {target}")

        try:
            response = urequests.get(file_url)
            with open(target, 'wb') as f:
                f.write(response.content)
            response.close()
            print(f"  ✓ {source} installiert")
        except Exception as e:
            print(f"  ✗ Fehler bei {source}: {e}")

    print("Installation abgeschlossen!")