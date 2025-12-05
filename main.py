# make sure boot.py include micropysensorbase.main

print(__package__)
print(__file__)
print(__name__)

try:
    import micropysensorbase.main
except Exception as ex:
    print(ex)