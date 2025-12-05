import urequests
import json
import gc

# import ssl
# ssl._create_default_context = lambda: ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
# del ssl

def do_miplike_install(mpy: bool=True, base_url: str = "https://raw.githubusercontent.com/vroomfondel/micropysensorbase/main") -> None:
    # 1. Lade package.json
    pkg_url = f"{base_url}/package.json"

    gc.collect()

    gc.threshold(gc.mem_free() // 4 + gc.mem_alloc())

    print("Lade package.json...")
    response = urequests.get(pkg_url)
    package_data = json.loads(response.text)
    response.close()

    gc.collect()  # Sofort nach dem Response

    print(f"Version: {package_data['version']}")
    print(f"{len(package_data['urls'])} Dateien gefunden")

    # 2. Lade jede Datei
    for source, target in package_data['urls']:
        gc.collect()
        file_url = f"{base_url}/{source}"

        if mpy and source.endswith(".py"):
            sourcen = source[:-3] + ".mpy"
            print(f"Setze {source} auf {sourcen}")
            source = sourcen
            del sourcen

        print(f"Lade {source} -> {target}")

        try:
            response = urequests.get(file_url)
            with open(target, 'wb') as f:
                f.write(response.content)
            response.close()
            print(f"  ✓ {source} installiert")
        except Exception as e:
            print(f"  ✗ Fehler bei {source}: {e}")

        gc.collect()

    print("Installation abgeschlossen!")

if __name__ == "__main__":
    do_miplike_install()