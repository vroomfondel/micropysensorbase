# make sure boot.py include micropysensorbase.main

try:
    import micropysensorbase.main

    micropysensorbase.main.main()
except Exception as ex:
    print(ex)