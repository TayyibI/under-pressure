import sys
print("python:", sys.executable, sys.version.split()[0])
sys.exit(0 if sys.version_info >= (3, 10) else 1)
