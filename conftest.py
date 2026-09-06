import os
import sys

# Zaisti, aby boli moduly na koreňovej úrovni repozitára (napr. timelapse_core)
# importovateľné bez ohľadu na to, odkiaľ sa pytest spúšťa.
sys.path.insert(0, os.path.dirname(__file__))
